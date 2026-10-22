import csv
import tempfile
import unittest
from pathlib import Path

from opsnexus_synthetic.exporter import export_bundle
from opsnexus_synthetic.validation import validate_bundle


class ValidationTests(unittest.TestCase):
    def test_generated_bundle_passes_and_writes_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "bundle"
            export_bundle(root, 314)
            report = validate_bundle(root)
            self.assertTrue(report["valid"], report["errors"])
            self.assertEqual(report["error_count"], 0)
            self.assertTrue((root / "validation-report.json").is_file())

    def test_bad_foreign_key_fails_with_actionable_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "bundle"
            export_bundle(root, 315)
            path = root / "data/pipeline_runs.csv"
            with path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
                fields = list(rows[0])
            rows[0]["pipeline_id"] = "pl_unknown"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            report = validate_bundle(root)
            self.assertFalse(report["valid"])
            self.assertTrue(any(error.startswith("INVALID_REFERENCE: pipeline_runs.pipeline_id") for error in report["errors"]))
            self.assertEqual(report["error_count"], len(report["errors"]))

    def test_quality_measurement_must_match_observation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "bundle"
            export_bundle(root, 316)
            path = root / "data/quality_results.csv"
            with path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
                fields = list(rows[0])
            rows[0]["measured_value"] = "999"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            report = validate_bundle(root)
            self.assertFalse(report["valid"])
            self.assertTrue(any(error.startswith(("QUALITY_MEASUREMENT_MISMATCH:", "QUALITY_RESULT_MISMATCH:")) for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
