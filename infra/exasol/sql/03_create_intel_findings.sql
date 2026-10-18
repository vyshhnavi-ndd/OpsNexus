-- Deterministic Module 1 intelligence over operational staging data only.
-- Re-running replaces only the view definition; no staging or runtime data is changed.
-- Ground truth is an offline evaluation input and is never referenced here.

CREATE OR REPLACE VIEW OPS_INTEL.V_FINDINGS AS
WITH
-- Collapse dependency/run context before joining it to findings. This avoids
-- multiplying one failed run by its dependency fan-out.
downstream_context AS (
    SELECT
        d.UPSTREAM_PIPELINE_ID,
        r.SCENARIO_INSTANCE_ID,
        LISTAGG(d.DEPENDENCY_ID || ':' || d.DOWNSTREAM_PIPELINE_ID || ':' ||
                COALESCE(UPPER(r.STATUS), 'NO_RUN'), ', ')
            WITHIN GROUP (ORDER BY d.DEPENDENCY_ID, d.DOWNSTREAM_PIPELINE_ID) AS CONTEXT_TEXT,
        LISTAGG(COALESCE(r.RUN_ID, 'NO_RUN'), ', ')
            WITHIN GROUP (ORDER BY d.DEPENDENCY_ID, d.DOWNSTREAM_PIPELINE_ID) AS SOURCE_RUNS
    FROM OPS_STAGE.STG_DEPENDENCIES d
    LEFT JOIN OPS_STAGE.STG_PIPELINE_RUNS r
      ON r.PIPELINE_ID = d.DOWNSTREAM_PIPELINE_ID
    GROUP BY d.UPSTREAM_PIPELINE_ID, r.SCENARIO_INSTANCE_ID
),
upstream_context AS (
    SELECT
        d.DOWNSTREAM_PIPELINE_ID,
        r.SCENARIO_INSTANCE_ID,
        LISTAGG(d.DEPENDENCY_ID || ':' || d.UPSTREAM_PIPELINE_ID || ':' ||
                COALESCE(UPPER(r.STATUS), 'NO_RUN'), ', ')
            WITHIN GROUP (ORDER BY d.DEPENDENCY_ID, d.UPSTREAM_PIPELINE_ID) AS CONTEXT_TEXT,
        LISTAGG(COALESCE(r.RUN_ID, 'NO_RUN'), ', ')
            WITHIN GROUP (ORDER BY d.DEPENDENCY_ID, d.UPSTREAM_PIPELINE_ID) AS SOURCE_RUNS
    FROM OPS_STAGE.STG_DEPENDENCIES d
    LEFT JOIN OPS_STAGE.STG_PIPELINE_RUNS r
      ON r.PIPELINE_ID = d.UPSTREAM_PIPELINE_ID
    GROUP BY d.DOWNSTREAM_PIPELINE_ID, r.SCENARIO_INSTANCE_ID
),
pipeline_failures AS (
    SELECT
        CAST('pipeline_failure:' || r.RUN_ID AS VARCHAR(200)) AS FINDING_ID,
        CAST(r.SCENARIO_INSTANCE_ID AS VARCHAR(200)) AS SCENARIO_INSTANCE_ID,
        CAST('PIPELINE_FAILURE' AS VARCHAR(100)) AS FINDING_TYPE,
        CAST('HIGH' AS VARCHAR(20)) AS SEVERITY,
        CAST('PIPELINE' AS VARCHAR(100)) AS AFFECTED_ENTITY_TYPE,
        CAST(r.PIPELINE_ID AS VARCHAR(200)) AS AFFECTED_ENTITY_ID,
        CAST('run_id=' || r.RUN_ID || '; measured_status=' || UPPER(r.STATUS) ||
             '; expected_status=SUCCEEDED; started_at=' || CAST(r.STARTED_AT AS VARCHAR(50)) ||
             '; upstream_dependency_context=' || COALESCE(uc.CONTEXT_TEXT, 'none') ||
             '; downstream_dependency_context=' || COALESCE(dc.CONTEXT_TEXT, 'none')
             AS VARCHAR(2000)) AS EVIDENCE,
        CAST('Inspect this failed run and its dependent pipeline statuses; repair the upstream cause before retrying downstream work.'
             AS VARCHAR(2000)) AS RECOMMENDED_ACTION,
        CAST(r.RUN_ID AS VARCHAR(200)) AS SOURCE_RUN_ID,
        CAST('run_id=' || r.RUN_ID || COALESCE('; upstream_runs=' || uc.SOURCE_RUNS, '') ||
             COALESCE('; dependent_runs=' || dc.SOURCE_RUNS, '') AS VARCHAR(4000)) AS SOURCE_REFERENCES,
        CAST(UPPER(r.STATUS) AS VARCHAR(2000)) AS MEASURED_VALUE,
        CAST('SUCCEEDED' AS VARCHAR(2000)) AS EXPECTED_VALUE,
        CAST(NULL AS VARCHAR(2000)) AS THRESHOLD_VALUE
    FROM OPS_STAGE.STG_PIPELINE_RUNS r
    LEFT JOIN downstream_context dc
      ON dc.UPSTREAM_PIPELINE_ID = r.PIPELINE_ID
     AND dc.SCENARIO_INSTANCE_ID = r.SCENARIO_INSTANCE_ID
    LEFT JOIN upstream_context uc
      ON uc.DOWNSTREAM_PIPELINE_ID = r.PIPELINE_ID
     AND uc.SCENARIO_INSTANCE_ID = r.SCENARIO_INSTANCE_ID
    WHERE UPPER(r.STATUS) = 'FAILED'
),
freshness_results AS (
    SELECT
        qr.QUALITY_RESULT_ID,
        qr.QUALITY_CHECK_ID,
        qr.OBSERVATION_ID,
        qr.MEASURED_VALUE,
        qr.EXPECTED_VALUE,
        ROW_NUMBER() OVER (
            PARTITION BY qr.OBSERVATION_ID
            ORDER BY qr.EXPECTED_VALUE ASC, qr.QUALITY_RESULT_ID
        ) AS RN
    FROM OPS_STAGE.STG_QUALITY_RESULTS qr
    JOIN OPS_STAGE.STG_QUALITY_CHECKS qc
      ON qc.QUALITY_CHECK_ID = qr.QUALITY_CHECK_ID
    WHERE UPPER(qc.CHECK_TYPE) = 'FRESHNESS'
      AND qr.EXPECTED_VALUE IS NOT NULL
),
stale_datasets AS (
    SELECT
        CAST('stale_dataset:' || fr.QUALITY_RESULT_ID AS VARCHAR(200)) AS FINDING_ID,
        CAST(o.SCENARIO_INSTANCE_ID AS VARCHAR(200)) AS SCENARIO_INSTANCE_ID,
        CAST('STALE_DATASET' AS VARCHAR(100)) AS FINDING_TYPE,
        CAST('HIGH' AS VARCHAR(20)) AS SEVERITY,
        CAST('DATASET' AS VARCHAR(100)) AS AFFECTED_ENTITY_TYPE,
        CAST(o.DATASET_ID AS VARCHAR(200)) AS AFFECTED_ENTITY_ID,
        CAST('observation_id=' || o.OBSERVATION_ID || '; run_id=' || o.RUN_ID ||
             '; measured_freshness_lag_seconds=' || CAST(o.FRESHNESS_LAG_SECONDS AS VARCHAR(50)) ||
             '; expected_max_lag_seconds=' || CAST(fr.EXPECTED_VALUE AS VARCHAR(50)) ||
             '; quality_result=' || COALESCE(UPPER(qr."RESULT"), 'NULL')
             AS VARCHAR(2000)) AS EVIDENCE,
        CAST('Investigate the dataset refresh path and restore freshness within its configured quality threshold.'
             AS VARCHAR(2000)) AS RECOMMENDED_ACTION,
        CAST(o.RUN_ID AS VARCHAR(200)) AS SOURCE_RUN_ID,
        CAST('observation_id=' || o.OBSERVATION_ID || '; quality_result_id=' || fr.QUALITY_RESULT_ID AS VARCHAR(4000)) AS SOURCE_REFERENCES,
        CAST(o.FRESHNESS_LAG_SECONDS AS VARCHAR(2000)) AS MEASURED_VALUE,
        CAST(fr.EXPECTED_VALUE AS VARCHAR(2000)) AS EXPECTED_VALUE,
        CAST(fr.EXPECTED_VALUE AS VARCHAR(2000)) AS THRESHOLD_VALUE
    FROM freshness_results fr
    JOIN OPS_STAGE.STG_DATASET_OBSERVATIONS o
      ON o.OBSERVATION_ID = fr.OBSERVATION_ID
    LEFT JOIN OPS_STAGE.STG_QUALITY_RESULTS qr
      ON qr.QUALITY_RESULT_ID = fr.QUALITY_RESULT_ID
    WHERE fr.RN = 1
      AND (UPPER(qr."RESULT") = 'FAIL' OR o.FRESHNESS_LAG_SECONDS > fr.EXPECTED_VALUE)
),
completeness_results AS (
    SELECT
        qr.QUALITY_RESULT_ID,
        qr.OBSERVATION_ID,
        qr.MEASURED_VALUE,
        qr.EXPECTED_VALUE,
        ROW_NUMBER() OVER (
            PARTITION BY qr.OBSERVATION_ID
            ORDER BY qr.EXPECTED_VALUE ASC, qr.QUALITY_RESULT_ID
        ) AS RN
    FROM OPS_STAGE.STG_QUALITY_RESULTS qr
    JOIN OPS_STAGE.STG_QUALITY_CHECKS qc
      ON qc.QUALITY_CHECK_ID = qr.QUALITY_CHECK_ID
    WHERE UPPER(qc.CHECK_TYPE) = 'COMPLETENESS'
      AND qr.EXPECTED_VALUE IS NOT NULL
),
incomplete_datasets AS (
    SELECT
        CAST('incomplete_data:' || cr.QUALITY_RESULT_ID AS VARCHAR(200)) AS FINDING_ID,
        CAST(o.SCENARIO_INSTANCE_ID AS VARCHAR(200)) AS SCENARIO_INSTANCE_ID,
        CAST('INCOMPLETE_DATA' AS VARCHAR(100)) AS FINDING_TYPE,
        CAST('HIGH' AS VARCHAR(20)) AS SEVERITY,
        CAST('DATASET' AS VARCHAR(100)) AS AFFECTED_ENTITY_TYPE,
        CAST(o.DATASET_ID AS VARCHAR(200)) AS AFFECTED_ENTITY_ID,
        CAST('observation_id=' || o.OBSERVATION_ID || '; run_id=' || o.RUN_ID ||
             '; measured_row_count=' || CAST(o.ROW_COUNT AS VARCHAR(50)) ||
             '; expected_row_count=' || CAST(o.EXPECTED_ROW_COUNT AS VARCHAR(50)) ||
             '; measured_completeness_ratio=' || CAST(o.COMPLETENESS_RATIO AS VARCHAR(50)) ||
             '; configured_min_ratio=' || CAST(cr.EXPECTED_VALUE AS VARCHAR(50))
             AS VARCHAR(2000)) AS EVIDENCE,
        CAST('Trace the incomplete load and reconcile observed rows with the expected count before publishing the dataset.'
             AS VARCHAR(2000)) AS RECOMMENDED_ACTION,
        CAST(o.RUN_ID AS VARCHAR(200)) AS SOURCE_RUN_ID,
        CAST('observation_id=' || o.OBSERVATION_ID || '; quality_result_id=' || cr.QUALITY_RESULT_ID AS VARCHAR(4000)) AS SOURCE_REFERENCES,
        CAST(o.COMPLETENESS_RATIO AS VARCHAR(2000)) AS MEASURED_VALUE,
        CAST(cr.EXPECTED_VALUE AS VARCHAR(2000)) AS EXPECTED_VALUE,
        CAST(cr.EXPECTED_VALUE AS VARCHAR(2000)) AS THRESHOLD_VALUE
    FROM completeness_results cr
    JOIN OPS_STAGE.STG_DATASET_OBSERVATIONS o
      ON o.OBSERVATION_ID = cr.OBSERVATION_ID
    WHERE cr.RN = 1
      AND o.EXPECTED_ROW_COUNT > 0
      AND o.ROW_COUNT < o.EXPECTED_ROW_COUNT
      AND COALESCE(o.COMPLETENESS_RATIO, cr.MEASURED_VALUE) < cr.EXPECTED_VALUE
),
quality_failures AS (
    SELECT
        CAST('quality_failure:' || qr.QUALITY_RESULT_ID AS VARCHAR(200)) AS FINDING_ID,
        CAST(o.SCENARIO_INSTANCE_ID AS VARCHAR(200)) AS SCENARIO_INSTANCE_ID,
        CAST('QUALITY_FAILURE' AS VARCHAR(100)) AS FINDING_TYPE,
        CAST(CASE WHEN UPPER(qc.CHECK_TYPE) IN ('FRESHNESS', 'COMPLETENESS') THEN 'HIGH' ELSE 'MEDIUM' END AS VARCHAR(20)) AS SEVERITY,
        CAST('DATASET' AS VARCHAR(100)) AS AFFECTED_ENTITY_TYPE,
        CAST(o.DATASET_ID AS VARCHAR(200)) AS AFFECTED_ENTITY_ID,
        CAST('quality_result_id=' || qr.QUALITY_RESULT_ID || '; observation_id=' || o.OBSERVATION_ID ||
             '; run_id=' || o.RUN_ID || '; check_type=' || qc.CHECK_TYPE ||
             '; measured_value=' || COALESCE(CAST(qr.MEASURED_VALUE AS VARCHAR(50)), 'NULL') ||
             '; expected_value=' || COALESCE(CAST(qr.EXPECTED_VALUE AS VARCHAR(50)), 'NULL') ||
             '; configured_threshold=' || qc.THRESHOLD_JSON
             AS VARCHAR(2000)) AS EVIDENCE,
        CAST('Review the failed configured data-quality check and its source observation before publishing the dataset.'
             AS VARCHAR(2000)) AS RECOMMENDED_ACTION,
        CAST(o.RUN_ID AS VARCHAR(200)) AS SOURCE_RUN_ID,
        CAST('quality_result_id=' || qr.QUALITY_RESULT_ID || '; quality_check_id=' || qr.QUALITY_CHECK_ID ||
             '; observation_id=' || o.OBSERVATION_ID AS VARCHAR(4000)) AS SOURCE_REFERENCES,
        CAST(qr.MEASURED_VALUE AS VARCHAR(2000)) AS MEASURED_VALUE,
        CAST(qr.EXPECTED_VALUE AS VARCHAR(2000)) AS EXPECTED_VALUE,
        CAST(qr.EXPECTED_VALUE AS VARCHAR(2000)) AS THRESHOLD_VALUE
    FROM OPS_STAGE.STG_QUALITY_RESULTS qr
    JOIN OPS_STAGE.STG_QUALITY_CHECKS qc
      ON qc.QUALITY_CHECK_ID = qr.QUALITY_CHECK_ID
    JOIN OPS_STAGE.STG_DATASET_OBSERVATIONS o
      ON o.OBSERVATION_ID = qr.OBSERVATION_ID
    WHERE UPPER(qr."RESULT") = 'FAIL'
),
metric_range_results AS (
    -- If duplicate range checks exist for an observation, use the strictest
    -- configured limit and a stable result ID as the deterministic tie-break.
    SELECT
        qr.QUALITY_RESULT_ID,
        qr.OBSERVATION_ID,
        qr.EXPECTED_VALUE,
        ROW_NUMBER() OVER (
            PARTITION BY qr.OBSERVATION_ID
            ORDER BY qr.EXPECTED_VALUE ASC, qr.QUALITY_RESULT_ID
        ) AS RN
    FROM OPS_STAGE.STG_QUALITY_RESULTS qr
    JOIN OPS_STAGE.STG_QUALITY_CHECKS qc
      ON qc.QUALITY_CHECK_ID = qr.QUALITY_CHECK_ID
    WHERE UPPER(qc.CHECK_TYPE) = 'METRIC_RANGE'
      AND qr.EXPECTED_VALUE IS NOT NULL
),
kpi_anomalies AS (
    SELECT
        CAST('kpi_anomaly:' || k.KPI_ID AS VARCHAR(200)) AS FINDING_ID,
        CAST(k.SCENARIO_INSTANCE_ID AS VARCHAR(200)) AS SCENARIO_INSTANCE_ID,
        CAST('KPI_ANOMALY' AS VARCHAR(100)) AS FINDING_TYPE,
        CAST('MEDIUM' AS VARCHAR(20)) AS SEVERITY,
        CAST('KPI' AS VARCHAR(100)) AS AFFECTED_ENTITY_TYPE,
        CAST(k.KPI_ID AS VARCHAR(200)) AS AFFECTED_ENTITY_ID,
        CAST('kpi_id=' || k.KPI_ID || '; observation_id=' || o.OBSERVATION_ID ||
             '; dataset_id=' || k.DATASET_ID || '; metric=' || o.METRIC_NAME ||
             '; measured_relative_deviation=' || CAST(ABS(k.OBSERVED_VALUE - k.BASELINE_VALUE) / NULLIF(ABS(k.BASELINE_VALUE), 0) AS VARCHAR(50)) ||
             '; baseline_value=' || CAST(k.BASELINE_VALUE AS VARCHAR(50)) ||
             '; observed_value=' || CAST(k.OBSERVED_VALUE AS VARCHAR(50)) ||
             '; configured_max_relative_deviation=' || CAST(mrr.EXPECTED_VALUE AS VARCHAR(50)) ||
             '; impact_type=' || k.IMPACT_TYPE ||
             CASE WHEN UPPER(k.IMPACT_TYPE) LIKE '%SYNTHETIC%' THEN '; impact_is_illustrative=true' ELSE '' END
             AS VARCHAR(2000)) AS EVIDENCE,
        CAST('Validate the metric definition and its source observation; any synthetic KPI impact is illustrative and is not measured business loss.'
             AS VARCHAR(2000)) AS RECOMMENDED_ACTION,
        CAST(o.RUN_ID AS VARCHAR(200)) AS SOURCE_RUN_ID,
        CAST('kpi_id=' || k.KPI_ID || '; observation_id=' || o.OBSERVATION_ID ||
             '; quality_result_id=' || mrr.QUALITY_RESULT_ID AS VARCHAR(4000)) AS SOURCE_REFERENCES,
        CAST(ABS(k.OBSERVED_VALUE - k.BASELINE_VALUE) / NULLIF(ABS(k.BASELINE_VALUE), 0) AS VARCHAR(2000)) AS MEASURED_VALUE,
        CAST(mrr.EXPECTED_VALUE AS VARCHAR(2000)) AS EXPECTED_VALUE,
        CAST(mrr.EXPECTED_VALUE AS VARCHAR(2000)) AS THRESHOLD_VALUE
    FROM OPS_STAGE.STG_BUSINESS_KPIS k
    JOIN OPS_STAGE.STG_DATASET_OBSERVATIONS o
      ON o.OBSERVATION_ID = k.OBSERVATION_ID
     AND o.DATASET_ID = k.DATASET_ID
     AND o.SCENARIO_INSTANCE_ID = k.SCENARIO_INSTANCE_ID
    JOIN metric_range_results mrr
      ON mrr.OBSERVATION_ID = k.OBSERVATION_ID
     AND mrr.RN = 1
    WHERE k.BASELINE_VALUE IS NOT NULL
      AND k.OBSERVED_VALUE IS NOT NULL
      AND k.BASELINE_VALUE <> 0
      AND ABS(k.OBSERVED_VALUE - k.BASELINE_VALUE) > ABS(k.BASELINE_VALUE) * mrr.EXPECTED_VALUE
),
KPI_OBSERVATION_REFS AS (
    SELECT OBSERVATION_ID, MIN(KPI_ID) AS KPI_ID
    FROM OPS_STAGE.STG_BUSINESS_KPIS
    GROUP BY OBSERVATION_ID
),
ranked_domain_observations AS (
    SELECT
        o.SCENARIO_INSTANCE_ID,
        o.OBSERVATION_ID,
        o.RUN_ID,
        o.DATASET_ID,
        ds."DOMAIN" AS DATA_DOMAIN,
        o.METRIC_NAME,
        o.METRIC_VALUE,
        r.PIPELINE_ID,
        kr.KPI_ID,
        ROW_NUMBER() OVER (
            PARTITION BY o.SCENARIO_INSTANCE_ID, o.DATASET_ID
            ORDER BY o.OBSERVED_AT DESC, o.OBSERVATION_ID DESC
        ) AS OBSERVATION_RN
    FROM OPS_STAGE.STG_DATASET_OBSERVATIONS o
    JOIN OPS_STAGE.STG_PIPELINE_RUNS r
      ON r.RUN_ID = o.RUN_ID AND UPPER(r.STATUS) = 'SUCCEEDED'
    JOIN OPS_STAGE.STG_DATASETS ds
      ON ds.DATASET_ID = o.DATASET_ID
    JOIN KPI_OBSERVATION_REFS kr
      ON kr.OBSERVATION_ID = o.OBSERVATION_ID
),
eligible_domain_observations AS (
    SELECT * FROM ranked_domain_observations WHERE OBSERVATION_RN = 1
),
related_domain_pairs AS (
    SELECT
        o1.SCENARIO_INSTANCE_ID,
        o1.OBSERVATION_ID AS OBSERVATION_ID_1,
        o2.OBSERVATION_ID AS OBSERVATION_ID_2,
        o1.RUN_ID AS RUN_ID_1,
        o2.RUN_ID AS RUN_ID_2,
        o1.DATASET_ID AS DATASET_ID_1,
        o2.DATASET_ID AS DATASET_ID_2,
        o1.DATA_DOMAIN AS DOMAIN_1,
        o2.DATA_DOMAIN AS DOMAIN_2,
        o1.METRIC_NAME,
        o1.METRIC_VALUE AS METRIC_VALUE_1,
        o2.METRIC_VALUE AS METRIC_VALUE_2,
        o1.KPI_ID AS KPI_ID_1,
        o2.KPI_ID AS KPI_ID_2,
        dep1.DEPENDENCY_ID AS DEPENDENCY_ID_1,
        dep2.DEPENDENCY_ID AS DEPENDENCY_ID_2,
        ABS(o1.METRIC_VALUE - o2.METRIC_VALUE) /
            NULLIF(GREATEST(ABS(o1.METRIC_VALUE), ABS(o2.METRIC_VALUE)), 0) AS RELATIVE_GAP,
        ROW_NUMBER() OVER (
            PARTITION BY o1.SCENARIO_INSTANCE_ID, o1.DATASET_ID, o2.DATASET_ID
            ORDER BY dep1.DEPENDENCY_ID, dep2.DEPENDENCY_ID
        ) AS PAIR_RN
    FROM eligible_domain_observations o1
    JOIN OPS_STAGE.STG_DEPENDENCIES dep1
      ON dep1.UPSTREAM_PIPELINE_ID = o1.PIPELINE_ID
    JOIN OPS_STAGE.STG_DEPENDENCIES dep2
      ON dep2.DOWNSTREAM_PIPELINE_ID = dep1.DOWNSTREAM_PIPELINE_ID
     AND dep2.UPSTREAM_PIPELINE_ID <> dep1.UPSTREAM_PIPELINE_ID
    JOIN eligible_domain_observations o2
      ON o2.PIPELINE_ID = dep2.UPSTREAM_PIPELINE_ID
     AND o2.SCENARIO_INSTANCE_ID = o1.SCENARIO_INSTANCE_ID
     AND o2.METRIC_NAME = o1.METRIC_NAME
     AND o2.DATASET_ID > o1.DATASET_ID
     AND UPPER(o2.DATA_DOMAIN) <> UPPER(o1.DATA_DOMAIN)
    WHERE o1.METRIC_VALUE IS NOT NULL
      AND o2.METRIC_VALUE IS NOT NULL
),
cross_domain_inconsistencies AS (
    SELECT
        CAST('cross_domain_inconsistency:' || p.SCENARIO_INSTANCE_ID || ':' || p.DATASET_ID_1 || ':' || p.DATASET_ID_2 AS VARCHAR(200)) AS FINDING_ID,
        CAST(p.SCENARIO_INSTANCE_ID AS VARCHAR(200)) AS SCENARIO_INSTANCE_ID,
        CAST('CROSS_DOMAIN_INCONSISTENCY' AS VARCHAR(100)) AS FINDING_TYPE,
        CAST('MEDIUM' AS VARCHAR(20)) AS SEVERITY,
        CAST('DATASET_PAIR' AS VARCHAR(100)) AS AFFECTED_ENTITY_TYPE,
        CAST(p.DATASET_ID_1 || '|' || p.DATASET_ID_2 AS VARCHAR(200)) AS AFFECTED_ENTITY_ID,
        CAST('metric=' || p.METRIC_NAME || '; dataset_1=' || p.DATASET_ID_1 || '(' || p.DOMAIN_1 ||
             ') measured=' || CAST(p.METRIC_VALUE_1 AS VARCHAR(50)) ||
             '; dataset_2=' || p.DATASET_ID_2 || '(' || p.DOMAIN_2 ||
             ') measured=' || CAST(p.METRIC_VALUE_2 AS VARCHAR(50)) ||
             '; measured_relative_gap=' || CAST(p.RELATIVE_GAP AS VARCHAR(50)) ||
             '; proposed_max_relative_gap=0.10; related_by_shared_downstream_dependencies=true'
             AS VARCHAR(2000)) AS EVIDENCE,
        CAST('Reconcile the linked observations and metric definitions across both domains; neither domain is presumed authoritative.'
             AS VARCHAR(2000)) AS RECOMMENDED_ACTION,
        CAST(p.RUN_ID_1 AS VARCHAR(200)) AS SOURCE_RUN_ID,
        CAST('observation_id=' || p.OBSERVATION_ID_1 || '; observation_id=' || p.OBSERVATION_ID_2 ||
             '; run_id=' || p.RUN_ID_1 || '; run_id=' || p.RUN_ID_2 ||
             '; kpi_id=' || p.KPI_ID_1 || '; kpi_id=' || p.KPI_ID_2 ||
             '; dependency_id=' || p.DEPENDENCY_ID_1 || '; dependency_id=' || p.DEPENDENCY_ID_2 AS VARCHAR(4000)) AS SOURCE_REFERENCES,
        CAST(p.RELATIVE_GAP AS VARCHAR(2000)) AS MEASURED_VALUE,
        CAST('0.10' AS VARCHAR(2000)) AS EXPECTED_VALUE,
        CAST('0.10' AS VARCHAR(2000)) AS THRESHOLD_VALUE
    FROM related_domain_pairs p
    WHERE p.PAIR_RN = 1
      AND p.RELATIVE_GAP > 0.10
),
historical_recurrence AS (
    SELECT
        i.PIPELINE_ID,
        i.INCIDENT_CATEGORY,
        COUNT(DISTINCT i.INCIDENT_ID) AS OCCURRENCE_COUNT,
        LISTAGG(i.INCIDENT_ID, ', ') WITHIN GROUP (ORDER BY i.INCIDENT_ID) AS INCIDENT_IDS
    FROM OPS_STAGE.STG_INCIDENT_HISTORY i
    GROUP BY i.PIPELINE_ID, i.INCIDENT_CATEGORY
    HAVING COUNT(DISTINCT i.INCIDENT_ID) >= 2
),
scenario_incident_history AS (
    SELECT
        i.PIPELINE_ID,
        i.INCIDENT_CATEGORY,
        i.SCENARIO_INSTANCE_ID,
        COUNT(DISTINCT i.INCIDENT_ID) AS OCCURRENCE_COUNT,
        LISTAGG(i.INCIDENT_ID, ', ') WITHIN GROUP (ORDER BY i.INCIDENT_ID) AS INCIDENT_IDS
    FROM OPS_STAGE.STG_INCIDENT_HISTORY i
    GROUP BY i.PIPELINE_ID, i.INCIDENT_CATEGORY, i.SCENARIO_INSTANCE_ID
),
historical_recurrence_findings AS (
    SELECT
        CAST('incident_recurrence:' || h.PIPELINE_ID || ':' || h.INCIDENT_CATEGORY AS VARCHAR(200)) AS FINDING_ID,
        CAST(NULL AS VARCHAR(200)) AS SCENARIO_INSTANCE_ID,
        CAST('INCIDENT_RECURRENCE' AS VARCHAR(100)) AS FINDING_TYPE,
        CAST('MEDIUM' AS VARCHAR(20)) AS SEVERITY,
        CAST('PIPELINE' AS VARCHAR(100)) AS AFFECTED_ENTITY_TYPE,
        CAST(h.PIPELINE_ID AS VARCHAR(200)) AS AFFECTED_ENTITY_ID,
        CAST('incident_category=' || h.INCIDENT_CATEGORY || '; distinct_historical_incidents=' || CAST(h.OCCURRENCE_COUNT AS VARCHAR(50)) ||
             '; recurrence_threshold=2' AS VARCHAR(2000)) AS EVIDENCE,
        CAST('Review the repeated incident history, identify shared causes, and track durable remediation.' AS VARCHAR(2000)) AS RECOMMENDED_ACTION,
        CAST(NULL AS VARCHAR(200)) AS SOURCE_RUN_ID,
        CAST('incident_ids=' || h.INCIDENT_IDS AS VARCHAR(4000)) AS SOURCE_REFERENCES,
        CAST(h.OCCURRENCE_COUNT AS VARCHAR(2000)) AS MEASURED_VALUE,
        CAST('2' AS VARCHAR(2000)) AS EXPECTED_VALUE,
        CAST('2' AS VARCHAR(2000)) AS THRESHOLD_VALUE
    FROM historical_recurrence h
),
active_freshness_events AS (
    SELECT
        o.SCENARIO_INSTANCE_ID,
        o.RUN_ID,
        r.PIPELINE_ID,
        COUNT(DISTINCT o.RUN_ID) AS EVENT_COUNT,
        LISTAGG(qr.QUALITY_RESULT_ID, ', ') WITHIN GROUP (ORDER BY qr.QUALITY_RESULT_ID) AS QUALITY_RESULT_IDS
    FROM OPS_STAGE.STG_DATASET_OBSERVATIONS o
    JOIN OPS_STAGE.STG_PIPELINE_RUNS r
      ON r.RUN_ID = o.RUN_ID AND UPPER(r.STATUS) = 'SUCCEEDED'
    JOIN OPS_STAGE.STG_QUALITY_RESULTS qr
      ON qr.OBSERVATION_ID = o.OBSERVATION_ID AND UPPER(qr."RESULT") = 'FAIL'
    JOIN OPS_STAGE.STG_QUALITY_CHECKS qc
      ON qc.QUALITY_CHECK_ID = qr.QUALITY_CHECK_ID AND UPPER(qc.CHECK_TYPE) = 'FRESHNESS'
    GROUP BY o.SCENARIO_INSTANCE_ID, o.RUN_ID, r.PIPELINE_ID
),
active_freshness_by_scenario AS (
    SELECT
        a.SCENARIO_INSTANCE_ID,
        a.PIPELINE_ID,
        COUNT(DISTINCT a.RUN_ID) AS EVENT_COUNT,
        MIN(a.RUN_ID) AS SOURCE_RUN_ID,
        LISTAGG(a.RUN_ID, ', ') WITHIN GROUP (ORDER BY a.RUN_ID) AS RUN_IDS,
        LISTAGG(a.QUALITY_RESULT_IDS, '; ') WITHIN GROUP (ORDER BY a.RUN_ID) AS QUALITY_RESULT_IDS
    FROM active_freshness_events a
    GROUP BY a.SCENARIO_INSTANCE_ID, a.PIPELINE_ID
),
active_recurrence_findings AS (
    -- FRESHNESS_DELAY is the explicitly supported correspondence between an
    -- incident category and a current failed freshness check. Require the same
    -- scenario link plus one prior incident: two distinct occurrences total.
    SELECT
        CAST('incident_recurrence:' || i.PIPELINE_ID || ':' || i.INCIDENT_CATEGORY || ':' || i.SCENARIO_INSTANCE_ID AS VARCHAR(200)) AS FINDING_ID,
        CAST(i.SCENARIO_INSTANCE_ID AS VARCHAR(200)) AS SCENARIO_INSTANCE_ID,
        CAST('INCIDENT_RECURRENCE' AS VARCHAR(100)) AS FINDING_TYPE,
        CAST('MEDIUM' AS VARCHAR(20)) AS SEVERITY,
        CAST('PIPELINE' AS VARCHAR(100)) AS AFFECTED_ENTITY_TYPE,
        CAST(i.PIPELINE_ID AS VARCHAR(200)) AS AFFECTED_ENTITY_ID,
        CAST('incident_category=' || i.INCIDENT_CATEGORY || '; prior_incident_ids=' || i.INCIDENT_IDS ||
             '; current_run_ids=' || a.RUN_IDS || '; distinct_occurrences=' || CAST(i.OCCURRENCE_COUNT + a.EVENT_COUNT AS VARCHAR(50)) ||
             '; recurrence_threshold=2' AS VARCHAR(2000)) AS EVIDENCE,
        CAST('Compare the current freshness failure with the linked incident history and track a durable remediation.' AS VARCHAR(2000)) AS RECOMMENDED_ACTION,
        CAST(a.SOURCE_RUN_ID AS VARCHAR(200)) AS SOURCE_RUN_ID,
        CAST('incident_ids=' || i.INCIDENT_IDS || '; run_ids=' || a.RUN_IDS ||
             '; quality_result_ids=' || a.QUALITY_RESULT_IDS AS VARCHAR(4000)) AS SOURCE_REFERENCES,
        CAST(i.OCCURRENCE_COUNT + a.EVENT_COUNT AS VARCHAR(2000)) AS MEASURED_VALUE,
        CAST('2' AS VARCHAR(2000)) AS EXPECTED_VALUE,
        CAST('2' AS VARCHAR(2000)) AS THRESHOLD_VALUE
    FROM scenario_incident_history i
    JOIN active_freshness_by_scenario a
      ON a.PIPELINE_ID = i.PIPELINE_ID
     AND a.SCENARIO_INSTANCE_ID = i.SCENARIO_INSTANCE_ID
    WHERE UPPER(i.INCIDENT_CATEGORY) = 'FRESHNESS_DELAY'
      AND i.OCCURRENCE_COUNT + a.EVENT_COUNT >= 2
      AND NOT EXISTS (
          SELECT 1 FROM historical_recurrence h
          WHERE h.PIPELINE_ID = i.PIPELINE_ID
            AND h.INCIDENT_CATEGORY = i.INCIDENT_CATEGORY
      )
),
all_findings AS (
    SELECT * FROM pipeline_failures
    UNION ALL SELECT * FROM stale_datasets
    UNION ALL SELECT * FROM incomplete_datasets
    UNION ALL SELECT * FROM quality_failures
    UNION ALL SELECT * FROM kpi_anomalies
    UNION ALL SELECT * FROM cross_domain_inconsistencies
    UNION ALL SELECT * FROM historical_recurrence_findings
    UNION ALL SELECT * FROM active_recurrence_findings
)
SELECT
    FINDING_ID, SCENARIO_INSTANCE_ID, FINDING_TYPE, SEVERITY,
    AFFECTED_ENTITY_TYPE, AFFECTED_ENTITY_ID, EVIDENCE,
    RECOMMENDED_ACTION, SOURCE_RUN_ID, SOURCE_REFERENCES,
    MEASURED_VALUE, EXPECTED_VALUE, THRESHOLD_VALUE
FROM all_findings;
