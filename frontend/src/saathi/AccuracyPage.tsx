import React, { useCallback, useEffect, useState } from "react";
import {
  AuthExpiredError,
  FeedbackItem,
  TestResultRec,
  TestRunRec,
  dismissFeedback,
  downloadTestRunCsv,
  feedbackToTest,
  fetchFeedback,
  fetchTestRun,
  fetchTestRuns,
  fetchTests,
  generateTests,
  importTests,
  startTestRun,
} from "../api/gujrera";
import { ChartCard, ColumnChart } from "./Charts";
import { useSaathi } from "./context";

const n = (v: number) => v.toLocaleString("en-IN");
const pct = (passed: number, judged: number) => (judged ? `${Math.round((1000 * passed) / judged) / 10}%` : "—");
const LANG: Record<string, string> = { gu: "Gujarati", hi: "Hindi", en: "English", any: "Not set" };
const REASON: Record<string, string> = {
  wrong_answer: "Wrong answer", wrong_project: "Wrong project", should_have_found: "Should have found it",
  not_relevant: "Not what was asked", unclear: "Hard to understand", wrong_language: "Wrong language", other: "Other", none: "No reason",
};
const TEMPLATE = "question,lang,role,expect_intent,must_contain,must_not_contain,expected_source,category,note\n" +
  "\"મંગલ સ્ક્વેર નું પઝેશન ક્યારે મળશે?\",gu,citizen,possession,,could not find,,possession,\n" +
  "\"Projects under scrutiny in Ahmedabad\",en,officer,analytics,,,,officer reports,The department's expected answer\n";

/** Accuracy by one dimension, as bars with the share passed. */
const Breakdown: React.FC<{ title: string; data: Record<string, { total: number; judged: number; passed: number }>; label?: (k: string) => string }> = ({ title, data, label }) => (
  <div className="warm-card p-4">
    <h4 className="text-xs font-semibold text-muted uppercase tracking-wide">{title}</h4>
    <ul className="mt-2 flex flex-col gap-2">
      {Object.entries(data).sort((a, b) => b[1].total - a[1].total).map(([k, v]) => {
        const share = v.judged ? v.passed / v.judged : 0;
        return (
          <li key={k} className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-2 text-xs">
            <span className="text-body truncate" title={k}>{label ? label(k) : k}</span>
            <span className="h-2 rounded-full bg-subtle overflow-hidden" aria-hidden="true">
              <span className="block h-full rounded-full" style={{ width: `${100 * share}%`, background: share >= 0.9 ? "#0ca30c" : share >= 0.7 ? "#fab219" : "#d03b3b" }} />
            </span>
            <span className="tabular-nums text-body">{pct(v.passed, v.judged)} <span className="text-muted">({v.passed}/{v.judged}{v.total > v.judged ? `, ${v.total - v.judged} to review` : ""})</span></span>
          </li>
        );
      })}
    </ul>
  </div>
);

const FeedbackRow: React.FC<{ f: FeedbackItem; token: string; onDone: () => void; onError: (e: unknown) => void }> = ({ f, token, onDone, onError }) => {
  const [mustContain, setMustContain] = useState("");
  const [mustNot, setMustNot] = useState(f.reason === "should_have_found" ? "could not find" : "");
  const act = async (fn: () => Promise<unknown>) => { try { await fn(); onDone(); } catch (e) { onError(e); } };
  return (
    <li className="py-3 flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="px-2 py-0.5 rounded-full border border-red-300 bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-200 dark:border-red-900 font-semibold">{REASON[f.reason ?? "none"] ?? f.reason}</span>
        <span className="text-muted">{f.at.replace("T", " ")} · {f.role} · {f.surface}{f.lang ? ` · ${LANG[f.lang] ?? f.lang}` : ""}</span>
      </div>
      <div className="text-sm text-body"><b>Q:</b> {f.question}</div>
      <div className="text-xs text-muted line-clamp-3"><b>Answer given:</b> {f.answer}</div>
      {f.comment && <div className="text-xs text-body"><b>User said:</b> “{f.comment}”</div>}
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-[11px] text-muted flex flex-col gap-1">A right answer must contain (separate with ;)
          <input value={mustContain} onChange={(e) => setMustContain(e.target.value)} className="rounded-md border border-warm-border bg-card text-body text-xs px-2 py-1 w-64" />
        </label>
        <label className="text-[11px] text-muted flex flex-col gap-1">…and must not contain
          <input value={mustNot} onChange={(e) => setMustNot(e.target.value)} className="rounded-md border border-warm-border bg-card text-body text-xs px-2 py-1 w-48" />
        </label>
        <button type="button" onClick={() => void act(() => feedbackToTest(token, f.id, { must_contain: mustContain, must_not_contain: mustNot }))}
          className="px-3 py-1.5 rounded-lg bg-brand text-on-brand text-xs font-bold">Add to test set</button>
        <button type="button" onClick={() => void act(() => dismissFeedback(token, f.id))}
          className="px-3 py-1.5 rounded-lg border border-warm-border text-body text-xs">Dismiss</button>
      </div>
    </li>
  );
};

export const AccuracyPage: React.FC = () => {
  const { user, token, logout } = useSaathi();
  const allowed = user?.role === "officer" && !user.district_scope;
  const [runs, setRuns] = useState<TestRunRec[]>([]);
  const [detail, setDetail] = useState<{ run: TestRunRec; results: TestResultRec[] } | null>(null);
  const [show, setShow] = useState<"failed" | "unjudged">("failed");
  const [tests, setTests] = useState<{ active: number; by_origin: Record<string, number>; by_lang: Record<string, number>; by_role: Record<string, number> } | null>(null);
  const [fb, setFb] = useState<{ feedback: FeedbackItem[]; counts: Record<string, number>; ratings: Record<string, number> } | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const fail = useCallback((e: unknown) => {
    if (e instanceof AuthExpiredError) logout();
    setError((e as Error).message);
  }, [logout]);
  const loadAll = useCallback(async () => {
    if (!token || !allowed) return;
    try {
      const [r, t, f] = await Promise.all([fetchTestRuns(token), fetchTests(token), fetchFeedback(token)]);
      setRuns(r.runs);
      setTests(t);
      setFb(f);
      if (r.runs[0]) setDetail(await fetchTestRun(token, r.runs[0].id, show));
    } catch (e) { fail(e); }
  }, [token, allowed, fail, show]);
  useEffect(() => { void loadAll(); }, [loadAll]);

  // poll while a run is in progress
  const running = runs[0]?.status === "running";
  useEffect(() => {
    if (!running || !token) return;
    const id = window.setInterval(() => {
      fetchTestRun(token, runs[0].id, show).then((d) => {
        setDetail(d);
        if (d.run.status !== "running") void loadAll();
        else setRuns((x) => [d.run, ...x.slice(1)]);
      }).catch(fail);
    }, 2000);
    return () => window.clearInterval(id);
  }, [running, token, runs, show, loadAll, fail]);

  if (!allowed) return <div className="max-w-3xl mx-auto px-4 py-8 text-sm text-muted">The accuracy console is for state-level GUJRERA officers.</div>;

  const act = async (fn: () => Promise<string | void>) => {
    setBusy(true); setError(null); setMsg(null);
    try { const m = await fn(); if (m) setMsg(m); await loadAll(); } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const latest = runs.find((r) => r.status === "done");
  const r0 = detail?.run;
  const s = latest?.summary;
  const trend = [...runs].filter((r) => r.status === "done" && r.accuracy !== null).reverse()
    .map((r) => ({ label: `#${r.id}`, value: r.accuracy as number }));

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <section className="hero-band p-6">
        <p className="text-xs font-semibold uppercase tracking-wider text-accent-amber-strong">Administration</p>
        <h2 className="mt-1 font-heading text-2xl font-bold text-body">Accuracy</h2>
        <p className="mt-1 text-sm text-muted max-w-3xl">
          Measure how often the assistants answer correctly, on a test set you control: questions generated from the registry,
          the department's own test set, and questions users marked 👎. Each run scores every question by language, category and
          role, and keeps the history, so accuracy can be reported week by week.
        </p>
      </section>

      {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 dark:bg-red-950/40 dark:text-red-200 dark:border-red-900 p-3 text-sm">{error}</div>}
      {msg && <div role="status" className="rounded-xl border border-emerald-300 bg-emerald-50 text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-900 p-3 text-sm">{msg}</div>}

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        {[
          ["Accuracy, latest run", latest ? pct(latest.passed, latest.judged) : "—"],
          ["Questions scored", latest ? `${n(latest.passed)} / ${n(latest.judged)}` : "—"],
          ["To review by hand", latest ? n(latest.unjudged) : "—"],
          ["Response time, 95th percentile", s ? `${n(s.latency_ms.p95)} ms` : "—"],
          ["User 👎 waiting for review", fb ? n(fb.counts.new ?? 0) : "—"],
        ].map(([label, value]) => (
          <div key={label} className="warm-card p-3"><div className="font-heading text-2xl font-bold text-body tabular-nums">{value}</div><div className="text-xs text-muted leading-snug">{label}</div></div>
        ))}
      </div>

      {/* Test set and run */}
      <section className="warm-card p-5 flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="font-heading text-sm font-bold text-body">Test set: {tests ? n(tests.active) : "…"} active questions</h3>
            {tests && (
              <p className="text-xs text-muted mt-0.5">
                {Object.entries(tests.by_origin).map(([k, v]) => `${n(v)} ${k}`).join(" · ")}
                {" · "}{Object.entries(tests.by_lang).map(([k, v]) => `${LANG[k] ?? k} ${n(v)}`).join(", ")}
                {" · "}{Object.entries(tests.by_role).map(([k, v]) => `${k} ${n(v)}`).join(", ")}
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={busy || running} onClick={() => void act(async () => { const r = await generateTests(token!); return `Generated ${r.generated} questions from the registry.`; })}
              className="text-xs px-3 py-1.5 rounded-lg border border-warm-border text-body hover:border-brand disabled:opacity-50">Generate from the registry</button>
            <label className={`text-xs px-3 py-1.5 rounded-lg border border-warm-border text-body hover:border-brand cursor-pointer ${busy || running ? "opacity-50 pointer-events-none" : ""}`}>
              Import the department's test set
              <input type="file" accept=".csv,.json" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) void act(async () => { const r = await importTests(token!, f); return `Imported ${r.added} questions${r.rejected ? `, ${r.rejected} rows rejected (${r.errors.slice(0, 2).map((x) => `row ${x.row}: ${x.error}`).join("; ")})` : ""}.`; }); }} />
            </label>
            <a href={`data:text/csv;charset=utf-8,${encodeURIComponent("﻿" + TEMPLATE)}`} download="gujrera_test_set_template.csv"
              className="text-xs px-3 py-1.5 rounded-lg border border-warm-border text-body hover:border-brand">CSV template</a>
            <button type="button" disabled={busy || running || !tests?.active} onClick={() => void act(async () => { await startTestRun(token!); })}
              className="text-xs px-4 py-1.5 rounded-lg bg-brand text-on-brand font-bold disabled:opacity-50">{running ? "Running…" : "Run the test set"}</button>
          </div>
        </div>
        {running && r0 && (
          <div className="flex items-center gap-3 text-xs text-muted" role="status">
            <span className="flex-1 h-2 rounded-full bg-subtle overflow-hidden"><span className="block h-full bg-brand" style={{ width: `${(100 * r0.done) / Math.max(1, r0.total)}%` }} /></span>
            {n(r0.done)} / {n(r0.total)} · {n(r0.passed)} passed so far
          </div>
        )}
      </section>

      {s && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Breakdown title="By language" data={s.lang} label={(k) => LANG[k] ?? k} />
          <Breakdown title="By role" data={s.role} />
          <Breakdown title="By source of the question" data={s.origin} />
          <div className="lg:col-span-2"><Breakdown title="By category" data={s.category} label={(k) => k.replace(/_/g, " ")} /></div>
          {trend.length > 0 && (
            <ChartCard title="Accuracy by run (%)" sub="Each completed run of the test set.">
              <ColumnChart data={trend} head={["Run", "Accuracy %"]} height={160} unit="%" />
            </ChartCard>
          )}
        </div>
      )}

      {/* Failures and review */}
      {detail && detail.run.status === "done" && (
        <section className="warm-card p-5 flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-heading text-sm font-bold text-body mr-2">Run #{detail.run.id}, {detail.run.finished_at?.replace("T", " ")}</h3>
            {(["failed", "unjudged"] as const).map((k) => (
              <button key={k} type="button" onClick={() => setShow(k)} aria-pressed={show === k}
                className={`text-xs px-2.5 py-1 rounded-md font-semibold ${show === k ? "bg-brand-soft text-body ring-1 ring-brand" : "text-muted hover:text-body"}`}>
                {k === "failed" ? `Failed (${n(detail.run.judged - detail.run.passed)})` : `To review by hand (${n(detail.run.unjudged)})`}
              </button>
            ))}
            <button type="button" onClick={() => void downloadTestRunCsv(token!, detail.run.id).catch(fail)}
              className="ml-auto text-xs px-3 py-1.5 rounded-lg bg-primary-bg text-primary-text font-semibold">All results (CSV)</button>
          </div>
          {detail.results.length === 0 ? (
            <p className="text-sm text-muted">{show === "failed" ? "No failures in this run." : "Nothing to review by hand."}</p>
          ) : (
            <ul className="divide-y divide-warm-border">
              {detail.results.map((x) => (
                <li key={x.case_id} className="py-2.5 text-xs flex flex-col gap-1">
                  <div className="flex flex-wrap gap-2 text-muted">
                    <span>#{x.case_id}</span><span>{LANG[x.lang ?? "any"] ?? x.lang}</span><span>{x.role}</span><span>{x.category}</span><span>{x.origin}</span><span>{x.ms} ms</span>
                  </div>
                  <div className="text-sm text-body"><b>Q:</b> {x.question}</div>
                  {x.problems.length > 0 && <div className="text-red-700 dark:text-red-300">{x.problems.join(" · ")}</div>}
                  {x.expected.note && <div className="text-body"><b>Expected (department):</b> {x.expected.note}</div>}
                  <div className="text-muted line-clamp-3"><b>Answer:</b> {x.answer}</div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {/* Feedback queue */}
      <section className="warm-card p-5">
        <h3 className="font-heading text-sm font-bold text-body">User feedback to review</h3>
        {fb && <p className="text-xs text-muted mt-0.5">👍 {n(fb.ratings.up ?? 0)} · 👎 {n(fb.ratings.down ?? 0)} · added to the test set {n(fb.counts.added ?? 0)} · dismissed {n(fb.counts.dismissed ?? 0)}</p>}
        {fb && fb.feedback.length === 0 ? (
          <p className="mt-2 text-sm text-muted">No 👎 waiting. Users mark answers under each reply in Ask Saathi and under officer reports.</p>
        ) : (
          <ul className="divide-y divide-warm-border">{fb?.feedback.map((f) => <FeedbackRow key={f.id} f={f} token={token!} onDone={() => void loadAll()} onError={fail} />)}</ul>
        )}
      </section>
    </div>
  );
};
