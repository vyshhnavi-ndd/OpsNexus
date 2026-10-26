import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  RefreshCw, ChevronDown, ChevronRight, Search, CheckCircle2,
  Clock3, Activity, CalendarClock, UserRound, AlertCircle,
  Wrench, X, Bell
} from "lucide-react";
const API_URL = "http://127.0.0.1:5000/api/adf";
const POLL_MS = 15000;

function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatDuration(ms) {
  if (ms == null || !Number.isFinite(Number(ms))) return "—";
  const seconds = Number(ms) / 1000;
  return seconds >= 60
    ? `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
    : `${seconds.toFixed(2)}s`;
}

function triggerLabel(run) {
  const type = run.invoked_by?.invokedByType || run.invokedBy?.invokedByType;
  if (type === "Manual") return "Manual";
  if (type === "ScheduleTrigger") return "Scheduled";
  if (["BlobEventsTrigger", "CustomEventsTrigger"].includes(type)) return "Event-triggered";
  if (type === "TumblingWindowTrigger") return "Tumbling window";
  return type || run.trigger_name || "Unknown";
}

function StatusBadge({ status }) {
  const normalized = (status || "Unknown").toLowerCase();
  const className =
    normalized === "succeeded" ? "run-status success" :
    normalized === "failed" ? "run-status failed" :
    ["inprogress", "queued"].includes(normalized) ? "run-status running" :
    normalized === "cancelled" ? "run-status cancelled" : "run-status unknown";
  return <span className={className}>{status || "Unknown"}</span>;
}

function getActivityError(activity) {
  if (!activity) return "";
  const err = activity.error;
  if (typeof err === "string") return err;
  return err?.message || err?.failureType || err?.errorCode || "";
}

function ErrorPreview({ diagnostic }) {
  if (!diagnostic) return null;
  const rows = [
    ["Pipeline / activity", diagnostic.activity_name || diagnostic.pipeline_name || "Not provided"],
    ["Error code", diagnostic.error_code || "Not returned by Azure"],
    ["Observed error", diagnostic.error_message || "No detailed error message was returned."],
    ["Likely cause", diagnostic.likely_cause || "The available logs are not sufficient to confirm the root cause."],
    ["Recommended solution", diagnostic.recommended_solution || "Open the linked activity output in Azure Data Factory and inspect the complete error details."],
    ["Next action", diagnostic.next_action || "Validate the source, sink, credentials, schema, and Integration Runtime, then rerun."]
  ];
  return (
    <div className="diagnostic-preview">
      <div className="diagnostic-title">
        <div>
          <h4>Error explanation & solution</h4>
          <p>Based on the error details returned by Azure. Likely causes are suggestions, not confirmed root causes.</p>
        </div>
        <span className="diagnostic-tag">Top preview</span>
      </div>
      <div className="diagnostic-table-wrap">
        <table className="diagnostic-table">
          <thead><tr><th>Field</th><th>Details</th></tr></thead>
          <tbody>
            {rows.map(([label, value]) => (
              <tr key={label}><th scope="row">{label}</th><td>{value}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function PipelineTable({ runs = [], loading = false, error = "", onRefresh }) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [triggerFilter, setTriggerFilter] = useState("All");
  const [expanded, setExpanded] = useState({});
  const [activityData, setActivityData] = useState({});
  const [activityLoading, setActivityLoading] = useState({});
  const [activityErrors, setActivityErrors] = useState({});
  const [diagnostics, setDiagnostics] = useState({});
  const [diagnosticLoading, setDiagnosticLoading] = useState({});
  const [failureAlerts, setFailureAlerts] = useState([]);
  const [failureAlertError, setFailureAlertError] = useState("");
  const [toasts, setToasts] = useState([]);
  const seenFailureIds = useRef(new Set());
  const toastCounter = useRef(0);

  function pushToast(message, kind = "error") {
    const id = ++toastCounter.current;
    setToasts((old) => [...old, { id, message, kind }].slice(-4));
    window.setTimeout(() => {
      setToasts((old) => old.filter((toast) => toast.id !== id));
    }, 7000);
  }

  useEffect(() => {
    let active = true;
    async function loadFailureAlerts() {
      try {
        const response = await fetch(`${API_URL}/failure-alerts?hours=24`, { cache: "no-store" });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || "Unable to retrieve pipeline alerts");
        if (!active) return;

        const failures = data.failures || [];
        setFailureAlerts(failures);
        setFailureAlertError("");

        // Only toast a failure once per run ID during this page session.
        for (const failure of failures) {
          const id = failure.run_id || `${failure.pipeline_name}-${failure.run_end}`;
          if (!seenFailureIds.current.has(id)) {
            seenFailureIds.current.add(id);
            pushToast(`Pipeline failed: ${failure.pipeline_name || "Unnamed pipeline"}`, "error");
          }
        }
      } catch (err) {
        if (active) setFailureAlertError(err.message || "Unable to refresh failure alerts");
      }
    }
    loadFailureAlerts();
    const intervalId = window.setInterval(loadFailureAlerts, POLL_MS);
    return () => { active = false; window.clearInterval(intervalId); };
  }, []);

  useEffect(() => {
    setExpanded({});
    setActivityData({});
    setActivityErrors({});
    setDiagnostics({});
  }, [runs]);

  const filteredRuns = useMemo(() => {
    const query = search.trim().toLowerCase();
    return runs.filter((run) => {
      const name = run.pipeline_name || "Unnamed pipeline";
      const trigger = triggerLabel(run);
      const status = run.status || "Unknown";
      const matchesSearch = !query || `${name} ${trigger} ${status} ${run.run_id || ""}`.toLowerCase().includes(query);
      return matchesSearch &&
        (statusFilter === "All" || status === statusFilter) &&
        (triggerFilter === "All" || trigger === triggerFilter);
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
      const response = await fetch(`${API_URL}/debug-run/${encodeURIComponent(runId)}`, { cache: "no-store" });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || "Unable to load activity logs");
      setActivityData((old) => ({ ...old, [runId]: data.pipeline?.activities || [] }));
      if (data.pipeline?.activity_log_error) {
        setActivityErrors((old) => ({ ...old, [runId]: data.pipeline.activity_log_error }));
      }
    } catch (err) {
      setActivityErrors((old) => ({ ...old, [runId]: err.message || "Unable to load activity logs" }));
    } finally {
      setActivityLoading((old) => ({ ...old, [runId]: false }));
    }
  }
  

  async function explainFailure(run, activity = null) {
    const runId = run.run_id;
    const key = `${runId}:${activity?.activityRunId || activity?.activityName || "pipeline"}`;
    if (diagnostics[key]) return;
    setDiagnosticLoading((old) => ({ ...old, [key]: true }));
    try {
      const response = await fetch(`${API_URL}/explain-error`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          run_id: runId,
          pipeline_name: run.pipeline_name,
          pipeline_status: run.status,
          pipeline_message: run.message || "",
          activity: activity ? {
            activity_name: activity.activityName,
            activity_type: activity.activityType,
            status: activity.status,
            error: activity.error || null,
            output: activity.output || null,
            activity_run_id: activity.activityRunId
          } : null
        })
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || "Could not explain this error");
      setDiagnostics((old) => ({ ...old, [key]: data.diagnostic }));
    } catch (err) {
      pushToast(err.message || "Unable to generate error explanation", "error");
    } finally {
      setDiagnosticLoading((old) => ({ ...old, [key]: false }));
    }
  }

  const uniqueStatuses = [...new Set(runs.map((r) => r.status).filter(Boolean))];
  const triggerTypes = [...new Set(runs.map(triggerLabel))];

  if (loading && runs.length === 0) return <div className="pipeline-state">Loading live Azure pipeline runs…</div>;

  return (
    <section className="pipeline-table-card">
      <div className="pipeline-table-toolbar">
        <div><h2>Pipeline execution history</h2><p>Live Azure Data Factory runs and activity logs</p></div>
        <button type="button" className="pipeline-refresh" onClick={onRefresh} disabled={loading}>
          <RefreshCw size={15} className={loading ? "spin" : ""} /> Refresh
        </button>
      </div>

      <div className="pipeline-filters">
        <label className="pipeline-search"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search pipeline, run ID, trigger…" /></label>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Filter by status">
          <option value="All">All statuses</option>{uniqueStatuses.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={triggerFilter} onChange={(e) => setTriggerFilter(e.target.value)} aria-label="Filter by trigger">
          <option value="All">All trigger types</option>{triggerTypes.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <span className="pipeline-result-count">{filteredRuns.length} of {runs.length} runs</span>
      </div>

      {error && <div className="pipeline-error">{error}</div>}
      {failureAlertError && <div className="pipeline-error"><AlertCircle size={17} /> Unable to refresh failure alerts: {failureAlertError}</div>}

      {failureAlerts.length > 0 && (
        <section className="pipeline-failure-alert" role="region" aria-label="Recent pipeline failures">
          <div className="pipeline-failure-alert-heading"><AlertCircle size={22} /><div><h3>Pipeline failure alerts</h3><p>{failureAlerts.length} failed run(s) detected in the last 24 hours.</p></div></div>
          <div className="pipeline-failure-alert-list">
            {failureAlerts.map((failure) => (
              <div className="pipeline-failure-alert-item" key={failure.run_id}>
                <div><strong>{failure.pipeline_name || "Unnamed pipeline"}</strong><span className="pipeline-run-id">Run ID: {failure.run_id || "Unavailable"}</span><p>{failure.message || "Pipeline execution failed."}</p><small>Failed at: {formatTime(failure.run_end)}</small></div>
                <StatusBadge status={failure.status} />
              </div>
            ))}
          </div>
        </section>
      )}

      {!error && runs.length === 0 && !loading && <div className="pipeline-state"><Activity size={24} /><strong>No pipeline runs returned</strong><span>Check the ADF factory, permissions, and selected history window.</span></div>}
      {runs.length > 0 && filteredRuns.length === 0 && <div className="pipeline-state">No runs match your filters.</div>}

      {filteredRuns.length > 0 && (
        <div className="pipeline-table-scroll">
          <table className="pipeline-table">
            <thead><tr><th>Pipeline / Run ID</th><th>Trigger</th><th>Status</th><th>Duration</th><th>Started</th><th>Finished</th><th>Activities</th><th></th></tr></thead>
            <tbody>
              {filteredRuns.map((run) => {
                const runId = run.run_id;
                const activities = activityData[runId] || [];
                const isExpanded = Boolean(expanded[runId]);
                const isFailed = (run.status || "").toLowerCase() === "failed";
                return (
                  <React.Fragment key={runId}>
                    <tr>
                      <td><strong>{run.pipeline_name || "Unnamed pipeline"}</strong><span className="pipeline-run-id">{runId || "No run ID"}</span></td>
                      <td><span className="trigger-chip">{triggerLabel(run) === "Manual" ? <UserRound size={14} /> : <CalendarClock size={14} />}{triggerLabel(run)}</span>{run.trigger_name && run.trigger_name !== "Manual" && <span className="pipeline-trigger-name">{run.trigger_name}</span>}</td>
                      <td><StatusBadge status={run.status} /></td>
                      <td className="pipeline-duration">{formatDuration(run.duration_in_ms)}</td><td>{formatTime(run.run_start)}</td><td>{formatTime(run.run_end)}</td><td>{run.activity_count == null ? "Load on demand" : run.activity_count}</td>
                      <td><button type="button" className="pipeline-expand" onClick={() => toggleRow(run)} disabled={!runId} aria-expanded={isExpanded}>{isExpanded ? <ChevronDown size={17} /> : <ChevronRight size={17} />}{isExpanded ? "Hide" : "Logs"}</button></td>
                    </tr>
                    {isExpanded && (
                      <tr className="pipeline-detail-row"><td colSpan={8}>
                        <div className="pipeline-activity-panel">
                          <div className="activity-panel-heading"><div><h3>Execution details</h3><p>Run ID: {runId}</p></div><span>{run.parameters ? Object.keys(run.parameters).length : 0} parameters</span></div>
                          {run.message && <div className="pipeline-error">{run.message}</div>}
                          {isFailed && <div className="failure-action-row"><div><strong>This pipeline failed</strong><p>Open the diagnostic preview to see the error, likely cause, and recommended solution.</p></div><button className="explain-button" type="button" onClick={() => explainFailure(run)} disabled={diagnosticLoading[`${runId}:pipeline`]}><Wrench size={15} />{diagnosticLoading[`${runId}:pipeline`] ? "Analyzing…" : "Explain Error & Solution"}</button></div>}
                          <ErrorPreview diagnostic={diagnostics[`${runId}:pipeline`]} />
                          {activityLoading[runId] ? <div className="pipeline-state">Loading activity logs…</div> :
                           activityErrors[runId] ? <div className="pipeline-error"><AlertCircle size={16} />{activityErrors[runId]}</div> :
                           activities.length === 0 ? <div className="pipeline-state"><Activity size={20} />No activity records returned for this run.</div> : (
                            <div className="pipeline-table-scroll"><table className="pipeline-table activity-table">
                              <thead><tr><th>Activity</th><th>Type</th><th>Status</th><th>Started</th><th>Finished</th><th>Duration</th><th>Error / solution</th></tr></thead>
                              <tbody>{activities.map((activity, index) => {
                                const failed = (activity.status || "").toLowerCase() === "failed";
                                const key = `${runId}:${activity.activityRunId || activity.activityName || "pipeline"}`;
                                return <React.Fragment key={activity.activityRunId || `${activity.activityName}-${index}`}>
                                  <tr><td>{activity.activityName || "—"}</td><td>{activity.activityType || "—"}</td><td><StatusBadge status={activity.status} /></td><td>{formatTime(activity.activityRunStart)}</td><td>{formatTime(activity.activityRunEnd)}</td><td>{formatDuration(activity.durationInMs)}</td><td>{getActivityError(activity) || "—"}{failed && <div><button className="explain-button small" type="button" onClick={() => explainFailure(run, activity)} disabled={diagnosticLoading[key]}><Wrench size={13} />{diagnosticLoading[key] ? "Analyzing…" : "Explain & fix"}</button></div>}</td></tr>
                                  {diagnostics[key] && <tr><td colSpan={7}><ErrorPreview diagnostic={diagnostics[key]} /></td></tr>}
                                </React.Fragment>;
                              })}</tbody>
                            </table></div>
                          )}
                          {run.parameters && Object.keys(run.parameters).length > 0 && <details className="pipeline-parameters"><summary>View pipeline parameters</summary><pre>{JSON.stringify(run.parameters, null, 2)}</pre></details>}
                        </div>
                      </td></tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="pipeline-table-footer"><span><CheckCircle2 size={14} /> Live ADF execution data</span><span><Clock3 size={14} /> Times shown in your local timezone</span></div>

      <div className="toast-stack" aria-live="polite" aria-atomic="false">
        {toasts.map((toast) => <div className={`pipeline-toast ${toast.kind}`} key={toast.id} role="status"><Bell size={17} /><span>{toast.message}</span><button type="button" aria-label="Dismiss notification" onClick={() => setToasts((old) => old.filter((t) => t.id !== toast.id))}><X size={15} /></button></div>)}
      </div>
    </section>
  );
}
