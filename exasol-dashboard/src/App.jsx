import React, { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  Activity, ShieldCheck, Wallet, MessageSquare, Database, Bell, Search,
  RefreshCw, CheckCircle2, XCircle, Clock3, AlertTriangle, Menu, X, Server,
  Zap, FileText, LayoutDashboard, Settings2
} from "lucide-react";
import "./App.css";
import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";
import Metric from "./components/Metric";
import Badge from "./components/Badge";
import Card from "./components/Card";
import SectionTitle from "./components/SectionTitle";
import PipelineTable from "./components/PipelineTable";
import TrustCard from "./components/TrustCard";
import CostChart from "./components/CostChart";
import ExasolDatabase from "./pages/ExasolDatabase";
import ChatPage from "./pages/ChatPage";
import RequestsPage from "./pages/RequestsPage";

const API = "http://127.0.0.1:5000/api";
const NAV = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "pipelines", label: "Pipeline Reliability", icon: Activity },
  { id: "trust", label: "Data Trust", icon: ShieldCheck },
  { id: "cost", label: "Cost Intelligence", icon: Wallet },
  { id: "chat", label: "Data Assistant", icon: MessageSquare },
  { id: "requests", label: "Data Requests", icon: FileText },
  { id: "database", label: "Exasol Database", icon: Database }
];
const DEMO = {
  pipelines: [
    { name: "Customer ETL", source: "Azure Data Factory", status: "SUCCESS", duration: 142, time: "09:42", sla: "On time" },
    { name: "Sales Warehouse", source: "Exasol", status: "FAILED", duration: 310, time: "09:35", sla: "Breached" },
    { name: "Inventory Sync", source: "Azure Data Factory", status: "RUNNING", duration: 85, time: "09:30", sla: "On time" },
    { name: "Finance Aggregation", source: "Exasol", status: "SUCCESS", duration: 196, time: "09:15", sla: "On time" },
    { name: "Marketing Analytics", source: "Python ETL", status: "FAILED", duration: 422, time: "08:50", sla: "Breached" }
  ],
  trend: [
    { day: "Mon", success: 92, failures: 8 }, { day: "Tue", success: 96, failures: 4 },
    { day: "Wed", success: 88, failures: 12 }, { day: "Thu", success: 97, failures: 3 },
    { day: "Fri", success: 91, failures: 9 }, { day: "Sat", success: 98, failures: 2 },
    { day: "Sun", success: 94, failures: 6 }
  ],
  trust: [
    { name: "Customer Sales", score: 96, owner: "Analytics", freshness: "5 min ago", status: "Trusted" },
    { name: "Product Inventory", score: 82, owner: "Operations", freshness: "2 hours ago", status: "Review" },
    { name: "Finance KPIs", score: 61, owner: "Finance", freshness: "Yesterday", status: "At risk" },
    { name: "Marketing Events", score: 93, owner: "Marketing", freshness: "15 min ago", status: "Trusted" }
  ],
  costs: [
    { day: "Mon", cost: 320, usage: 290 }, { day: "Tue", cost: 350, usage: 330 },
    { day: "Wed", cost: 410, usage: 350 }, { day: "Thu", cost: 390, usage: 370 },
    { day: "Fri", cost: 490, usage: 380 }, { day: "Sat", cost: 450, usage: 410 },
    { day: "Sun", cost: 520, usage: 420 }
  ]
};
const num = (v) => v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const pct = (v) => v == null ? "—" : `${num(v)}%`;

export default function App() {
  const [page, setPage] = useState("overview");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [apiState, setApiState] = useState("checking");
  const [apiError, setApiError] = useState("");
  const [overview, setOverview] = useState(null);
  const [pipelineMetrics, setPipelineMetrics] = useState(null);
  const [trustMetrics, setTrustMetrics] = useState(null);
  const [costMetrics, setCostMetrics] = useState(null);
  const [pipelineRows, setPipelineRows] = useState(null);
  const [tableList, setTableList] = useState([]);
  const [requests, setRequests] = useState([]);
  const [requestForm, setRequestForm] = useState({ dataset: "", reason: "", priority: "Medium" });
  const [messages, setMessages] = useState([{ role: "assistant", text: "Hello! Ask me about pipeline failures, dataset trust, platform costs, or data requests." }]);
  const [chatText, setChatText] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  

  const loadData = useCallback(async () => {
    setBusy(true); setApiError("");
    const results = await Promise.allSettled([
      axios.get(`${API}/health`, { timeout: 4000 }),
      axios.get(`${API}/metrics/overview`, { timeout: 6000 }),
      axios.get(`${API}/metrics/pipelines`, { timeout: 6000 }),
      axios.get(`${API}/metrics/trust`, { timeout: 6000 }),
      axios.get(`${API}/metrics/cost`, { timeout: 6000 }),
      axios.get(`${API}/tables`, { timeout: 6000 })
    ]);
    const [health, ov, pipe, trust, cost, tables] = results;
    const connected = health.status === "fulfilled" && health.value.data?.connected;
    setApiState(connected ? "connected" : "offline");
    if (!connected) setApiError(health.status === "rejected" ? "Cannot reach Flask/Exasol. Demo values are shown where live values are unavailable." : "Exasol connection is not confirmed.");
    if (ov.status === "fulfilled" && ov.value.data?.success) setOverview(ov.value.data);
    if (pipe.status === "fulfilled" && pipe.value.data?.success) setPipelineMetrics(pipe.value.data.metrics);
    if (trust.status === "fulfilled" && trust.value.data?.success) setTrustMetrics(trust.value.data.metrics);
    if (cost.status === "fulfilled" && cost.value.data?.success) setCostMetrics(cost.value.data.metrics);
    if (tables.status === "fulfilled" && tables.value.data?.success) setTableList(tables.value.data.tables || []);
    const runs = tables.status === "fulfilled" ? (tables.value.data.tables || []).some(t => t.table_name?.toUpperCase() === "PIPELINE_RUNS") : false;
    if (runs) {
      try {
        const r = await axios.get(`${API}/tables/HACKATHON/PIPELINE_RUNS?limit=100`, { timeout: 8000 });
        setPipelineRows(r.data.data || []);
      } catch { setPipelineRows(null); }
    } else setPipelineRows(null);
    setBusy(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const actualPipelines = useMemo(() => pipelineRows ? pipelineRows.map(row => ({
    name: row.pipeline_name || row.run_id || "Unnamed pipeline",
    source: row.source_system || "—", status: row.status || "UNKNOWN",
    duration: row.duration_seconds,
    time: row.start_time ? new Date(row.start_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—",
    sla: row.sla_minutes != null && row.duration_seconds != null ? (Number(row.duration_seconds) > Number(row.sla_minutes) * 60 ? "Breached" : "On time") : "Unknown",
    error: row.error_message
  })) : DEMO.pipelines, [pipelineRows]);
  const filteredPipelines = actualPipelines.filter(r => `${r.name} ${r.source} ${r.status}`.toLowerCase().includes(search.toLowerCase()));
  const demoMode = apiState !== "connected";
  const totalRuns = pipelineMetrics?.total_runs ?? DEMO.pipelines.length;
  const successfulRuns = pipelineMetrics?.successful_runs ?? 3;
  const failedRuns = pipelineMetrics?.failed_runs ?? 2;
  const successRate = pipelineMetrics?.success_rate_pct ?? successfulRuns * 100 / Math.max(totalRuns, 1);
  const trustScore = trustMetrics?.tables?.trust_scores?.avg_trust_score ?? 88;
  const totalCost = costMetrics?.total_cost ?? 2930;
  const totalUsage = costMetrics?.total_usage ?? 2550;
  const trustRows = DEMO.trust;

  const switchPage = (id) => { setPage(id); setMobileOpen(false); setSearch(""); setNotice(""); };
  const pageTitle = NAV.find(n => n.id === page)?.label || "Overview";

  async function submitRequest(event) {
    event.preventDefault();
    if (!requestForm.dataset.trim() || !requestForm.reason.trim()) return;
    let record;
    try {
      const response = await axios.post(`${API}/requests`, {
        requester: "demo.user", dataset_id: requestForm.dataset,
        business_justification: requestForm.reason, priority: requestForm.priority
      }, { timeout: 6000 });
      record = { id: response.data.request_id || `REQ-${Date.now()}`, ...requestForm, status: "Pending" };
      setNotice("Request submitted to the backend.");
    } catch {
      record = { id: `DEMO-${Date.now().toString().slice(-6)}`, ...requestForm, status: "Pending (Demo)" };
      setNotice("Saved in this browser session only. The backend request API is unavailable.");
    }
    setRequests(old => [record, ...old]);
    setRequestForm({ dataset: "", reason: "", priority: "Medium" });
  }

  
const sendChat = async (e) => {
  e.preventDefault();

  const question = chatText.trim();

  if (!question || busy) return;

  setMessages((prev) => [
    ...prev,
    { role: "user", text: question }
  ]);

  setChatText("");
  setBusy(true);

  try {
    const response = await fetch(
      "http://127.0.0.1:5000/api/rag/query",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ question })
      }
    );

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(
        typeof data.error === "string"
          ? data.error
          : data.error?.message || "RAG request failed."
      );
    }

    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        text: data.answer
      }
    ]);
  } catch (error) {
    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        text: `Error: ${error.message}`
      }
    ]);
  } finally {
    setBusy(false);
  }
};


  return <div className="app-shell">
    <Sidebar nav={NAV} page={page} switchPage={switchPage} mobileOpen={mobileOpen} failedRuns={failedRuns} apiState={apiState} schema={overview?.schema || "HACKATHON"} tableCount={overview?.table_count ?? tableList.length} />
    <main className="main">
      <Topbar title={pageTitle} search={search} setSearch={setSearch} onRefresh={loadData} busy={busy} onMenu={() => setMobileOpen(v => !v)} mobileOpen={mobileOpen} onChat={() => switchPage("chat")} />
      <div className="content">
        {demoMode && <div className="notice"><strong>DEMO / CONNECTION NOTICE</strong> — {apiError || "Live database metrics have not been verified."} Illustrative values are not retrieved from Exasol.</div>}
        {notice && <div className="notice">{notice}<button className="notice-close" onClick={() => setNotice("")}><X size={14}/></button></div>}
        <div className="page-intro">
          <div><h1>{page === "overview" ? "DataOps at a glance" : pageTitle}</h1><p>{({
            overview: "Monitor reliability, data trust and platform efficiency from one place.",
            pipelines: "Identify failed jobs, delayed runs and SLA breaches.",
            trust: "Understand data freshness, validation and KPI reliability.",
            cost: "Compare platform expenditure with measurable usage.",
            chat: "Ask questions and discover trusted enterprise data.",
            requests: "Create and track business data requests.",
            database: "Browse schemas, inspect table columns, and review live records stored in Exasol."
          })[page]}</p></div>
          <div className="actions"><button className="btn" onClick={loadData}><RefreshCw size={13} className={busy ? "spin" : ""}/> Refresh</button>{page !== "chat" && page !== "requests" && <button className="btn btn-primary" onClick={() => switchPage("chat")}><MessageSquare size={14}/> Ask assistant</button>}</div>
        </div>

        {page === "overview" && <>
          <div className="grid metrics-grid">
            <Metric label="Pipeline success rate" value={pct(successRate)} hint={`${num(successfulRuns)} successful runs`} icon={Activity} color="green" trend={2.4}/>
            <Metric label="Failed pipeline runs" value={num(failedRuns)} hint="Check recent incidents" icon={AlertTriangle} color="red"/>
            <Metric label="Average trust score" value={pct(trustScore)} hint="Dataset trust indicators" icon={ShieldCheck} color="blue"/>
            <Metric label="Total recorded cost" value={costMetrics?.total_cost != null ? num(totalCost) : `₹${num(totalCost)}`} hint={costMetrics?.total_usage != null ? `${num(totalUsage)} usage units` : "Illustrative demo cost"} icon={Wallet} color="orange"/>
          </div>
          <div className="content-grid">
            <Card><SectionTitle title="Pipeline execution trend" subtitle="Illustrative daily success and failure percentage"/><div className="chart-wrap"><CostChart data={DEMO.trend} mode="trend"/></div><div className="legend"><span>● Success rate</span><span>● Failure rate</span></div></Card>
            <Card><SectionTitle title="Platform health" subtitle="Current system indicators"/><div className="health-list">
              <div className="health-item"><Server size={17}/><span>Exasol connection</span><Badge>{apiState === "connected" ? "SUCCESS" : "UNKNOWN"}</Badge></div>
              <div className="health-item"><Activity size={17}/><span>Pipeline reliability</span><strong>{pct(successRate)}</strong></div>
              <div className="health-item"><ShieldCheck size={17}/><span>Data trust</span><strong>{pct(trustScore)}</strong></div>
              <div className="health-item"><Wallet size={17}/><span>Cost monitoring</span><Badge>{costMetrics?.total_cost != null ? "SUCCESS" : "DEMO"}</Badge></div>
            </div></Card>
          </div>
          <Card className="table-card"><SectionTitle title="Recent pipeline runs" subtitle="Search and review execution status" action={<button className="btn" onClick={() => switchPage("pipelines")}>View all →</button>}/><PipelineTable rows={filteredPipelines.slice(0,5)}/></Card>
          <div className="bottom-grid"><TrustCard rows={trustRows}/><CostChart data={DEMO.costs}/></div>
        </>}
        {page === "pipelines" && <>
          <div className="grid metrics-grid"><Metric label="Total runs" value={num(totalRuns)} hint="Retrieved run records" icon={Activity}/><Metric label="Successful" value={num(successfulRuns)} hint="Completed successfully" icon={CheckCircle2} color="green"/><Metric label="Failed" value={num(failedRuns)} hint="Requires investigation" icon={XCircle} color="red"/><Metric label="Success rate" value={pct(successRate)} hint="Based on available statuses" icon={Clock3} color="blue"/></div>
          <Card className="table-card"><SectionTitle title="Pipeline execution records" subtitle="Live records when available; otherwise illustrative demo records."/><PipelineTable rows={filteredPipelines}/></Card>
        </>}
        {page === "trust" && <>
          <div className="grid metrics-grid"><Metric label="Average trust score" value={pct(trustScore)} hint="Stored score average" icon={ShieldCheck}/><Metric label="Datasets discovered" value={num(tableList.length)} hint="Tables returned by API" icon={Database} color="blue"/><Metric label="Quality checks" value={num(trustMetrics?.tables?.quality_results?.total_checks)} hint="Recorded validation results" icon={CheckCircle2} color="orange"/><Metric label="Trust data source" value={trustMetrics ? "Available" : "Demo"} hint="Based on API response" icon={Server} color="red"/></div>
          <TrustCard rows={trustRows}/>
          <Card className="table-card"><SectionTitle title="Exasol schema inventory" subtitle="Tables discovered by the configured schema"/><div className="table-scroll"><table><thead><tr><th>Table</th><th>Schema</th><th>Purpose</th></tr></thead><tbody>{tableList.map((t,i)=><tr key={t.table_name || i}><td><strong>{t.table_name}</strong></td><td>{t.table_schema || overview?.schema || "—"}</td><td>Exasol table</td></tr>)}</tbody></table></div></Card>
        </>}
        {page === "cost" && <>
          <div className="grid metrics-grid"><Metric label="Total recorded cost" value={costMetrics?.total_cost != null ? num(totalCost) : `₹${num(totalCost)}`} hint="Confirm source currency" icon={Wallet} color="orange"/><Metric label="Total usage" value={num(totalUsage)} hint="Recorded usage units" icon={Zap} color="blue"/><Metric label="Cost per usage unit" value={costMetrics?.cost_per_usage_unit != null ? num(costMetrics.cost_per_usage_unit) : "—"} hint="Requires consistent units" icon={Activity}/><Metric label="Cost records" value={num(costMetrics?.record_count)} hint="Stored observations" icon={Database} color="red"/></div>
          <CostChart data={DEMO.costs}/><div className="notice">The chart uses illustrative data unless period-level live records are available. Verify currency and usage units before making cost decisions.</div>
        </>}
        {page === "database" && <ExasolDatabase api={API} schemaDefault={overview?.schema || "HACKATHON"}/>}
        {page === "chat" &&<ChatPage
  messages={messages}
  chatText={chatText}
  setChatText={setChatText}
  sendChat={sendChat}
  busy={busy}
/>}
{page === "requests" && <RequestsPage requests={requests} form={requestForm} setForm={setRequestForm} onSubmit={submitRequest} search={search}/>}
      </div>
    </main>
  </div>;
}
