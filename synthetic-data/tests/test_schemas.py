import unittest
import tomllib
from pathlib import Path

from opsnexus_synthetic import SCHEMA_VERSION
from opsnexus_synthetic.schemas import SCHEMAS, schema_document


class SchemaTests(unittest.TestCase):
    def test_all_expected_tables_have_versioned_unique_keys(self):
        expected = {
            "data_sources", "pipeline_definitions", "pipeline_runs", "datasets", "dataset_observations",
            "quality_checks", "quality_results", "dependencies", "business_kpis",
            "incident_history", "scenario_metadata",
        }
        self.assertEqual(set(SCHEMAS), expected)
        for schema in SCHEMAS.values():
            names = [field.name for field in schema.fields]
            self.assertEqual(len(names), len(set(names)))
            self.assertIn(schema.primary_key, names)
            self.assertEqual(schema.schema_version, SCHEMA_VERSION)

    def test_manifest_schema_document_is_json_serializable(self):
        import json
        document = schema_document()
        self.assertEqual(set(document), set(SCHEMAS))
        self.assertEqual(json.loads(json.dumps(document)), document)

    def test_standard_project_metadata_matches_source_package(self):
        project_file = Path(__file__).parents[1] / "pyproject.toml"
        with project_file.open("rb") as stream:
            project = tomllib.load(stream)
        metadata = project["project"]
        self.assertEqual(metadata["name"], "opsnexus-synthetic-data")
        self.assertEqual(metadata["version"], "0.2.0")
        self.assertEqual(metadata["requires-python"], ">=3.11")
        self.assertEqual(metadata["dependencies"], [])
        self.assertEqual(project["build-system"]["build-backend"], "setuptools.build_meta")
        self.assertIn("setuptools>=77", project["build-system"]["requires"])
        self.assertEqual(metadata["scripts"]["opsnexus-synthetic"], "opsnexus_synthetic.cli:main")


if __name__ == "__main__":
    unittest.main()
