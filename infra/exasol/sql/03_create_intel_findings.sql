-- Deterministic, evidence-backed Module 1 intelligence.
-- This view reads operational staging data only. Evaluation ground truth is not used.
-- Re-running this script replaces the view definition without deleting staging data.

CREATE OR REPLACE VIEW OPS_INTEL.V_FINDINGS AS
WITH
pipeline_failures AS (
    SELECT
        CAST('pipeline_failure:' || r.RUN_ID AS VARCHAR(200)) AS FINDING_ID,
        CAST(r.SCENARIO_INSTANCE_ID AS VARCHAR(200)) AS SCENARIO_INSTANCE_ID,
        CAST('PIPELINE_FAILURE' AS VARCHAR(100)) AS FINDING_TYPE,
        CAST('HIGH' AS VARCHAR(20)) AS SEVERITY,
        CAST('PIPELINE' AS VARCHAR(100)) AS AFFECTED_ENTITY_TYPE,
        CAST(r.PIPELINE_ID AS VARCHAR(200)) AS AFFECTED_ENTITY_ID,
        CAST(
            'run_id=' || r.RUN_ID || '; status=' || r.STATUS ||
            '; started_at=' || CAST(r.STARTED_AT AS VARCHAR(50)) ||
            '; scenario_instance_id=' || r.SCENARIO_INSTANCE_ID
            AS VARCHAR(2000)
        ) AS EVIDENCE,
        CAST(
            'Inspect the failed pipeline run and its upstream dependencies before retrying.'
            AS VARCHAR(2000)
        ) AS RECOMMENDED_ACTION,
        CAST(r.RUN_ID AS VARCHAR(200)) AS SOURCE_RUN_ID
    FROM OPS_STAGE.STG_PIPELINE_RUNS r
    WHERE UPPER(r.STATUS) = 'FAILED'
),
stale_datasets AS (
    SELECT
        CAST('stale_dataset:' || qr.QUALITY_RESULT_ID AS VARCHAR(200)) AS FINDING_ID,
        CAST(o.SCENARIO_INSTANCE_ID AS VARCHAR(200)) AS SCENARIO_INSTANCE_ID,
        CAST('STALE_DATASET' AS VARCHAR(100)) AS FINDING_TYPE,
        CAST('HIGH' AS VARCHAR(20)) AS SEVERITY,
        CAST('DATASET' AS VARCHAR(100)) AS AFFECTED_ENTITY_TYPE,
        CAST(o.DATASET_ID AS VARCHAR(200)) AS AFFECTED_ENTITY_ID,
        CAST(
            'quality_result_id=' || qr.QUALITY_RESULT_ID ||
            '; check_id=' || qr.QUALITY_CHECK_ID ||
            '; result=' || qr."RESULT" ||
            '; measured_lag_seconds=' || CAST(qr.MEASURED_VALUE AS VARCHAR(50)) ||
            '; expected_lag_seconds=' || CAST(qr.EXPECTED_VALUE AS VARCHAR(50))
            AS VARCHAR(2000)
        ) AS EVIDENCE,
        CAST(
            'Investigate the dataset refresh path and restore freshness within the configured check threshold.'
            AS VARCHAR(2000)
        ) AS RECOMMENDED_ACTION,
        CAST(o.RUN_ID AS VARCHAR(200)) AS SOURCE_RUN_ID
    FROM OPS_STAGE.STG_QUALITY_RESULTS qr
    JOIN OPS_STAGE.STG_QUALITY_CHECKS qc
      ON qc.QUALITY_CHECK_ID = qr.QUALITY_CHECK_ID
    JOIN OPS_STAGE.STG_DATASET_OBSERVATIONS o
      ON o.OBSERVATION_ID = qr.OBSERVATION_ID
    WHERE UPPER(qc.CHECK_TYPE) = 'FRESHNESS'
      AND UPPER(qr."RESULT") = 'FAIL'
),
quality_failures AS (
    SELECT
        CAST('quality_failure:' || qr.QUALITY_RESULT_ID AS VARCHAR(200)) AS FINDING_ID,
        CAST(o.SCENARIO_INSTANCE_ID AS VARCHAR(200)) AS SCENARIO_INSTANCE_ID,
        CAST('QUALITY_FAILURE' AS VARCHAR(100)) AS FINDING_TYPE,
        CAST(
            CASE WHEN UPPER(qc.CHECK_TYPE) IN ('FRESHNESS', 'COMPLETENESS')
                 THEN 'HIGH' ELSE 'MEDIUM' END
            AS VARCHAR(20)
        ) AS SEVERITY,
        CAST('DATASET' AS VARCHAR(100)) AS AFFECTED_ENTITY_TYPE,
        CAST(o.DATASET_ID AS VARCHAR(200)) AS AFFECTED_ENTITY_ID,
        CAST(
            'quality_result_id=' || qr.QUALITY_RESULT_ID ||
            '; check_id=' || qr.QUALITY_CHECK_ID ||
            '; check_type=' || qc.CHECK_TYPE ||
            '; result=' || qr."RESULT" ||
            '; measured_value=' || COALESCE(CAST(qr.MEASURED_VALUE AS VARCHAR(50)), 'NULL') ||
            '; expected_value=' || COALESCE(CAST(qr.EXPECTED_VALUE AS VARCHAR(50)), 'NULL')
            AS VARCHAR(2000)
        ) AS EVIDENCE,
        CAST(
            'Review the failed data-quality check, its source observation, and the upstream load before publishing the dataset.'
            AS VARCHAR(2000)
        ) AS RECOMMENDED_ACTION,
        CAST(o.RUN_ID AS VARCHAR(200)) AS SOURCE_RUN_ID
    FROM OPS_STAGE.STG_QUALITY_RESULTS qr
    JOIN OPS_STAGE.STG_QUALITY_CHECKS qc
      ON qc.QUALITY_CHECK_ID = qr.QUALITY_CHECK_ID
    JOIN OPS_STAGE.STG_DATASET_OBSERVATIONS o
      ON o.OBSERVATION_ID = qr.OBSERVATION_ID
    WHERE UPPER(qr."RESULT") = 'FAIL'
),
kpi_anomalies AS (
    SELECT
        CAST('kpi_anomaly:' || k.KPI_ID AS VARCHAR(200)) AS FINDING_ID,
        CAST(k.SCENARIO_INSTANCE_ID AS VARCHAR(200)) AS SCENARIO_INSTANCE_ID,
        CAST('KPI_ANOMALY' AS VARCHAR(100)) AS FINDING_TYPE,
        CAST(
            CASE WHEN ABS(k.OBSERVED_VALUE - k.BASELINE_VALUE) > ABS(k.BASELINE_VALUE) * 0.5
                 THEN 'HIGH' ELSE 'MEDIUM' END
            AS VARCHAR(20)
        ) AS SEVERITY,
        CAST('KPI' AS VARCHAR(100)) AS AFFECTED_ENTITY_TYPE,
        CAST(k.KPI_ID AS VARCHAR(200)) AS AFFECTED_ENTITY_ID,
        CAST(
            'kpi_name=' || k.KPI_NAME ||
            '; dataset_id=' || k.DATASET_ID ||
            '; baseline_value=' || CAST(k.BASELINE_VALUE AS VARCHAR(50)) ||
            '; observed_value=' || CAST(k.OBSERVED_VALUE AS VARCHAR(50)) ||
            '; relative_deviation=' ||
                CAST(
                    ABS(k.OBSERVED_VALUE - k.BASELINE_VALUE) /
                    NULLIF(ABS(k.BASELINE_VALUE), 0)
                    AS VARCHAR(50)
                ) ||
            '; detection_threshold=' || CAST(qr.EXPECTED_VALUE AS VARCHAR(50)) ||
            '; impact_type=' || k.IMPACT_TYPE
            AS VARCHAR(2000)
        ) AS EVIDENCE,
        CAST(
            'Validate the KPI source and the associated dataset-quality results; treat this synthetic impact link as an investigative signal, not measured business loss.'
            AS VARCHAR(2000)
        ) AS RECOMMENDED_ACTION,
        CAST(o.RUN_ID AS VARCHAR(200)) AS SOURCE_RUN_ID
    FROM OPS_STAGE.STG_BUSINESS_KPIS k
    JOIN OPS_STAGE.STG_DATASET_OBSERVATIONS o
      ON o.OBSERVATION_ID = k.OBSERVATION_ID
    JOIN OPS_STAGE.STG_QUALITY_RESULTS qr
      ON qr.OBSERVATION_ID = k.OBSERVATION_ID
    JOIN OPS_STAGE.STG_QUALITY_CHECKS qc
      ON qc.QUALITY_CHECK_ID = qr.QUALITY_CHECK_ID
    WHERE UPPER(qc.CHECK_TYPE) = 'METRIC_RANGE'
      AND ABS(k.OBSERVED_VALUE - k.BASELINE_VALUE) >
          ABS(k.BASELINE_VALUE) * qr.EXPECTED_VALUE
),
incident_recurrence AS (
    SELECT
        CAST(
            'incident_recurrence:' || i.PIPELINE_ID || ':' || i.INCIDENT_CATEGORY
            AS VARCHAR(200)
        ) AS FINDING_ID,
        CAST(NULL AS VARCHAR(200)) AS SCENARIO_INSTANCE_ID,
        CAST('INCIDENT_RECURRENCE' AS VARCHAR(100)) AS FINDING_TYPE,
        CAST(CASE WHEN COUNT(*) >= 3 THEN 'HIGH' ELSE 'MEDIUM' END AS VARCHAR(20)) AS SEVERITY,
        CAST('PIPELINE' AS VARCHAR(100)) AS AFFECTED_ENTITY_TYPE,
        CAST(i.PIPELINE_ID AS VARCHAR(200)) AS AFFECTED_ENTITY_ID,
        CAST(
            'incident_category=' || i.INCIDENT_CATEGORY ||
            '; incident_count=' || CAST(COUNT(*) AS VARCHAR(50)) ||
            '; scenario_count=' || CAST(COUNT(DISTINCT i.SCENARIO_INSTANCE_ID) AS VARCHAR(50))
            AS VARCHAR(2000)
        ) AS EVIDENCE,
        CAST(
            'Review the recurring incident pattern, identify the common upstream cause, and track a durable remediation.'
            AS VARCHAR(2000)
        ) AS RECOMMENDED_ACTION,
        CAST(NULL AS VARCHAR(200)) AS SOURCE_RUN_ID
    FROM OPS_STAGE.STG_INCIDENT_HISTORY i
    GROUP BY i.PIPELINE_ID, i.INCIDENT_CATEGORY
    HAVING COUNT(*) > 1
)
SELECT FINDING_ID, SCENARIO_INSTANCE_ID, FINDING_TYPE, SEVERITY,
       AFFECTED_ENTITY_TYPE, AFFECTED_ENTITY_ID, EVIDENCE,
       RECOMMENDED_ACTION, SOURCE_RUN_ID
FROM pipeline_failures
UNION ALL
SELECT FINDING_ID, SCENARIO_INSTANCE_ID, FINDING_TYPE, SEVERITY,
       AFFECTED_ENTITY_TYPE, AFFECTED_ENTITY_ID, EVIDENCE,
       RECOMMENDED_ACTION, SOURCE_RUN_ID
FROM stale_datasets
UNION ALL
SELECT FINDING_ID, SCENARIO_INSTANCE_ID, FINDING_TYPE, SEVERITY,
       AFFECTED_ENTITY_TYPE, AFFECTED_ENTITY_ID, EVIDENCE,
       RECOMMENDED_ACTION, SOURCE_RUN_ID
FROM quality_failures
UNION ALL
SELECT FINDING_ID, SCENARIO_INSTANCE_ID, FINDING_TYPE, SEVERITY,
       AFFECTED_ENTITY_TYPE, AFFECTED_ENTITY_ID, EVIDENCE,
       RECOMMENDED_ACTION, SOURCE_RUN_ID
FROM kpi_anomalies
UNION ALL
SELECT FINDING_ID, SCENARIO_INSTANCE_ID, FINDING_TYPE, SEVERITY,
       AFFECTED_ENTITY_TYPE, AFFECTED_ENTITY_ID, EVIDENCE,
       RECOMMENDED_ACTION, SOURCE_RUN_ID
FROM incident_recurrence;
