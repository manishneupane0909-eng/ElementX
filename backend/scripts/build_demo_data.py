"""Build (or verify) the static snapshots behind the ElementX portfolio demo.

The public demo has no backend. Everything it shows is a snapshot of what the real
ElementX backend returns for two bundled test files, so no number in the demo is typed
in or recomputed by the frontend.

Run from the ``backend`` directory:

    python -m scripts.build_demo_data            # regenerate the snapshots
    python -m scripts.build_demo_data --check    # regenerate in memory and compare
    python -m scripts.build_demo_data --refresh-materials   # re-query Materials Project

How the snapshots are produced
------------------------------
* The real FastAPI application is driven through ``TestClient`` against a throw-away SQLite
  database and data directory, using the same routes and code paths as the live app.
* Record ids and timestamps are made deterministic by substituting ``uuid4`` and
  ``datetime`` inside ``services.experiment_records`` for the duration of the run. No
  production code is changed, and no scientific value depends on either.
* The language model is forced off, so Copilot replies are the backend's deterministic
  stored-record readout.
* The only edit made to a public copy is removing the instrument ``*_SERIAL_NUMBER``
  header fields from the stored analysis metadata. It is recorded in every experiment's
  ``demo.modifications`` and in the manifest. The unchanged original stays at
  ``backend/tests/fixtures``.

``--check`` compares everything except the Materials Project data (which needs network
access and a key) and the informational ``manifest.environment`` block. Floating-point
values are compared with a relative tolerance of 1e-9, so a different BLAS/NumPy build
does not cause a false failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import sys
import tempfile
import uuid
from contextlib import ExitStack
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
FIXTURES = BACKEND_DIR / "tests" / "fixtures"
MAGNETOMETRY_FIXTURE = FIXTURES / "Fe2CoGe_annealed_48hrs_900C_M_H_M_T.dat"
XRD_FIXTURE = FIXTURES / "two_column_xrd_test.xy"
OUTPUT_DIR = REPO_ROOT / "frontend" / "elementx-frontend" / "public-demo" / "demo"

SCHEMA_VERSION = 1

# Fixed so the snapshots are reproducible. These are the dates of the demo records, not
# of the measurement; the measurement date lives in the instrument header.
RECORD_TIME = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)
DEMO_USER_ID = "portfolio-demo"
ID_NAMESPACE = uuid.UUID("5d5f2c9a-0c3e-4a64-9c1a-3a3a6f1d2b10")

# Curated Materials Project lookups. Fe2CoGe is the measured compound; the others are the
# permanent-magnet benchmarks the Materials Explorer is built around.
CURATED_FORMULAS = ["Fe2CoGe", "Nd2Fe14B", "SmCo5", "Fe3Ga"]

SERIAL_SUFFIX = "_SERIAL_NUMBER"

SAMPLE_MAGNETOMETRY = {
    "label": "fe2coge",
    "name": "Fe2CoGe, annealed 900 °C for 48 h",
    "formula": "Fe2CoGe",
    "notes": (
        "Real Quantum Design VersaLab VSM measurement: ten M-H loops at different "
        "temperatures and one M-T sweep. The annealing conditions are taken from the "
        "instrument file title."
    ),
}
SAMPLE_XRD = {
    "label": "xrd-synthetic",
    "name": "Synthetic XRD test pattern",
    "formula": None,
    "notes": (
        "SYNTHETIC. A hand-written software test pattern, not a laboratory measurement "
        "and not from the Fe2CoGe sample. It only demonstrates how ElementX reads a "
        "two-column XRD file and lists candidate intensity maxima."
    ),
}

COPILOT_OVERVIEW_PROMPT = "Which samples are stored?"
COPILOT_SAMPLE_PROMPT = "Summarize the stored results for this sample."


class DemoDataMismatch(Exception):
    """Raised by ``--check`` when the committed snapshots differ from a rebuild."""


# --------------------------------------------------------------------------- helpers


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def demo_id(label: str) -> str:
    return str(uuid.uuid5(ID_NAMESPACE, label))


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"


def _frozen_datetime() -> type:
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D102 - mirrors datetime.now
            return RECORD_TIME if tz is not None else RECORD_TIME.replace(tzinfo=None)

    return FrozenDatetime


def redact_metadata(analysis: dict) -> list[str]:
    """Drop instrument serial numbers from ``analysis_json.metadata`` (in place)."""
    metadata = analysis.get("metadata")
    if not isinstance(metadata, dict):
        return []
    removed = sorted(key for key in metadata if key.upper().endswith(SERIAL_SUFFIX))
    for key in removed:
        del metadata[key]
    return removed


# ------------------------------------------------------------------- snapshot building


def _drive_backend(workdir: Path) -> dict[str, Any]:
    """Run the real routes and return raw responses. Everything here is production code."""
    os.environ["DATABASE_URL"] = f"sqlite:///{workdir / 'demo.db'}"
    os.environ["DATA_DIR"] = str(workdir / "data")

    from fastapi.testclient import TestClient

    import services.experiment_records as experiment_records
    from main import app
    from services.db import (
        configure_engine,
        get_db,
        get_session_factory,
        init_db,
        reset_engine,
    )
    from tests.auth_helpers import auth_headers

    ids = iter(
        [
            uuid.UUID(demo_id(SAMPLE_MAGNETOMETRY["label"])),
            uuid.UUID(demo_id("experiment:magnetometry")),
            uuid.UUID(demo_id(SAMPLE_XRD["label"])),
            uuid.UUID(demo_id("experiment:xrd")),
        ]
    )

    def next_id() -> uuid.UUID:
        return next(ids)

    def override_get_db():
        db = get_session_factory()()
        try:
            yield db
        finally:
            db.close()

    reset_engine()
    configure_engine(os.environ["DATABASE_URL"])
    init_db()
    app.dependency_overrides[get_db] = override_get_db

    out: dict[str, Any] = {}
    try:
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(experiment_records, "datetime", _frozen_datetime())
            )
            stack.enter_context(patch.object(experiment_records, "uuid4", next_id))
            stack.enter_context(
                patch("routers.research_copilot.llm_available", return_value=False)
            )
            client = TestClient(app, headers=auth_headers(DEMO_USER_ID))

            def post_sample(sample: dict) -> dict:
                response = client.post(
                    "/api/research/samples",
                    json={k: sample[k] for k in ("name", "formula", "notes")},
                )
                assert response.status_code == 201, response.text
                return response.json()

            mag_sample = post_sample(SAMPLE_MAGNETOMETRY)
            response = client.post(
                f"/api/research/samples/{mag_sample['id']}/experiments",
                files={"file": (MAGNETOMETRY_FIXTURE.name, MAGNETOMETRY_FIXTURE.read_bytes())},
            )
            assert response.status_code == 201, response.text
            mag_experiment = response.json()

            xrd_sample = post_sample(SAMPLE_XRD)
            response = client.post(
                f"/api/research/samples/{xrd_sample['id']}/xrd-experiments",
                files={"file": (XRD_FIXTURE.name, XRD_FIXTURE.read_bytes())},
            )
            assert response.status_code == 201, response.text
            xrd_experiment = response.json()

            if list(ids):
                raise RuntimeError("Unexpected number of record ids consumed.")

            listing = client.get("/api/research/samples")
            assert listing.status_code == 200, listing.text
            details = {}
            for sample in (mag_sample, xrd_sample):
                detail = client.get(f"/api/research/samples/{sample['id']}")
                assert detail.status_code == 200, detail.text
                details[sample["id"]] = detail.json()
            stored = {}
            for experiment in (mag_experiment, xrd_experiment):
                fetched = client.get(f"/api/research/experiments/{experiment['id']}")
                assert fetched.status_code == 200, fetched.text
                stored[experiment["id"]] = fetched.json()

            status = client.get("/api/research-copilot/status")
            assert status.status_code == 200, status.text

            def chat(message: str, sample_id: str | None) -> dict:
                response = client.post(
                    "/api/research-copilot/chat",
                    json={"message": message, "sample_id": sample_id, "history": []},
                )
                assert response.status_code == 200, response.text
                return response.json()

            replies = {"overview": chat(COPILOT_OVERVIEW_PROMPT, None)}
            for sample in (mag_sample, xrd_sample):
                replies[sample["id"]] = chat(COPILOT_SAMPLE_PROMPT, sample["id"])

        out.update(
            listing=listing.json(),
            details=details,
            experiments=stored,
            copilot_status=status.json(),
            copilot_replies=replies,
            mag_sample_id=mag_sample["id"],
            xrd_sample_id=xrd_sample["id"],
            mag_experiment_id=mag_experiment["id"],
            xrd_experiment_id=xrd_experiment["id"],
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
        reset_engine()
    return out


def _provenance(kind: str, fixture: Path, removed: list[str], pipeline: str) -> dict:
    data = fixture.read_bytes()
    if kind == "real-measurement":
        label = "Real laboratory measurement"
        description = (
            "Quantum Design VersaLab vibrating-sample magnetometer data, analysed by the "
            "ElementX magnetometry pipeline."
        )
    else:
        label = "Synthetic test pattern, not a laboratory measurement"
        description = (
            "A hand-written software test fixture. It does not describe any real sample "
            "and must not be read as laboratory data."
        )
    modifications = (
        [
            f"Removed {len(removed)} instrument serial-number fields "
            f"({', '.join(removed)}) from the stored metadata of this public copy. "
            "No measured value or derived result was changed."
        ]
        if removed
        else []
    )
    return {
        "data_kind": kind,
        "label": label,
        "description": description,
        "source_file": fixture.name,
        "source_sha256": sha256_bytes(data),
        "source_bytes": len(data),
        "analysis_pipeline": pipeline,
        "modifications": modifications,
    }


def build_snapshots(workdir: Path) -> dict[str, Any]:
    """Return ``{relative path: JSON-serialisable value}`` for the science snapshots."""
    raw = _drive_backend(workdir)

    from services.magnetometry_analysis import MAGNETOMETRY_PIPELINE_VERSION
    from services.xrd_analysis import XRD_PIPELINE_VERSION

    mag_id, xrd_id = raw["mag_sample_id"], raw["xrd_sample_id"]
    mag_exp_id, xrd_exp_id = raw["mag_experiment_id"], raw["xrd_experiment_id"]

    files: dict[str, Any] = {}

    removed_serials: list[str] = []
    provenance_by_experiment: dict[str, dict] = {}
    for exp_id, kind, fixture, pipeline in (
        (
            mag_exp_id,
            "real-measurement",
            MAGNETOMETRY_FIXTURE,
            f"magnetometry v{MAGNETOMETRY_PIPELINE_VERSION}",
        ),
        (xrd_exp_id, "synthetic", XRD_FIXTURE, f"xrd v{XRD_PIPELINE_VERSION}"),
    ):
        experiment = raw["experiments"][exp_id]
        removed = redact_metadata(experiment["analysis_json"])
        if exp_id == mag_exp_id:
            removed_serials = removed
        provenance = _provenance(kind, fixture, removed, pipeline)
        provenance_by_experiment[exp_id] = provenance
        experiment["demo"] = provenance
        files[f"experiments/{exp_id}.json"] = experiment

    sample_demo = {
        mag_id: {"data_kind": "real-measurement", "label": "Real laboratory measurement"},
        xrd_id: {
            "data_kind": "synthetic",
            "label": "Synthetic test pattern, not a laboratory measurement",
        },
    }
    experiment_demo = {
        exp_id: {"data_kind": p["data_kind"], "label": p["label"]}
        for exp_id, p in provenance_by_experiment.items()
    }

    summaries = []
    for summary in raw["listing"]:
        summaries.append({**summary, "demo": sample_demo[summary["id"]]})
    files["samples.json"] = summaries

    for sample_id, detail in raw["details"].items():
        detail = {**detail, "demo": sample_demo[sample_id]}
        detail["experiments"] = [
            {**experiment, "demo": experiment_demo[experiment["id"]]}
            for experiment in detail["experiments"]
        ]
        files[f"samples/{sample_id}.json"] = detail

    status = raw["copilot_status"]
    copilot = {
        "status": {
            "llmAvailable": False,
            "model": "none (stored-record readout)",
            "researchContext": bool(status.get("researchContext", True)),
        },
        "note": (
            "Each reply was produced by the ElementX backend's deterministic stored-record "
            "readout with the language model switched off. The readout does not depend on "
            "the wording of the question."
        ),
        "replies": {},
    }
    for key, reply in raw["copilot_replies"].items():
        copilot["replies"][key] = {
            "prompt": COPILOT_OVERVIEW_PROMPT if key == "overview" else COPILOT_SAMPLE_PROMPT,
            "answer": reply["answer"],
            "source": reply.get("source"),
            "sampleId": reply.get("sampleId"),
            "sampleName": reply.get("sampleName"),
            "researchContext": bool(reply.get("researchContext", True)),
            "llmAvailable": False,
        }
    files["copilot.json"] = copilot

    files["manifest.json"] = {
        "schema_version": SCHEMA_VERSION,
        "title": "ElementX portfolio demo data",
        "generator": "backend/scripts/build_demo_data.py",
        "record_time_note": (
            "Record dates are fixed constants so the snapshots are reproducible. They are "
            "not measurement dates; the measurement date is in the instrument header."
        ),
        "record_time": RECORD_TIME.isoformat(),
        "pipelines": {
            "magnetometry": MAGNETOMETRY_PIPELINE_VERSION,
            "xrd": XRD_PIPELINE_VERSION,
        },
        "featured": {
            "sample_id": mag_id,
            "experiment_id": mag_exp_id,
        },
        "samples": [
            {
                "id": mag_id,
                "name": SAMPLE_MAGNETOMETRY["name"],
                "data_kind": "real-measurement",
                "experiment_id": mag_exp_id,
            },
            {
                "id": xrd_id,
                "name": SAMPLE_XRD["name"],
                "data_kind": "synthetic",
                "experiment_id": xrd_exp_id,
            },
        ],
        "sources": {
            exp_id: {
                "file": p["source_file"],
                "sha256": p["source_sha256"],
                "bytes": p["source_bytes"],
                "data_kind": p["data_kind"],
            }
            for exp_id, p in provenance_by_experiment.items()
        },
        "redactions": {
            "removed_metadata_keys": removed_serials,
            "scope": "analysis_json.metadata of the public snapshot only",
            "original_unmodified_at": "backend/tests/fixtures/" + MAGNETOMETRY_FIXTURE.name,
        },
        "raw_instrument_files_published": False,
    }
    return files


def build_materials() -> dict[str, Any]:
    """Query Materials Project for the curated formulas (needs MP_API_KEY and network)."""
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    from services.materials_client import MaterialsClient

    client = MaterialsClient()
    entries: dict[str, Any] = {}
    for formula in CURATED_FORMULAS:
        try:
            entries[formula] = client.query_formula(formula).model_dump()
        except Exception as exc:  # noqa: BLE001 - report which formula and continue
            print(f"  materials: {formula} skipped ({type(exc).__name__})", file=sys.stderr)
    return {
        "source": {
            "name": "Materials Project",
            "url": "https://next-gen.materialsproject.org/",
            "license": "CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "retrieved": date.today().isoformat(),
            "access": "Materials Project API through the ElementX backend client",
            "note": (
                "Entries are shown as returned by the ElementX backend's Materials client, "
                "which selects the lowest energy-above-hull entry for the formula."
            ),
        },
        "formulas": [f for f in CURATED_FORMULAS if f in entries],
        "entries": entries,
    }


# ---------------------------------------------------------------------- write / check


def _close(a: Any, b: Any, path: str, problems: list[str]) -> None:
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None:
        if a != b:
            problems.append(f"{path}: {a!r} != {b!r}")
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if not math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12):
            problems.append(f"{path}: {a!r} != {b!r}")
    elif isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                problems.append(f"{path}.{key}: present on one side only")
            else:
                _close(a[key], b[key], f"{path}.{key}", problems)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            problems.append(f"{path}: length {len(a)} != {len(b)}")
        else:
            for index, (x, y) in enumerate(zip(a, b)):
                _close(x, y, f"{path}[{index}]", problems)
    elif a != b:
        problems.append(f"{path}: {str(a)[:60]!r} != {str(b)[:60]!r}")


def compare(rebuilt: dict[str, Any], output_dir: Path) -> list[str]:
    problems: list[str] = []
    for rel, value in rebuilt.items():
        target = output_dir / rel
        if not target.exists():
            problems.append(f"{rel}: missing")
            continue
        committed = json.loads(target.read_text(encoding="utf-8"))
        if rel == "manifest.json":
            committed = {k: v for k, v in committed.items() if k not in ("files", "environment", "materials")}
        _close(committed, value, rel, problems)
        if len(problems) > 25:
            problems.append("... more differences omitted")
            return problems
    return problems


def write_snapshots(files: dict[str, Any], materials: dict[str, Any], output_dir: Path) -> None:
    import numpy
    import scipy

    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in list(output_dir.rglob("*.json")):
        stale.unlink()
    hashes: dict[str, str] = {}
    to_write = {**files, "materials.json": materials}
    for rel, value in to_write.items():
        if rel == "manifest.json":
            continue
        text = dumps(value)
        target = output_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        hashes[rel] = sha256_bytes(text.encode("utf-8"))

    manifest = dict(files["manifest.json"])
    manifest["materials"] = {
        "retrieved": materials["source"]["retrieved"],
        "formulas": materials["formulas"],
        "license": materials["source"]["license"],
    }
    manifest["files"] = dict(sorted(hashes.items()))
    manifest["environment"] = {
        "note": "Informational only; not compared by --check.",
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
    }
    (output_dir / "manifest.json").write_text(dumps(manifest), encoding="utf-8")


def load_existing_materials(output_dir: Path) -> dict[str, Any] | None:
    path = output_dir / "materials.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def run(check: bool, refresh_materials: bool, output_dir: Path = OUTPUT_DIR) -> int:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    previous_env = {key: os.environ.get(key) for key in ("DATABASE_URL", "DATA_DIR")}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            files = build_snapshots(Path(tmp))
    finally:
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    if check:
        problems = compare(files, output_dir)
        if problems:
            print("Demo snapshots differ from a fresh rebuild:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        print(f"OK: {len(files)} snapshot files match a fresh run of the backend pipeline.")
        return 0

    materials = None if refresh_materials else load_existing_materials(output_dir)
    if materials is None:
        print("Querying Materials Project for the curated formulas...")
        materials = build_materials()
        if not materials["entries"]:
            print("No Materials Project entries could be retrieved.", file=sys.stderr)
            return 1
    write_snapshots(files, materials, output_dir)
    print(f"Wrote {len(files) + 1} files to {output_dir.relative_to(REPO_ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--check", action="store_true", help="Compare with a fresh rebuild; write nothing.")
    parser.add_argument(
        "--refresh-materials",
        action="store_true",
        help="Re-query Materials Project (needs MP_API_KEY and network) instead of reusing materials.json.",
    )
    args = parser.parse_args(argv)
    return run(check=args.check, refresh_materials=args.refresh_materials)


if __name__ == "__main__":
    raise SystemExit(main())
