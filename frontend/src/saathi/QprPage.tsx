import React, { useEffect, useState } from "react";
import { AuthExpiredError, QprDraft, QprInput, QprIssue, QprProject, checkQpr, fetchQprDraft, fetchQprOverview, submitQpr } from "../api/gujrera";
import { Icon } from "./Brand";
import { useSaathi } from "./context";
import { En } from "./En";
import { LoginPrompt } from "./RolePages";
import { tr } from "./strings";

const fmt = (iso: string) => new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(/[,\s₹]/g, "")));
const inputCls = "w-full rounded-lg border border-warm-border bg-card text-body px-3 py-2 text-sm focus:outline-none focus:border-brand focus:ring-2 focus:ring-brand/30";

const Field: React.FC<{ label: string; hint?: string; children: React.ReactNode }> = ({ label, hint, children }) => (
  <label className="block text-xs font-semibold text-body">
    {label}
    {hint && <span className="block font-normal text-muted">{hint}</span>}
    <div className="mt-1">{children}</div>
  </label>
);

const Form: React.FC<{ d: QprDraft; onFiled: () => void }> = ({ d, onFiled }) => {
  const { token, lang } = useSaathi();
  const pf = d.prefill;
  const s = (v: number | null) => (v == null ? "" : String(v));
  const [pct, setPct] = useState(s(pf.percent_complete));
  const [units, setUnits] = useState(s(pf.units_booked));
  const [garages, setGarages] = useState(s(pf.garages_booked));
  const [collected, setCollected] = useState(s(pf.collected_total));
  const [deposited, setDeposited] = useState(s(pf.deposited_total));
  const [withdrawn, setWithdrawn] = useState(s(pf.withdrawn_total));
  const [cost, setCost] = useState(s(pf.project_cost));
  const [pending, setPending] = useState<string[]>(pf.approvals.filter((a) => a.status !== "granted").map((a) => a.kind));
  const [note, setNote] = useState("");
  const [issues, setIssues] = useState<QprIssue[] | null>(null);
  const [receipt, setReceipt] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const data = (): QprInput => ({
    percent_complete: num(pct), units_booked: num(units), garages_booked: num(garages), collected_total: num(collected),
    deposited_total: num(deposited), withdrawn_total: num(withdrawn), project_cost: num(cost), approvals_pending: pending,
    status_note: note || null,
  });
  const run = async (file: boolean) => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      if (file) {
        const r = await submitQpr(token, d.project.id, d.quarter, data());
        setIssues(r.issues);
        if (r.filed) { setReceipt(r.receipt ?? null); onFiled(); }
      } else {
        setIssues((await checkQpr(token, d.project.id, d.quarter, data())).issues);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const errors = (issues ?? []).filter((i) => i.level === "error");

  if (receipt) {
    return (
      <div className="p-6 flex flex-col items-start gap-3">
        <span className="w-10 h-10 rounded-lg bg-brand-soft text-brand-strong flex items-center justify-center"><Icon name="doc" /></span>
        <div className="text-sm text-body">Report for <b>{d.quarter}</b> filed. Receipt <span className="font-mono">{receipt}</span></div>
        {(issues ?? []).length > 0 && <ul className="text-xs text-muted list-disc pl-5">{issues!.map((i) => <li key={i.code}>{i.text}</li>)}</ul>}
      </div>
    );
  }
  return (
    <div className="p-5 flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-heading font-bold text-body">{d.project.name} · {d.quarter}</h3>
          <div className="text-xs text-muted">Due {fmt(d.due_on)}{d.late ? " · late" : ""} · last report {d.previous ? `${d.previous.percent}% (${d.previous.quarter})` : "none"}</div>
        </div>
        <span className="text-[11px] text-muted">Section 11(1) · Section 4(2)(l)(D)</span>
      </div>

      <fieldset className="grid sm:grid-cols-3 gap-3">
        <Field label="Completion %" hint={d.previous ? `was ${d.previous.percent}%` : undefined}>
          <input inputMode="decimal" value={pct} onChange={(e) => setPct(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Units booked" hint={`of ${d.project.units} (11(1)(b))`}>
          <input inputMode="numeric" value={units} onChange={(e) => setUnits(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Garages booked" hint="11(1)(c)">
          <input inputMode="numeric" value={garages} onChange={(e) => setGarages(e.target.value)} className={inputCls} />
        </Field>
      </fieldset>

      <fieldset>
        <legend className="text-xs font-semibold text-body mb-1">Approvals still pending <span className="font-normal text-muted">(11(1)(d))</span></legend>
        <div className="flex flex-wrap gap-2">
          {d.prefill.approvals.map((a) => (
            <label key={a.id} className="inline-flex items-center gap-1.5 text-xs rounded-full border border-warm-border px-2.5 py-1">
              <input type="checkbox" checked={pending.includes(a.kind)} className="accent-[var(--brand)]"
                onChange={(e) => setPending((p) => (e.target.checked ? [...p, a.kind] : p.filter((x) => x !== a.kind)))} />
              {a.kind} · {a.authority}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="grid sm:grid-cols-2 gap-3">
        <legend className="col-span-full text-xs font-semibold text-body">Project account to date (₹) <span className="font-normal text-muted">· Section 4(2)(l)(D)</span></legend>
        <Field label="Collected from buyers"><input inputMode="numeric" value={collected} onChange={(e) => setCollected(e.target.value)} className={inputCls} /></Field>
        <Field label="Deposited in the separate account" hint="at least 70% of collections"><input inputMode="numeric" value={deposited} onChange={(e) => setDeposited(e.target.value)} className={inputCls} /></Field>
        <Field label="Withdrawn from it" hint="in proportion to completion, certified"><input inputMode="numeric" value={withdrawn} onChange={(e) => setWithdrawn(e.target.value)} className={inputCls} /></Field>
        <Field label="Estimated project cost"><input inputMode="numeric" value={cost} onChange={(e) => setCost(e.target.value)} className={inputCls} /></Field>
      </fieldset>

      <Field label="Status of the project" hint="11(1)(e): short note, e.g. slab work on floors 6-8">
        <input value={note} onChange={(e) => setNote(e.target.value)} className={inputCls} />
      </Field>

      {issues && (
        <ul className="flex flex-col gap-1.5" aria-live="polite">
          {issues.length === 0 && <li className="text-sm text-emerald-700 dark:text-emerald-300">No problems found.</li>}
          {issues.map((i) => (
            <li key={i.code} className={`text-sm rounded-md px-3 py-2 border ${i.level === "error"
              ? "bg-red-50 text-red-900 border-red-200 dark:bg-red-950/40 dark:text-red-200 dark:border-red-900"
              : "bg-accent-surface text-accent-amber-strong border-accent-border"}`}>
              <b className="uppercase text-[10px] tracking-wide mr-1">{i.level}</b>{i.text}
            </li>
          ))}
        </ul>
      )}
      {error && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>}
      <div className="flex gap-2">
        <button type="button" disabled={busy} onClick={() => void run(false)} className="px-4 py-2 rounded-lg border border-warm-strong text-sm font-semibold text-body leading-tight">
          {tr("qprCheck", lang)}<En k="qprCheck" className="font-normal" />
        </button>
        <button type="button" disabled={busy || issues === null || errors.length > 0} onClick={() => void run(true)}
          className="px-4 py-2 rounded-lg bg-primary-bg text-primary-text text-sm font-semibold leading-tight disabled:opacity-40">
          {tr("qprFile", lang)}<En k="qprFile" className="font-normal" />
        </button>
      </div>
      <p className="text-[11px] text-muted">Check first; filing is enabled when there are no errors. Warnings are filed with the report.</p>
    </div>
  );
};

export const QprPage: React.FC = () => {
  const { user, token, lang, logout } = useSaathi();
  const allowed = user?.role === "developer";
  const [projects, setProjects] = useState<QprProject[] | null>(null);
  const [sel, setSel] = useState<{ pid: number; q: string } | null>(null);
  const [draft, setDraft] = useState<QprDraft | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    if (!allowed || !token) return;
    fetchQprOverview(token).then((o) => {
      setProjects(o.projects);
      const first = o.projects.find((p) => p.to_file.length);
      setSel((s) => s ?? (first ? { pid: first.project_id, q: first.to_file[0] } : null));
    }).catch((e) => { if (e instanceof AuthExpiredError) logout(); setError((e as Error).message); });
  };
  useEffect(load, [allowed, token]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!sel || !token) return;
    setDraft(null);
    fetchQprDraft(token, sel.pid, sel.q).then(setDraft).catch((e) => setError((e as Error).message));
  }, [sel, token]);

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <div className="max-w-3xl">
        <p className="text-sm text-muted leading-relaxed">{tr("qprIntro", lang)}</p>
        {lang !== "en" && <p lang="en" className="text-xs text-muted opacity-80 mt-0.5">{tr("qprIntro", "en")}</p>}
      </div>
      {!allowed && <LoginPrompt k="loginNeededQpr" />}
      {allowed && error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 p-4 text-sm">{error}</div>}
      {allowed && projects && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] items-start">
          <ul className="flex flex-col gap-3">
            {projects.map((p) => (
              <li key={p.project_id} className="rounded-xl border border-warm-border bg-card p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold text-body">{lang === "gu" && p.name_gu ? p.name_gu : p.name}</div>
                    <div className="text-[11px] text-muted">{p.district} · last filed {p.last_filed ? `${p.last_filed.percent}% (${p.last_filed.quarter})` : "—"}</div>
                  </div>
                  {p.overdue.length > 0
                    ? <span className="rounded-full border px-2 py-0.5 text-[11px] font-semibold bg-red-50 text-red-800 border-red-200 dark:bg-red-950/50 dark:text-red-200 dark:border-red-900">{p.overdue.length} overdue</span>
                    : <span className="rounded-full border px-2 py-0.5 text-[11px] font-semibold bg-subtle text-muted border-warm-border">up to date</span>}
                </div>
                {p.to_file.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {p.to_file.map((q) => (
                      <button key={q} type="button" onClick={() => setSel({ pid: p.project_id, q })}
                        className={`text-[11px] font-mono rounded border px-2 py-0.5 ${sel?.pid === p.project_id && sel.q === q ? "border-brand bg-brand-soft text-body" : "border-warm-border hover:border-warm-strong"}`}>
                        {q}
                      </button>
                    ))}
                  </div>
                )}
                <div className="mt-2 text-[11px] text-muted">
                  Next: {p.next_due.quarter} due {fmt(p.next_due.due_on)}
                  {p.penalties_pending.length > 0 && ` · ${p.penalties_pending.length} late-filing penalty notice(s) unpaid`}
                </div>
              </li>
            ))}
            {projects.length === 0 && <li className="text-sm text-muted">No ongoing projects.</li>}
          </ul>
          <div className="rounded-xl border border-warm-border bg-card lg:sticky lg:top-20">
            {draft ? <Form key={`${draft.project.id}-${draft.quarter}`} d={draft} onFiled={load} />
              : <div className="p-6 text-sm text-muted">{sel ? "…" : "All reports are filed. The next one opens when the quarter ends."}</div>}
          </div>
        </div>
      )}
    </div>
  );
};
