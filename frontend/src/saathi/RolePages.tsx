import React, { useEffect, useState } from "react";
import {
  AnalyticsResponse,
  AuthExpiredError,
  SelfServiceSummary,
  fetchSelfServiceSummary,
  runAnalytics,
} from "../api/gujrera";
import { SavedReport, deleteSavedReport, fetchHealth, fetchSavedReports, navigateTo, saveReport } from "../api/gujrera";
import { AnalyticsCard, AnalyticsCardData } from "../components/AnalyticsCard";
import { AccountBar } from "../components/AccountBar";
import { Icon } from "./Brand";
import { useSaathi } from "./context";
import { En } from "./En";
import { StringKey, tr } from "./strings";

export const LoginPrompt: React.FC<{ k: StringKey }> = ({ k }) => {
  const { lang } = useSaathi();
  return (
  <div className="rounded-2xl border border-warm-border bg-card p-8 flex flex-col items-center text-center gap-4">
    <span className="w-12 h-12 rounded-full bg-brand-soft text-brand-strong flex items-center justify-center">
      <Icon name="lock" className="w-6 h-6" />
    </span>
    <p className="text-body max-w-md">{tr(k, lang)}<En k={k} className="mt-1 text-muted" /></p>
    <AccountBar />
  </div>
  );
};

const Stat: React.FC<{ k: StringKey; value: string | number; tone?: "warn" | "bad" | "ok" }> = ({ k, value, tone }) => {
  const { lang } = useSaathi();
  return (
  <div className="rounded-xl border border-warm-border bg-card p-4">
    <div className="text-xs text-muted">{tr(k, lang)}<En k={k} /></div>
    <div className={`mt-1 font-heading text-2xl font-bold ${
      tone === "bad" ? "text-red-700 dark:text-red-300" : tone === "warn" ? "text-amber-700 dark:text-amber-300" : "text-body"
    }`}>{value}</div>
  </div>
  );
};

type Due = { description: string; amount: number | null; due_date: string; overdue: boolean };
type Reg = { project: string; rera_no: string; valid_until: string; days_left: number };

export const PromoterPage: React.FC<{ onAsk: (q: string) => void }> = ({ onAsk }) => {
  const { user, token, lang, logout } = useSaathi();
  const [data, setData] = useState<SelfServiceSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const allowed = user && (user.role === "developer" || user.role === "agent");

  useEffect(() => {
    if (!allowed || !token) return;
    setError(null);
    fetchSelfServiceSummary(token, lang)
      .then(setData)
      .catch((e: Error) => {
        if (e instanceof AuthExpiredError) logout();
        setError(e.message);
      });
  }, [allowed, token, lang, logout]);

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <div>
        <h2 className="font-heading text-xl font-bold text-body">{tr("dashTitle", lang)}<En k="dashTitle" className="text-muted" /></h2>
        {allowed && <p className="text-sm text-muted mt-1">{user?.display_name}{data?.is_mock ? " · demo data" : ""}</p>}
      </div>
      {!allowed && <LoginPrompt k="loginNeededPromoter" />}
      {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 p-4 text-sm">{error}</div>}
      {allowed && data && data.card.role === "developer" && (() => {
        const dues = (data.card.dues as Due[]) ?? [];
        const regs = (data.card.registrations as Reg[]) ?? [];
        const qpr = (data.card.qpr_missing as { project: string; quarters: string[] }[]) ?? [];
        const notices = (data.card.notices as { description: string; issued_on: string; due_date: string | null }[]) ?? [];
        const total = dues.reduce((s, d) => s + (d.amount ?? 0), 0);
        const overdue = dues.filter((d) => d.overdue).length;
        const ending = regs.filter((r) => r.days_left <= 180).length;
        return (
          <>
            <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
              <Stat k="statDues" value={`₹${total.toLocaleString("en-IN")}`} tone={total ? "warn" : "ok"} />
              <Stat k="statOverdue" value={overdue} tone={overdue ? "bad" : "ok"} />
              <Stat k="statNotices" value={notices.length} tone={notices.length ? "warn" : "ok"} />
              <Stat k="statEnding" value={ending} tone={ending ? "warn" : "ok"} />
            </div>
            <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
              <section className="rounded-2xl border border-warm-border bg-card p-5">
                <h2 className="font-heading font-bold text-body mb-3">{tr("attention", lang)}<En k="attention" className="text-muted" /></h2>
                <ul className="flex flex-col gap-2.5">
                  {data.sentences.slice(1).map((s, i) => (
                    <li key={i} className="flex gap-2 text-sm text-body leading-relaxed">
                      <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-accent-amber shrink-0" />{s.text}
                    </li>
                  ))}
                </ul>
                <button
                  type="button"
                  onClick={() => onAsk({ en: "What are my dues?", gu: "મારી બાકી ચુકવણી", hi: "मेरे बकाया क्या हैं?" }[lang])}
                  className="mt-4 px-4 py-2 rounded-lg bg-primary-bg text-primary-text text-sm font-semibold"
                >
                  {tr("dashAsk", lang)}
                  <En k="dashAsk" />
                </button>
                <button type="button" onClick={() => navigateTo("qpr")}
                  className="mt-4 ml-2 px-4 py-2 rounded-lg border border-warm-strong text-body text-sm font-semibold">
                  {tr("qprPrepare", lang)}
                  <En k="qprPrepare" />
                </button>
              </section>
              <section className="flex flex-col gap-4">
                {dues.length > 0 && (
                  <div className="rounded-2xl border border-warm-border bg-card p-5">
                    <h2 className="font-heading font-bold text-body mb-2">{tr("statDues", lang)}<En k="statDues" className="text-muted" /></h2>
                    <ul className="divide-y divide-warm-border text-sm">
                      {dues.map((d, i) => (
                        <li key={i} className="py-2 flex justify-between gap-3">
                          <span className="text-body">{d.description}</span>
                          <span className="whitespace-nowrap text-right">
                            {d.amount ? `₹${d.amount.toLocaleString("en-IN")}` : "—"}
                            <span className={`block text-xs ${d.overdue ? "text-red-700 dark:text-red-300" : "text-muted"}`}>
                              {d.overdue ? "overdue · " : "due "}{d.due_date}
                            </span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {qpr.length > 0 && (
                  <div className="rounded-2xl border border-warm-border bg-card p-5 text-sm">
                    <h2 className="font-heading font-bold text-body mb-2">{tr("qprNotFiled", lang)}<En k="qprNotFiled" className="text-muted" /></h2>
                    {qpr.map((q) => <div key={q.project}><b>{q.project}</b>: <span className="text-muted">{q.quarters.join(", ")}</span></div>)}
                  </div>
                )}
                {regs.length > 0 && (
                  <div className="rounded-2xl border border-warm-border bg-card p-5 text-sm">
                    <h2 className="font-heading font-bold text-body mb-2">{tr("registrations", lang)}<En k="registrations" className="text-muted" /></h2>
                    {regs.map((r) => (
                      <div key={r.rera_no} className="flex justify-between gap-2 py-1">
                        <span>{r.project}</span>
                        <span className={r.days_left < 0 ? "text-red-700 dark:text-red-300" : r.days_left <= 180 ? "text-amber-700 dark:text-amber-300" : "text-muted"}>
                          {r.valid_until} ({r.days_left < 0 ? "ended" : `${r.days_left} days`})
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </div>
          </>
        );
      })()}
      {allowed && data && data.card.role === "agent" && (
        <section className="rounded-2xl border border-warm-border bg-card p-5">
          <ul className="flex flex-col gap-2.5 text-sm">
            {data.sentences.map((s, i) => <li key={i}>{s.text}</li>)}
          </ul>
        </section>
      )}
    </div>
  );
};

const REPORTS = [
  "Which promoters have the most delayed projects?",
  "Most delayed ongoing projects",
  "Complaints by category",
  "Oldest open complaints",
  "Promoters with the most complaints",
  "Lapsed or soon-ending registrations",
  "Agents with expired registration",
  "District-wise projects and delays",
  "Promoters with penalty or show-cause orders",
];
/** Public GUJRERA records have registrations only: no complaints, agents, orders or promoter names for many
 * projects. Offer the reports those records can answer. */
const PUBLIC_REPORTS = [
  "Lapsed or soon-ending registrations",
  "Projects past their completion date",
  "District-wise projects and delays",
];

const NARROW_PERIODS = ["last 3 months", "last 6 months", "this financial year"];
const NARROW_DISTRICTS = ["Ahmedabad", "Surat", "Vadodara", "Rajkot", "Gandhinagar"];
const REFINED_LABEL: Record<string, string> = { district: "District", locality: "Area", period: "Period", top: "Top" };

export const OfficerPage: React.FC = () => {
  const { user, token, lang, logout } = useSaathi();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AnalyticsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The last standard report's question: the next short message can narrow it ("only Bopal", "last 3 months").
  const [current, setCurrent] = useState<string | null>(null);
  const [narrowed, setNarrowed] = useState<{ kind: string; value: string }[]>([]);
  const [saved, setSaved] = useState<SavedReport[]>([]);
  const [saveName, setSaveName] = useState("");
  const [saving, setSaving] = useState(false);
  const allowed = user?.role === "officer";
  const [demo, setDemo] = useState(true);
  useEffect(() => {
    fetchHealth().then((h) => setDemo(h.mock_projects > 0)).catch(() => setDemo(true));
  }, []);
  const fail = (e: unknown) => {
    if (e instanceof AuthExpiredError) logout();
    setError((e as Error).message);
  };
  useEffect(() => {
    if (allowed && token) fetchSavedReports(token).then((r) => setSaved(r.saved)).catch(() => setSaved([]));
  }, [allowed, token]);

  const run = async (question: string, opts: { fresh?: boolean } = {}) => {
    if (!token || !question.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await runAnalytics(token, question, lang, opts.fresh ? null : current);
      setResult(r);
      if (r.intent === "analytics" && r.card && (r.card as { source?: string }).source === "report") {
        setCurrent(r.question ?? question);
        setNarrowed(r.refined ? [...(opts.fresh ? [] : narrowed.filter((x) => !r.refined!.some((y) => y.kind === x.kind))), ...r.refined] : []);
        setSaveName("");
      }
      setQ("");
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const onSave = async () => {
    if (!token || !current) return;
    setSaving(true);
    try {
      await saveReport(token, saveName || current, current, lang);
      setSaved((await fetchSavedReports(token)).saved);
      setSaveName("");
    } catch (e) { fail(e); } finally { setSaving(false); }
  };
  const onDelete = async (id: number) => {
    if (!token) return;
    try { await deleteSavedReport(token, id); setSaved((x) => x.filter((r) => r.id !== id)); } catch (e) { fail(e); }
  };
  const statewide = !user?.district_scope;
  const isSaved = !!current && saved.some((r) => r.question.toLowerCase() === current.toLowerCase());

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <section className="hero-band p-6">
        <p className="text-xs font-semibold uppercase tracking-wider text-accent-amber-strong">
          {{ en: "Reports by asking", gu: "પૂછીને રિપોર્ટ", hi: "पूछकर रिपोर्ट" }[lang]}
        </p>
        <h2 className="mt-1 font-heading text-2xl font-bold text-body">{tr("analyticsTitle", lang)}<En k="analyticsTitle" className="text-muted" /></h2>
        {allowed && (
          <p className="text-sm text-muted mt-1 max-w-3xl">
            {user?.display_name} · Ask for a report, then narrow it in a few words: “only Bopal”, “last 3 months”, “top 10”. Read-only, every query logged.
          </p>
        )}
      </section>
      {!allowed && <LoginPrompt k="loginNeededOfficer" />}
      {allowed && (
        <>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void run(q); }}>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={current ? "Narrow it (“only Bopal”, “last 3 months”) or ask a new report" : tr("analyticsPlaceholder", lang)}
              aria-label={tr("analyticsTitle", lang)}
              className="flex-1 min-w-0 rounded-xl border border-warm-strong bg-card text-body px-4 py-3 shadow-sm focus:outline-none focus:ring-2 focus:ring-brand"
            />
            <button type="submit" disabled={busy || !q.trim()}
              className="px-5 rounded-xl bg-primary-bg text-primary-text font-semibold disabled:opacity-50">
              {busy ? "…" : <>{tr("run", lang)}<En k="run" /></>}
            </button>
          </form>
          <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
            <div className="flex flex-col gap-4 min-w-0">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-muted mb-2">{tr("reports", lang)}<En k="reports" className="normal-case tracking-normal" /></div>
                <div className="flex flex-wrap gap-2">
                  {(demo ? REPORTS : PUBLIC_REPORTS).map((r) => (
                    <button key={r} type="button" onClick={() => void run(r, { fresh: true })} disabled={busy}
                      className="text-xs px-3 py-1.5 rounded-full border border-warm-border bg-card text-body hover:border-brand disabled:opacity-50">
                      {r}
                    </button>
                  ))}
                </div>
              </div>
              {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 p-4 text-sm">{error}</div>}
              {busy && !result && <div className="text-sm text-muted">Running…</div>}
              {result && (
                <section className="warm-card p-5 flex flex-col gap-3" aria-live="polite">
                  {current && result.intent === "analytics" && (
                    <div className="flex flex-col gap-2">
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span className="text-muted">Report:</span>
                        <span className="font-semibold text-body">{current}</span>
                        {narrowed.map((n) => (
                          <span key={n.kind} className="px-2 py-0.5 rounded-full bg-brand-soft border border-accent-border text-accent-amber-strong font-semibold">
                            {REFINED_LABEL[n.kind] ?? n.kind}: {n.value}
                          </span>
                        ))}
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-[11px] text-muted mr-1">Narrow:</span>
                        {NARROW_PERIODS.map((t) => (
                          <button key={t} type="button" disabled={busy} onClick={() => void run(t)}
                            className="text-[11px] px-2.5 py-1 rounded-full border border-warm-border bg-card text-body hover:border-brand disabled:opacity-50">{t}</button>
                        ))}
                        {statewide && NARROW_DISTRICTS.map((d) => (
                          <button key={d} type="button" disabled={busy} onClick={() => void run(`only ${d}`)}
                            className="text-[11px] px-2.5 py-1 rounded-full border border-warm-border bg-card text-body hover:border-brand disabled:opacity-50">{d}</button>
                        ))}
                        <button type="button" disabled={busy} onClick={() => void run("top 10")}
                          className="text-[11px] px-2.5 py-1 rounded-full border border-warm-border bg-card text-body hover:border-brand disabled:opacity-50">top 10</button>
                      </div>
                    </div>
                  )}
                  {result.sentences.map((s, i) => <p key={i} className="text-sm text-body">{s.text}</p>)}
                  {result.card && <AnalyticsCard card={result.card as unknown as AnalyticsCardData} question={result.question} />}
                  {current && result.intent === "analytics" && (
                    <div className="flex flex-wrap items-center gap-2 pt-1">
                      {isSaved ? (
                        <span className="text-xs text-muted">Saved in your reports.</span>
                      ) : (
                        <>
                          <input value={saveName} onChange={(e) => setSaveName(e.target.value)} placeholder="Name this report (optional)"
                            aria-label="Report name" className="rounded-lg border border-warm-border bg-card text-body text-xs px-2.5 py-1.5 min-w-[200px]" />
                          <button type="button" disabled={saving} onClick={() => void onSave()}
                            className="text-xs px-3 py-1.5 rounded-lg bg-brand text-on-brand font-semibold disabled:opacity-50">Save report</button>
                        </>
                      )}
                    </div>
                  )}
                </section>
              )}
            </div>
            <aside className="warm-card p-4 h-fit" aria-label="My saved reports">
              <h3 className="font-heading text-sm font-bold text-body">My saved reports</h3>
              {saved.length === 0 ? (
                <p className="mt-2 text-xs text-muted">Run a report, narrow it, and save it to run again with one click.</p>
              ) : (
                <ul className="mt-2 flex flex-col divide-y divide-warm-border">
                  {saved.map((r) => (
                    <li key={r.id} className="py-2 flex items-start gap-2">
                      <button type="button" onClick={() => void run(r.question, { fresh: true })} disabled={busy}
                        className="flex-1 min-w-0 text-left text-xs hover:text-brand-strong disabled:opacity-50">
                        <span className="block font-semibold text-body truncate">{r.name}</span>
                        <span className="block text-muted truncate">{r.question}</span>
                        {r.last_run_at && <span className="block text-[10px] text-muted">Last run {r.last_run_at.replace("T", " ")}</span>}
                      </button>
                      <button type="button" onClick={() => void onDelete(r.id)} aria-label={`Delete ${r.name}`}
                        className="text-[11px] text-muted hover:text-red-700 px-1">✕</button>
                    </li>
                  ))}
                </ul>
              )}
            </aside>
          </div>
        </>
      )}
    </div>
  );
};
