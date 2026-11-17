import React from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

type Cell = string | number | null;

export interface AnalyticsCardData {
  type: "analytics";
  title: string;
  columns: string[];
  rows: Cell[][];
  sql: string;
  source: "report" | "llm";
  scoped_to?: string | null;
  truncated?: boolean;
  chart?: { x: string; y: string } | null;
  elapsed_ms?: number;
  refused?: string;
}

function toCsv(columns: string[], rows: Cell[][]): string {
  const esc = (v: Cell) => {
    const s = v === null || v === undefined ? "" : String(v);
    // Neutralise spreadsheet formulas and quote every field.
    const safe = /^[=+\-@]/.test(s) ? `'${s}` : s;
    return `"${safe.replace(/"/g, '""')}"`;
  };
  return [columns.map(esc).join(","), ...rows.map((r) => r.map(esc).join(","))].join("\r\n");
}

function download(card: AnalyticsCardData) {
  const blob = new Blob(["﻿" + toCsv(card.columns, card.rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${card.title.replace(/[^\w઀-૿ऀ-ॿ]+/g, "_").slice(0, 60) || "report"}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

const label = (c: string) => c.replace(/_/g, " ");

/** SVG fill attributes cannot read CSS variables, so resolve the theme colours when rendering. */
function themeColor(name: string, fallback: string): string {
  try {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  } catch {
    return fallback;
  }
}

export const AnalyticsCard: React.FC<{ card: AnalyticsCardData }> = ({ card }) => {
  const chartData =
    card.chart && card.rows.length > 0
      ? card.rows.slice(0, 15).map((r) => ({
          x: String(r[card.columns.indexOf(card.chart!.x)] ?? "").replace(" (Demo)", "").replace(/_/g, " "),
          y: Number(r[card.columns.indexOf(card.chart!.y)] ?? 0),
        }))
      : null;

  return (
    <div className="mt-3 rounded-lg border border-warm-border bg-subtle p-3 text-xs flex flex-col gap-3 min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-heading text-sm font-bold text-body">{card.title}</span>
        <span
          className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold ${
            card.source === "llm"
              ? "border-amber-400 text-amber-800 dark:text-amber-200"
              : "border-warm-border text-muted"
          }`}
        >
          {card.source === "llm" ? "AI-written query" : "Standard report"}
        </span>
        {card.scoped_to && (
          <span className="px-2 py-0.5 rounded-full border border-warm-border text-[10px] text-muted">
            {card.scoped_to} only
          </span>
        )}
        {card.rows.length > 0 && (
          <button
            type="button"
            onClick={() => download(card)}
            className="ml-auto px-2.5 py-1 rounded-md border border-warm-border bg-card text-body font-semibold hover:bg-page"
          >
            Download CSV
          </button>
        )}
      </div>

      {chartData && (
        <div className="h-56 w-full" aria-label={`Bar chart of ${label(card.chart!.y)} by ${label(card.chart!.x)}`}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 16, left: 4, bottom: 4 }}>
              <XAxis type="number" tick={{ fontSize: 10, fill: themeColor("--text-muted", "#55657F") }} axisLine={false} tickLine={false} allowDecimals={false} />
              <YAxis type="category" dataKey="x" width={150} interval={0} tick={{ fontSize: 10, fill: themeColor("--text-body", "#0F1E3A") }} axisLine={false} tickLine={false} />
              <Tooltip
                formatter={(v: number) => [v, label(card.chart!.y)]}
                contentStyle={{ backgroundColor: themeColor("--bg-card", "#fff"), border: `1px solid ${themeColor("--border-warm", "#DCE4EF")}`, fontSize: 11 }}
              />
              <Bar dataKey="y" fill={themeColor("--brand", "#F5B400")} radius={[0, 3, 3, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {card.rows.length > 0 && (
        <div className="overflow-x-auto max-h-72 overflow-y-auto rounded-md border border-warm-border bg-card">
          <table className="w-full text-left border-collapse">
            <thead className="sticky top-0 bg-card">
              <tr>
                {card.columns.map((c) => (
                  <th key={c} className="px-2 py-1.5 font-semibold text-muted border-b border-warm-border whitespace-nowrap capitalize">
                    {label(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {card.rows.slice(0, 100).map((r, i) => (
                <tr key={i} className="border-b border-warm-border last:border-0">
                  {r.map((v, j) => (
                    <td key={j} className={`px-2 py-1 whitespace-nowrap ${typeof v === "number" ? "text-right tabular-nums" : "text-body"}`}>
                      {v === null ? "—" : String(v)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {card.rows.length > 100 && <div className="text-muted">Showing 100 of {card.rows.length} rows; the CSV has all of them.</div>}
      {card.truncated && <div className="text-muted">Results were capped at the row limit.</div>}

      <details>
        <summary className="cursor-pointer text-muted">SQL used{card.elapsed_ms !== undefined ? ` · ${card.elapsed_ms} ms` : ""} · read-only, logged</summary>
        <pre className="mt-1 p-2 rounded bg-card border border-warm-border font-mono text-[11px] text-body whitespace-pre-wrap break-words">{card.sql}</pre>
        {card.refused && <div className="mt-1 text-red-700 dark:text-red-300">Refused: {card.refused}</div>}
      </details>
    </div>
  );
};
