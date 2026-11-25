import React, { useEffect, useState } from "react";
import {
  AnalyticsResponse,
  AuthExpiredError,
  SelfServiceSummary,
  fetchSelfServiceSummary,
  runAnalytics,
} from "../api/gujrera";
import { fetchHealth, navigateTo } from "../api/gujrera";
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

export const OfficerPage: React.FC = () => {
  const { user, token, lang, logout } = useSaathi();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AnalyticsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const allowed = user?.role === "officer";
  const [demo, setDemo] = useState(true);
  useEffect(() => {
    fetchHealth().then((h) => setDemo(h.mock_projects > 0)).catch(() => setDemo(true));
  }, []);

  const run = async (question: string) => {
    if (!token || !question.trim()) return;
    setQ(question);
    setBusy(true);
    setError(null);
    try {
      setResult(await runAnalytics(token, question, lang));
    } catch (e) {
      if (e instanceof AuthExpiredError) logout();
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <div>
        <h2 className="font-heading text-xl font-bold text-body">{tr("analyticsTitle", lang)}<En k="analyticsTitle" className="text-muted" /></h2>
        {allowed && (
          <p className="text-sm text-muted mt-1">
            {user?.display_name} · read-only queries on reporting views, every query logged
          </p>
        )}
      </div>
      {!allowed && <LoginPrompt k="loginNeededOfficer" />}
      {allowed && (
        <>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void run(q); }}>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={tr("analyticsPlaceholder", lang)}
              aria-label={tr("analyticsTitle", lang)}
              className="flex-1 min-w-0 rounded-xl border border-warm-border bg-card text-body px-4 py-3 focus:outline-none focus:ring-2 focus:ring-brand"
            />
            <button type="submit" disabled={busy || !q.trim()}
              className="px-5 rounded-xl bg-primary-bg text-primary-text font-semibold disabled:opacity-50">
              {busy ? "…" : <>{tr("run", lang)}<En k="run" /></>}
            </button>
          </form>
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-muted mb-2">{tr("reports", lang)}<En k="reports" className="normal-case tracking-normal" /></div>
            <div className="flex flex-wrap gap-2">
              {(demo ? REPORTS : PUBLIC_REPORTS).map((r) => (
                <button key={r} type="button" onClick={() => void run(r)} disabled={busy}
                  className="text-xs px-3 py-1.5 rounded-full border border-warm-border bg-card text-body hover:border-brand disabled:opacity-50">
                  {r}
                </button>
              ))}
            </div>
          </div>
          {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 p-4 text-sm">{error}</div>}
          {busy && !result && <div className="text-sm text-muted">Running…</div>}
          {result && (
            <section className="rounded-2xl border border-warm-border bg-card p-5" aria-live="polite">
              {result.sentences.map((s, i) => <p key={i} className="text-sm text-body">{s.text}</p>)}
              {result.card && <AnalyticsCard card={result.card as unknown as AnalyticsCardData} />}
            </section>
          )}
        </>
      )}
    </div>
  );
};
