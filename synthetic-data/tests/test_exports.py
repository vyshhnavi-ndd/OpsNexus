import csv
import json
import tempfile
import unittest
from pathlib import Path

from opsnexus_synthetic.exporter import export_bundle


class ExportTests(unittest.TestCase):
    def test_export_paths_counts_and_ground_truth_separation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "bundle"
            manifest = export_bundle(root, seed=42)
            self.assertEqual(len(manifest["files"]), 11)
            self.assertFalse(manifest["ground_truth"]["ingest"])
            self.assertTrue((root / "ground_truth/expected_outcomes.json").is_file())
            for entry in manifest["files"]:
                path = root / entry["path"]
                self.assertTrue(path.is_file())
                with path.open(encoding="utf-8", newline="") as stream:
                    rows = list(csv.DictReader(stream))
                self.assertEqual(len(rows), entry["row_count"])
            truth = json.loads((root / manifest["ground_truth"]["path"]).read_text(encoding="utf-8"))
            truth_ids = {row["scenario_instance_id"] for row in truth["scenarios"].values()}
            self.assertEqual(set(truth_ids), set(manifest["scenario_instance_ids"]))
            self.assertEqual(manifest["scenario_count"], 8)
            operational_json = json.dumps(manifest).casefold()
            for label in truth["scenarios"]:
                self.assertNotIn(label.casefold(), operational_json)
            for entry in manifest["files"]:
                if entry["path"].endswith(".csv"):
                    operational_csv = (root / entry["path"]).read_text(encoding="utf-8").casefold()
                    for label in truth["scenarios"]:
                        self.assertNotIn(label.casefold(), operational_csv)

    def test_export_is_byte_deterministic_for_same_seed(self):
        with tempfile.TemporaryDirectory() as temp:
            first, second = Path(temp) / "first", Path(temp) / "second"
            export_bundle(first, 77)
            export_bundle(second, 77)
            files1 = sorted(p.relative_to(first).as_posix() for p in first.rglob("*") if p.is_file())
            files2 = sorted(p.relative_to(second).as_posix() for p in second.rglob("*") if p.is_file())
            self.assertEqual(files1, files2)
            for relative in files1:
                self.assertEqual((first / relative).read_bytes(), (second / relative).read_bytes())


if __name__ == "__main__":
    unittest.main()
