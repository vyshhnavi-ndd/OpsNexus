
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

// Cache successful responses briefly so React StrictMode, repeated renders,
// and quick refreshes do not repeatedly hit the Flask/Azure billing endpoint.
const billingCache = new Map();
const billingInFlight = new Map();
const BILLING_CACHE_TTL = 60_000;
const DEFAULT_RATE_LIMIT_COOLDOWN_MS = 15 * 60_000;
let billingRateLimitedUntil = 0;

async function fetchBilling(days) {
  const key = String(days);
  const now = Date.now();
  const cached = billingCache.get(key);

  if (cached && now - cached.time < BILLING_CACHE_TTL) {
    return cached.data;
  }

  if (billingInFlight.has(key)) {
    return billingInFlight.get(key);
  }

  if (now < billingRateLimitedUntil) {
    // During cooldown, reuse the last successful result even when its normal
    // frontend TTL has elapsed. This avoids needless refresh errors.
    if (cached?.data) {
      return {
        ...cached.data,
        cached: true,
        stale: true,
        warning: "Billing refresh is paused after rate limiting. Showing the last successful result.",
      };
    }
    const waitSeconds = Math.ceil((billingRateLimitedUntil - now) / 1000);
    const error = new Error(
      `Billing API is rate-limited. Please wait ${waitSeconds} seconds before trying again.`
    );
    error.response = { status: 429 };
    throw error;
  }

  const request = axios
    .get(`${API}/metrics/usage-billing`, {
      params: { days },
      timeout: 90000,
    })
    .then((response) => {
      const result = response.data;
      // Cache only successful, usable payloads. Keep older successful data
      // available in case Azure temporarily throttles the next refresh.
      if (result && result.success !== false) {
        billingCache.set(key, { data: result, time: Date.now() });
        billingRateLimitedUntil = 0;
      }
      return result;
    })
    .catch((error) => {
      if (error.response?.status === 429) {
        const retryAfter = Number(error.response.headers?.["retry-after"]);
        // Honour Retry-After when supplied; otherwise pause requests for 30s.
        const cooldownSeconds =
          Number.isFinite(retryAfter) && retryAfter > 0
            ? retryAfter
            : DEFAULT_RATE_LIMIT_COOLDOWN_MS / 1000;
        billingRateLimitedUntil = Date.now() + cooldownSeconds * 1000;

        // If we have a prior successful response, display it instead of
        // replacing the dashboard with an error during Azure throttling.
        const previous = billingCache.get(key);
        if (previous?.data) {
          return {
            ...previous.data,
            cached: true,
            stale: true,
            warning: "Billing refresh was rate-limited. Showing the last successful result.",
          };
        }
      }
      throw error;
    })
    .finally(() => {
      billingInFlight.delete(key);
    });

  billingInFlight.set(key, request);
  return request;
}

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

  return number.toLocaleString("en-IN", {
    maximumFractionDigits: 2,
  });
}

function formatDate(value) {
  if (!value) return "Unknown";

  const text = String(value);

  if (/^\d{8}$/.test(text)) {
    return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`;
  }

  return /^\d{4}-\d{2}-\d{2}/.test(text)
    ? text.slice(0, 10)
    : text;
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

function SummaryCard({ title, value, detail, accent }) {
  return (
    <article
      className="usage-card"
      style={{
        borderTop: `3px solid ${accent}`,
        minWidth: 0,
      }}
    >
      <span>{title}</span>
      <strong style={{ overflowWrap: "anywhere" }}>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}


function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;

  return (
    <div
      style={{
        background: "var(--card-bg, #fff)",
        color: "var(--text-primary, #1f2937)",
        border: "1px solid var(--border-color, #e5e7eb)",
        borderRadius: 10,
        padding: "12px 14px",
        boxShadow: "0 8px 24px rgba(15, 23, 42, 0.12)",
      }}
    >
      <strong style={{ fontSize: 12 }}>Date: {label}</strong>

      {payload.map((item) => (
        <div
          key={item.dataKey}
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: 22,
            marginTop: 9,
            fontSize: 12,
          }}
        >
          <span style={{ color: item.color }}>
            {item.name}
          </span>

          <strong>
            {item.dataKey === "cost_inr"
              ? money(item.value)
              : formatNumber(item.value)}
          </strong>
        </div>
      ))}
    </div>
  );
}

export default function UsageBillingDashboard() {
  const [days, setDays] = useState(7);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const requestId = useRef(0);

  const loadData = useCallback(async () => {
    const currentRequestId = ++requestId.current;

    setLoading(true);
    setError("");

    try {
      const result = await fetchBilling(days);

      if (currentRequestId !== requestId.current) return;

      if (!result || typeof result !== "object") {
        throw new Error("The API returned an invalid response.");
      }

      setData(result);

      const errors = result.errors || {};

      if (Object.keys(errors).length > 0) {
        setError(
          Object.entries(errors)
            .map(([source, message]) => {
              const detail =
                typeof message === "string"
                  ? message
                  : JSON.stringify(message);

              return `${source}: ${detail}`;
            })
            .join(" | ")
        );
      } else if (result.success === false) {
        setError(result.error || "Unable to retrieve dashboard data.");
      }
    } catch (err) {
      if (currentRequestId !== requestId.current) return;

      if (err.response?.status === 404) {
        setError(
          "Usage-billing API route not found. Check the Flask route and Vite proxy."
        );
      } else if (err.response?.status === 429) {
        setError("Too many requests. Wait briefly before refreshing.");
      } else {
        setError(
          err.response?.data?.error ||
          err.message ||
          "Unable to load billing data."
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

  // The provided API returns data.daily with date, cost_inr and pipeline_runs.
  const rawDaily = Array.isArray(data?.daily)
    ? data.daily
    : [];

  const daily = rawDaily
    .map((row) => ({
      ...row,
      date: formatDate(row.date),
      cost_inr: toNumber(row.cost_inr),
      pipeline_runs: toNumber(row.pipeline_runs),
      succeeded: toNumber(row.succeeded),
      failed: toNumber(row.failed),
    }))
    .sort((a, b) => a.date.localeCompare(b.date));

  // Keep records with missing cost values so missing is not misrepresented as zero.
  const chartData = daily
    .filter((row) => row.date !== "Unknown")
    .map((row) => ({
      ...row,
      chartDate: formatChartDate(row.date),
    }));

  const summary = data?.summary || {};
  const period = data?.period || {};

  const hasCostData = chartData.some(
    (row) => row.cost_inr !== null
  );

  const hasPipelineData = chartData.some(
    (row) => row.pipeline_runs !== null
  );

  const hasChartData = hasCostData || hasPipelineData;

  const assessmentRows = daily
    .filter(
      (row) =>
        ["heavy", "unknown"].includes(
          String(row.cost_level || "").toLowerCase()
        ) ||
        ["heavy", "unknown"].includes(
          String(row.usage_level || "").toLowerCase()
        ) ||
        (row.failed || 0) > 0
    )
    .slice()
    .reverse();

  const hasAssessment = assessmentRows.length > 0;

  const totalFailed = daily.reduce(
    (sum, row) => sum + (row.failed || 0),
    0
  );

  const totalSucceeded = daily.reduce(
    (sum, row) => sum + (row.succeeded || 0),
    0
  );

  return (
    <section className="usage-dashboard">
      {/* Header and controls */}
      <div
        className="usage-toolbar"
        style={{ gap: 16, flexWrap: "wrap" }}
      >
        <div>
          <h2>Pipeline Usage &amp; Billing</h2>
          <p>
            Monitor Azure spending alongside Data Factory execution activity.
          </p>
        </div>

        <div
          className="usage-actions"
          style={{ display: "flex", gap: 10, flexWrap: "wrap" }}
        >
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

          <button
            type="button"
            onClick={loadData}
            disabled={loading}
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>
      </div>

      {error && (
        <div className="usage-error" role="alert">
          {error}
        </div>
      )}

      {(data?.stale || data?.warning) && (
        <div className="usage-footnote" role="status">
          {data.warning || "Showing cached data while the billing service recovers."}
        </div>
      )}

      {loading && !data && (
        <div className="usage-loading">
          Loading usage and billing data...
        </div>
      )}

      {data && (
        <>
          {/* Summary cards */}
          <div className="usage-summary-grid">
            <SummaryCard
              title="Recorded cost"
              value={money(summary.recorded_cost_inr)}
              detail={
                period.days_with_cost_records == null
                  ? "Billing record count unavailable"
                  : `${period.days_with_cost_records} days with cost records`
              }
              accent="#6478f5"
            />

            <SummaryCard
              title="Pipeline runs"
              value={formatNumber(summary.pipeline_runs)}
              detail={`Selected ${days}-day window`}
              accent="#10b981"
            />

            <SummaryCard
              title="Succeeded"
              value={formatNumber(totalSucceeded)}
              detail="From daily pipeline records"
              accent="#16a085"
            />

            <SummaryCard
              title="Failed"
              value={formatNumber(totalFailed)}
              detail="Review failed pipeline executions"
              accent="#ef4444"
            />
          </div>

          {/* API connection status */}
          <div
            className="usage-summary-grid"
            style={{ marginTop: 14 }}
          >
            <SummaryCard
              title="Billing API"
              value={
                data.billing_status === "working"
                  ? "Connected"
                  : "Unavailable"
              }
              detail="Azure Cost Management"
              accent={
                data.billing_status === "working"
                  ? "#10b981"
                  : "#ef4444"
              }
            />

            <SummaryCard
              title="Pipeline API"
              value={
                data.pipeline_status === "working"
                  ? "Connected"
                  : "Unavailable"
              }
              detail="Azure Data Factory"
              accent={
                data.pipeline_status === "working"
                  ? "#10b981"
                  : "#ef4444"
              }
            />
          </div>


          {/* Daily records table */}
          <article className="usage-panel">
            <div className="usage-panel-heading">
              <h3>Daily usage assessment</h3>
              <p>
                Costs and execution counts returned by the backend.
              </p>
            </div>

            <div
              className="table-container"
              style={{ overflowX: "auto" }}
            >
                <table className="data-table">
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
                              <td>{row.date}</td>
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
                                {row.cost_reason ||
                                  "No explanation available."}
                              </td>
                              <td>
                                {row.usage_reason ||
                                  "No explanation available."}
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

          {/* Anomaly and assessment explanations */}
          <article className="usage-panel">
            <div className="usage-panel-heading">
              <h3>Why did this happen?</h3>
              <p>
                Assessments are based on the billing and pipeline data
                returned by Azure and the backend thresholds.
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
                    <strong>{row.date}</strong>

                    <div className="usage-reason-statuses">
                      <Status value={row.cost_level} />
                      <Status value={row.usage_level} />

                      {(row.failed || 0) > 0 && (
                        <Status value="failed" />
                      )}
                    </div>

                    <p>
                      {row.relationship_reason ||
                        "Review the billing and pipeline records for this date."}
                    </p>

                    {row.cost_reason && <p>{row.cost_reason}</p>}

                    {row.usage_reason && <p>{row.usage_reason}</p>}

                    {(row.failed || 0) > 0 && (
                      <p>
                        {formatNumber(row.failed)} pipeline run(s) failed.
                        Inspect the corresponding Azure Data Factory run
                        details to identify the cause.
                      </p>
                    )}
                  </div>
                ))
              ) : (
                <p>
                  No heavy or unknown days, or failed runs, were detected
                  using the returned data and configured thresholds.
                </p>
              )}
            </div>
          </article>

          {data.note && (
            <p className="usage-footnote">{data.note}</p>
          )}

          {data.scope && (
            <p className="usage-footnote">
              Billing scope: {data.scope}
            </p>
          )}
        </>
      )}
    </section>
  );
}
