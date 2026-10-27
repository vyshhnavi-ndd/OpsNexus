
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

const API = "/api";

function toNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function money(value) {
  const number = toNumber(value);

  if (number === null) return "Unavailable";

  return `₹${number.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatNumber(value) {
  const number = toNumber(value);

  if (number === null) return "Unavailable";

  return number.toLocaleString("en-IN");
}

function formatDate(value) {
  if (typeof value !== "string" || value.length < 10) {
    return "Unknown";
  }

  return value.slice(0, 10);
}

function formatChartDate(value) {
  const date = formatDate(value);
  return date === "Unknown" ? date : date.slice(5);
}

function Status({ value }) {
  const label =
    typeof value === "string" && value.trim()
      ? value.trim().toLowerCase().replace(/\s+/g, "-")
      : "unknown";

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

  const requestId = useRef(0);

  const loadData = useCallback(async () => {
    const currentRequestId = ++requestId.current;

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

      if (currentRequestId !== requestId.current) return;

      const result = response.data;

      if (!result || typeof result !== "object") {
        throw new Error("The API returned an invalid response.");
      }

      setData(result);

      if (result.errors && Object.keys(result.errors).length > 0) {
        const messages = Object.entries(result.errors)
          .map(([source, message]) => {
            const detail =
              typeof message === "string"
                ? message
                : JSON.stringify(message);

            return `${source}: ${detail}`;
          })
          .join(" | ");

        setError(messages);
      } else if (result.success === false) {
        setError(result.error || "Unable to retrieve dashboard data.");
      }
    } catch (err) {
      if (currentRequestId !== requestId.current) return;

      const status = err.response?.status;

      if (status === 429) {
        setError("Too many requests. Wait briefly before refreshing.");
      } else if (status === 404) {
        setError(
          "The usage-billing API route was not found. Check your Flask route and frontend proxy."
        );
      } else {
        setError(
          err.response?.data?.error ||
            err.message ||
            "Unable to load usage and billing data."
        );
      }
    } finally {
      if (currentRequestId === requestId.current) {
        setLoading(false);
      }
    }
  }, [days]);

  useEffect(() => {
    loadData();

    return () => {
      requestId.current += 1;
    };
  }, [loadData]);

  const daily = Array.isArray(data?.daily) ? data.daily : [];
  const summary = data?.summary || {};
  const period = data?.period || {};

  const chartData = daily
    .map((row) => ({
      ...row,
      chartDate: formatChartDate(row.date),
      cost_inr: toNumber(row.cost_inr),
      pipeline_runs: toNumber(row.pipeline_runs),
    }))
    .sort((a, b) => {
      const dateA = String(a.date || "");
      const dateB = String(b.date || "");
      return dateA.localeCompare(dateB);
    });

  const assessmentRows = daily
    .filter(
      (row) =>
        ["heavy", "unknown"].includes(
          String(row.cost_level || "").toLowerCase()
        ) ||
        ["heavy", "unknown"].includes(
          String(row.usage_level || "").toLowerCase()
        ) ||
        (toNumber(row.failed) || 0) > 0
    )
    .slice()
    .reverse();

  const hasAssessment = assessmentRows.length > 0;

  const hasCostData = chartData.some(
    (row) => row.cost_inr !== null
  );

  const hasPipelineData = chartData.some(
    (row) => row.pipeline_runs !== null
  );

  const hasChartData = hasCostData || hasPipelineData;

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
                {period.days_with_cost_records == null
                  ? "Unavailable"
                  : period.days_with_cost_records === 0
                    ? "No cost records returned"
                    : `${period.days_with_cost_records} days with cost records`}
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
              {hasChartData ? (
                <ResponsiveContainer
                  width="100%"
                  height="100%"
                  minWidth={0}
                >
                  <ComposedChart
                    data={chartData}
                    margin={{
                      top: 12,
                      right: 20,
                      left: 12,
                      bottom: 8,
                    }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="#e2e8f0"
                    />

                    <XAxis
                      dataKey="chartDate"
                      minTickGap={24}
                      tick={{ fontSize: 12 }}
                    />

                    <YAxis
                      yAxisId="cost"
                      tickFormatter={(value) => `₹${value}`}
                      tick={{ fontSize: 12 }}
                      width={75}
                    />

                    <YAxis
                      yAxisId="runs"
                      orientation="right"
                      allowDecimals={false}
                      tick={{ fontSize: 12 }}
                      width={45}
                    />

                    <Tooltip
                      labelFormatter={(label) => `Date: ${label}`}
                      formatter={(value, name) => {
                        if (value == null) {
                          return ["Unavailable", name];
                        }

                        return [
                          name === "Cost (INR)"
                            ? money(value)
                            : formatNumber(value),
                          name,
                        ];
                      }}
                    />

                    <Legend />

                    <Bar
                      yAxisId="cost"
                      dataKey="cost_inr"
                      name="Cost (INR)"
                      fill="#6478f5"
                      radius={[4, 4, 0, 0]}
                      maxBarSize={32}
                      isAnimationActive={false}
                    />

                    <Line
                      yAxisId="runs"
                      type="monotone"
                      dataKey="pipeline_runs"
                      name="Pipeline runs"
                      stroke="#16a085"
                      strokeWidth={3}
                      connectNulls
                      dot={{ r: 3 }}
                      activeDot={{ r: 5 }}
                      isAnimationActive={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              ) : (
                <div className="usage-chart-empty">
                  {daily.length === 0
                    ? "No daily records were returned by the API."
                    : "Daily records exist, but cost_inr and pipeline_runs contain no valid numeric values."}
                </div>
              )}
            </div>

            {daily.length > 0 && !hasChartData && (
              <p className="usage-footnote">
                Check the API response field names and values for each daily
                record.
              </p>
            )}
          </article>

          <article className="usage-panel">
            <div className="usage-panel-heading">
              <h3>Daily usage assessment</h3>
              <p>Thresholds are configured by the Flask backend.</p>
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
                        <tr key={row.date || `row-${index}`}>
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

                    <div className="usage-reason-statuses">
                      <Status value={row.cost_level} />
                      <Status value={row.usage_level} />
                      {(toNumber(row.failed) || 0) > 0 && (
                        <Status value="failed" />
                      )}
                    </div>

                    <p>
                      {row.relationship_reason ||
                        "Review the billing and pipeline records for this date."}
                    </p>

                    {(toNumber(row.failed) || 0) > 0 && (
                      <p>
                        {formatNumber(row.failed)} pipeline run(s) failed.
                        Inspect the corresponding Azure Data Factory run
                        details to identify the cause.
                      </p>
                    )}

                    {row.cost_reason && <p>{row.cost_reason}</p>}
                    {row.usage_reason && <p>{row.usage_reason}</p>}
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
