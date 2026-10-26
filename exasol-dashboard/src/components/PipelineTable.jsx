
import { Fragment, useEffect, useMemo, useState } from "react";
import {
  RefreshCw, ChevronDown, ChevronRight, Search,
  CheckCircle2, Clock3, Activity, CalendarClock,
  UserRound, AlertCircle
} from "lucide-react";

const API_URL = "/api/adf";

function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString();
}

function formatDuration(ms) {
  if (ms == null || !Number.isFinite(Number(ms))) return "—";
  const seconds = Number(ms) / 1000;
  return seconds >= 60
    ? `${Math.floor(seconds / 60)}m ${(seconds % 60).toFixed(0)}s`
    : `${seconds.toFixed(2)}s`;
}

function triggerLabel(run) {
  const type = run.invoked_by?.invokedByType;

  if (type === "Manual") return "Manual";
  if (type === "ScheduleTrigger") return "Scheduled";
  if (type === "BlobEventsTrigger" || type === "CustomEventsTrigger") {
    return "Event-triggered";
  }
  if (type === "TumblingWindowTrigger") return "Tumbling window";

  return type || run.trigger_name || "Unknown";
}

function StatusBadge({ status }) {
  const normalized = (status || "Unknown").toLowerCase();

  const className =
    normalized === "succeeded" ? "run-status success" :
    normalized === "failed" ? "run-status failed" :
    normalized === "inprogress" ? "run-status running" :
    normalized === "cancelled" ? "run-status cancelled" :
    "run-status unknown";

  return <span className={className}>{status || "Unknown"}</span>;
}

export default function PipelineTable({
  runs = [],
  loading = false,
  error = "",
  onRefresh,
}) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [triggerFilter, setTriggerFilter] = useState("All");
  const [expanded, setExpanded] = useState({});
  const [activityData, setActivityData] = useState({});
  const [activityLoading, setActivityLoading] = useState({});
  const [activityErrors, setActivityErrors] = useState({});

const [failureAlerts, setFailureAlerts] = useState([]);
const [failureAlertError, setFailureAlertError] = useState("");

useEffect(() => {
  let active = true;

  async function loadFailureAlerts() {
    try {
      const response = await fetch(
        `${API_URL}/failure-alerts?hours=24`,
        { cache: "no-store" }
      );

      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(
          data.error || "Unable to retrieve pipeline alerts"
        );
      }

      if (active) {
        setFailureAlerts(data.failures || []);
        setFailureAlertError("");
      }
    } catch (err) {
      if (active) {
        setFailureAlertError(err.message);
      }
    }
  }

  loadFailureAlerts();

  const intervalId = setInterval(loadFailureAlerts, 15000);

  return () => {
    active = false;
    clearInterval(intervalId);
  };
}, []);


  useEffect(() => {
    setExpanded({});
    setActivityData({});
    setActivityErrors({});
  }, [runs]);

  const filteredRuns = useMemo(() => {
    const query = search.trim().toLowerCase();

    return runs.filter((run) => {
      const name = run.pipeline_name || "Unnamed pipeline";
      const trigger = triggerLabel(run);
      const status = run.status || "Unknown";

      const matchesSearch =
        !query ||
        `${name} ${trigger} ${status} ${run.run_id || ""}`
          .toLowerCase()
          .includes(query);

      const matchesStatus =
        statusFilter === "All" || status === statusFilter;

      const matchesTrigger =
        triggerFilter === "All" || trigger === triggerFilter;

      return matchesSearch && matchesStatus && matchesTrigger;
    });
  }, [runs, search, statusFilter, triggerFilter]);

  async function toggleRow(run) {
    const runId = run.run_id;
    if (!runId) return;

    if (expanded[runId]) {
      setExpanded((old) => ({ ...old, [runId]: false }));
      return;
    }

    setExpanded((old) => ({ ...old, [runId]: true }));

    if (activityData[runId] || activityLoading[runId]) return;

    setActivityLoading((old) => ({ ...old, [runId]: true }));
    setActivityErrors((old) => ({ ...old, [runId]: "" }));

    try {
      const response = await fetch(
        `${API_URL}/debug-run/${encodeURIComponent(runId)}`
      );

      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.error || "Unable to load activity logs");
      }

      setActivityData((old) => ({
        ...old,
        [runId]: data.pipeline?.activities || [],
      }));

      if (data.pipeline?.activity_log_error) {
        setActivityErrors((old) => ({
          ...old,
          [runId]: data.pipeline.activity_log_error,
        }));
      }
    } catch (err) {
      setActivityErrors((old) => ({
        ...old,
        [runId]: err.message,
      }));
    } finally {
      setActivityLoading((old) => ({ ...old, [runId]: false }));
    }
  }

  const uniqueStatuses = [...new Set(runs.map((r) => r.status).filter(Boolean))];
  const triggerTypes = [...new Set(runs.map(triggerLabel))];

  if (loading && runs.length === 0) {
    return <div className="pipeline-state">Loading live Azure pipeline runs…</div>;
  }

  return (
    <section className="pipeline-table-card">
      <div className="pipeline-table-toolbar">
        <div>
          <h2>Pipeline execution history</h2>
          <p>Live Azure Data Factory runs and their activity logs</p>
        </div>

        <button
          type="button"
          className="pipeline-refresh"
          onClick={onRefresh}
          disabled={loading}
        >
          <RefreshCw size={15} className={loading ? "spin" : ""} />
          Refresh
        </button>
      </div>

      <div className="pipeline-filters">
        <label className="pipeline-search">
          <Search size={16} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search pipeline, run ID, trigger…"
          />
        </label>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          aria-label="Filter by status"
        >
          <option value="All">All statuses</option>
          {uniqueStatuses.map((status) => (
            <option key={status} value={status}>{status}</option>
          ))}
        </select>

        <select
          value={triggerFilter}
          onChange={(e) => setTriggerFilter(e.target.value)}
          aria-label="Filter by trigger"
        >
          <option value="All">All trigger types</option>
          {triggerTypes.map((trigger) => (
            <option key={trigger} value={trigger}>{trigger}</option>
          ))}
        </select>

        <span className="pipeline-result-count">
          {filteredRuns.length} of {runs.length} runs
        </span>
      </div>

      {error && <div className="pipeline-error">{error}</div>}

      {!error && runs.length === 0 && !loading && (
        <div className="pipeline-state">
          <Activity size={24} />
          <strong>No pipeline runs returned</strong>
          <span>Check the ADF factory, permissions, and selected history window.</span>
        </div>
      )}

      {runs.length > 0 && filteredRuns.length === 0 && (
        <div className="pipeline-state">No runs match your filters.</div>
      )}

{failureAlertError && (
  <div className="pipeline-error" role="status">
    <AlertCircle size={17} />
    Unable to refresh failure alerts: {failureAlertError}
  </div>
)}

{failureAlerts.length > 0 && (
  <section className="pipeline-failure-alert" role="alert">
    <div className="pipeline-failure-alert-heading">
      <AlertCircle size={22} />

      <div>
        <h3>
          Pipeline failure alert
          {failureAlerts.length > 1 ? "s" : ""}
        </h3>

        <p>
          {failureAlerts.length} failed pipeline run
          {failureAlerts.length > 1 ? "s" : ""} detected
          in the last 24 hours.
        </p>
      </div>
    </div>

    <div className="pipeline-failure-alert-list">
      {failureAlerts.map((failure) => (
        <div
          className="pipeline-failure-alert-item"
          key={failure.run_id}
        >
          <div>
            <strong>
              {failure.pipeline_name || "Unnamed pipeline"}
            </strong>

            <span className="pipeline-run-id">
              Run ID: {failure.run_id || "Unavailable"}
            </span>

            <p>
              {failure.message || "Pipeline execution failed."}
            </p>

            <small>
              Failed at: {formatTime(failure.run_end)}
            </small>
          </div>

          <StatusBadge status={failure.status} />
        </div>
      ))}
    </div>
  </section>
)}


      {filteredRuns.length > 0 && (
        <div className="pipeline-table-scroll">
          <table className="pipeline-table">
            <thead>
              <tr>
                <th>Pipeline / Run ID</th>
                <th>Trigger</th>
                <th>Status</th>
                <th>Duration</th>
                <th>Started</th>
                <th>Finished</th>
                <th>Activities</th>
                <th></th>
              </tr>
            </thead>

            <tbody>
              {filteredRuns.map((run) => {
                const runId = run.run_id;
                const activities = activityData[runId] || [];
                const isExpanded = Boolean(expanded[runId]);

                return (
                  <Fragment key={runId}>
                    <tr>
                      <td>
                        <strong>{run.pipeline_name || "Unnamed pipeline"}</strong>
                        <span className="pipeline-run-id">{runId || "No run ID"}</span>
                      </td>

                      <td>
                        <span className="trigger-chip">
                          {triggerLabel(run) === "Manual"
                            ? <UserRound size={14} />
                            : <CalendarClock size={14} />}
                          {triggerLabel(run)}
                        </span>
                        {run.trigger_name && run.trigger_name !== "Manual" && (
                          <span className="pipeline-trigger-name">{run.trigger_name}</span>
                        )}
                      </td>

                      <td><StatusBadge status={run.status} /></td>
                      <td className="pipeline-duration">
                        {formatDuration(run.duration_in_ms)}
                      </td>
                      <td>{formatTime(run.run_start)}</td>
                      <td>{formatTime(run.run_end)}</td>
                      <td>
                        {run.activity_count == null
                          ? "Load on demand"
                          : run.activity_count}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="pipeline-expand"
                          onClick={() => toggleRow(run)}
                          disabled={!runId}
                          aria-expanded={isExpanded}
                        >
                          {isExpanded
                            ? <ChevronDown size={17} />
                            : <ChevronRight size={17} />}
                          {isExpanded ? "Hide" : "Logs"}
                        </button>
                      </td>
                    </tr>

                    {isExpanded && (
                      <tr className="pipeline-detail-row">
                        <td colSpan={8}>
                          <div className="pipeline-activity-panel">
                            <div className="activity-panel-heading">
                              <div>
                                <h3>Execution details</h3>
                                <p>Run ID: {runId}</p>
                              </div>
                              <span>{run.parameters && Object.keys(run.parameters).length} parameters</span>
                            </div>

                            {run.message && (
                              <div className="pipeline-error">{run.message}</div>
                            )}

                            {activityLoading[runId] ? (
                              <div className="pipeline-state">Loading activity logs…</div>
                            ) : activityErrors[runId] ? (
                              <div className="pipeline-error">
                                <AlertCircle size={16} />
                                {activityErrors[runId]}
                              </div>
                            ) : activities.length === 0 ? (
                              <div className="pipeline-state">
                                <Activity size={20} />
                                No activity records returned for this run.
                              </div>
                            ) : (
                              <div className="pipeline-table-scroll">
                                <table className="pipeline-table activity-table">
                                  <thead>
                                    <tr>
                                      <th>Activity</th>
                                      <th>Type</th>
                                      <th>Status</th>
                                      <th>Started</th>
                                      <th>Finished</th>
                                      <th>Duration</th>
                                      <th>Error</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {activities.map((activity, index) => (
                                      <tr key={activity.activityRunId || `${activity.activityName}-${index}`}>
                                        <td>{activity.activityName || "—"}</td>
                                        <td>{activity.activityType || "—"}</td>
                                        <td><StatusBadge status={activity.status} /></td>
                                        <td>{formatTime(activity.activityRunStart)}</td>
                                        <td>{formatTime(activity.activityRunEnd)}</td>
                                        <td>{formatDuration(activity.durationInMs)}</td>
                                        <td>{activity.error?.message || "—"}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            )}

                            {run.parameters && Object.keys(run.parameters).length > 0 && (
                              <details className="pipeline-parameters">
                                <summary>View pipeline parameters</summary>
                                <pre>{JSON.stringify(run.parameters, null, 2)}</pre>
                              </details>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="pipeline-table-footer">
        <span><CheckCircle2 size={14} /> Live ADF execution data</span>
        <span><Clock3 size={14} /> Times shown in your local timezone</span>
      </div>
    </section>
  );
}
