"""Production access control, error sanitisation, CORS behaviour and health reporting."""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

import main
from main import app
from services.materials_client import MaterialsClient, MaterialsClientError
from services.production_config import cors_settings
from tests.auth_helpers import USER_A_ID, auth_headers, make_token

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MAGNETOMETRY_FIXTURE = FIXTURES / "Fe2CoGe_annealed_48hrs_900C_M_H_M_T.dat"

PUBLIC_ROUTES = {
    ("GET", "/"),
    ("GET", "/health"),
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/demo/bootstrap"),  # 404 in production, see tests below
}
SENSITIVE_MARKERS = ("mongodb://", "mongodb+srv://", "/var/data", "Traceback", "api_key=", "hunter2")

NAIVE_CIF = b"""data_NaCl
_cell_length_a 5.64
_cell_length_b 5.64
_cell_length_c 5.64
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'F m -3 m'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Na1 Na 0 0 0
Cl1 Cl 0.5 0.5 0.5
"""


def _concrete_path(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "11111111-1111-1111-1111-111111111111", path)


class EveryRouteRequiresAuthInProductionTests(unittest.TestCase):
    def test_no_route_except_the_public_allowlist_is_reachable_anonymously(self) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        checked = 0
        # The OpenAPI schema enumerates every route, including those from included routers.
        for path, operations in app.openapi()["paths"].items():
            for method in operations:
                method = method.upper()
                if (method, path) in PUBLIC_ROUTES:
                    continue
                with patch.dict(os.environ, {"ELEMENTX_ENV": "production"}):
                    response = client.request(method, _concrete_path(path))
                self.assertIn(
                    response.status_code,
                    (401, 403),
                    f"{method} {path} answered {response.status_code} without credentials",
                )
                checked += 1
        self.assertGreater(checked, 25)

    def test_garbage_and_wrong_secret_tokens_are_rejected_on_stateless_endpoints(self) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        forged = make_token(USER_A_ID, secret="x" * 40)
        with patch.dict(os.environ, {"ELEMENTX_ENV": "production"}):
            for token in ("garbage", forged):
                response = client.post(
                    "/api/query-formula",
                    json={"formula": "Fe"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                self.assertEqual(response.status_code, 401)


class StatelessEndpointsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.anon = TestClient(app, raise_server_exceptions=False)
        self.auth = TestClient(app, headers=auth_headers(USER_A_ID), raise_server_exceptions=False)

    def test_authenticated_client_still_works_in_production(self) -> None:
        with patch.dict(os.environ, {"ELEMENTX_ENV": "production"}):
            cif = self.auth.post("/api/parse-cif", files={"file": ("nacl.cif", NAIVE_CIF)})
            mag = self.auth.post(
                "/api/magnetometry/analyze",
                files={"file": (MAGNETOMETRY_FIXTURE.name, MAGNETOMETRY_FIXTURE.read_bytes())},
            )
            analyze = self.auth.post(
                "/api/analyze-magnet",
                json={
                    "formula": "Nd2Fe14B",
                    "magnetic_moment": 31.3,
                    "volume": 856.0,
                    "formula_units_per_cell": 4,
                    "fetch_from_materials_project": False,
                },
            )
        self.assertEqual(cif.status_code, 200, cif.text)
        self.assertEqual(cif.json()["formula"], "NaCl")
        self.assertEqual(mag.status_code, 200, mag.text)
        self.assertEqual(analyze.status_code, 200, analyze.text)

    def test_anonymous_access_is_denied_in_production_but_open_in_development(self) -> None:
        with patch.dict(os.environ, {"ELEMENTX_ENV": "production"}):
            denied = self.anon.post("/api/parse-cif", files={"file": ("nacl.cif", NAIVE_CIF)})
        self.assertEqual(denied.status_code, 401)
        with patch.dict(os.environ, {"ELEMENTX_ENV": "development"}):
            allowed = self.anon.post("/api/parse-cif", files={"file": ("nacl.cif", NAIVE_CIF)})
        self.assertEqual(allowed.status_code, 200)

    def test_denied_requests_do_not_spend_materials_project_quota(self) -> None:
        with patch.dict(os.environ, {"ELEMENTX_ENV": "production"}), patch.object(
            MaterialsClient, "query_formula", side_effect=AssertionError("must not be called")
        ):
            response = self.anon.post("/api/query-formula", json={"formula": "Nd2Fe14B"})
        self.assertEqual(response.status_code, 401)

    def test_upload_limits_still_apply_in_production(self) -> None:
        with patch.dict(os.environ, {"ELEMENTX_ENV": "production", "MAX_CIF_UPLOAD_MB": "1"}):
            response = self.auth.post(
                "/api/parse-cif", files={"file": ("big.cif", b"x" * (1024 * 1024 + 10))}
            )
        self.assertEqual(response.status_code, 413)
        self.assertIn("too large", response.json()["detail"].lower())


class ErrorSanitisationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app, headers=auth_headers(USER_A_ID), raise_server_exceptions=False)

    def _assert_clean(self, response) -> None:
        self.assertGreaterEqual(response.status_code, 500)
        for marker in SENSITIVE_MARKERS:
            self.assertNotIn(marker, response.text)

    def test_formula_query_hides_internal_exception_text(self) -> None:
        with patch.object(
            main.materials_client, "query_formula",
            side_effect=RuntimeError("boom mongodb://admin:hunter2@db /var/data/elementx.db"),
        ):
            response = self.client.post("/api/query-formula", json={"formula": "Fe"})
        self._assert_clean(response)
        self.assertEqual(response.json()["detail"], "Formula query failed.")

    def test_materials_project_upstream_errors_are_not_echoed(self) -> None:
        class FailingMPRester:
            def __init__(self, *_a, **_k) -> None:
                raise RuntimeError("GET https://api.materialsproject.org/?api_key=SECRETKEY failed")

        import mp_api.client

        client = MaterialsClient(api_key="SECRETKEY")
        with patch.object(mp_api.client, "MPRester", FailingMPRester):
            with self.assertRaises(MaterialsClientError) as ctx:
                client.query_formula("Fe")
        self.assertNotIn("SECRETKEY", str(ctx.exception))
        self.assertNotIn("api_key", str(ctx.exception))

    def test_cif_parser_failure_is_generic(self) -> None:
        with patch.object(main, "parse_cif_bytes", side_effect=RuntimeError("/var/data/secret.cif")):
            response = self.client.post("/api/parse-cif", files={"file": ("a.cif", NAIVE_CIF)})
        self._assert_clean(response)
        self.assertEqual(response.json()["detail"], "CIF parsing failed.")

    def test_legacy_upload_failures_are_generic(self) -> None:
        with patch.object(main, "parse_raw_file", side_effect=RuntimeError("mongodb://admin:hunter2@db")):
            xrd = self.client.post("/api/xrd/upload", files={"file": ("a.xy", b"1 2\n" * 10)})
            magnetic = self.client.post(
                "/api/magnetic/upload", files={"file": ("a.txt", b"1 2\n" * 10)}
            )
        self._assert_clean(xrd)
        self._assert_clean(magnetic)

    def test_registration_and_login_failures_are_generic(self) -> None:
        with patch.dict(os.environ, {"ELEMENTX_ENV": "development"}), patch.object(
            main.database, "DB_AVAILABLE", True
        ), patch.object(main.database, "db", side_effect=RuntimeError("mongodb://admin:hunter2@db")):
            response = TestClient(app, raise_server_exceptions=False).post(
                "/api/auth/login", json={"email": "a@example.com", "password": "x" * 12}
            )
        for marker in SENSITIVE_MARKERS:
            self.assertNotIn(marker, response.text)


class CorsBehaviourTests(unittest.TestCase):
    def _app(self, env: dict) -> TestClient:
        probe = FastAPI()
        probe.add_middleware(CORSMiddleware, **cors_settings(env))

        @probe.get("/ping")
        def ping():  # noqa: ANN202
            return {"ok": True}

        return TestClient(probe)

    def test_production_allows_only_configured_origins(self) -> None:
        client = self._app(
            {"ELEMENTX_ENV": "production", "CORS_ORIGINS": "https://app.elementx.example"}
        )
        allowed = client.options(
            "/ping",
            headers={
                "Origin": "https://app.elementx.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        self.assertEqual(allowed.headers.get("access-control-allow-origin"), "https://app.elementx.example")

        for hostile in ("https://evil.example", "https://app.elementx.example.evil.example", "null"):
            response = client.get("/ping", headers={"Origin": hostile})
            self.assertNotIn("access-control-allow-origin", response.headers, hostile)
        preflight = client.options(
            "/ping",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
        )
        self.assertNotEqual(preflight.status_code, 200)
        self.assertNotIn("access-control-allow-origin", preflight.headers)

    def test_production_never_allows_credentials_or_wildcards(self) -> None:
        settings = cors_settings({"ELEMENTX_ENV": "production", "CORS_ORIGINS": "https://a.example,*"})
        self.assertNotIn("*", settings["allow_origins"])
        self.assertFalse(settings["allow_credentials"])


class SharedDemoAccountTests(unittest.TestCase):
    def test_demo_credentials_do_not_work_in_production_even_if_the_account_exists(self) -> None:
        import local_store
        from services.demo_data import DEMO_EMAIL, DEMO_NAME, DEMO_PASSWORD

        import bcrypt

        local_store._LOCAL_USERS_BY_EMAIL[DEMO_EMAIL] = {  # noqa: SLF001
            "_id": "demo-id",
            "name": DEMO_NAME,
            "email": DEMO_EMAIL,
            "password": bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt()),
        }
        client = TestClient(app, raise_server_exceptions=False)
        try:
            with patch.dict(os.environ, {"ELEMENTX_ENV": "development"}):
                self.assertEqual(
                    client.post("/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}).status_code,
                    200,
                )
            with patch.dict(os.environ, {"ELEMENTX_ENV": "production"}), patch.object(
                main.database, "DB_AVAILABLE", True
            ):
                login = client.post("/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
                register = client.post(
                    "/api/auth/register",
                    json={"name": "x", "email": DEMO_EMAIL.upper(), "password": "correct-horse-battery"},
                )
            self.assertEqual(login.status_code, 401)
            self.assertNotIn("token", login.text)
            self.assertEqual(register.status_code, 400)
        finally:
            local_store._LOCAL_USERS_BY_EMAIL.pop(DEMO_EMAIL, None)  # noqa: SLF001


class ProductionApiSurfaceTests(unittest.TestCase):
    def test_interactive_docs_and_schema_are_disabled_in_production(self) -> None:
        from services.production_config import api_docs_settings

        self.assertEqual(
            api_docs_settings({"ELEMENTX_ENV": "production"}),
            {"docs_url": None, "redoc_url": None, "openapi_url": None},
        )
        self.assertEqual(api_docs_settings({})["docs_url"], "/docs")

    def test_a_valid_production_environment_boots_the_real_app(self) -> None:
        import subprocess
        import sys
        import tempfile

        backend = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            env = {k: v for k, v in os.environ.items() if k not in {"MP_API_KEY"}}
            env.update(
                {
                    "ELEMENTX_ENV": "production",
                    "PYTHONPATH": str(backend),
                    "JWT_SECRET": "Zq7-" + "x" * 40,
                    "MONGODB_URI": "mongodb+srv://u:p@cluster.example.net/elementx",
                    "DATA_DIR": str(data),
                    "DATABASE_URL": f"sqlite:///{data / 'elementx.db'}",
                    "CORS_ORIGINS": "https://app.elementx.example",
                    "ELEMENTX_ALLOW_UNMOUNTED_DATA_DIR": "true",
                }
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import main; print(main.app.docs_url, main.app.openapi_url, main.app.redoc_url)",
                ],
                cwd=backend, env=env, capture_output=True, text=True, timeout=120,
            )
        self.assertEqual(result.returncode, 0, result.stderr[-800:])
        self.assertTrue(result.stdout.strip().endswith("None None None"), result.stdout)


class HealthTests(unittest.TestCase):
    def test_health_reports_storage_and_exposes_no_secrets(self) -> None:
        body = TestClient(app).get("/health").json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("researchStorage", body)
        self.assertIsInstance(body["researchStorage"], bool)
        flat = str(body).lower()
        for marker in ("secret", "password", "mongodb://", "api_key"):
            self.assertNotIn(marker, flat)


if __name__ == "__main__":
    unittest.main()
