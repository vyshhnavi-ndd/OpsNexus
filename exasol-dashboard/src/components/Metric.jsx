import React from "react";
import Card from "./Card";
import { ArrowUpRight, ArrowDownRight } from "lucide-react";
export default function Metric({ label, value, hint, icon: Icon, color="green", trend }) {
  return <Card className="metric"><div className="metric-top"><span>{label}</span><span className={`metric-icon ${color}`}><Icon size={19}/></span></div><div className="metric-value">{value}</div><div className="metric-bottom">{trend!=null&&<span className={trend>=0?"trend-up":"trend-down"}>{trend>=0?<ArrowUpRight size={14}/>:<ArrowDownRight size={14}/>} {Math.abs(trend)}%</span>}<span>{hint}</span></div></Card>;
}
