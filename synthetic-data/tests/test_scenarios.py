import json
import unittest

from opsnexus_synthetic.generator import generate
from opsnexus_synthetic.scenarios import EXPECTED_OUTCOMES, SCENARIO_IDS
from opsnexus_synthetic.schemas import SCHEMAS


class ScenarioGenerationTests(unittest.TestCase):
    def test_all_eight_scenarios_have_correlated_opaque_instances(self):
        tables, truth = generate(23)
        metadata_ids = {row["scenario_instance_id"] for row in tables["scenario_metadata"]}
        truth_ids = {row["scenario_instance_id"] for row in truth["scenarios"].values()}
        self.assertEqual(set(truth["scenarios"]), set(SCENARIO_IDS))
        self.assertEqual(metadata_ids, truth_ids)
        self.assertEqual(len(metadata_ids), 8)
        self.assertTrue(all(case_id.startswith("case_") for case_id in metadata_ids))

    def test_seed_repeats_exactly_and_changes_fixture_values(self):
        first, first_truth = generate(1234)
        repeat, repeat_truth = generate(1234)
        different, _ = generate(1235)
        self.assertEqual(first, repeat)
        self.assertEqual(first_truth, repeat_truth)
        self.assertNotEqual(first["pipeline_runs"], different["pipeline_runs"])

    def test_labels_and_expected_outcomes_are_not_operational_evidence(self):
        tables, truth = generate(10)
        operational_text = json.dumps(tables, sort_keys=True).casefold()
        for scenario_id in SCENARIO_IDS:
            self.assertNotIn(scenario_id.casefold(), operational_text)
        for outcome in EXPECTED_OUTCOMES.values():
            cause = outcome["expected_cause_category"]
            if cause is not None:
                self.assertNotIn(str(cause).casefold(), operational_text)
        for expected in truth["scenarios"].values():
            for key in ("scenario_type", "expected_trust_band", "expected_investigation_disposition", "expected_cause_category"):
                value = expected.get(key)
                if value is not None:
                    self.assertNotIn(str(value).casefold(), operational_text)
        operational_fields = {
            field.name
            for table_schema in SCHEMAS.values()
            for field in table_schema.fields
        }
        truth_only_fields = {
            "expected_trust_band", "expected_investigation_disposition",
            "expected_cause_category", "expected_recovery_status", "rationale",
        }
        self.assertFalse(truth_only_fields & operational_fields)
        self.assertEqual(truth["data_classification"], "SYNTHETIC_GROUND_TRUTH_NOT_OPERATIONAL_EVIDENCE")
        self.assertEqual(set(truth["scenarios"]), set(SCENARIO_IDS))

    def test_each_scenario_has_its_expected_observed_facts(self):
        tables, truth = generate(20261014)
        token = {name: data["scenario_instance_id"] for name, data in truth["scenarios"].items()}
        runs_by_case = {
            case_id: [row for row in tables["pipeline_runs"] if row["scenario_instance_id"] == instance_id]
            for case_id, instance_id in token.items()
        }
        observations_by_case = {
            case_id: [row for row in tables["dataset_observations"] if row["scenario_instance_id"] == instance_id]
            for case_id, instance_id in token.items()
        }

        healthy_obs = {row["observation_id"] for row in observations_by_case["healthy_baseline"]}
        self.assertEqual(len(healthy_obs), 3)
        self.assertTrue(all(run["status"] == "SUCCEEDED" for run in runs_by_case["healthy_baseline"]))
        self.assertTrue(all(
            result["result"] == "PASS" for result in tables["quality_results"]
            if result["observation_id"] in healthy_obs
        ))
        self.assertEqual(sum(result["observation_id"] in healthy_obs for result in tables["quality_results"]), 9)

        failure_statuses = {row["status"] for row in runs_by_case["pipeline_failure"]}
        self.assertIn("FAILED", failure_statuses)
        self.assertIn("SKIPPED", failure_statuses)
        failed_run = next(row for row in runs_by_case["pipeline_failure"] if row["status"] == "FAILED")
        required_dependents = {
            edge["downstream_pipeline_id"] for edge in tables["dependencies"]
            if edge["upstream_pipeline_id"] == failed_run["pipeline_id"]
        }
        self.assertTrue(required_dependents)
        self.assertTrue(all(
            any(run["pipeline_id"] == downstream_id and run["status"] == "SKIPPED"
                for run in runs_by_case["pipeline_failure"])
            for downstream_id in required_dependents
        ))
        self.assertFalse(any(row["dataset_id"] == "ds_orders" for row in observations_by_case["pipeline_failure"]))

        stale_orders = next(row for row in observations_by_case["stale_data"] if row["dataset_id"] == "ds_orders")
        self.assertGreater(stale_orders["freshness_lag_seconds"], 3600)
        self.assertTrue(any(result["observation_id"] == stale_orders["observation_id"] and result["result"] == "FAIL"
                            for result in tables["quality_results"]))

        incomplete_orders = next(row for row in observations_by_case["incomplete_data"] if row["dataset_id"] == "ds_orders")
        self.assertEqual((incomplete_orders["row_count"], incomplete_orders["expected_row_count"]), (800, 1000))
        self.assertLess(incomplete_orders["completeness_ratio"], 0.95)

        anomaly_orders = next(row for row in observations_by_case["metric_anomaly"] if row["dataset_id"] == "ds_orders")
        self.assertEqual(anomaly_orders["metric_value"], 150.0)
        self.assertTrue(any(result["observation_id"] == anomaly_orders["observation_id"] and result["result"] == "FAIL"
                            for result in tables["quality_results"]))

        cross_domain = {row["dataset_id"]: row["metric_value"] for row in observations_by_case["cross_domain_inconsistency"]}
        self.assertEqual(cross_domain["ds_orders"], 100.0)
        self.assertEqual(cross_domain["ds_finance"], 82.0)
        self.assertNotEqual(cross_domain["ds_orders"], cross_domain["ds_finance"])

        recurring_orders = next(row for row in observations_by_case["recurring_incident"] if row["dataset_id"] == "ds_orders")
        self.assertGreater(recurring_orders["freshness_lag_seconds"], 3600)
        prior = next(row for row in tables["incident_history"]
                     if row["scenario_instance_id"] == token["recurring_incident"])
        self.assertEqual(prior["incident_category"], "FRESHNESS_DELAY")
        self.assertEqual(prior["resolution_status"], "CLOSED")

        inconclusive = truth["scenarios"]["inconclusive"]
        inconclusive_orders = next(row for row in observations_by_case["inconclusive"] if row["dataset_id"] == "ds_orders")
        inconclusive_finance = next(row for row in observations_by_case["inconclusive"] if row["dataset_id"] == "ds_finance")
        self.assertGreater(inconclusive_orders["freshness_lag_seconds"], 3600)
        self.assertLess(inconclusive_finance["completeness_ratio"], 0.95)
        self.assertEqual(inconclusive["expected_investigation_disposition"], "INCONCLUSIVE")

        expected_contract = {
            "healthy_baseline": ("HIGH", "HEALTHY_NO_ACTION", None),
            "pipeline_failure": ("LOW", "ACTIONABLE_CANDIDATE", "UPSTREAM_PIPELINE_FAILURE"),
            "stale_data": ("LOW", "ACTIONABLE_CANDIDATE", "STALE_DATA"),
            "incomplete_data": ("LOW", "ACTIONABLE_CANDIDATE", "INCOMPLETE_DATA"),
            "metric_anomaly": ("MEDIUM", "AMBIGUOUS", "METRIC_ANOMALY"),
            "cross_domain_inconsistency": ("LOW", "AMBIGUOUS", "CROSS_DOMAIN_INCONSISTENCY"),
            "recurring_incident": ("MEDIUM", "AMBIGUOUS", "RECURRING_PATTERN"),
            "inconclusive": ("UNKNOWN", "INCONCLUSIVE", None),
        }
        for scenario_id, (trust, disposition, cause) in expected_contract.items():
            outcome = truth["scenarios"][scenario_id]
            self.assertEqual(outcome["expected_trust_band"], trust)
            self.assertEqual(outcome["expected_investigation_disposition"], disposition)
            self.assertEqual(outcome["expected_cause_category"], cause)
            self.assertEqual(outcome["expected_cause_category"], EXPECTED_OUTCOMES[scenario_id]["expected_cause_category"])
            self.assertIsNone(outcome["expected_recovery_status"])


if __name__ == "__main__":
    unittest.main()
