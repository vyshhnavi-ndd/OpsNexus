
import { useCallback, useEffect, useState } from "react";
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

const API = "/api";

function money(value) {
  return value == null
    ? "—"
    : `₹${Number(value).toLocaleString("en-IN", {
        maximumFractionDigits: 2,
      })}`;
}

function Status({ value }) {
  const label = value || "unknown";
  return (
    <span className={`usage-status ${label}`}>
      {label.toUpperCase()}
    </span>
  );
}

export default function UsageBillingDashboard() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const response = await axios.get(
        `${API}/metrics/usage-billing`,
        { params: { days }, timeout: 90000 }
      );

      setData(response.data);
      if (response.data?.errors) {
        const messages = Object.entries(response.data.errors)
          .map(([source]) => {
            const status = source === "billing"
              ? "Azure Cost Management is unavailable or throttling this request. Retry after a short wait."
              : "Azure Data Factory usage data is unavailable. Check its service connection.";
            return `${source}: ${status}`;
          })
          .join(" | ");
        if (messages) setError(messages);
      }
    } catch (err) {
      setError(
        err.response?.data?.error ||
          err.message ||
          "Unable to load usage and billing data."
      );
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const daily = data?.daily || [];
  const summary = data?.summary || {};

  const chartData = daily.map((row) => ({
    ...row,
    chartDate: row.date.slice(5),
  }));

  return (
    <section className="usage-dashboard">
      <div className="usage-toolbar">
        <div>
          <h2>Pipeline Usage & Billing</h2>
          <p>
            Compare Azure Data Factory executions with recorded Azure costs.
          </p>
        </div>

        <div className="usage-actions">
          <select
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
            aria-label="History window"
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

      {error && <div className="usage-error">{error}</div>}

      {data && (
        <>
          <div className="usage-summary-grid">
            <article className="usage-card">
              <span>Recorded cost</span>
              <strong>{money(summary.recorded_cost_inr)}</strong>
              <small>
                {data.period?.days_with_cost_records ?? 0} days with cost records
              </small>
            </article>

            <article className="usage-card">
              <span>Pipeline runs</span>
              <strong>
                {summary.pipeline_runs == null
                  ? "—"
                  : summary.pipeline_runs.toLocaleString("en-IN")}
              </strong>
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
                Cost is shown in INR; run count uses the right-hand axis.
              </p>
            </div>

            <div className="usage-chart">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={chartData}
                  margin={{ top: 12, right: 16, left: 8, bottom: 8 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="chartDate" minTickGap={24} />
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
                      if (name === "Cost (INR)") return [money(value), name];
                      return [value == null ? "Unavailable" : value, name];
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
                Limits are configurable in the Flask environment.
              </p>
            </div>

            <div className="usage-table-wrap">
              <table className="usage-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Cost</th>
                    <th>Usage</th>
                    <th>Runs</th>
                    <th>Succeeded</th>
                    <th>Failed</th>
                    <th>Cost reason</th>
                    <th>Usage reason</th>
                  </tr>
                </thead>
                <tbody>
                  {daily.slice().reverse().map((row) => (
                    <tr key={row.date}>
                      <td>{row.date}</td>
                      <td>{money(row.cost_inr)}</td>
                      <td><Status value={row.cost_level} /></td>
                      <td>{row.pipeline_runs ?? "—"}</td>
                      <td>{row.succeeded ?? "—"}</td>
                      <td>{row.failed ?? "—"}</td>
                      <td>{row.cost_reason}</td>
                      <td>{row.usage_reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>

          <article className="usage-panel">
            <div className="usage-panel-heading">
              <h3>Why did this happen?</h3>
              <p>
                Daily explanations based on the cost and pipeline data returned.
              </p>
            </div>

            <div className="usage-reasons">
              {daily
                .filter((row) =>
                  row.cost_level === "heavy" ||
                  row.usage_level === "heavy" ||
                  row.cost_level === "unknown" ||
                  row.usage_level === "unknown"
                )
                .slice()
                .reverse()
                .map((row) => (
                  <div className="usage-reason" key={row.date}>
                    <strong>{row.date}</strong>
                    <div>
                      <Status value={row.cost_level} />
                      <Status value={row.usage_level} />
                    </div>
                    <p>{row.relationship_reason}</p>
                  </div>
                ))}

              {daily.every(
                (row) =>
                  row.cost_level !== "heavy" &&
                  row.usage_level !== "heavy" &&
                  row.cost_level !== "unknown" &&
                  row.usage_level !== "unknown"
              ) && (
                <p>
                  No heavy or unknown days were detected using the current
                  thresholds. Review the chart for trends and compare them
                  with your actual budget.
                </p>
              )}
            </div>
          </article>

          <p className="usage-footnote">{data.note}</p>
        </>
      )}
    </section>
  );
}
