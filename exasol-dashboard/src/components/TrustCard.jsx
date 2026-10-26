
import React from "react";
import Card from "./Card";
import SectionTitle from "./SectionTitle";
import Badge from "./Badge";

const number = (value, digits = 0) => {
  if (
    value == null ||
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
  if (value == null || !Number.isFinite(Number(value))) {
    return "—";
  }

  return `${number(value, digits)}%`;
};

function MetricCard({ label, value, color = "blue", description }) {
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
    count != null && total > 0
      ? Math.min(100, (count / total) * 100)
      : 0;

  const invalid = /invalid|reject|fail|mismatch/i.test(label);

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
            invalid ? "invalid" : "valid"
          }`}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

function QualityChart({ title, subtitle, items, total }) {
  return (
    <Card>
      <SectionTitle title={title} subtitle={subtitle} />

      <div className="trust-quality-chart">
        {items.map((item) => (
          <QualityBar
            key={item.label}
            label={item.label}
            value={item.value}
            total={total}
          />
        ))}
      </div>

      <div className="trust-chart-total">
        Total records: {number(total)}
      </div>
    </Card>
  );
}

export default function TrustCard({ metrics = {} }) {
  const total = Number(metrics.total_records) || 0;
  const valid = Number(metrics.valid_records) || 0;
  const invalid = Number(metrics.invalid_records) || 0;

  // Prefer backend values; calculate rates only when counts are available.
  const trustScore =
    metrics.trust_score != null
      ? Number(metrics.trust_score)
      : total > 0
        ? (valid / total) * 100
        : null;

  const validationRate =
    total > 0 ? (valid / total) * 100 : null;

  const invalidRate =
    total > 0 ? (invalid / total) * 100 : null;

  const rejectionRate =
    metrics.rejection_rate != null
      ? Number(metrics.rejection_rate)
      : invalidRate;

  const status = metrics.status || "UNKNOWN";

  // Do not render metrics that have no actual values.
  const optionalMetrics = [
    {
      label: "Average Completeness",
      value: metrics.avg_completeness,
      format: (v) => percent(v),
    },
    {
      label: "Financial Mismatches",
      value: metrics.financial_mismatches,
      format: (v) => number(v),
    },
    {
      label: "Accuracy Failures",
      value: metrics.accuracy_failures,
      format: (v) => number(v),
    },
    {
      label: "Correctness Failures",
      value: metrics.correctness_failures,
      format: (v) => number(v),
    },
    {
      label: "Missing IDs",
      value: metrics.missing_ids,
      format: (v) => number(v),
    },
    {
      label: "Reported Amount at Risk",
      value: metrics.reported_total_at_risk,
      format: (v) => number(v, 2),
    },
  ].filter(
    (item) =>
      item.value != null &&
      item.value !== "" &&
      Number.isFinite(Number(item.value))
  );

  const recordChart = [
    { label: "Valid Rows", value: valid },
    { label: "Invalid Rows", value: invalid },
  ];

  const financialChart = Array.isArray(
    metrics.charts?.financial_quality
  )
    ? metrics.charts.financial_quality.filter(
        (item) =>
          item.value != null &&
          Number.isFinite(Number(item.value))
      )
    : [];

  return (
    <div className="trust-dashboard">
      {/* Page heading */}
      <div className="trust-page-heading">
        <div>
          <span className="trust-eyebrow">WORKSPACE / DATAOPS</span>
          <h2>Data Trust</h2>
          <p>
            Review trust metrics and the live Exasol data quality status.
          </p>
        </div>

        <button
          type="button"
          className="trust-action-button"
          onClick={() => window.location.reload()}
        >
          ↻ Refresh
        </button>
      </div>

      {/* KPI row */}
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
          value={percent(trustScore, 2)}
          color="purple"
          description="Valid records as a share of total"
        />
      </div>

      {/* Derived KPI row */}
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
          description="Reported by the backend"
        />
      </div>

      {/* Trust overview */}
      <Card>
        <SectionTitle
          title="Dataset Trust Overview"
          subtitle={`Source: ${
            metrics.source || "Exasol data quality records"
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
                Number.isFinite(trustScore)
                  ? Math.min(100, Math.max(0, trustScore))
                  : 0
              }
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="trust-progress-fill"
                style={{
                  width: `${
                    Number.isFinite(trustScore)
                      ? Math.min(100, Math.max(0, trustScore))
                      : 0
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

      {/* Charts */}
      <div className="trust-chart-grid">
        <QualityChart
          title="Record Distribution"
          subtitle="Valid versus invalid records"
          items={recordChart}
          total={total}
        />

        {financialChart.length > 0 && (
          <QualityChart
            title="Financial Quality"
            subtitle="Financial validation results reported by Exasol"
            items={financialChart}
            total={total}
          />
        )}
      </div>

      {/* Only show actual, available validation metrics */}
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
