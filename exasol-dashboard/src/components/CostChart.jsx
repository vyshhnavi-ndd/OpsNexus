import React from "react";
import { ResponsiveContainer, AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip } from "recharts";
import Card from "./Card";
import SectionTitle from "./SectionTitle";
export default function CostChart({ data=[], mode="cost" }) {
  if(mode==="trend") return <ResponsiveContainer width="100%" height="100%"><AreaChart data={data}><CartesianGrid stroke="#edf1f6" strokeDasharray="4 4" vertical={false}/><XAxis dataKey="day"/><YAxis domain={[0,100]}/><Tooltip/><Area dataKey="success" name="Success %" stroke="#10b981" fill="#10b981" fillOpacity={.12}/><Area dataKey="failures" name="Failure %" stroke="#f87171" fill="#f87171" fillOpacity={.06}/></AreaChart></ResponsiveContainer>;
  return <Card><SectionTitle title="Cost vs usage" subtitle="Illustrative daily comparison; verify source units and currency"/><div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data}><CartesianGrid stroke="#edf1f6" strokeDasharray="4 4" vertical={false}/><XAxis dataKey="day"/><YAxis/><Tooltip/><Area type="monotone" dataKey="cost" name="Cost (demo units)" stroke="#818cf8" fill="#818cf8" fillOpacity={.12} strokeWidth={2.5}/><Area type="monotone" dataKey="usage" name="Usage (demo units)" stroke="#10b981" fill="#10b981" fillOpacity={.1} strokeWidth={2.5}/></AreaChart></ResponsiveContainer></div></Card>;
}
