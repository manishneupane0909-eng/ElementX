"""The static portfolio-demo snapshots must stay a faithful product of the real pipeline."""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

from scripts import build_demo_data as demo

SNAPSHOT_DIR = demo.OUTPUT_DIR


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@unittest.skipUnless(SNAPSHOT_DIR.exists(), "demo snapshots have not been generated")
class DemoSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text(encoding="utf-8"))
        cls.all_text = {
            str(path.relative_to(SNAPSHOT_DIR)): path.read_text(encoding="utf-8")
            for path in SNAPSHOT_DIR.rglob("*.json")
        }

    def test_snapshots_match_a_fresh_run_of_the_pipeline(self) -> None:
        self.assertEqual(demo.run(check=True, refresh_materials=False), 0)

    def test_rebuild_is_deterministic(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            a = demo.build_snapshots(Path(first))
            b = demo.build_snapshots(Path(second))
        self.assertEqual(demo.dumps(a), demo.dumps(b))

    def test_manifest_hashes_match_files(self) -> None:
        for rel, digest in self.manifest["files"].items():
            self.assertEqual(_sha256(SNAPSHOT_DIR / rel), digest, rel)

    def test_source_hashes_match_the_unmodified_fixtures(self) -> None:
        by_file = {entry["file"]: entry["sha256"] for entry in self.manifest["sources"].values()}
        self.assertEqual(by_file[demo.MAGNETOMETRY_FIXTURE.name], _sha256(demo.MAGNETOMETRY_FIXTURE))
        self.assertEqual(by_file[demo.XRD_FIXTURE.name], _sha256(demo.XRD_FIXTURE))

    def test_no_instrument_serial_values_are_published(self) -> None:
        header = demo.MAGNETOMETRY_FIXTURE.read_bytes().decode("latin-1")
        values = {
            match.group(1).strip()
            for match in re.finditer(r"INFO,([^,\r\n]+),[A-Z_]*SERIAL_NUMBER", header)
        }
        values |= {
            match.group(1).strip()
            for match in re.finditer(r"[A-Z_]*SERIAL_NUMBER,([^,\r\n]+)", header)
        }
        values = {value for value in values if len(value) >= 3}  # noqa: E501
        self.assertTrue(values, "fixture header no longer lists serial numbers; update this test")
        for rel, text in self.all_text.items():
            for value in values:
                # Short numeric identifiers are only meaningful as whole JSON strings.
                pattern = rf'"{re.escape(value)}"' if value.isdigit() else re.escape(value)
                self.assertIsNone(
                    re.search(pattern, text), f"{rel} contains an instrument identifier"
                )
            self.assertNotRegex(text, r'"[A-Z_]*SERIAL_NUMBER"\s*:')

    def test_synthetic_pattern_is_labelled_synthetic(self) -> None:
        xrd = next(
            entry for entry in self.manifest["samples"] if entry["data_kind"] == "synthetic"
        )
        experiment = json.loads(
            (SNAPSHOT_DIR / "experiments" / f"{xrd['experiment_id']}.json").read_text(encoding="utf-8")
        )
        self.assertEqual(experiment["demo"]["data_kind"], "synthetic")
        self.assertIn("not a laboratory measurement", experiment["demo"]["label"].lower())
        self.assertIn("SYNTHETIC", json.loads(self.all_text[f"samples/{xrd['id']}.json"])["notes"])

    def test_no_saturation_claims_or_curie_temperature(self) -> None:
        for rel, text in self.all_text.items():
            if rel.startswith("materials"):
                continue
            self.assertNotRegex(text, r"\bTc\b|Curie temperature", rel)
        copilot = json.loads(self.all_text["copilot.json"])
        for reply in copilot["replies"].values():
            self.assertFalse(reply["llmAvailable"])
            self.assertEqual(reply["source"], "stored-records")


if __name__ == "__main__":
    unittest.main()
