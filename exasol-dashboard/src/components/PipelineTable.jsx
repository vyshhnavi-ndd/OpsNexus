import React from "react";
import Badge from "./Badge";
export default function PipelineTable({ rows=[] }) {
  if(!rows.length) return <div className="empty">No pipeline records available.</div>;
  return <div className="table-scroll"><table><thead><tr><th>Pipeline</th><th>Source</th><th>Status</th><th>Duration</th><th>Time</th><th>SLA</th></tr></thead><tbody>{rows.map((r,i)=><tr key={`${r.name}-${i}`}><td><strong>{r.name}</strong>{r.error&&<div className="muted">{r.error}</div>}</td><td>{r.source}</td><td><Badge>{r.status}</Badge></td><td>{r.duration==null?"—":`${r.duration}s`}</td><td>{r.time}</td><td><Badge>{r.sla}</Badge></td></tr>)}</tbody></table></div>;
}
