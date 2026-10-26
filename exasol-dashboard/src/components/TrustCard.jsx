import React, { useMemo } from "react";
import Card from "./Card";
import SectionTitle from "./SectionTitle";
import Badge from "./Badge";

const number = (value, digits = 0) => {
  if (
    value === null ||
    value === undefined ||
    value === "" ||
    !Number.isFinite(Number(value))
  ) {
    return "—";
  }

  return Number(value).toLocaleString("en-IN", {
    maximumFractionDigits: digits,
  });
};

const percent = (value, digits = 2) => {
  if (
    value === null ||
    value === undefined ||
    value === "" ||
    !Number.isFinite(Number(value))
  ) {
    return "—";
  }

  return `${number(value, digits)}%`;
};

function MetricCard({ label, value, color, description }) {
  return (
    <div className={`trust-summary-card trust-${color}`}>
      <div className="trust-summary-heading">
        <span>{label}</span>
      </div>

      <strong className="trust-summary-value">{value}</strong>

      {description && (
        <span className="trust-summary-description">
          {description}
        </span>
      )}
    </div>
  );
}

function DetailMetric({ label, value }) {
  return (
    <div className="trust-metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function QualityBar({ label, value, total }) {
  const count =
    value != null && Number.isFinite(Number(value))
      ? Math.max(0, Number(value))
      : null;

  const width =
    count !== null && total > 0
      ? Math.min(100, (count / total) * 100)
      : 0;

  const isInvalid = /invalid|reject|fail|mismatch/i.test(label);

  return (
    <div className="trust-quality-item">
      <div className="trust-quality-heading">
        <span>{label}</span>
        <strong>{number(count)}</strong>
      </div>

      <div
        className="trust-quality-track"
        role="progressbar"
        aria-label={label}
        aria-valuenow={width}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={`trust-quality-fill ${
            isInvalid ? "invalid" : "valid"
          }`}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

function normalizeMetrics(input) {
  let result = input;

  // Support direct responses and common Flask response wrappers.
  for (let i = 0; i < 4; i += 1) {
    if (!result || typeof result !== "object" || Array.isArray(result)) {
      return {};
    }

    if (
      result.total_records !== undefined ||
      result.valid_records !== undefined ||
      result.trust_score !== undefined
    ) {
      return result;
    }

    if (result.trust_metrics && typeof result.trust_metrics === "object") {
      result = result.trust_metrics;
    } else if (result.metrics && typeof result.metrics === "object") {
      result = result.metrics;
    } else if (result.data && typeof result.data === "object") {
      result = result.data;
    } else {
      return result;
    }
  }

  return result || {};
}

export default function TrustCard({ metrics = {} }) {
  const data = useMemo(() => normalizeMetrics(metrics), [metrics]);

  const total = data.total_records ?? null;
  const valid = data.valid_records ?? null;
  const invalid = data.invalid_records ?? null;

  // Use the backend's trust score when available.
  const trustScore =
    data.trust_score != null
      ? Number(data.trust_score)
      : total != null && Number(total) > 0 && valid != null
        ? (Number(valid) / Number(total)) * 100
        : null;

  const validationRate =
    total != null && Number(total) > 0 && valid != null
      ? (Number(valid) / Number(total)) * 100
      : null;

  const invalidRate =
    total != null && Number(total) > 0 && invalid != null
      ? (Number(invalid) / Number(total)) * 100
      : null;

  const rejectionRate =
    data.rejection_rate != null
      ? Number(data.rejection_rate)
      : invalidRate;

  const status = data.status || "UNKNOWN";

  const optionalMetrics = [
    {
      label: "Average Completeness",
      value: data.avg_completeness,
      format: (value) => percent(value),
    },
    {
      label: "Financial Mismatches",
      value: data.financial_mismatches,
      format: (value) => number(value),
    },
    {
      label: "Accuracy Failures",
      value: data.accuracy_failures,
      format: (value) => number(value),
    },
    {
      label: "Correctness Failures",
      value: data.correctness_failures,
      format: (value) => number(value),
    },
    {
      label: "Missing IDs",
      value: data.missing_ids,
      format: (value) => number(value),
    },
    {
      label: "Reported Amount at Risk",
      value: data.reported_total_at_risk,
      format: (value) => number(value, 2),
    },
  ].filter(
    (item) =>
      item.value !== null &&
      item.value !== undefined &&
      item.value !== "" &&
      Number.isFinite(Number(item.value))
  );

  // Your API provides charts.record_distribution.
  const distribution =
    Array.isArray(data.charts?.record_distribution)
      ? data.charts.record_distribution
      : [
          { label: "Valid", value: valid },
          { label: "Invalid", value: invalid },
        ];

  const chartItems = distribution.filter(
    (item) =>
      item.value !== null &&
      item.value !== undefined &&
      Number.isFinite(Number(item.value))
  );

  return (
    <div className="trust-dashboard">
      {/* Heading */}
      <div className="trust-summary-grid">
        <MetricCard
          label="Raw Data / Total Records"
          value={number(total)}
          color="blue"
          description="Total records evaluated"
        />

        <MetricCard
          label="Valid Rows"
          value={number(valid)}
          color="green"
          description="Records accepted"
        />

        <MetricCard
          label="Invalid Rows"
          value={number(invalid)}
          color="red"
          description="Records requiring review"
        />

        <MetricCard
          label="Data Quality / Trust Score"
          value={percent(trustScore)}
          color="purple"
          description="Trust score returned by the backend"
        />
      </div>

      {/* Derived metrics */}
      <div className="trust-summary-grid trust-secondary-grid">
        <MetricCard
          label="Validation Rate"
          value={percent(validationRate)}
          color="green"
          description="Valid rows / total records"
        />

        <MetricCard
          label="Invalid Rate"
          value={percent(invalidRate)}
          color="red"
          description="Invalid rows / total records"
        />

        <MetricCard
          label="Rejection Rate"
          value={percent(rejectionRate)}
          color="orange"
          description="Rejection rate returned by the backend"
        />
      </div>

      {/* Trust overview */}
      <Card>
        <SectionTitle
          title="Dataset Trust Overview"
          subtitle={`Source: ${
            data.source || "Exasol data quality records"
          }`}
        />

        <div className="trust-overview">
          <div className="trust-score-panel">
            <span className="trust-muted">Dataset Trust Score</span>

            <div className="trust-big-score">
              {percent(trustScore)}
            </div>

            <div
              className="trust-progress"
              role="progressbar"
              aria-label="Dataset trust score"
              aria-valuenow={
                trustScore == null
                  ? 0
                  : Math.min(100, Math.max(0, trustScore))
              }
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="trust-progress-fill"
                style={{
                  width: `${
                    trustScore == null
                      ? 0
                      : Math.min(100, Math.max(0, trustScore))
                  }%`,
                }}
              />
            </div>
          </div>

          <div className="trust-status">
            <Badge>{status}</Badge>
            <p>
              {status === "HEALTHY"
                ? "Dataset validation completed successfully."
                : status === "REVIEW_REQUIRED"
                  ? "Validation issues require review."
                  : "Review the latest validation results."}
            </p>
          </div>
        </div>

        <div className="trust-metric-grid">
          <DetailMetric
            label="Total Records"
            value={number(total)}
          />
          <DetailMetric
            label="Valid Records"
            value={number(valid)}
          />
          <DetailMetric
            label="Invalid Records"
            value={number(invalid)}
          />
          <DetailMetric
            label="Trust Score"
            value={percent(trustScore)}
          />
          <DetailMetric
            label="Validation Rate"
            value={percent(validationRate)}
          />
          <DetailMetric
            label="Rejection Rate"
            value={percent(rejectionRate)}
          />
        </div>
      </Card>

      {/* Record distribution chart */}
      <Card>
        <SectionTitle
          title="Record Distribution"
          subtitle="Valid and invalid records returned by Exasol"
        />

        <div className="trust-quality-chart">
          {chartItems.map((item) => (
            <QualityBar
              key={item.label}
              label={item.label}
              value={item.value}
              total={Number(total) || 0}
            />
          ))}
        </div>

        <div className="trust-chart-total">
          Total records: {number(total)}
        </div>
      </Card>

      {/* Additional non-null metrics only */}
      {optionalMetrics.length > 0 && (
        <Card>
          <SectionTitle
            title="Additional Validation Metrics"
            subtitle="Only metrics with reported values are displayed"
          />

          <div className="trust-failure-grid">
            {optionalMetrics.map((item) => (
              <DetailMetric
                key={item.label}
                label={item.label}
                value={item.format(item.value)}
              />
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}