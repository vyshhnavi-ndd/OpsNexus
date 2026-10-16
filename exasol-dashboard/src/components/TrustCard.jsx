import React from "react";
import Card from "./Card";
import SectionTitle from "./SectionTitle";
import Badge from "./Badge";
export default function TrustCard({ rows=[] }) {
  return <Card><SectionTitle title="Dataset trust" subtitle="Illustrative scores unless live trust records are connected"/><div className="trust-list">{rows.map(row=><div className="trust-row" key={row.name}><div><div className="trust-name">{row.name}</div><div className="muted">{row.owner} · {row.freshness}</div></div><div className="progress"><div className="progress-fill" style={{width:`${Math.max(0,Math.min(100,row.score))}%`}}/></div><div className="trust-score">{row.score}%</div><Badge>{row.status}</Badge></div>)}</div></Card>;
}
