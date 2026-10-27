import React from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

import Card from "./Card";
import SectionTitle from "./SectionTitle";

const toNumberOrNull = (value) => {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

const formatNumber = (value) => {
  const number = toNumberOrNull(value);
  return number === null
    ? "Unavailable"
    : number.toLocaleString("en-IN", { maximumFractionDigits: 2 });
};

const formatCost = (value, currency = "INR") => {
  const number = toNumberOrNull(value);
  if (number === null) return "Unavailable";
  if (currency === "INR") {
    return `₹${number.toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }
  return `${currency} ${number.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
};

function CustomTooltip({ active, payload, label, mode, currency }) {
  if (!active || !payload?.length) return null;

  return (
    <div
      style={{
        background: "var(--card-bg, #ffffff)",
        border: "1px solid var(--border-color, #e5e7eb)",
        borderRadius: 10,
        padding: "12px 14px",
        boxShadow: "0 8px 24px rgba(15, 23, 42, 0.10)",
      }}
    >
      <p style={{
        margin: "0 0 10px",
        fontSize: 12,
        fontWeight: 600,
        color: "var(--text-primary, #111827)",
      }}>{label}</p>

      {payload.map((item) => {
        const value = toNumberOrNull(item.value);
        return (
          <div
            key={item.dataKey}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 24,
              marginTop: 7,
              fontSize: 12,
            }}
          >
            <span style={{ color: item.color }}>● {item.name}</span>
            <strong style={{ color: "var(--text-primary, #111827)" }}>
              {value === null
                ? "Unavailable"
                : mode === "trend"
                  ? `${formatNumber(value)}%`
                  : item.dataKey === "cost"
                    ? formatCost(value, currency)
                    : formatNumber(value)}
            </strong>
          </div>
        );
      })}
    </div>
  );
}

export default function CostChart({ data = [], mode = "cost", currency = "INR" }) {
  const isTrend = mode === "trend";
  const hasValidData = data.some((row) => {
    const keys = isTrend ? ["success", "failures"] : ["cost", "usage"];
    return keys.some((key) => toNumberOrNull(row?.[key]) !== null);
  });

  return (
    <Card>
      <SectionTitle
        title={isTrend ? "Pipeline reliability trend" : "Cost vs usage"}
        subtitle={isTrend
          ? "Daily pipeline success and failure percentages"
          : "Daily platform spending and usage comparison"}
      />

      {!data.length || !hasValidData ? (
        <div style={{
          minHeight: 280,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexDirection: "column",
          gap: 8,
          color: "var(--text-secondary, #6b7280)",
          textAlign: "center",
        }}>
          <span style={{ fontSize: 28 }}>📊</span>
          <strong>No chart data available</strong>
          <span style={{ fontSize: 12 }}>
            Data will appear when the API returns valid numeric records.
          </span>
        </div>
      ) : (
        <div className="chart-wrap" style={{ width: "100%", height: 300, minWidth: 0 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 12, right: 12, left: 8, bottom: 4 }}>
              <defs>
                <linearGradient id="costGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#818cf8" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#818cf8" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="usageGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#10b981" stopOpacity={0.22} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0.02} />
                </linearGradient>
              </defs>

              <CartesianGrid stroke="var(--border-color, #e5e7eb)" strokeDasharray="4 5" vertical={false} />
              <XAxis dataKey="day" tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} tickMargin={10} />
              <YAxis
                domain={isTrend ? [0, 100] : [0, "auto"]}
                tick={{ fontSize: 11, fill: "#9ca3af" }}
                axisLine={false}
                tickLine={false}
                tickMargin={8}
                tickFormatter={(value) => isTrend ? `${value}%` : Number(value).toLocaleString("en-IN")}
                width={55}
              />
              <Tooltip
                content={<CustomTooltip mode={mode} currency={currency} />}
                cursor={{ stroke: "#94a3b8", strokeDasharray: "4 4" }}
              />

              {isTrend ? (
                <>
                  <Area type="monotone" dataKey="success" name="Success" stroke="#10b981" fill="url(#usageGradient)" strokeWidth={2.5} activeDot={{ r: 5, strokeWidth: 0 }} connectNulls={false} />
                  <Area type="monotone" dataKey="failures" name="Failure" stroke="#f87171" fill="none" strokeWidth={2.5} activeDot={{ r: 5, strokeWidth: 0 }} connectNulls={false} />
                </>
              ) : (
                <>
                  <Area type="monotone" dataKey="cost" name="Cost" stroke="#818cf8" fill="url(#costGradient)" strokeWidth={2.5} activeDot={{ r: 5, strokeWidth: 0 }} connectNulls={false} />
                  <Area type="monotone" dataKey="usage" name="Usage" stroke="#10b981" fill="url(#usageGradient)" strokeWidth={2.5} activeDot={{ r: 5, strokeWidth: 0 }} connectNulls={false} />
                </>
              )}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
