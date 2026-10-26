import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import {
  ResponsiveContainer,
  ComposedChart,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  Bar,
  Line,
} from "recharts";

const API = "http://127.0.0.1:5000/api";

function money(value) {
  if (value == null || value === "" || !Number.isFinite(Number(value))) {
    return "—";
  }

  return `₹${Number(value).toLocaleString("en-IN", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  })}`;
}

function formatNumber(value) {
  if (value == null || !Number.isFinite(Number(value))) {
    return "—";
  }

  return Number(value).toLocaleString("en-IN");
}

function Status({ value }) {
  const label =
    typeof value === "string" && value.trim()
      ? value.toLowerCase()
      : "unknown";

  return (
    <span className={`usage-status ${label}`}>
      {label.toUpperCase()}
    </span>
  );
}

function formatDate(date) {
  if (typeof date !== "string" || date.length < 10) {
    return "Unknown";
  }

  return date;
}

function formatChartDate(date) {
  if (typeof date !== "string" || date.length < 10) {
    return "Unknown";
  }

  return date.slice(5);
}

export default function UsageBillingDashboard() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Prevent overlapping requests from this component.
  const requestInFlight = useRef(false);

  const loadData = useCallback(async () => {
    if (requestInFlight.current) return;

    requestInFlight.current = true;
    setLoading(true);
    setError("");

    try {
      const response = await axios.get(
        `${API}/metrics/usage-billing`,
        {
          params: { days },
          timeout: 90000,
        }
      );

      const result = response.data;

      if (!result || typeof result !== "object") {
        throw new Error("The API returned an invalid response.");
      }

      setData(result);

      if (result.errors && Object.keys(result.errors).length > 0) {
        const messages = Object.entries(result.errors)
          .map(([source, message]) => `${source}: ${message}`)
          .join(" | ");

        setError(messages);
      } else if (result.success === false) {
        setError(
          result.error || "Unable to retrieve usage and billing data."
        );
      }
    } catch (err) {
      const status = err.response?.status;

      if (status === 429) {
        setError(
          "Too many requests. Wait briefly before refreshing."
        );
      } else if (status === 404) {
        setError(
          "Usage and billing endpoint not found. Check the Flask route."
        );
      } else if (status >= 500) {
        setError(
          err.response?.data?.error ||
            "The backend encountered an error."
        );
      } else {
        setError(
          err.response?.data?.error ||
            err.message ||
            "Unable to load usage and billing data."
        );
      }
    } finally {
      requestInFlight.current = false;
      setLoading(false);
    }
  }, [days]);

  // One initial fetch per effect execution. No duplicate effect.
  useEffect(() => {
    loadData();
  }, [loadData]);

  const daily = Array.isArray(data?.daily) ? data.daily : [];
  const summary = data?.summary || {};
  const period = data?.period || {};

  const chartData = daily.map((row) => ({
    ...row,
    chartDate: formatChartDate(row.date),
    cost_inr:
      row.cost_inr == null ? null : Number(row.cost_inr),
    pipeline_runs:
      row.pipeline_runs == null ? null : Number(row.pipeline_runs),
  }));

  const assessmentRows = daily
    .filter(
      (row) =>
        row.cost_level === "heavy" ||
        row.usage_level === "heavy" ||
        row.cost_level === "unknown" ||
        row.usage_level === "unknown" ||
        Number(row.failed || 0) > 0
    )
    .slice()
    .reverse();

  const hasAssessment = daily.some(
    (row) =>
      row.cost_level === "heavy" ||
      row.usage_level === "heavy" ||
      row.cost_level === "unknown" ||
      row.usage_level === "unknown" ||
      Number(row.failed || 0) > 0
  );

  return (
    <section className="usage-dashboard">
      <div className="usage-toolbar">
        <div>
          <h2>Pipeline Usage &amp; Billing</h2>
          <p>
            Compare Azure Data Factory executions with recorded Azure costs.
          </p>
        </div>

        <div className="usage-actions">
          <select
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
            aria-label="History window"
            disabled={loading}
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>

          <button onClick={loadData} disabled={loading}>
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>
      </div>

      {error && (
        <div className="usage-error" role="alert">
          {error}
        </div>
      )}

      {loading && !data && (
        <div className="usage-loading">
          Loading usage and billing data...
        </div>
      )}

      {data && (
        <>
          <div className="usage-summary-grid">
            <article className="usage-card">
              <span>Recorded cost</span>
              <strong>{money(summary.recorded_cost_inr)}</strong>
              <small>
                {period.days_with_cost_records ?? 0} days with cost records
              </small>
            </article>

            <article className="usage-card">
              <span>Pipeline runs</span>
              <strong>{formatNumber(summary.pipeline_runs)}</strong>
              <small>Within the selected history window</small>
            </article>

            <article className="usage-card">
              <span>Billing API</span>
              <strong>
                {data.billing_status === "working"
                  ? "Connected"
                  : "Unavailable"}
              </strong>
              <small>Azure Cost Management</small>
            </article>

            <article className="usage-card">
              <span>Pipeline API</span>
              <strong>
                {data.pipeline_status === "working"
                  ? "Connected"
                  : "Unavailable"}
              </strong>
              <small>Azure Data Factory</small>
            </article>
          </div>

          <article className="usage-panel">
            <div className="usage-panel-heading">
              <h3>Daily cost vs pipeline activity</h3>
              <p>
                Cost is shown in INR; pipeline run count uses the right axis.
                Missing billing records are not treated as zero.
              </p>
            </div>

            <div className="usage-chart">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={chartData}
                  margin={{
                    top: 12,
                    right: 16,
                    left: 8,
                    bottom: 8,
                  }}
                >
                  <CartesianGrid strokeDasharray="3 3" />

                  <XAxis
                    dataKey="chartDate"
                    minTickGap={24}
                  />

                  <YAxis
                    yAxisId="cost"
                    tickFormatter={(value) => `₹${value}`}
                  />

                  <YAxis
                    yAxisId="runs"
                    orientation="right"
                    allowDecimals={false}
                  />

                  <Tooltip
                    labelFormatter={(label) => `Date: ${label}`}
                    formatter={(value, name) => {
                      if (value == null) {
                        return ["Unavailable", name];
                      }

                      if (name === "Cost (INR)") {
                        return [money(value), name];
                      }

                      return [formatNumber(value), name];
                    }}
                  />

                  <Legend />

                  <Bar
                    yAxisId="cost"
                    dataKey="cost_inr"
                    name="Cost (INR)"
                    fill="#6478f5"
                    radius={[4, 4, 0, 0]}
                  />

                  <Line
                    yAxisId="runs"
                    type="monotone"
                    dataKey="pipeline_runs"
                    name="Pipeline runs"
                    stroke="#16a085"
                    strokeWidth={2}
                    connectNulls={false}
                    dot={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </article>

          <article className="usage-panel">
            <div className="usage-panel-heading">
              <h3>Daily usage assessment</h3>
              <p>
                Thresholds are configured by the Flask backend.
              </p>
            </div>

            <div className="usage-table-wrap">
              <table className="usage-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Cost</th>
                    <th>Cost status</th>
                    <th>Usage status</th>
                    <th>Runs</th>
                    <th>Succeeded</th>
                    <th>Failed</th>
                    <th>Cost reason</th>
                    <th>Usage reason</th>
                  </tr>
                </thead>

                <tbody>
                  {daily.length > 0 ? (
                    daily
                      .slice()
                      .reverse()
                      .map((row, index) => (
                        <tr
                          key={row.date || `row-${index}`}
                        >
                          <td>{formatDate(row.date)}</td>
                          <td>{money(row.cost_inr)}</td>
                          <td>
                            <Status value={row.cost_level} />
                          </td>
                          <td>
                            <Status value={row.usage_level} />
                          </td>
                          <td>{formatNumber(row.pipeline_runs)}</td>
                          <td>{formatNumber(row.succeeded)}</td>
                          <td>{formatNumber(row.failed)}</td>
                          <td>
                            {row.cost_reason || "No explanation available."}
                          </td>
                          <td>
                            {row.usage_reason || "No explanation available."}
                          </td>
                        </tr>
                      ))
                  ) : (
                    <tr>
                      <td colSpan={9}>
                        No daily records are available for this period.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>

          <article className="usage-panel">
            <div className="usage-panel-heading">
              <h3>Why did this happen?</h3>
              <p>
                Explanations are based on the returned cost and pipeline data.
              </p>
            </div>

            <div className="usage-reasons">
              {daily.length === 0 ? (
                <p>No usage or billing records are available.</p>
              ) : hasAssessment ? (
                assessmentRows.map((row, index) => (
                  <div
                    className="usage-reason"
                    key={row.date || `assessment-${index}`}
                  >
                    <strong>{formatDate(row.date)}</strong>

                    <div>
                      <Status value={row.cost_level} />
                      <Status value={row.usage_level} />
                      {Number(row.failed || 0) > 0 && (
                        <Status value="failed" />
                      )}
                    </div>

                    <p>
                      {row.relationship_reason ||
                        "Review the billing and pipeline records for this date."}
                    </p>

                    {Number(row.failed || 0) > 0 && (
                      <p>
                        {formatNumber(row.failed)} pipeline run(s) failed.
                        Inspect the corresponding Azure Data Factory run
                        details to identify the cause.
                      </p>
                    )}

                    {row.cost_reason && (
                      <p>{row.cost_reason}</p>
                    )}

                    {row.usage_reason && (
                      <p>{row.usage_reason}</p>
                    )}
                  </div>
                ))
              ) : (
                <p>
                  No heavy or unknown days, or failed runs, were detected
                  using the returned data and current thresholds.
                </p>
              )}
            </div>
          </article>

          {data.note && (
            <p className="usage-footnote">{data.note}</p>
          )}

          {period.from && period.to && (
            <p className="usage-footnote">
              Period: {period.from} to {period.to}
              {period.days_requested
                ? ` (${period.days_requested} days requested)`
                : ""}
            </p>
          )}
        </>
      )}
    </section>
  );
}
