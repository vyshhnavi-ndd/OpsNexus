import { Zap } from "lucide-react";
export default function Sidebar({ nav, page, switchPage, mobileOpen, failedRuns, apiState, schema, tableCount }) {
  return <aside className={`sidebar ${mobileOpen ? "open" : ""}`}>
    <div className="brand"><div className="brand-logo"><Zap size={22}/></div><div><div className="brand-name">EXASOL DATAOPS</div><div className="brand-sub">INTELLIGENCE PLATFORM</div></div></div>
    <div className="nav-label">Workspace</div>
    {nav.map(item => { const Icon=item.icon; return <button key={item.id} className={`nav-item ${page===item.id?"active":""}`} onClick={()=>switchPage(item.id)}><Icon size={17}/>{item.label}{item.id==="pipelines"&&failedRuns>0&&<span className="nav-count">{failedRuns}</span>}</button>; })}
    <div className="nav-label platform-label">Platform</div>
    <div className="nav-footer"><div className="db-card"><div className="db-top"><span className={`green-dot ${apiState!=="connected"?"offline":""}`}/>{apiState==="connected"?"Database connected":apiState==="checking"?"Connecting…":"Connection unavailable"}</div><div className="db-sub">Local Exasol Personal<br/>{schema} schema<br/>{tableCount} discovered tables</div></div></div>
  </aside>;
}
