import React, { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Database, Table2, Columns3, Rows3, RefreshCw, Download, Play, AlertTriangle, LoaderCircle, Terminal } from "lucide-react";
import Card from "../components/Card";
import SectionTitle from "../components/SectionTitle";

export default function ExasolDatabase({ api, schemaDefault="HACKATHON" }) {
  const [schemas,setSchemas]=useState([]);
  const [schema,setSchema]=useState(schemaDefault);
  const [tables,setTables]=useState([]);
  const [selected,setSelected]=useState(null);
  const [rows,setRows]=useState([]);
  const [columns,setColumns]=useState([]);
  const [offset,setOffset]=useState(0);
  const [limit,setLimit]=useState(50);
  const [total,setTotal]=useState(null);
  const [filter,setFilter]=useState("");
  const [tableSearch,setTableSearch]=useState("");
  const [tab,setTab]=useState("data");
  const [sql,setSql]=useState(`SELECT * FROM ${schemaDefault}.CUSTOMERS LIMIT 50`);
  const [sqlRows,setSqlRows]=useState([]);
  const [sqlColumns,setSqlColumns]=useState([]);
  const [loading,setLoading]=useState(false);
  const [running,setRunning]=useState(false);
  const [error,setError]=useState("");
  const [sqlError,setSqlError]=useState("");
  const [connected,setConnected]=useState(false);

  const loadStructure=useCallback(async()=>{
    setLoading(true);setError("");
    try{
      const res=await axios.get(`${api}/database-structure`,{timeout:10000});
      const payload=res.data||{};
      const raw=payload.schemas||payload.structure||payload.data||[];
      if(payload.success===false) throw new Error(payload.error||"Unable to load database structure.");
      let groups=Array.isArray(raw)?raw.map(s=>({schema_name:s.schema_name||s.name||s.schema||schemaDefault,tables:(s.tables||[]).map(t=>({...t,table_schema:t.table_schema||s.schema_name||s.name||schemaDefault,table_name:t.table_name||t.name}))})): [];
      if(!groups.length){
        const fallback=await axios.get(`${api}/tables`,{timeout:10000});
        const list=fallback.data?.tables||fallback.data?.data||[];
        groups=[{schema_name:schemaDefault,tables:list.map(t=>({...t,table_schema:t.table_schema||schemaDefault,table_name:t.table_name||t.name}))}];
      }
      setSchemas(groups);setSchema(old=>groups.some(s=>s.schema_name===old)?old:groups[0]?.schema_name||schemaDefault);setConnected(true);
    }catch(e){setConnected(false);setError(e.response?.data?.error||e.message||"Cannot reach Flask API.");}
    finally{setLoading(false);}
  },[api,schemaDefault]);

  useEffect(()=>{loadStructure();},[loadStructure]);
  const activeSchema=schemas.find(s=>s.schema_name===schema);
  const visibleTables=useMemo(()=> (activeSchema?.tables||[]).filter(t=>(t.table_name||"").toLowerCase().includes(tableSearch.toLowerCase())),[activeSchema,tableSearch]);

  const openTable=useCallback(async(table,offsetValue=0)=>{
    const name=table.table_name||table.name;
    if(!name)return;
    const sch=table.table_schema||schema;
    setSelected({table_schema:sch,table_name:name});setOffset(offsetValue);setRows([]);setColumns(table.columns||[]);setLoading(true);setError("");setTab("data");
    try{
      const res=await axios.get(`${api}/tables/${encodeURIComponent(sch)}/${encodeURIComponent(name)}`,{params:{limit,offset:offsetValue},timeout:15000});
      const p=res.data||{};if(p.success===false)throw new Error(p.error||"Unable to load table.");
      const data=Array.isArray(p.data)?p.data:Array.isArray(p.rows)?p.rows:[];
      setRows(data);setTotal(p.total??p.total_rows??p.count??null);
      if(data.length&&!((table.columns||[]).length))setColumns(Object.keys(data[0]).map((column_name,i)=>({column_name,ordinal_position:i+1})));
    }catch(e){setError(e.response?.data?.error||e.message||"Unable to load table rows.");}
    finally{setLoading(false);}
  },[api,schema,limit]);

  async function changePage(next){
    if(!selected||next<0)return;
    await openTable(selected,next);
  }
  async function runSql(){
    setRunning(true);setSqlError("");setSqlRows([]);setSqlColumns([]);
    try{
      const res=await axios.post(`${api}/sql/execute`,{sql},{timeout:30000});
      const p=res.data||{};if(p.success===false)throw new Error(p.error||"SQL execution failed.");
      const data=Array.isArray(p.data)?p.data:Array.isArray(p.rows)?p.rows:[];
      setSqlRows(data);setSqlColumns(p.columns||(data[0]?Object.keys(data[0]):[]));setTab("results");
    }catch(e){setSqlError(e.response?.data?.error||e.message||"SQL execution failed.");}
    finally{setRunning(false);}
  }
  const shownRows=rows.filter(row=>!filter||Object.values(row).some(v=>String(v??"NULL").toLowerCase().includes(filter.toLowerCase())));
  function exportCsv(data,cols){
    if(!data.length||!cols.length)return;
    const quote=v=>`"${String(v??"").replaceAll('"','""')}"`;
    const csv=[cols.map(quote).join(","),...data.map(r=>cols.map(c=>quote(r[c])).join(","))].join("\r\n");
    const url=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"}));const a=document.createElement("a");a.href=url;a.download=`${selected?.table_name||"exasol"}-rows.csv`;a.click();URL.revokeObjectURL(url);
  }
  const dataColumns=rows[0]?Object.keys(rows[0]):columns.map(c=>c.column_name||c.name).filter(Boolean);

  return <div className="database-layout">
    <aside className="database-sidebar">
      <div className="database-heading"><h2><Database size={17}/>Database explorer</h2><button className="icon-btn" onClick={loadStructure} title="Refresh"><RefreshCw size={14} className={loading?"spin":""}/></button></div>
      <div className="connection-pill"><span className={`green-dot ${connected?"":"offline"}`}/>{connected?"Flask API connected":"Connection unavailable"}</div>
      <label className="field schema-field">Schema<select value={schema} onChange={e=>{setSchema(e.target.value);setSelected(null);setRows([]);}}>{schemas.length?schemas.map(s=><option key={s.schema_name}>{s.schema_name}</option>):<option>{schemaDefault}</option>}</select></label>
      <input className="database-search" value={tableSearch} onChange={e=>setTableSearch(e.target.value)} placeholder="Search tables…"/>
      <div className="tree-list">{visibleTables.map((t,i)=><button key={`${schema}.${t.table_name||i}`} className={`table-tree-item ${selected?.table_name===(t.table_name||t.name)?"active":""}`} onClick={()=>openTable(t)}><Table2 size={15}/><span className="table-tree-name">{t.table_name||t.name}</span></button>)}
      {!loading&&!visibleTables.length&&<div className="empty compact"><Database size={22}/><p>No tables found.</p></div>}</div>
    </aside>
    <section className="database-main">
      {error&&<div className="error-banner"><AlertTriangle size={15}/>{error}</div>}
      <div className="database-stats"><div className="database-stat"><div className="database-stat-label"><Table2 size={14}/>Selected table</div><div className="database-stat-value small-value">{selected?.table_name||"—"}</div></div><div className="database-stat"><div className="database-stat-label"><Columns3 size={14}/>Columns</div><div className="database-stat-value">{dataColumns.length||"—"}</div></div><div className="database-stat"><div className="database-stat-label"><Rows3 size={14}/>Rows loaded</div><div className="database-stat-value">{rows.length}</div></div></div>
      <Card className="database-card">
        <div className="database-toolbar"><div><h2>{selected?`${selected.table_schema}.${selected.table_name}`:"SQL workspace"}</h2><p>{selected?"Preview rows returned by Flask/Exasol":"Select a table or open the SQL editor."}</p></div><div className="actions"><select className="small-select" value={limit} onChange={e=>setLimit(Number(e.target.value))}><option value={25}>25 rows</option><option value={50}>50 rows</option><option value={100}>100 rows</option><option value={250}>250 rows</option></select><button className="btn" onClick={()=>selected&&openTable(selected,offset)} disabled={!selected||loading}><RefreshCw size={13}/> Reload</button><button className="btn" onClick={()=>exportCsv(shownRows,dataColumns)} disabled={!rows.length}><Download size={13}/> CSV</button></div></div>
        <div className="database-tabs"><button className={tab==="data"?"active":""} onClick={()=>setTab("data")}>Table data</button><button className={tab==="columns"?"active":""} onClick={()=>setTab("columns")}>Columns</button><button className={tab==="sql"||tab==="results"?"active":""} onClick={()=>setTab("sql")}><Terminal size={13}/> SQL editor</button></div>
        {(tab==="sql"||tab==="results")?<div className="sql-area"><div className="sql-note">Read-only SQL · SELECT / WITH only (enforced by backend)</div><textarea value={sql} onChange={e=>setSql(e.target.value)} spellCheck="false" aria-label="SQL editor"/><div className="actions"><button className="btn btn-primary" onClick={runSql} disabled={running||!sql.trim()}><Play size={13}/>{running?"Running…":"Run query"}</button></div>{sqlError&&<div className="error-banner">{sqlError}</div>}{tab==="results"&&<DataGrid rows={sqlRows} columns={sqlColumns}/>}</div>
        :tab==="columns"?<div className="database-table-wrap"><table className="database-table"><thead><tr><th>#</th><th>Column</th><th>Data type</th><th>Nullable</th></tr></thead><tbody>{columns.map((c,i)=><tr key={c.column_name||c.name||i}><td>{c.ordinal_position||i+1}</td><td>{c.column_name||c.name||"—"}</td><td>{c.data_type||c.type||"—"}</td><td>{c.is_nullable??c.nullable??"—"}</td></tr>)}</tbody></table>{!columns.length&&<div className="empty">Select a table to inspect columns.</div>}</div>
        :<><input className="database-search row-filter" value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Filter loaded rows…"/>{loading?<div className="empty"><LoaderCircle className="spin" size={23}/><p>Loading records…</p></div>:selected?<DataGrid rows={shownRows} columns={dataColumns}/>:<div className="database-empty"><div className="database-empty-icon"><Database size={27}/></div><strong>Explore your Exasol data</strong><span>Select a table or use the SQL editor.</span></div>}
        {selected&&<div className="database-footer"><span>{total==null?`${rows.length} rows loaded`:`${Number(total).toLocaleString()} total rows`}</span><div className="actions"><button className="btn" onClick={()=>changePage(offset-limit)} disabled={loading||offset===0}>Previous</button><span>{rows.length?offset+1:0}–{offset+rows.length}</span><button className="btn" onClick={()=>changePage(offset+limit)} disabled={loading||rows.length<limit||(total!=null&&offset+limit>=Number(total))}>Next</button></div></div>}</>}
      </Card>
    </section>
  </div>;
}
function DataGrid({rows=[],columns=[]}){
  if(!rows.length||!columns.length)return <div className="empty"><Rows3 size={23}/><p>No rows to display.</p></div>;
  return <div className="database-table-wrap"><table className="database-table"><thead><tr><th>#</th>{columns.map(c=><th key={c}>{c}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={i}><td className="row-number">{i+1}</td>{columns.map(c=><td key={c}>{r[c]==null?<span className="null-value">NULL</span>:typeof r[c]==="object"?JSON.stringify(r[c]):String(r[c])}</td>)}</tr>)}</tbody></table></div>;
}
