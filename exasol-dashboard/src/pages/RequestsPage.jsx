import React from "react";
import Card from "../components/Card";
import SectionTitle from "../components/SectionTitle";
import Badge from "../components/Badge";
export default function RequestsPage({ requests, form, setForm, onSubmit, search="" }) {
  const visible=requests.filter(r=>`${r.dataset} ${r.reason} ${r.status}`.toLowerCase().includes(search.toLowerCase()));
  const update=(key,value)=>setForm(old=>({...old,[key]:value}));
  return <div className="page-two"><Card><SectionTitle title="Submit a data request" subtitle="Describe the dataset and why it is needed"/><form className="form-grid" onSubmit={onSubmit}><label className="field">Dataset or table<input value={form.dataset} onChange={e=>update("dataset",e.target.value)} placeholder="e.g. CUSTOMER_SALES" required/></label><label className="field">Priority<select value={form.priority} onChange={e=>update("priority",e.target.value)}><option>Low</option><option>Medium</option><option>High</option><option>Urgent</option></select></label><label className="field span-two">Business justification<textarea value={form.reason} onChange={e=>update("reason",e.target.value)} placeholder="Explain the business need…" required/></label><div className="span-two"><button className="btn btn-primary" type="submit">Submit request</button></div></form></Card><Card><SectionTitle title="Recent requests" subtitle="Browser session requests and backend submissions"/>{visible.length?<div className="table-scroll"><table><thead><tr><th>Request ID</th><th>Dataset</th><th>Priority</th><th>Status</th></tr></thead><tbody>{visible.map(r=><tr key={r.id}><td>{r.id}</td><td>{r.dataset}</td><td>{r.priority}</td><td><Badge>{r.status}</Badge></td></tr>)}</tbody></table></div>:<div className="empty">No requests yet.</div>}</Card></div>;
}
