from __future__ import annotations

import sqlite3
import uuid
from datetime import timedelta

from sqlalchemy import select

from main import app
from models.research import Experiment, Sample
from services.db import get_session_factory
from services.experiment_records import claim_unowned_samples
from tests.auth_helpers import USER_A_ID, USER_B_ID, auth_headers, make_token
from tests.research_base import (
    RESEARCH_EXPERIMENTS,
    RESEARCH_SAMPLES,
    ResearchApiTestCase,
)

PLACEHOLDER_ID = "00000000-0000-0000-0000-000000000000"


def _research_routes() -> list[tuple[str, str]]:
    """Every (method, path) under the research APIs, taken from the OpenAPI schema."""
    routes: list[tuple[str, str]] = []
    for path, operations in app.openapi()["paths"].items():
        if not path.startswith(("/api/research/", "/api/research-copilot/")):
            continue
        for method in operations:
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                routes.append((method.upper(), path))
    return sorted(routes)


class ResearchAuthenticationTests(ResearchApiTestCase):
    def test_route_inventory_is_not_empty(self) -> None:
        paths = {path for _, path in _research_routes()}
        self.assertIn("/api/research/samples", paths)
        self.assertIn("/api/research/samples/{sample_id}/experiments", paths)
        self.assertIn("/api/research/samples/{sample_id}/xrd-experiments", paths)
        self.assertIn("/api/research/experiments/{experiment_id}", paths)
        self.assertIn("/api/research-copilot/chat", paths)

    def test_every_research_endpoint_requires_authentication(self) -> None:
        routes = _research_routes()
        self.assertGreaterEqual(len(routes), 7)
        for method, path in routes:
            url = path.replace("{sample_id}", PLACEHOLDER_ID).replace(
                "{experiment_id}", PLACEHOLDER_ID
            )
            with self.subTest(method=method, path=path):
                response = self.anonymous.request(method, url)
                self.assertEqual(response.status_code, 401, response.text)

    def test_invalid_token_is_rejected(self) -> None:
        response = self.anonymous.get(
            RESEARCH_SAMPLES, headers={"Authorization": "Bearer not-a-jwt"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid token")

    def test_token_signed_with_wrong_secret_is_rejected(self) -> None:
        token = make_token(USER_A_ID, secret="a-completely-different-signing-secret")
        response = self.anonymous.get(
            RESEARCH_SAMPLES, headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_expired_token_is_rejected(self) -> None:
        expired = auth_headers(USER_A_ID, expires_in=timedelta(seconds=-5))
        response = self.anonymous.get(RESEARCH_SAMPLES, headers=expired)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Token has expired")

    def test_expired_token_cannot_create_sample(self) -> None:
        expired = auth_headers(USER_A_ID, expires_in=timedelta(minutes=-1))
        response = self.anonymous.post(
            RESEARCH_SAMPLES, json={"name": "Should not exist"}, headers=expired
        )
        self.assertEqual(response.status_code, 401)
        listed = self.client_a.get(RESEARCH_SAMPLES).json()
        self.assertNotIn("Should not exist", [s["name"] for s in listed])

    def test_token_without_user_id_is_rejected(self) -> None:
        import jwt
        from datetime import datetime

        import database

        token = jwt.encode(
            {"email": "x@example.test", "exp": datetime.utcnow() + timedelta(hours=1)},
            database.SECRET_KEY,
            algorithm="HS256",
        )
        response = self.anonymous.get(
            RESEARCH_SAMPLES, headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 401)


class ResearchOwnershipTests(ResearchApiTestCase):
    def test_sample_lists_are_filtered_by_owner(self) -> None:
        sample_a = self.create_sample(self.client_a, name="A private sample")
        sample_b = self.create_sample(self.client_b, name="B private sample")

        listed_a = {s["id"] for s in self.client_a.get(RESEARCH_SAMPLES).json()}
        listed_b = {s["id"] for s in self.client_b.get(RESEARCH_SAMPLES).json()}

        self.assertIn(sample_a["id"], listed_a)
        self.assertNotIn(sample_b["id"], listed_a)
        self.assertIn(sample_b["id"], listed_b)
        self.assertNotIn(sample_a["id"], listed_b)

    def test_owner_is_never_exposed_in_payloads(self) -> None:
        sample = self.create_sample(self.client_a)
        self.assertNotIn("owner_user_id", sample)
        detail = self.client_a.get(f"{RESEARCH_SAMPLES}/{sample['id']}").json()
        self.assertNotIn("owner_user_id", detail)

    def test_user_b_cannot_open_user_a_sample_or_experiment(self) -> None:
        sample = self.create_sample(self.client_a, name="A sample with data")
        mag = self.upload_magnetometry(sample["id"])
        xrd = self.upload_xrd(sample["id"])
        self.assertEqual(mag.status_code, 201, mag.text)
        self.assertEqual(xrd.status_code, 201, xrd.text)

        sample_response = self.client_b.get(f"{RESEARCH_SAMPLES}/{sample['id']}")
        self.assertEqual(sample_response.status_code, 404)
        self.assertEqual(sample_response.json()["detail"], "Sample not found.")

        for created in (mag.json(), xrd.json()):
            response = self.client_b.get(f"{RESEARCH_EXPERIMENTS}/{created['id']}")
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["detail"], "Experiment not found.")
            self.assertNotIn("analysis_json", response.text)

        # Foreign and missing ids are indistinguishable.
        missing = self.client_b.get(f"{RESEARCH_SAMPLES}/{uuid.uuid4()}")
        self.assertEqual(missing.json(), sample_response.json())

    def test_cross_user_uploads_are_rejected_and_leave_nothing_behind(self) -> None:
        sample = self.create_sample(self.client_a, name="A upload target")
        dirs_before = self.experiment_dirs()

        for upload in (self.upload_magnetometry, self.upload_xrd):
            response = upload(sample["id"], self.client_b)
            self.assertEqual(response.status_code, 404, response.text)
            self.assertEqual(response.json()["detail"], "Sample not found.")

        self.assertEqual(self.experiment_dirs(), dirs_before)
        detail = self.client_a.get(f"{RESEARCH_SAMPLES}/{sample['id']}").json()
        self.assertEqual(detail["experiments"], [])

    def test_client_supplied_owner_is_ignored(self) -> None:
        response = self.client_a.post(
            f"{RESEARCH_SAMPLES}?owner_user_id={USER_B_ID}&userId={USER_B_ID}",
            json={"name": "Spoof attempt", "owner_user_id": USER_B_ID, "userId": USER_B_ID},
            headers={"X-User-Id": USER_B_ID},
        )
        self.assertEqual(response.status_code, 201, response.text)
        sample_id = response.json()["id"]

        listed_b = {s["id"] for s in self.client_b.get(RESEARCH_SAMPLES).json()}
        self.assertNotIn(sample_id, listed_b)
        listed_a = {s["id"] for s in self.client_a.get(RESEARCH_SAMPLES).json()}
        self.assertIn(sample_id, listed_a)

    def test_owner_persists_in_database_and_across_restart(self) -> None:
        sample = self.create_sample(self.client_a, name="Persisted owner")
        self.assertEqual(self.upload_xrd(sample["id"]).status_code, 201)

        db = get_session_factory()()
        try:
            row = db.get(Sample, sample["id"])
            self.assertEqual(row.owner_user_id, USER_A_ID)
        finally:
            db.close()

        self.restart_engine()

        db = get_session_factory()()
        try:
            row = db.get(Sample, sample["id"])
            self.assertEqual(row.owner_user_id, USER_A_ID)
        finally:
            db.close()
        self.assertEqual(
            self.client_a.get(f"{RESEARCH_SAMPLES}/{sample['id']}").status_code, 200
        )
        self.assertEqual(
            self.client_b.get(f"{RESEARCH_SAMPLES}/{sample['id']}").status_code, 404
        )

    def test_saved_magnetometry_and_xrd_reopen_after_restart(self) -> None:
        sample = self.create_sample(self.client_a, name="Restart round trip")
        mag = self.upload_magnetometry(sample["id"])
        xrd = self.upload_xrd(sample["id"])
        self.assertEqual(mag.status_code, 201, mag.text)
        self.assertEqual(xrd.status_code, 201, xrd.text)

        self.restart_engine()

        reopened_mag = self.client_a.get(f"{RESEARCH_EXPERIMENTS}/{mag.json()['id']}").json()
        reopened_xrd = self.client_a.get(f"{RESEARCH_EXPERIMENTS}/{xrd.json()['id']}").json()
        self.assertEqual(reopened_mag["experiment_type"], "magnetometry")
        self.assertEqual(reopened_mag["analysis_json"], mag.json()["analysis_json"])
        self.assertEqual(reopened_xrd["experiment_type"], "xrd")
        self.assertEqual(reopened_xrd["analysis_json"], xrd.json()["analysis_json"])
        segment = next(
            entry
            for entry in reopened_mag["analysis_json"]["mh_analyses"]
            if abs(entry["analysis"]["segment"]["mean_temperature_K"] - 300.0) < 5.0
        )
        self.assertAlmostEqual(
            segment["analysis"]["hysteresis"]["Hc_negative_Oe"], -107.452, places=3
        )
        self.assertEqual(
            len(reopened_xrd["analysis_json"]["series"]["two_theta_deg"]),
            reopened_xrd["analysis_json"]["summary"]["point_count"],
        )

    def test_experiment_access_flows_through_parent_sample(self) -> None:
        sample = self.create_sample(self.client_a, name="Inherited access")
        created = self.upload_xrd(sample["id"]).json()

        db = get_session_factory()()
        try:
            experiment = db.get(Experiment, created["id"])
            # Experiments carry no owner of their own; access is the parent's owner.
            self.assertFalse(hasattr(experiment, "owner_user_id"))
            self.assertEqual(experiment.sample.owner_user_id, USER_A_ID)
        finally:
            db.close()


LEGACY_SCHEMA = """
CREATE TABLE scientific_samples (
    id VARCHAR(36) NOT NULL,
    name VARCHAR(255) NOT NULL,
    formula VARCHAR(255),
    notes TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id)
);
CREATE TABLE scientific_experiments (
    id VARCHAR(36) NOT NULL,
    sample_id VARCHAR(36) NOT NULL,
    experiment_type VARCHAR(64) NOT NULL,
    original_filename VARCHAR(512) NOT NULL,
    uploaded_at DATETIME NOT NULL,
    raw_file_path VARCHAR(1024) NOT NULL,
    analysis_version VARCHAR(32) NOT NULL,
    analysis_json JSON NOT NULL,
    user_confirmed_mass_mg FLOAT,
    PRIMARY KEY (id),
    FOREIGN KEY(sample_id) REFERENCES scientific_samples (id)
);
CREATE INDEX ix_scientific_experiments_sample_id ON scientific_experiments (sample_id);
"""


class ExistingDatabaseUpgradeTests(ResearchApiTestCase):
    """A database created before ownership existed must upgrade in place."""

    LEGACY_SAMPLE_ID = "11111111-1111-4111-8111-111111111111"
    LEGACY_EXPERIMENT_ID = "22222222-2222-4222-8222-222222222222"

    def _build_legacy_database(self) -> None:
        import json

        from services.xrd_analysis import analyze_xrd_bytes

        self.db_path.unlink(missing_ok=True)
        analysis = json.loads(
            json.dumps(analyze_xrd_bytes(self.xrd_bytes, "legacy.xy"), default=str)
        )
        analysis["analysis_version"] = "1"
        connection = sqlite3.connect(self.db_path)
        try:
            connection.executescript(LEGACY_SCHEMA)
            connection.execute(
                "INSERT INTO scientific_samples VALUES (?,?,?,?,?,?)",
                (
                    self.LEGACY_SAMPLE_ID,
                    "Legacy sample",
                    "Fe2CoGe",
                    "created before ownership",
                    "2026-09-01 10:00:00.000000",
                    "2026-09-01 10:00:00.000000",
                ),
            )
            connection.execute(
                "INSERT INTO scientific_experiments VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    self.LEGACY_EXPERIMENT_ID,
                    self.LEGACY_SAMPLE_ID,
                    "xrd",
                    "legacy.xy",
                    "2026-09-01 10:05:00.000000",
                    f"experiments/{self.LEGACY_EXPERIMENT_ID}/original.xy",
                    "1",
                    json.dumps(analysis),
                    None,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def _owner_column_present(self) -> bool:
        connection = sqlite3.connect(self.db_path)
        try:
            columns = [row[1] for row in connection.execute("PRAGMA table_info(scientific_samples)")]
        finally:
            connection.close()
        return "owner_user_id" in columns

    def test_upgrade_adds_owner_column_and_preserves_rows(self) -> None:
        self._build_legacy_database()
        self.assertFalse(self._owner_column_present())

        self.restart_engine()

        self.assertTrue(self._owner_column_present())
        connection = sqlite3.connect(self.db_path)
        try:
            sample_rows = connection.execute(
                "SELECT id, name, formula, notes, owner_user_id FROM scientific_samples"
            ).fetchall()
            experiment_rows = connection.execute(
                "SELECT id, sample_id, experiment_type, original_filename "
                "FROM scientific_experiments"
            ).fetchall()
            indexes = [
                row[1] for row in connection.execute("PRAGMA index_list(scientific_samples)")
            ]
        finally:
            connection.close()

        self.assertEqual(
            sample_rows,
            [
                (
                    self.LEGACY_SAMPLE_ID,
                    "Legacy sample",
                    "Fe2CoGe",
                    "created before ownership",
                    None,
                )
            ],
        )
        self.assertEqual(
            experiment_rows,
            [(self.LEGACY_EXPERIMENT_ID, self.LEGACY_SAMPLE_ID, "xrd", "legacy.xy")],
        )
        self.assertIn("ix_scientific_samples_owner_user_id", indexes)

    def test_upgrade_is_idempotent(self) -> None:
        self._build_legacy_database()
        self.restart_engine()
        self.restart_engine()
        self.restart_engine()
        self.assertTrue(self._owner_column_present())
        connection = sqlite3.connect(self.db_path)
        try:
            count = connection.execute("SELECT COUNT(*) FROM scientific_samples").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 1)

    def test_unowned_legacy_rows_are_hidden_until_claimed(self) -> None:
        self._build_legacy_database()
        self.restart_engine()

        for client in (self.client_a, self.client_b):
            self.assertEqual(client.get(RESEARCH_SAMPLES).json(), [])
            self.assertEqual(
                client.get(f"{RESEARCH_SAMPLES}/{self.LEGACY_SAMPLE_ID}").status_code, 404
            )
            self.assertEqual(
                client.get(f"{RESEARCH_EXPERIMENTS}/{self.LEGACY_EXPERIMENT_ID}").status_code,
                404,
            )

        db = get_session_factory()()
        try:
            self.assertEqual(claim_unowned_samples(db, USER_A_ID), 1)
            # A second claim by someone else must not steal an owned sample.
            self.assertEqual(claim_unowned_samples(db, USER_B_ID), 0)
            owner = db.scalars(
                select(Sample.owner_user_id).where(Sample.id == self.LEGACY_SAMPLE_ID)
            ).one()
        finally:
            db.close()
        self.assertEqual(owner, USER_A_ID)

        listed = self.client_a.get(RESEARCH_SAMPLES).json()
        self.assertEqual([s["id"] for s in listed], [self.LEGACY_SAMPLE_ID])
        reopened = self.client_a.get(f"{RESEARCH_EXPERIMENTS}/{self.LEGACY_EXPERIMENT_ID}")
        self.assertEqual(reopened.status_code, 200, reopened.text)
        self.assertEqual(reopened.json()["analysis_json"]["analysis_version"], "1")
        self.assertEqual(self.client_b.get(RESEARCH_SAMPLES).json(), [])

    def test_new_samples_work_after_upgrade(self) -> None:
        self._build_legacy_database()
        self.restart_engine()
        sample = self.create_sample(self.client_a, name="Post-upgrade sample")
        self.assertEqual(self.upload_xrd(sample["id"]).status_code, 201)
        listed = {s["id"] for s in self.client_a.get(RESEARCH_SAMPLES).json()}
        self.assertIn(sample["id"], listed)


if __name__ == "__main__":
    import unittest

    unittest.main()
