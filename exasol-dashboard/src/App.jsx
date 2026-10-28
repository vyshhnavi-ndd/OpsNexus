import React, { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Database,
  FileText,
  LayoutDashboard,
  MessageSquare,
  RefreshCw,
  Server,
  ShieldCheck,
  Wallet,
  X,
  XCircle,
  Zap,
} from "lucide-react";
import ExasolDatabase from "./pages/ExasolDatabase";
import TrustCard from "./components/TrustCard";
import "./App.css";
import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";
import Metric from "./components/Metric";
import Badge from "./components/Badge";
import Card from "./components/Card";
import SectionTitle from "./components/SectionTitle";
import PipelineTable from "./components/PipelineTable";
import ChatPage from "./pages/ChatPage";
import RequestsPage from "./pages/RequestsPage";
import UsageBillingDashboard from "./components/UsageBillingDashboard";

const API = "http://127.0.0.1:5000/api";
const DEFAULT_SCHEMA = "HACKATHON";
const DEFAULT_HISTORY_DAYS = 7;

// Share simultaneous GET requests (including React StrictMode's development replay).
const inFlightGets = new Map();
function getDeduplicated(url, config = {}) {
  const key = `${url}?${JSON.stringify(config.params || {})}`;
  if (inFlightGets.has(key)) return inFlightGets.get(key);
  const request = axios.get(url, config).finally(() => inFlightGets.delete(key));
  inFlightGets.set(key, request);
  return request;
}
const NAV = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "pipelines", label: "Pipeline Reliability", icon: Activity },
  { id: "trust", label: "Data Trust", icon: ShieldCheck },
  { id: "cost", label: "Cost Intelligence", icon: Wallet },
  { id: "chat", label: "Data Assistant", icon: MessageSquare },
  { id: "requests", label: "Data Requests", icon: FileText },
  { id: "database", label: "Exasol Database", icon: Database },
];

const EMPTY_REQUEST_FORM = {
  dataset: "",
  reason: "",
  priority: "Medium",
};

const INITIAL_MESSAGES = [
  {
    role: "assistant",
    text: "Hello! Ask me about pipeline failures, dataset trust, platform costs, or data requests.",
  },
];

function formatNumber(value, digits = 0) {
  if (value == null || value === "" || !Number.isFinite(Number(value))) {
    return "—";
  }

  return Number(value).toLocaleString("en-IN", {
    maximumFractionDigits: digits,
  });
}

function formatPercent(value) {
  return value == null || value === "" ? "—" : `${formatNumber(value, 1)}%`;
}

function getErrorMessage(error, fallback) {
  return (
    error?.response?.data?.error ||
    error?.response?.data?.message ||
    error?.message ||
    fallback

  );
}

function countRuns(runs) {
  const successful = runs.filter((run) => run.status === "Succeeded").length;
  const failed = runs.filter((run) => run.status === "Failed").length;
  const running = runs.filter((run) =>
    ["InProgress", "Queued", "Waiting"].includes(run.status)
  ).length;

  return {
    total: runs.length,
    successful,
    failed,
    running,
    successRate: runs.length ? (successful / runs.length) * 100 : null,
  };
}

function countTriggerType(runs, type) {
  return runs.filter((run) => run.invoked_by?.invokedByType === type).length;
}

export default function App() {
  const [page, setPage] = useState("overview");
  const [theme, setTheme] = useState(() => localStorage.getItem("exasol-theme") || "light");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [search, setSearch] = useState("");

  const [apiState, setApiState] = useState("checking");
  const [apiError, setApiError] = useState("");
  const [notice, setNotice] = useState("");

  const [busy, setBusy] = useState(false);
  const [historyDays, setHistoryDays] = useState(DEFAULT_HISTORY_DAYS);

  const [adfRuns, setAdfRuns] = useState([]);
  const [adfLoading, setAdfLoading] = useState(false);
  const [adfError, setAdfError] = useState("");

  const [overview, setOverview] = useState(null);
  const [trustMetrics, setTrustMetrics] = useState(null);
  const [costMetrics, setCostMetrics] = useState(null);
  const [tableList, setTableList] = useState([]);

  const [requests, setRequests] = useState([]);
  const [requestForm, setRequestForm] = useState(EMPTY_REQUEST_FORM);

  const [messages, setMessages] = useState(INITIAL_MESSAGES);
  const [chatText, setChatText] = useState("");
  const [chatBusy, setChatBusy] = useState(false);

  const pipelineMetrics = useMemo(() => countRuns(adfRuns), [adfRuns]);
  const pageTitle = NAV.find((item) => item.id === page)?.label || "Overview";


  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("exasol-theme", theme);
  }, [theme]);

  const loadAdfRuns = useCallback(async () => {
    setAdfLoading(true);
    setAdfError("");

    try {
      const response = await getDeduplicated(`${API}/adf/debug-runs`, {
        params: { days: historyDays },
        timeout: 60000,
      });

      if (!response.data?.success) {
        throw new Error(
          response.data?.error || "Azure Data Factory did not return pipeline runs."
        );
      }

      setAdfRuns(
        Array.isArray(response.data.pipelines) ? response.data.pipelines : []
      );
    } catch (error) {
      // Keep the last successful run list visible if a refresh fails.
      setAdfError(
        getErrorMessage(error, "Unable to retrieve Azure Data Factory runs.")
      );
    } finally {
      setAdfLoading(false);
    }
  }, [historyDays]);

  const loadPlatformData = useCallback(async () => {
    setBusy(true);
    setApiError("");

    try {
      const results = await Promise.allSettled([
        getDeduplicated(`${API}/health`, { timeout: 6000 }),
        getDeduplicated(`${API}/metrics/overview`, { timeout: 8000 }),
        getDeduplicated(`${API}/trust/metrics`, { timeout: 8000 }),
        getDeduplicated(`${API}/metrics/cost`, { timeout: 65000 }),
        getDeduplicated(`${API}/tables`, { timeout: 8000 }),
      ]);

      const [healthResult, overviewResult, trustResult, costResult, tablesResult] =
        results;

      const connected =
        healthResult.status === "fulfilled" &&
        Boolean(healthResult.value.data?.connected);

      setApiState(connected ? "connected" : "offline");

      if (!connected) {
        setApiError(
          healthResult.status === "rejected"
            ? getErrorMessage(
              healthResult.reason,
              "Cannot reach Flask or confirm the Exasol connection."
            )
            : "The Flask health endpoint did not confirm an Exasol connection."
        );
      }

      if (
        overviewResult.status === "fulfilled" &&
        overviewResult.value.data?.success
      ) {
        setOverview(overviewResult.value.data);
      }
      // Retain the last successful values when an individual endpoint temporarily fails.

      // Accept either direct trust JSON or a wrapped Flask response.
      if (trustResult.status === "fulfilled") {
        const payload = trustResult.value.data;

        const trustData =
          payload?.metrics ??
          payload?.trust_metrics ??
          payload?.data?.metrics ??
          payload?.data ??
          payload;

        if (trustData && typeof trustData === "object") {
          console.log("Trust API response:", payload);
          console.log("Trust metrics passed to component:", trustData);

          setTrustMetrics(trustData);
        }
      } else {
        console.error(
          "Trust API request failed:",
          getErrorMessage(
            trustResult.reason,
            "Unable to load trust metrics."
          )
        );
      }
      if (
        costResult.status === "fulfilled" &&
        (costResult.value.data?.success !== false)
      ) {
        const costResponse = costResult.value.data || {};
        // The current Flask API returns cost_data as an array of Azure billing rows.
        // Derive only metrics supported by that response; do not invent usage units.
        const costPayload =
          costResponse.metrics ??
          costResponse.data?.metrics ??
          costResponse.data ??
          null;

        if (costPayload && !Array.isArray(costPayload)) {
          setCostMetrics(costPayload);
        } else if (Array.isArray(costResponse.cost_data)) {
          const rows = costResponse.cost_data;
          const totalCost = rows.reduce(
            (sum, row) => sum + (Number(row?.PreTaxCost) || 0),
            0
          );
          const currencies = [...new Set(
            rows.map((row) => row?.Currency).filter(Boolean)
          )];

          setCostMetrics({
            total_cost: totalCost,
            total_usage: null,
            cost_per_usage_unit: null,
            currency: currencies.length === 1 ? currencies[0] : null,
            record_count: rows.length,
            cost_data: rows,
            period: costResponse.period || null,
            scope: costResponse.scope || null,
          });
        } else if (costResponse.success && (
          costResponse.total_cost != null ||
          costResponse.total_usage != null ||
          costResponse.cost_per_usage_unit != null
        )) {
          setCostMetrics(costResponse);
        }
      }

      if (
        tablesResult.status === "fulfilled" &&
        tablesResult.value.data?.success
      ) {
        setTableList(
          Array.isArray(tablesResult.value.data.tables)
            ? tablesResult.value.data.tables
            : []
        );
      }
    } catch (error) {
      setApiState("offline");
      setApiError(getErrorMessage(error, "Unable to load platform metrics."));
    } finally {
      setBusy(false);
    }
  }, []);
  const refreshAll = useCallback(async () => {
    await Promise.all([loadPlatformData(), loadAdfRuns()]);
  }, [loadPlatformData, loadAdfRuns]);


  useEffect(() => {
    loadPlatformData();
  }, [loadPlatformData]);

  useEffect(() => {
    if (page === "database") {
      console.info("ExasolDatabase page mounted");
    }
  }, [page]);

  useEffect(() => {
    loadAdfRuns();
  }, [loadAdfRuns]);

  // Load persisted requests if the backend exposes GET /api/requests.
  useEffect(() => {
    let active = true;
    getDeduplicated(`${API}/requests`, { timeout: 8000 })
      .then((response) => {
        if (!active) return;
        const payload = response.data;
        const rows = Array.isArray(payload)
          ? payload
          : Array.isArray(payload?.requests)
            ? payload.requests
            : Array.isArray(payload?.data)
              ? payload.data
              : null;
        if (rows) {
          setRequests(rows.map((item, index) => ({
            id: item.id ?? item.request_id ?? `REQ-${index + 1}`,
            dataset: item.dataset ?? item.dataset_id ?? item.dataset_name ?? "—",
            reason: item.reason ?? item.business_justification ?? "",
            priority: item.priority ?? "Medium",
            status: item.status ?? "Pending",
          })));
        }
      })
      .catch(() => {
        // GET may not be implemented; keep the in-session list without disrupting the app.
      });
    return () => { active = false; };
  }, []);

  function switchPage(nextPage) {
    setPage(nextPage);
    setMobileOpen(false);
    setSearch("");
    setNotice("");
  }

  async function submitRequest(event) {
    event.preventDefault();

    const dataset = requestForm.dataset.trim();
    const reason = requestForm.reason.trim();

    if (!dataset || !reason) {
      setNotice("Enter both a dataset and a business justification.");
      return;
    }

    try {
      const response = await axios.post(
        `${API}/requests`,
        {
          requester: "app.user",
          dataset_id: dataset,
          business_justification: reason,
          priority: requestForm.priority,
        },
        { timeout: 10000 }
      );

      const record = {
        id: response.data?.request_id || `REQ-${Date.now()}`,
        dataset,
        reason,
        priority: requestForm.priority,
        status: response.data?.status || "Pending",
      };

      setRequests((current) => [record, ...current]);
      setNotice("Data request submitted successfully.");
      setRequestForm(EMPTY_REQUEST_FORM);
    } catch (error) {
      setNotice(
        `Request was not submitted: ${getErrorMessage(
          error,
          "The request API is unavailable."
        )}`
      );
    }
  }

  async function sendChat(event) {
    event.preventDefault();

    const question = chatText.trim();
    if (!question || chatBusy) return;

    setMessages((current) => [...current, { role: "user", text: question }]);
    setChatText("");
    setChatBusy(true);

    try {
      const response = await axios.post(
        `${API}/rag/query`,
        { question },
        { timeout: 30000 }
      );

      const answer =
        response.data?.answer ||
        response.data?.message ||
        "The assistant returned an empty response.";

      setMessages((current) => [
        ...current,
        { role: "assistant", text: answer },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: `Unable to reach the chat API: ${getErrorMessage(
            error,
            "Check POST /api/rag/query and confirm Ollama and Exasol are available."
          )}`,
        },
      ]);
    } finally {
      setChatBusy(false);
    }
  }

  const visibleRequests = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return requests;

    return requests.filter((request) =>
      `${request.id} ${request.dataset} ${request.reason} ${request.status}`
        .toLowerCase()
        .includes(query)
    );
  }, [requests, search]);

  const trustScore =
    trustMetrics?.trust_score ??
    trustMetrics?.tables?.trust_scores?.avg_trust_score ??
    null;

  const totalCost = costMetrics?.total_cost ?? null;
  const totalUsage = costMetrics?.total_usage ?? null;
  const costPerUsageUnit = costMetrics?.cost_per_usage_unit ?? null;

  const schema = overview?.schema || DEFAULT_SCHEMA;
  const tableCount = overview?.table_count ?? tableList.length;

  return (
    <div className="app-shell">
      <Sidebar
        nav={NAV}
        page={page}
        switchPage={switchPage}
        mobileOpen={mobileOpen}
        failedRuns={pipelineMetrics.failed}
        apiState={apiState}
        schema={schema}
        tableCount={tableCount}
      />

      <main className="main">
        <Topbar
          title={pageTitle}
          search={search}
          setSearch={setSearch}
          onRefresh={refreshAll}
          busy={busy || adfLoading}
          onMenu={() => setMobileOpen((open) => !open)}
          mobileOpen={mobileOpen}
          onChat={() => switchPage("chat")}
          theme={theme}
          onToggleTheme={() => setTheme((current) => current === "light" ? "dark" : "light")}
        />

        <div className="content">
          {apiError && (
            <div className="notice">
              <strong>Exasol connection:</strong> {apiError}
            </div>
          )}

          {adfError && page !== "pipelines" && (
            <div className="notice">
              <strong>ADF pipeline data:</strong> {adfError}
            </div>
          )}

          {notice && (
            <div className="notice">
              {notice}
              <button
                type="button"
                className="notice-close"
                aria-label="Dismiss notification"
                onClick={() => setNotice("")}
              >
                <X size={14} />
              </button>
            </div>
          )}

          <div className="page-intro">
            <div>
              <h1>
                {page === "overview" ? "DataOps at a glance" : pageTitle}
              </h1>
              <p>
                {{
                  overview:
                    "Monitor live pipeline reliability and available platform metrics.",
                  pipelines:
                    "Inspect manual and triggered Azure Data Factory executions.",
                  trust:
                    "Review trust metrics and the live Exasol schema inventory.",
                  cost:
                    "Review cost and usage metrics returned by the backend.",
                  chat:
                    "Ask questions about pipeline runs and enterprise data.",
                  requests:
                    "Create and review data requests in this session.",
                  database:
                    "Browse schemas, inspect columns, and review Exasol records.",
                }[page]}
              </p>
            </div>

            <div className="actions">
              <button
                type="button"
                className="btn"
                onClick={refreshAll}
                disabled={busy || adfLoading}
              >
                <RefreshCw
                  size={14}
                  className={busy || adfLoading ? "spin" : ""}
                />
                Refresh
              </button>

              {!["chat", "requests"].includes(page) && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => switchPage("chat")}
                >
                  <MessageSquare size={14} />
                  Ask assistant
                </button>
              )}
            </div>
          </div>

          {page === "overview" && (
            <>
              <div className="grid metrics-grid">
                <Metric
                  label="Pipeline success rate"
                  value={formatPercent(pipelineMetrics.successRate)}
                  hint={`${formatNumber(pipelineMetrics.successful)} successful runs`}
                  icon={Activity}
                  color="green"
                />
                <Metric
                  label="Failed pipeline runs"
                  value={formatNumber(pipelineMetrics.failed)}
                  hint="From the selected ADF history window"
                  icon={AlertTriangle}
                  color="red"
                />
                <Metric
                  label="Average trust score"
                  value={formatPercent(trustScore)}
                  hint="Live trust metric, when available"
                  icon={ShieldCheck}
                  color="blue"
                />
                <Metric
                  label="Total recorded cost"
                  value={totalCost == null ? "—" : formatNumber(totalCost)}
                  hint={
                    totalUsage == null
                      ? "No live usage metric available"
                      : `${formatNumber(totalUsage)} usage units`
                  }
                  icon={Wallet}
                  color="orange"
                />
              </div>

              <div className="content-grid">
                <Card>
                  <SectionTitle
                    title="Pipeline reliability"
                    subtitle={`Live ADF runs over the last ${historyDays} days`}
                  />
                  <div className="health-list">
                    <div className="health-item">
                      <Activity size={17} />
                      <span>Total runs</span>
                      <strong>{formatNumber(pipelineMetrics.total)}</strong>
                    </div>
                    <div className="health-item">
                      <CheckCircle2 size={17} />
                      <span>Succeeded</span>
                      <strong>{formatNumber(pipelineMetrics.successful)}</strong>
                    </div>
                    <div className="health-item">
                      <XCircle size={17} />
                      <span>Failed</span>
                      <strong>{formatNumber(pipelineMetrics.failed)}</strong>
                    </div>
                    <div className="health-item">
                      <Clock3 size={17} />
                      <span>Currently running</span>
                      <strong>{formatNumber(pipelineMetrics.running)}</strong>
                    </div>
                  </div>
                </Card>

                <Card>
                  <SectionTitle
                    title="Platform connections"
                    subtitle="Current API connection checks"
                  />
                  <div className="health-list">
                    <div className="health-item">
                      <Server size={17} />
                      <span>Flask / Exasol</span>
                      <Badge>
                        {apiState === "connected"
                          ? "Connected"
                          : apiState === "checking"
                            ? "Checking"
                            : "Unavailable"}
                      </Badge>
                    </div>
                    <div className="health-item">
                      <Activity size={17} />
                      <span>Azure Data Factory</span>
                      <Badge>{adfError ? "Unavailable" : "Checked"}</Badge>
                    </div>
                    <div className="health-item">
                      <ShieldCheck size={17} />
                      <span>Trust metrics</span>
                      <strong>{trustScore == null ? "—" : formatPercent(trustScore)}</strong>
                    </div>
                    <div className="health-item">
                      <Zap size={17} />
                      <span>Cost per usage unit</span>
                      <strong>{formatNumber(costPerUsageUnit, 4)}</strong>
                    </div>
                  </div>
                </Card>
              </div>

              <Card className="table-card">
                <SectionTitle
                  title="Recent pipeline executions"
                  subtitle="Latest real runs returned by Azure Data Factory"
                  action={
                    <button
                      type="button"
                      className="btn"
                      onClick={() => switchPage("pipelines")}
                    >
                      View all →
                    </button>
                  }
                />
                <PipelineTable
                  runs={adfRuns.slice(0, 5)}
                  loading={adfLoading}
                  error={adfError}
                  onRefresh={loadAdfRuns}
                />
              </Card>
            </>
          )}

          {page === "pipelines" && (
            <>
              <div className="pipeline-history-controls">
                <div>
                  <span className="live-indicator" />
                  Azure Data Factory
                  <span className="pipeline-window-label">
                    Execution history
                  </span>
                </div>

                <label>
                  History
                  <select
                    value={historyDays}
                    onChange={(event) =>
                      setHistoryDays(Number(event.target.value))
                    }
                  >
                    <option value={1}>Last 24 hours</option>
                    <option value={7}>Last 7 days</option>
                    <option value={30}>Last 30 days</option>
                    <option value={90}>Last 90 days</option>
                  </select>
                </label>
              </div>

              <div className="grid metrics-grid">
                <Metric
                  label="Total runs"
                  value={formatNumber(pipelineMetrics.total)}
                  hint="Runs returned by Azure"
                  icon={Activity}
                />
                <Metric
                  label="Succeeded"
                  value={formatNumber(pipelineMetrics.successful)}
                  hint="Completed successfully"
                  icon={CheckCircle2}
                  color="green"
                />
                <Metric
                  label="Failed"
                  value={formatNumber(pipelineMetrics.failed)}
                  hint="Requires investigation"
                  icon={XCircle}
                  color="red"
                />
                <Metric
                  label="Success rate"
                  value={formatPercent(pipelineMetrics.successRate)}
                  hint="Succeeded divided by total runs"
                  icon={Clock3}
                  color="blue"
                />
              </div>

              <div className="pipeline-status-strip">
                <div>
                  <span>Currently running</span>
                  <strong>{formatNumber(pipelineMetrics.running)}</strong>
                </div>
                <div>
                  <span>Manual executions</span>
                  <strong>{formatNumber(countTriggerType(adfRuns, "Manual"))}</strong>
                </div>
                <div>
                  <span>Scheduled executions</span>
                  <strong>{formatNumber(countTriggerType(adfRuns, "ScheduleTrigger"))}</strong>
                </div>
                <div>
                  <span>History window</span>
                  <strong>{historyDays} days</strong>
                </div>
              </div>

              <PipelineTable
                runs={adfRuns}
                loading={adfLoading}
                error={adfError}
                onRefresh={loadAdfRuns}
              />
            </>
          )}


          {page === "trust" && (
            <>
              <TrustCard metrics={trustMetrics || {}} />
            </>
          )}


          {page === "cost" && <UsageBillingDashboard />}

          {page === "database" && (
            <ExasolDatabase
              api={API}
              schemaDefault="HACKATHON"
            />
          )}

          {page === "chat" && (
            <ChatPage
              messages={messages}
              chatText={chatText}
              setChatText={setChatText}
              sendChat={sendChat}
              busy={chatBusy}
            />
          )}

          {page === "requests" && (
            <RequestsPage
              requests={visibleRequests}
              form={requestForm}
              setForm={setRequestForm}
              onSubmit={submitRequest}
              search={search}
            />
          )}

          <footer
            style={{
              marginTop: 26,
              display: "flex",
              justifyContent: "space-between",
              gap: 12,
              flexWrap: "wrap",
              color: "#9aa4b3",
              fontSize: 10,
            }}
          >
            <span>Exasol DataOps Intelligence · Local development</span>
            <span>
              {busy || adfLoading
                ? "Refreshing data…"
                : `Last checked: ${new Date().toLocaleTimeString()}`}
            </span>
          </footer>
        </div>
      </main>
    </div>
  );
}
