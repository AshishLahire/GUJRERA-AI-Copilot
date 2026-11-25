import React, { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

/**
 * Small, accessible charts for the dashboards.
 * One series per chart in a single blue (validated against the light and dark card surfaces); the
 * "where projects stand" bar uses the fixed status colours, always with a text label and count.
 * Bars are at most 24px thick with 4px rounded ends; gridlines are hairlines; every chart has a
 * hover tooltip and a table view.
 */

const fmtN = (n: number) => n.toLocaleString("en-IN");

const TipBox: React.FC<{ label: string; value: number; unit?: string }> = ({ label, value, unit }) => (
  <div className="rounded-lg border border-warm-border bg-card px-3 py-2 shadow-sm text-xs">
    <div className="text-muted">{label}</div>
    <div className="font-semibold text-body tabular-nums">{fmtN(value)}{unit ? ` ${unit}` : ""}</div>
  </div>
);

const TableView: React.FC<{ rows: { label: string; value: number }[]; head: [string, string] }> = ({ rows, head }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="text-[11px] font-semibold text-muted hover:text-body">
        {open ? "Hide table" : "Show as table"}
      </button>
      {open && (
        <table className="mt-2 w-full text-xs">
          <thead><tr className="text-muted text-left"><th className="font-medium py-1">{head[0]}</th><th className="font-medium py-1 text-right">{head[1]}</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label} className="border-t border-warm-border"><td className="py-1 text-body">{r.label}</td><td className="py-1 text-right tabular-nums text-body">{fmtN(r.value)}</td></tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

export const ChartCard: React.FC<{ title: string; sub?: string; children: React.ReactNode; className?: string }> = ({ title, sub, children, className = "" }) => (
  <section className={`rounded-xl border border-warm-border bg-card p-5 ${className}`}>
    <h3 className="font-heading text-sm font-bold text-body">{title}</h3>
    {sub && <p className="text-xs text-muted mt-0.5 leading-relaxed">{sub}</p>}
    <div className="mt-4">{children}</div>
  </section>
);

const axisTick = { fill: "var(--text-muted)", fontSize: 11 };

/** Vertical columns along an ordered axis (years, months). */
export const ColumnChart: React.FC<{
  data: { label: string; value: number }[]; unit?: string; head: [string, string]; height?: number; highlight?: string;
}> = ({ data, unit, head, height = 220, highlight }) => (
  <div>
    <div style={{ height }} role="img" aria-label={`${head[1]} by ${head[0]}: ${data.map((d) => `${d.label} ${d.value}`).join(", ")}`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 18, right: 4, bottom: 0, left: 0 }} barCategoryGap="22%">
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
          <XAxis dataKey="label" tick={axisTick} tickLine={false} axisLine={{ stroke: "var(--chart-axis)" }} interval="preserveStartEnd" />
          <YAxis tick={axisTick} tickLine={false} axisLine={false} width={52} tickFormatter={(v: number) => fmtN(v)} />
          <Tooltip cursor={{ fill: "var(--chart-cursor)" }}
            content={({ active, payload }) => active && payload?.length
              ? <TipBox label={String(payload[0].payload.label)} value={Number(payload[0].value)} unit={unit} /> : null} />
          <Bar dataKey="value" maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false}>
            {data.map((d) => <Cell key={d.label} fill={highlight && d.label === highlight ? "var(--chart-1-strong)" : "var(--chart-1)"} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
    <TableView rows={data} head={head} />
  </div>
);

/** Horizontal bars for categories, value at the bar end. */
export const HBarChart: React.FC<{ data: { label: string; value: number }[]; unit?: string; head: [string, string] }> = ({ data, unit, head }) => {
  const height = Math.max(120, data.length * 34 + 16);
  return (
    <div>
      <div style={{ height }} role="img" aria-label={`${head[1]} by ${head[0]}: ${data.map((d) => `${d.label} ${d.value}`).join(", ")}`}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 0, right: 56, bottom: 0, left: 0 }} barCategoryGap="24%">
            <XAxis type="number" hide />
            <YAxis type="category" dataKey="label" tick={{ ...axisTick, fill: "var(--text-body)", fontSize: 12 }} tickLine={false}
              axisLine={{ stroke: "var(--chart-axis)" }} width={128} />
            <Tooltip cursor={{ fill: "var(--chart-cursor)" }}
              content={({ active, payload }) => active && payload?.length
                ? <TipBox label={String(payload[0].payload.label)} value={Number(payload[0].value)} unit={unit} /> : null} />
            <Bar dataKey="value" fill="var(--chart-1)" maxBarSize={24} radius={[0, 4, 4, 0]} isAnimationActive={false}>
              <LabelList dataKey="value" position="right" formatter={(v: number) => fmtN(v)}
                style={{ fill: "var(--text-muted)", fontSize: 11 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <TableView rows={data} head={head} />
    </div>
  );
};

export type Part = { key: string; label: string; value: number; color: string };

/** One whole split into parts (a tall segmented bar), with a legend of label, count and share. */
export const SegmentedBar: React.FC<{ parts: Part[]; total: number }> = ({ parts, total }) => {
  const shown = parts.filter((p) => p.value > 0);
  const [hover, setHover] = useState<string | null>(null);
  return (
    <div>
      <div className="flex gap-[2px] h-7 w-full" role="img"
        aria-label={shown.map((p) => `${p.label}: ${p.value} (${Math.round((100 * p.value) / Math.max(1, total))}%)`).join("; ")}>
        {shown.map((p) => (
          <div key={p.key} className="relative h-full rounded-[4px] transition-opacity"
            style={{ width: `${(100 * p.value) / Math.max(1, total)}%`, minWidth: 4, background: p.color, opacity: hover && hover !== p.key ? 0.45 : 1 }}
            onMouseEnter={() => setHover(p.key)} onMouseLeave={() => setHover(null)}>
            {hover === p.key && (
              <div className="absolute z-10 bottom-full mb-2 left-1/2 -translate-x-1/2 whitespace-nowrap pointer-events-none">
                <TipBox label={p.label} value={p.value} />
              </div>
            )}
          </div>
        ))}
      </div>
      <ul className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {shown.map((p) => (
          <li key={p.key} className="flex items-start gap-2 text-xs" onMouseEnter={() => setHover(p.key)} onMouseLeave={() => setHover(null)}>
            <span className="mt-0.5 w-3 h-3 rounded-sm shrink-0" style={{ background: p.color }} aria-hidden="true" />
            <span className="leading-snug">
              <span className="text-body font-semibold tabular-nums">{fmtN(p.value)}</span>{" "}
              <span className="text-muted">({Math.round((100 * p.value) / Math.max(1, total))}%)</span>
              <span className="block text-body">{p.label}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
};

/** Fixed status colours (never themed). Always shown with a text label. */
export const STATUS = { good: "#0ca30c", warning: "#fab219", serious: "#ec835a", critical: "#d03b3b", neutral: "#8b8f98" };
