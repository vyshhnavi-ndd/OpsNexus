import React from "react";
import { Bell, Menu, X, RefreshCw, Search } from "lucide-react";
export default function Topbar({ title, search, setSearch, onRefresh, busy, onMenu, mobileOpen, onChat }) {
  return <header className="topbar">
    <div className="topbar-left"><button className="icon-btn mobile-toggle" onClick={onMenu} aria-label="Toggle navigation">{mobileOpen?<X size={18}/>:<Menu size={18}/>}</button><div><div className="crumb">WORKSPACE / DATAOPS</div><div className="top-title">{title}</div></div></div>
    <div className="top-actions"><label className="search-box"><Search size={15}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search pipelines, datasets…"/></label><button className="icon-btn" title="Refresh" onClick={onRefresh}><RefreshCw size={15} className={busy?"spin":""}/></button><button className="icon-btn" title="Data assistant" onClick={onChat}><Bell size={15}/></button><div className="avatar">DU</div></div>
  </header>;
}
