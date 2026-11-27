import React, { useMemo, useState } from "react";
import { Lang, exportReport } from "../api/gujrera";
import { say, useSaathi, useUiLang } from "../saathi/context";
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
  /** The question that produced the card (chat cards carry it); enables the Excel export. */
  question?: string;
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

const esc = (v: unknown) => String(v ?? "").replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch] as string));

/** A clean printable page (Save as PDF from the print dialog): title, question, scope, time, table. */
function printReport(card: AnalyticsCardData, lang: Lang, question?: string) {
  const w = window.open("", "_blank", "noopener=no,width=1000,height=800");
  if (!w) return;
  const head = card.columns.map((c) => `<th>${esc(label(c))}</th>`).join("");
  const body = card.rows.map((r) => `<tr>${r.map((v) => `<td>${v === null ? "—" : esc(v)}</td>`).join("")}</tr>`).join("");
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(card.title)}</title>
<style>body{font:12px system-ui,sans-serif;color:#14161B;margin:24px}h1{font-size:18px;margin:0 0 4px}
.meta{color:#5E6370;margin:0 0 12px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #E3D09A;padding:4px 6px;text-align:left;vertical-align:top}
th{background:#FFF1BF}tr:nth-child(even) td{background:#FFFCF0}.foot{margin-top:10px;color:#5E6370;font-size:10px}</style></head><body>
<h1>${esc(card.title)}</h1>
<p class="meta">${question ? `${say({ en: "Question:", gu: "પ્રશ્ન:", hi: "प्रश्न:" }, lang)} ${esc(question)} · ` : ""}${card.scoped_to ? `${esc(say({ en: `${card.scoped_to} only`, gu: `ફક્ત ${card.scoped_to}`, hi: `केवल ${card.scoped_to}` }, lang))} · ` : `${say({ en: "All districts", gu: "બધા જિલ્લા", hi: "सभी ज़िले" }, lang)} · `}${say({ en: `${card.rows.length} rows`, gu: `${card.rows.length} પંક્તિઓ`, hi: `${card.rows.length} पंक्तियाँ` }, lang)} · ${esc(new Date().toLocaleString("en-IN"))}</p>
<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>
<p class="foot">${say({ en: "GujRERA Saathi · read-only query on the reporting views, logged.", gu: "GujRERA Saathi · રિપોર્ટિંગ વ્યૂ પર ફક્ત વાંચવા માટેની ક્વેરી, લૉગ થયેલી.", hi: "GujRERA Saathi · रिपोर्टिंग व्यू पर केवल पढ़ने वाली क्वेरी, लॉग की गई।" }, lang)}</p>
<script>window.onload=function(){window.print()}</script></body></html>`);
  w.document.close();
}

/** SVG fill attributes cannot read CSS variables, so resolve the theme colours when rendering. */
function themeColor(name: string, fallback: string): string {
  try {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  } catch {
    return fallback;
  }
}

export const AnalyticsCard: React.FC<{ card: AnalyticsCardData; question?: string }> = ({ card, question }) => {
  const { token } = useSaathi();
  const lang = useUiLang();
  const asked = question ?? card.question;
  const [sort, setSort] = useState<{ col: number; dir: 1 | -1 } | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const rows = useMemo(() => {
    if (!sort) return card.rows;
    const { col, dir } = sort;
    return [...card.rows].sort((a, b) => {
      const x = a[col], y = b[col];
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "en", { numeric: true })) * dir;
    });
  }, [card.rows, sort]);
  const toggle = (col: number) => setSort((s) => (s && s.col === col ? (s.dir === 1 ? { col, dir: -1 } : null) : { col, dir: 1 }));
  const toExcel = async () => {
    if (!token || !asked) return;
    setExporting(true);
    setExportError(null);
    try { await exportReport(token, asked, lang); } catch (e) { setExportError((e as Error).message); } finally { setExporting(false); }
  };
  const chartData =
    card.chart && card.rows.length > 1
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
          {card.source === "llm"
            ? say({ en: "AI-written query", gu: "AI દ્વારા લખાયેલી ક્વેરી", hi: "AI द्वारा लिखी गई क्वेरी" }, lang)
            : say({ en: "Standard report", gu: "માનક રિપોર્ટ", hi: "मानक रिपोर्ट" }, lang)}
        </span>
        {card.scoped_to && (
          <span className="px-2 py-0.5 rounded-full border border-warm-border text-[10px] text-muted">
            {say({ en: `${card.scoped_to} only`, gu: `ફક્ત ${card.scoped_to}`, hi: `केवल ${card.scoped_to}` }, lang)}
          </span>
        )}
        {card.rows.length > 0 && (
          <span className="ml-auto flex flex-wrap gap-1.5">
            {asked && token && (
              <button type="button" onClick={() => void toExcel()} disabled={exporting}
                className="px-2.5 py-1 rounded-md bg-primary-bg text-primary-text font-semibold disabled:opacity-60">
                {exporting ? say({ en: "Preparing…", gu: "તૈયાર થઈ રહ્યું છે…", hi: "तैयार हो रहा है…" }, lang) : "Excel"}
              </button>
            )}
            <button type="button" onClick={() => printReport({ ...card, rows }, lang, asked)}
              className="px-2.5 py-1 rounded-md border border-warm-border bg-card text-body font-semibold hover:border-brand">
              {say({ en: "Print / PDF", gu: "છાપો / PDF", hi: "प्रिंट करें / PDF" }, lang)}
            </button>
            <button type="button" onClick={() => download({ ...card, rows })}
              className="px-2.5 py-1 rounded-md border border-warm-border bg-card text-body font-semibold hover:border-brand">
              CSV
            </button>
          </span>
        )}
      </div>
      {exportError && <div role="alert" className="text-red-700 dark:text-red-300">{exportError}</div>}
      {chartData && (
        <div className="h-56 w-full" aria-label={say({
          en: `Bar chart of ${label(card.chart!.y)} by ${label(card.chart!.x)}`,
          gu: `${label(card.chart!.x)} પ્રમાણે ${label(card.chart!.y)} નો બાર ચાર્ટ`,
          hi: `${label(card.chart!.x)} के अनुसार ${label(card.chart!.y)} का बार चार्ट`,
        }, lang)}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 16, left: 4, bottom: 4 }}>
              <XAxis type="number" tick={{ fontSize: 10, fill: themeColor("--text-muted", "#55657F") }} axisLine={false} tickLine={false} allowDecimals={false} />
              <YAxis type="category" dataKey="x" width={150} interval={0} tick={{ fontSize: 10, fill: themeColor("--text-body", "#0F1E3A") }} axisLine={false} tickLine={false} />
              <Tooltip
                formatter={(v: number) => [v, label(card.chart!.y)]}
                contentStyle={{ backgroundColor: themeColor("--bg-card", "#fff"), border: `1px solid ${themeColor("--border-warm", "#DCE4EF")}`, fontSize: 11 }}
              />
              <Bar dataKey="y" fill={themeColor("--chart-1", "#C98500")} maxBarSize={24} radius={[0, 3, 3, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {card.rows.length > 0 && (
        <div className="overflow-x-auto max-h-72 overflow-y-auto rounded-md border border-warm-border bg-card">
          <table className="w-full text-left border-collapse">
            <thead className="sticky top-0 bg-card">
              <tr>
                {card.columns.map((c, i) => (
                  <th key={c} className="px-0 py-0 font-semibold text-muted border-b border-warm-border whitespace-nowrap capitalize"
                    aria-sort={sort?.col === i ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
                    <button type="button" onClick={() => toggle(i)} title={say({ en: "Sort by this column", gu: "આ કૉલમ પ્રમાણે ગોઠવો", hi: "इस कॉलम के अनुसार क्रम दें" }, lang)}
                      className="w-full text-left px-2 py-1.5 hover:text-body capitalize">
                      {label(c)}{sort?.col === i ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 100).map((r, i) => (
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
      {card.rows.length > 100 && <div className="text-muted">{say({
        en: `Showing 100 of ${card.rows.length} rows; Excel, CSV and print have all of them.`,
        gu: `${card.rows.length} માંથી 100 પંક્તિઓ બતાવી છે; Excel, CSV અને છાપવામાં બધી છે.`,
        hi: `${card.rows.length} में से 100 पंक्तियाँ दिखाई गई हैं; Excel, CSV और प्रिंट में सभी हैं।`,
      }, lang)}</div>}
      {card.truncated && <div className="text-muted">{say({ en: "Results were capped at the row limit.", gu: "પરિણામો પંક્તિ મર્યાદા સુધી સીમિત છે.", hi: "परिणाम पंक्ति सीमा तक सीमित हैं।" }, lang)}</div>}

      <details>
        <summary className="cursor-pointer text-muted">{(() => {
          const ms = card.elapsed_ms !== undefined ? ` · ${card.elapsed_ms} ms` : "";
          return say({ en: `SQL used${ms} · read-only, logged`, gu: `વપરાયેલી SQL${ms} · ફક્ત વાંચવા માટે, લૉગ થયેલી`, hi: `उपयोग की गई SQL${ms} · केवल पढ़ने के लिए, लॉग की गई` }, lang);
        })()}</summary>
        <pre className="mt-1 p-2 rounded bg-card border border-warm-border font-mono text-[11px] text-body whitespace-pre-wrap break-words">{card.sql}</pre>
        {card.refused && <div className="mt-1 text-red-700 dark:text-red-300">{say({ en: "Refused:", gu: "નકાર્યું:", hi: "अस्वीकार:" }, lang)} {card.refused}</div>}
      </details>
    </div>
  );
};
