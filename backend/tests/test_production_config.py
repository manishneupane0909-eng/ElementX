from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

import database
from main import _startup_check_db, app
from services.production_config import (
    INSECURE_DEFAULT_JWT_SECRET,
    ProductionConfigError,
    assert_production_ready,
    cors_settings,
    demo_bootstrap_enabled,
    is_production,
    validate_production_config,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
STRONG_SECRET = "p" * 8 + "Zq7-" + "x" * 30  # distinctive, 42 chars


class ProductionConfigValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.valid = {
            "ELEMENTX_ENV": "production",
            "JWT_SECRET": STRONG_SECRET,
            "MONGODB_URI": "mongodb+srv://lab-user:hunter2pass@cluster.example.net/elementx",
            "DATA_DIR": str(root / "data"),
            "DATABASE_URL": f"sqlite:///{root / 'data' / 'elementx.db'}",
            "CORS_ORIGINS": "https://app.elementx.example",
        }
        (root / "data").mkdir()
        # Pretend DATA_DIR is a mounted persistent disk (a temp dir never is).
        self._mount = patch("services.production_config._is_mount_point", return_value=True)
        self._mount.start()

    def tearDown(self) -> None:
        self._mount.stop()
        self._tmp.cleanup()

    def _without(self, key: str) -> dict:
        env = dict(self.valid)
        env.pop(key)
        return env

    def _problems(self, env: dict) -> str:
        return "\n".join(validate_production_config(env))

    def test_valid_production_config_passes(self) -> None:
        self.assertEqual(validate_production_config(self.valid), [])
        assert_production_ready(self.valid)  # does not raise

    def test_development_is_never_blocked(self) -> None:
        # Missing everything, but not production: no error.
        assert_production_ready({})
        assert_production_ready({"ELEMENTX_ENV": "development"})
        self.assertFalse(is_production({}))
        self.assertTrue(is_production({"ELEMENTX_ENV": "Production"}))

    def test_missing_jwt_secret_fails(self) -> None:
        self.assertIn("JWT_SECRET is not set", self._problems(self._without("JWT_SECRET")))

    def test_insecure_default_jwt_secret_fails(self) -> None:
        env = {**self.valid, "JWT_SECRET": INSECURE_DEFAULT_JWT_SECRET}
        self.assertIn("insecure", self._problems(env))

    def test_placeholder_jwt_secret_fails(self) -> None:
        env = {**self.valid, "JWT_SECRET": "please-changeme-" + "x" * 40}
        self.assertIn("insecure", self._problems(env))

    def test_short_jwt_secret_fails(self) -> None:
        env = {**self.valid, "JWT_SECRET": "short-but-unusual-7Qz"}
        self.assertIn("too short", self._problems(env))

    def test_missing_identity_database_fails(self) -> None:
        self.assertIn("MONGODB_URI is not set", self._problems(self._without("MONGODB_URI")))

    def test_placeholder_or_malformed_identity_database_fails(self) -> None:
        placeholder = {**self.valid, "MONGODB_URI": "mongodb://u:<password>@host/db"}
        self.assertIn("placeholder", self._problems(placeholder))
        malformed = {**self.valid, "MONGODB_URI": "postgres://host/db"}
        self.assertIn("must start with mongodb", self._problems(malformed))

    def test_missing_data_dir_and_database_url_fail(self) -> None:
        self.assertIn("DATA_DIR is not set", self._problems(self._without("DATA_DIR")))
        self.assertIn("DATABASE_URL is not set", self._problems(self._without("DATABASE_URL")))

    def test_relative_data_dir_fails(self) -> None:
        env = {**self.valid, "DATA_DIR": "./data"}
        self.assertIn("DATA_DIR must be an absolute path", self._problems(env))

    def test_data_dir_that_is_a_file_fails(self) -> None:
        file_path = Path(self._tmp.name) / "not-a-dir"
        file_path.write_text("x")
        env = {**self.valid, "DATA_DIR": str(file_path)}
        self.assertIn("not a directory", self._problems(env))

    def test_uncreatable_data_dir_fails(self) -> None:
        file_path = Path(self._tmp.name) / "blocker"
        file_path.write_text("x")
        env = {
            **self.valid,
            "DATA_DIR": str(file_path / "child"),
            "ELEMENTX_ALLOW_UNMOUNTED_DATA_DIR": "true",
        }
        self.assertIn("DATA_DIR is not writable", self._problems(env))

    def test_missing_data_dir_means_the_disk_is_not_attached(self) -> None:
        env = {**self.valid, "DATA_DIR": str(Path(self._tmp.name) / "not-mounted")}
        env["DATABASE_URL"] = f"sqlite:///{Path(env['DATA_DIR']) / 'elementx.db'}"
        problems = self._problems(env)
        self.assertIn("persistent disk", problems)
        self.assertFalse((Path(env["DATA_DIR"])).exists(), "validation must not create DATA_DIR")

    def test_unmounted_data_dir_is_refused_to_prevent_ephemeral_fallback(self) -> None:
        with patch("services.production_config._is_mount_point", return_value=False):
            self.assertIn("not a mounted persistent volume", self._problems(self.valid))
            override = {**self.valid, "ELEMENTX_ALLOW_UNMOUNTED_DATA_DIR": "true"}
            self.assertEqual(validate_production_config(override), [])

    def test_database_must_live_on_the_same_volume_as_original_files(self) -> None:
        elsewhere = Path(self._tmp.name) / "other-volume"
        elsewhere.mkdir()
        env = {**self.valid, "DATABASE_URL": f"sqlite:///{elsewhere / 'elementx.db'}"}
        self.assertIn("inside DATA_DIR", self._problems(env))
        # A symlink escaping DATA_DIR must not satisfy the check either.
        link = Path(self.valid["DATA_DIR"]) / "escape"
        link.symlink_to(elsewhere)
        env = {**self.valid, "DATABASE_URL": f"sqlite:///{link / 'elementx.db'}"}
        self.assertIn("inside DATA_DIR", self._problems(env))

    def test_only_sqlite_databases_are_accepted(self) -> None:
        env = {**self.valid, "DATABASE_URL": "postgresql://u:p@host/db"}
        self.assertIn("sqlite", self._problems(env))
        self.assertNotIn("p@host", self._problems(env))

    def test_multiple_workers_are_refused(self) -> None:
        self.assertIn("WEB_CONCURRENCY must be 1", self._problems({**self.valid, "WEB_CONCURRENCY": "4"}))
        self.assertEqual(validate_production_config({**self.valid, "WEB_CONCURRENCY": "1"}), [])
        self.assertIn("integer", self._problems({**self.valid, "WEB_CONCURRENCY": "many"}))

    def test_cors_origins_must_be_bare_origins(self) -> None:
        env = {**self.valid, "CORS_ORIGINS": "https://app.elementx.example/app"}
        self.assertIn("bare origins", self._problems(env))
        env = {**self.valid, "CORS_ORIGINS": "app.elementx.example"}
        self.assertIn("bare origins", self._problems(env))

    def test_relative_or_memory_sqlite_url_fails(self) -> None:
        relative = {**self.valid, "DATABASE_URL": "sqlite:///./data/elementx.db"}
        self.assertIn("absolute", self._problems(relative))
        memory = {**self.valid, "DATABASE_URL": "sqlite:///:memory:"}
        self.assertIn("file-backed", self._problems(memory))

    def test_cors_must_be_explicit_without_wildcard(self) -> None:
        self.assertIn("CORS_ORIGINS is not set", self._problems(self._without("CORS_ORIGINS")))
        wildcard = {**self.valid, "CORS_ORIGINS": "https://a.example, *"}
        self.assertIn("wildcard", self._problems(wildcard))

    def test_error_messages_never_contain_secret_values(self) -> None:
        env = {
            **self.valid,
            "JWT_SECRET": "weak-" + "Qx9Zk",
            "MONGODB_URI": "mongodb://admin:SuperSecretDbPass@host/<password>",
        }
        with self.assertRaises(ProductionConfigError) as ctx:
            assert_production_ready(env)
        message = str(ctx.exception)
        self.assertNotIn("Qx9Zk", message)
        self.assertNotIn("SuperSecretDbPass", message)
        self.assertNotIn("admin", message)

    def test_all_problems_are_reported_together(self) -> None:
        with self.assertRaises(ProductionConfigError) as ctx:
            assert_production_ready({"ELEMENTX_ENV": "production"})
        self.assertGreaterEqual(len(ctx.exception.problems), 5)


class CorsAndDemoPolicyTests(unittest.TestCase):
    def test_development_cors_is_permissive(self) -> None:
        settings = cors_settings({})
        self.assertEqual(settings["allow_origins"], ["*"])

    def test_production_cors_is_restricted(self) -> None:
        settings = cors_settings(
            {
                "ELEMENTX_ENV": "production",
                "CORS_ORIGINS": "https://app.elementx.example/, https://other.example",
            }
        )
        self.assertEqual(
            settings["allow_origins"],
            ["https://app.elementx.example", "https://other.example"],
        )
        self.assertFalse(settings["allow_credentials"])
        self.assertNotIn("*", settings["allow_headers"])
        self.assertNotIn("*", settings["allow_methods"])

    def test_production_cors_drops_wildcard(self) -> None:
        settings = cors_settings({"ELEMENTX_ENV": "production", "CORS_ORIGINS": "*"})
        self.assertEqual(settings["allow_origins"], [])

    def test_demo_bootstrap_flag(self) -> None:
        self.assertTrue(demo_bootstrap_enabled({}))
        self.assertFalse(demo_bootstrap_enabled({"ELEMENTX_ENV": "production"}))
        # There is deliberately no production override for the shared demo account.
        self.assertFalse(
            demo_bootstrap_enabled({"ELEMENTX_ENV": "production", "ELEMENTX_ENABLE_DEMO": "1"})
        )


class ProductionRuntimeBehaviourTests(unittest.TestCase):
    def test_demo_bootstrap_is_disabled_in_production(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"ELEMENTX_ENV": "production", "ELEMENTX_ENABLE_DEMO": "true"}):
            response = client.post("/api/demo/bootstrap")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("password", response.text.lower())

    def test_demo_bootstrap_does_not_touch_accounts_in_production(self) -> None:
        import local_store

        before = dict(local_store._LOCAL_USERS_BY_EMAIL)  # noqa: SLF001
        client = TestClient(app)
        with patch.dict(os.environ, {"ELEMENTX_ENV": "production"}):
            client.post("/api/demo/bootstrap")
        self.assertEqual(before, local_store._LOCAL_USERS_BY_EMAIL)  # noqa: SLF001

    def test_production_never_falls_back_to_in_memory_accounts(self) -> None:
        client = TestClient(app)
        email = "prod-guard@example.com"
        with (
            patch.dict(os.environ, {"ELEMENTX_ENV": "production"}),
            patch.object(database, "DB_AVAILABLE", False),
        ):
            registered = client.post(
                "/api/auth/register",
                json={"name": "Guard", "email": email, "password": "correct-horse-battery"},
            )
            login = client.post(
                "/api/auth/login", json={"email": email, "password": "correct-horse-battery"}
            )
        self.assertEqual(registered.status_code, 503)
        self.assertEqual(login.status_code, 503)
        import local_store

        self.assertNotIn(email, local_store._LOCAL_USERS_BY_EMAIL)  # noqa: SLF001

    def test_development_still_supports_local_accounts_without_mongo(self) -> None:
        client = TestClient(app)
        email = f"dev-local-{os.getpid()}@example.com"
        with patch.dict(os.environ, {"ELEMENTX_ENV": "development"}), patch.object(
            database, "DB_AVAILABLE", False
        ):
            registered = client.post(
                "/api/auth/register",
                json={"name": "Dev", "email": email, "password": "correct-horse-battery"},
            )
            login = client.post(
                "/api/auth/login", json={"email": email, "password": "correct-horse-battery"}
            )
        self.assertEqual(registered.status_code, 200, registered.text)
        self.assertEqual(login.status_code, 200, login.text)
        self.assertIn("token", login.json())

    def test_startup_aborts_in_production_when_identity_database_is_down(self) -> None:
        fake_client = MagicMock()
        fake_client.admin.command = AsyncMock(
            side_effect=RuntimeError("mongodb://admin:SuperSecretDbPass@host unreachable")
        )
        with (
            patch.dict(os.environ, {"ELEMENTX_ENV": "production"}),
            patch.object(database, "client", fake_client),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(_startup_check_db())
        self.assertNotIn("SuperSecretDbPass", str(ctx.exception))
        self.assertFalse(database.DB_AVAILABLE)

    def test_startup_tolerates_missing_mongo_in_development(self) -> None:
        fake_client = MagicMock()
        fake_client.admin.command = AsyncMock(side_effect=RuntimeError("down"))
        with (
            patch.dict(os.environ, {"ELEMENTX_ENV": "development"}),
            patch.object(database, "client", fake_client),
        ):
            asyncio.run(_startup_check_db())  # must not raise
        self.assertFalse(database.DB_AVAILABLE)

    def test_importing_the_app_fails_fast_with_unsafe_production_env(self) -> None:
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"DATA_DIR", "DATABASE_URL", "CORS_ORIGINS"}
        }
        env.update(
            {
                "ELEMENTX_ENV": "production",
                "PYTHONPATH": str(BACKEND_DIR),
                "JWT_SECRET": INSECURE_DEFAULT_JWT_SECRET,
            }
        )
        result = subprocess.run(
            [sys.executable, "-c", "import main"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Production configuration is invalid", output)
        self.assertIn("DATA_DIR is not set", output)
        self.assertNotIn(database.SECRET_KEY, output)


if __name__ == "__main__":
    unittest.main()
