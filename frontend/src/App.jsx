import { useCallback, useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import { Activity, AlertTriangle, Bot, CheckCircle2, ChevronLeft, ChevronRight, Database, RefreshCw, Search, Send, ShieldAlert, X } from 'lucide-react'

const api = axios.create({ timeout: 12000 })
const PAGE_SIZE = 50
const TYPES = ['', 'PIPELINE_FAILURE', 'STALE_DATASET', 'INCOMPLETE_DATA', 'QUALITY_FAILURE', 'KPI_ANOMALY', 'CROSS_DOMAIN_INCONSISTENCY', 'INCIDENT_RECURRENCE']
const SEVERITIES = ['', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
const messageOf = (error) => error.response?.data?.error?.message || error.message || 'Request failed'

function App() {
  const [health, setHealth] = useState('checking')
  const [rows, setRows] = useState([])
  const [pagination, setPagination] = useState({ page: 1, page_size: PAGE_SIZE, total_count: 0, total_pages: 0 })
  const [page, setPage] = useState(1)
  const [findingType, setFindingType] = useState('')
  const [severity, setSeverity] = useState('')
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [assistantOpen, setAssistantOpen] = useState(false)
  const [chatQuestion, setChatQuestion] = useState('')
  const [chatBusy, setChatBusy] = useState(false)
  const [chatMessages, setChatMessages] = useState([
    { role: 'assistant', text: 'Ask about the findings currently available in Exasol. I will cite finding IDs and say when the evidence is insufficient.' },
  ])

  const refresh = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      const [h, f] = await Promise.all([
        api.get('/health'),
        api.get('/api/findings', { params: { page, page_size: PAGE_SIZE, ...(findingType && { finding_type: findingType }), ...(severity && { severity }) } }),
      ])
      setHealth(h.data.database === 'connected' ? 'connected' : 'unavailable')
      setRows(f.data.data || [])
      setPagination(f.data.pagination)
    } catch (e) {
      setHealth('unavailable')
      setError(messageOf(e))
      setRows([])
    } finally { setBusy(false) }
  }, [page, findingType, severity])

  useEffect(() => { refresh() }, [refresh])

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return rows
    return rows.filter((r) => [r.finding_id, r.finding_type, r.severity, r.affected_entity?.id, r.evidence, r.recommended_action, r.source_references].join(' ').toLowerCase().includes(q))
  }, [rows, search])

  const counts = useMemo(() => ({
    critical: rows.filter((x) => x.severity === 'CRITICAL').length,
    high: rows.filter((x) => x.severity === 'HIGH').length,
    other: rows.filter((x) => ['MEDIUM', 'LOW'].includes(x.severity)).length,
  }), [rows])

  async function openFinding(id) {
    setSelected({ loading: true })
    try { setSelected((await api.get(`/api/findings/${encodeURIComponent(id)}`)).data.data) }
    catch (e) { setSelected({ error: messageOf(e) }) }
  }

  async function askAssistant(event) {
    event.preventDefault()
    const question = chatQuestion.trim()
    if (!question || chatBusy) return
    setChatMessages((messages) => [...messages, { role: 'user', text: question }])
    setChatQuestion('')
    setChatBusy(true)
    try {
      const { data } = await api.post('/api/rag/query', { question }, { timeout: 100000 })
      const refs = data.source_finding_ids?.length ? `\n\nSources: ${data.source_finding_ids.join(', ')}` : ''
      setChatMessages((messages) => [...messages, { role: 'assistant', text: `${data.answer}${refs}` }])
    } catch (e) {
      setChatMessages((messages) => [...messages, { role: 'assistant', text: messageOf(e) }])
    } finally { setChatBusy(false) }
  }

  return <div className="shell">
    <aside className="rail"><div className="brand-mark">ON</div><div className="rail-icon active"><Activity size={19}/></div><div className="rail-bottom"><Database size={18}/></div></aside>
    <main className="main">
      <header className="top"><div className="brand"><span className="eyebrow">DATA OPERATIONS</span><strong>OpsNexus</strong></div><div className={`connection ${health}`}><span/>Exasol {health === 'connected' ? 'connected' : health === 'checking' ? 'checking' : 'unavailable'}</div><button className="refresh" onClick={() => setAssistantOpen(true)}><Bot size={16}/> Ask Llama</button><button className="refresh" onClick={refresh} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''}/> Refresh</button></header>
      <section className="intro"><div><span className="eyebrow">INTELLIGENCE CENTER / FINDINGS</span><h1>Operational findings</h1><p>Evidence-backed signals from the OpsNexus intelligence view.</p></div><div className="last-updated">Read-only · OPS_INTEL.V_FINDINGS</div></section>
      {error && <div className="alert"><ShieldAlert size={18}/><div><strong>Could not load live findings</strong><p>{error}</p></div></div>}
      <section className="stats">
        <div className="stat"><div className="stat-icon blue"><Database size={18}/></div><span>Findings matching filters</span><strong>{pagination.total_count}</strong><small>from the live Exasol view</small></div>
        <div className="stat"><div className="stat-icon red"><AlertTriangle size={18}/></div><span>Critical / high on page</span><strong>{counts.critical + counts.high}</strong><small>{counts.critical} critical · {counts.high} high</small></div>
        <div className="stat"><div className="stat-icon green"><CheckCircle2 size={18}/></div><span>Other severity on page</span><strong>{counts.other}</strong><small>medium and low signals</small></div>
      </section>
      <section className="panel">
        <div className="panel-head"><div><h2>Findings feed</h2><p>Review the evidence and recommended next step for each signal.</p></div><div className="filters"><label className="search"><Search size={15}/><input placeholder="Search this page" value={search} onChange={(e) => setSearch(e.target.value)}/></label><select value={findingType} onChange={(e) => { setPage(1); setFindingType(e.target.value) }} aria-label="Filter by finding type">{TYPES.map((x) => <option key={x} value={x}>{x ? x.replaceAll('_', ' ') : 'All types'}</option>)}</select><select value={severity} onChange={(e) => { setPage(1); setSeverity(e.target.value) }} aria-label="Filter by severity">{SEVERITIES.map((x) => <option key={x} value={x}>{x || 'All severity'}</option>)}</select></div></div>
        <div className="table-wrap"><table><thead><tr><th>Finding</th><th>Severity</th><th>Affected entity</th><th>Evidence</th><th>Recommended action</th></tr></thead><tbody>
          {busy && !rows.length ? <tr><td colSpan="5" className="empty">Loading findings…</td></tr> : visible.length ? visible.map((r) => <tr key={r.finding_id} onClick={() => openFinding(r.finding_id)} className="clickable"><td><strong>{r.finding_type?.replaceAll('_', ' ') || 'Finding'}</strong><small>{r.finding_id}</small></td><td><span className={`pill ${r.severity?.toLowerCase()}`}>{r.severity || 'Unknown'}</span></td><td>{r.affected_entity?.id || '—'}<small>{r.affected_entity?.type || ''}</small></td><td className="evidence">{r.evidence || 'No evidence supplied'}</td><td>{r.recommended_action || 'Review source evidence'}</td></tr>) : <tr><td colSpan="5" className="empty">No findings match these filters.</td></tr>}
        </tbody></table></div>
        <div className="pager"><span>Page {pagination.page || page} of {pagination.total_pages || 0} · {pagination.total_count || 0} findings</span><div><button onClick={() => setPage((x) => Math.max(1, x - 1))} disabled={page <= 1 || busy}><ChevronLeft size={16}/>Previous</button><button onClick={() => setPage((x) => x + 1)} disabled={page >= pagination.total_pages || busy}>Next<ChevronRight size={16}/></button></div></div>
      </section>
      <footer>Signals describe observed evidence and do not establish root cause by themselves.</footer>
    </main>
    {selected && <div className="overlay" onClick={() => setSelected(null)}><section className="detail" onClick={(e) => e.stopPropagation()}><button className="close" onClick={() => setSelected(null)}>×</button>{selected.loading ? <p>Loading finding…</p> : selected.error ? <p>{selected.error}</p> : <><span className={`pill ${selected.severity?.toLowerCase()}`}>{selected.severity}</span><h2>{selected.finding_type?.replaceAll('_', ' ')}</h2><p className="muted">{selected.finding_id} · {selected.affected_entity?.type}: {selected.affected_entity?.id}</p><h3>Evidence</h3><p className="detail-box">{selected.evidence || 'No evidence supplied.'}</p><h3>Recommended action</h3><p>{selected.recommended_action || 'Review the referenced source records.'}</p><h3>Source references</h3><p className="detail-box">{selected.source_references || 'None provided'}</p>{selected.scenario_instance_id && <><h3>Scenario reference</h3><p>{selected.scenario_instance_id}</p></>}</>}</section></div>}
    {assistantOpen && <div className="overlay" onClick={() => setAssistantOpen(false)}><section className="detail assistant-panel" onClick={(e) => e.stopPropagation()}><button className="close" aria-label="Close assistant" onClick={() => setAssistantOpen(false)}><X size={20}/></button><span className="eyebrow">LOCAL MODEL · FINDINGS EVIDENCE ONLY</span><h2><Bot size={20}/> OpsNexus Assistant</h2><p className="muted">Answers use the curated findings view. The assistant cannot run SQL or change data.</p><div className="chat-messages">{chatMessages.map((message, i) => <div key={i} className={`chat-bubble ${message.role}`}>{message.text}</div>)}{chatBusy && <div className="chat-bubble assistant">Thinking…</div>}</div><form className="chat-form" onSubmit={askAssistant}><textarea value={chatQuestion} onChange={(e) => setChatQuestion(e.target.value)} maxLength={2000} placeholder="Ask about the findings and their evidence…" disabled={chatBusy} /><button className="refresh" type="submit" disabled={chatBusy || !chatQuestion.trim()}><Send size={15}/> Send</button></form></section></div>}
  </div>
}

export default App
