import React, { useEffect, useMemo, useState } from "react";
import { CalcProject, ProjectReport, fetchProjectReport } from "../api/gujrera";
import { BrandMark, Icon } from "./Brand";
import { ProjectPicker } from "./CalculatorPage";
import { StateChip } from "./OrderTrackerPage";
import { useSaathi } from "./context";
import { En } from "./En";
import { StringKey, tr } from "./strings";

type Tone = "good" | "warn" | "bad";
const TONE_DOT: Record<Tone, string> = { good: "bg-emerald-600", warn: "bg-brand", bad: "bg-red-600" };
const TONE_BANNER: Record<Tone, string> = {
  good: "border-emerald-200 bg-emerald-50 text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-900",
  warn: "border-accent-border bg-accent-surface text-accent-amber-strong",
  bad: "border-red-200 bg-red-50 text-red-900 dark:bg-red-950/40 dark:text-red-200 dark:border-red-900",
};
const TONE_KEY: Record<Tone, StringKey> = { good: "repGood", warn: "repWarn", bad: "repBad" };
const fmt = (iso: string | null) =>
  iso ? new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—";

const H: React.FC<{ k: StringKey }> = ({ k }) => {
  const { lang } = useSaathi();
  return (
    <h3 className="font-heading text-sm font-bold text-body border-b border-warm-border pb-1.5 mb-3 break-after-avoid">
      {tr(k, lang)}
      {lang !== "en" && <span lang="en" className="ml-2 font-normal text-muted text-xs">{tr(k, "en")}</span>}
    </h3>
  );
};

/** Plain-language name for a cited record. */
function sourceLabel(c: { type: string; id: string }): string {
  switch (c.type) {
    case "project": return `GUJRERA registration record ${c.id}`;
    case "progress_report": return `Quarterly progress report ${c.id.split(":")[1] ?? c.id}`;
    case "approval": return `Approval record no. ${c.id}`;
    case "complaint_stats": return "Complaint counts for this project (GUJRERA)";
    case "promoter_scorecard": return "Promoter's record in the GUJRERA registry";
    case "order": return `GUJRERA order ${c.id}`;
    default: return c.id;
  }
}

function initialProjectId(): number | null {
  const v = Number(new URLSearchParams(window.location.search).get("project"));
  return Number.isFinite(v) && v > 0 ? v : null;
}

export const ReportPage: React.FC<{ projectId: number | null }> = ({ projectId }) => {
  const { lang } = useSaathi();
  const [picked, setPicked] = useState<CalcProject | null>(null);
  const [id, setId] = useState<number | null>(projectId ?? initialProjectId());
  const [rep, setRep] = useState<ProjectReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (projectId) setId(projectId);
  }, [projectId]);

  useEffect(() => {
    if (!id) return;
    const url = new URL(window.location.href);
    url.searchParams.set("project", String(id));
    window.history.replaceState(null, "", url.toString());
    setError(null);
    fetchProjectReport(id, lang).then(setRep).catch((e) => { setRep(null); setError((e as Error).message); });
  }, [id, lang]);

  // Number every source once, in order of first use.
  const sources = useMemo(() => {
    const list: { type: string; id: string }[] = [];
    if (rep) {
      for (const block of [rep.glance, rep.questions, rep.rights]) {
        for (const item of block) for (const c of item.citations) if (!list.some((x) => x.type === c.type && x.id === c.id)) list.push(c);
      }
    }
    return list;
  }, [rep]);
  const refs = (cs: { type: string; id: string }[]) => (
    <sup className="ml-0.5 text-[10px] font-semibold text-brand-strong">
      {Array.from(new Set(cs.map((c) => sources.findIndex((x) => x.type === c.type && x.id === c.id) + 1))).map((n) => `[${n}]`).join("")}
    </sup>
  );

  const p = rep?.project;
  const name = p ? (lang === "gu" && p.name_gu ? p.name_gu : p.name) : "";
  const maxPct = 100;

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6 print:p-0 print:max-w-none">
      <div className="flex flex-col gap-4 print:hidden">
        <div className="max-w-3xl">
          <p className="text-sm text-muted leading-relaxed">{tr("repIntro", lang)}</p>
          {lang !== "en" && <p lang="en" className="text-xs text-muted opacity-80 mt-0.5">{tr("repIntro", "en")}</p>}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-full sm:w-96">
            <label htmlFor="report-project" className="block text-xs font-semibold text-body mb-1.5">{tr("calcProject", lang)}<En k="calcProject" className="font-normal text-muted" /></label>
            <ProjectPicker inputId="report-project" value={picked} onChange={(x) => { setPicked(x); if (x) setId(x.id); }} />
          </div>
          {rep && (
            <button type="button" onClick={() => window.print()}
              className="inline-flex items-center gap-2 rounded-lg bg-primary-bg text-primary-text px-4 py-2.5 text-sm font-semibold leading-tight">
              <Icon name="printer" className="w-4 h-4" />
              <span className="text-left">{tr("repPrint", lang)}<En k="repPrint" className="font-normal" /></span>
            </button>
          )}
        </div>
        {error && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>}
        {!id && (
          <div className="rounded-xl border border-dashed border-warm-strong p-8 text-center text-sm text-muted">
            <span className="inline-flex w-10 h-10 rounded-lg bg-brand-soft text-brand-strong items-center justify-center mb-3"><Icon name="doc" /></span>
            <p>Choose a project to see its report.</p>
          </div>
        )}
      </div>

      {rep && p && (
        <article className="report-sheet mx-auto w-full max-w-4xl rounded-xl border border-warm-border bg-card p-6 sm:p-8 text-body print:border-0 print:rounded-none print:p-0 print:max-w-none">
          {/* Letterhead */}
          <header className="flex items-start justify-between gap-4 border-b-2 border-brand pb-4">
            <div className="flex items-center gap-3">
              <BrandMark className="w-10 h-10" />
              <div className="leading-tight">
                <div className="font-heading font-bold">GujRERA Saathi</div>
                <div className="text-xs text-muted">{tr("navReport", lang)}{lang !== "en" ? ` · ${tr("navReport", "en")}` : ""}</div>
              </div>
            </div>
            <div className="text-right text-xs text-muted">
              <div>{fmt(rep.generated_on)}</div>
              <div>From GUJRERA registry records</div>
            </div>
          </header>

          {/* Project */}
          <section className="mt-5">
            <h2 className="font-heading text-2xl font-bold">{name}</h2>
            {lang === "gu" && p.name_gu && <div className="text-sm text-muted">{p.name}</div>}
            <div className="mt-1 font-mono text-xs text-muted break-all">{p.rera_no}</div>
            <dl className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-2 text-sm">
              <div><dt className="text-xs text-muted">Promoter</dt><dd>{p.promoter.replace(" (Demo)", "")}</dd></div>
              <div><dt className="text-xs text-muted">Location</dt><dd>{[p.taluka, p.district].filter(Boolean).join(", ")}</dd></div>
              <div><dt className="text-xs text-muted">Type / units</dt><dd>{p.type}{p.units ? ` · ${p.units}` : ""}</dd></div>
              <div><dt className="text-xs text-muted">Status</dt><dd>{p.status_text}</dd></div>
            </dl>
          </section>

          {/* Overall */}
          <div className={`mt-5 rounded-lg border px-4 py-3 text-sm font-semibold ${TONE_BANNER[rep.overall]}`}>
            {tr(TONE_KEY[rep.overall], lang)}
            {lang !== "en" && <span lang="en" className="block text-xs font-normal opacity-80">{tr(TONE_KEY[rep.overall], "en")}</span>}
          </div>

          {/* At a glance */}
          <section className="mt-6 break-inside-avoid">
            <H k="repGlance" />
            <ul className="flex flex-col gap-2 text-sm">
              {rep.glance.map((g, i) => (
                <li key={i} className="flex gap-2.5">
                  <span className={`mt-1.5 w-2 h-2 shrink-0 rounded-full ${TONE_DOT[g.tone]}`} aria-label={g.tone} />
                  <span>{g.text}{refs(g.citations)}</span>
                </li>
              ))}
            </ul>
          </section>

          <div className="mt-6 grid gap-6 md:grid-cols-2 print:grid-cols-2">
            {/* Dates */}
            <section className="break-inside-avoid">
              <H k="repDates" />
              <table className="w-full text-sm">
                <tbody>
                  {[
                    ["Registered", p.reg_date],
                    ["Completion first promised", p.proposed_completion],
                    ["Completion date now", p.revised_completion ?? p.proposed_completion],
                    ["Completed on", p.actual_completion],
                    ["Registration valid until", p.reg_valid_until],
                  ].filter(([, v]) => v).map(([k, v]) => (
                    <tr key={k as string} className="border-b border-warm-border last:border-0">
                      <td className="py-1.5 text-muted">{k}</td><td className="py-1.5 text-right tabular-nums">{fmt(v as string)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            {/* Approvals */}
            <section className="break-inside-avoid">
              <H k="repApprovals" />
              {rep.approvals.length === 0 ? <p className="text-sm text-muted">None listed.</p> : (
                <ul className="text-sm flex flex-col gap-1.5">
                  {rep.approvals.map((a, i) => (
                    <li key={i} className="flex justify-between gap-3">
                      <span>{a.kind} <span className="text-muted">· {a.authority}</span></span>
                      <span className={a.status === "granted" ? "text-emerald-700 dark:text-emerald-300" : "text-red-700 dark:text-red-300 font-semibold"}>{a.status}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          {/* Progress */}
          {rep.progress.length > 0 && (
            <section className="mt-6 break-inside-avoid">
              <H k="repProgress" />
              <div className="flex items-end gap-1 h-28 print:h-20 border-b border-warm-border" role="img" aria-label="Percent complete by quarter">
                {rep.progress.map((q) => (
                  <div key={q.quarter} className="flex-1 min-w-0 flex flex-col items-center justify-end h-full" title={`${q.quarter}: ${q.state === "missing" ? "not filed" : `${q.percent}%`}`}>
                    {q.state === "missing" ? (
                      <div className="w-full max-w-[18px] h-3 border border-dashed border-red-500 rounded-sm" />
                    ) : (
                      <div className={`w-full max-w-[18px] rounded-t-sm ${q.state === "late" ? "bg-brand/60" : "bg-brand"}`} style={{ height: `${(100 * q.percent) / maxPct}%` }} />
                    )}
                  </div>
                ))}
              </div>
              <div className="flex gap-1 mt-1">
                {rep.progress.map((q, i) => (
                  <div key={q.quarter} className="flex-1 min-w-0 text-center text-[9px] text-muted truncate">
                    {i === 0 || i === rep.progress.length - 1 || i % 4 === 0 ? q.quarter : ""}
                  </div>
                ))}
              </div>
              <p className="mt-1 text-[11px] text-muted">
                Last filed: {(() => { const f = [...rep.progress].reverse().find((q) => q.filed_on); return f ? `${f.percent}% (${f.quarter})` : "—"; })()}
                {" · "}Dashed red: report not filed · Lighter: filed late
              </p>
            </section>
          )}

          <div className="mt-6 grid gap-6 md:grid-cols-2 print:grid-cols-2">
            {/* Complaints */}
            <section className="break-inside-avoid">
              <H k="repComplaints" />
              <p className="text-sm">Total {rep.complaints.total} · open {rep.complaints.open}</p>
              {Object.keys(rep.complaints.by_category).length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {Object.entries(rep.complaints.by_category).map(([c, n]) => (
                    <span key={c} className="text-[11px] rounded-full border border-warm-border px-2 py-0.5">{c.replace(/_/g, " ")} · {n}</span>
                  ))}
                </div>
              )}
            </section>
            {/* Promoter */}
            <section className="break-inside-avoid">
              <H k="repPromoter" />
              <p className="text-sm">{rep.promoter.name.replace(" (Demo)", "")}: {rep.promoter.projects ?? 0} projects · {rep.promoter.delayed ?? 0} delayed · {rep.promoter.complaints_total ?? 0} complaints · {rep.promoter.adverse_orders ?? 0} adverse orders</p>
              {rep.promoter.other_projects.length > 0 && (
                <ul className="mt-2 text-xs text-muted flex flex-col gap-0.5">
                  {rep.promoter.other_projects.map((o) => (
                    <li key={o.id}>{o.name} · {o.district} · {o.status}{o.delay_days > 0 ? ` · ${o.delay_days} days behind` : ""}</li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          {/* Orders */}
          {rep.orders.length > 0 && (
            <section className="mt-6 break-inside-avoid">
              <H k="repOrders" />
              <ul className="text-sm flex flex-col gap-1.5">
                {rep.orders.map((o) => (
                  <li key={o.order_no}>
                    <span className="font-mono text-xs">{o.order_no}</span> · {o.type} · {fmt(o.issued_on)}
                    {o.compliance && <span className="ml-2"><StateChip state={o.compliance.state} /></span>}
                    <div className="text-xs text-muted">{o.summary}{o.compliance?.text ? ` ${o.compliance.text}` : ""}</div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Questions */}
          <section className="mt-6 break-inside-avoid">
            <H k="repQuestions" />
            <ul className="flex flex-col gap-2 text-sm">
              {rep.questions.map((q, i) => (
                <li key={i} className="flex gap-2.5">
                  <span className="mt-0.5 w-4 h-4 shrink-0 rounded border border-warm-strong" aria-hidden="true" />
                  <span>{q.text}{refs(q.citations)}</span>
                </li>
              ))}
            </ul>
          </section>

          {/* Rights */}
          <section className="mt-6 break-inside-avoid">
            <H k="repRights" />
            <ul className="flex flex-col gap-1.5 text-sm list-disc pl-5">
              {rep.rights.map((r, i) => <li key={i}>{r.text}{refs(r.citations)}</li>)}
            </ul>
          </section>

          {/* Sources */}
          <section className="mt-6">
            <H k="repSources" />
            <ol className="text-[11px] text-muted list-decimal pl-5 grid sm:grid-cols-2 print:grid-cols-2 gap-x-6 gap-y-0.5">
              {sources.map((s) => <li key={`${s.type}:${s.id}`} className="break-words">{sourceLabel(s)}</li>)}
            </ol>
          </section>

          <footer className="mt-6 pt-3 border-t border-warm-border text-[11px] text-muted leading-relaxed">
            Prepared by GujRERA Saathi from GUJRERA registry records on {fmt(rep.generated_on)}. Check the latest status on the
            GUJRERA portal before paying. This report states registry facts; it is not legal advice.
          </footer>
        </article>
      )}
    </div>
  );
};
