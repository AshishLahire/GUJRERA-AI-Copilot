import React, { useCallback, useEffect, useState } from "react";
import {
  AuthExpiredError,
  FeedbackItem,
  Lang,
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
import { PocMeasures } from "./PocMeasures";
import { Said, say, useSaathi } from "./context";

const n = (v: number) => v.toLocaleString("en-IN");
const pct = (passed: number, judged: number) => (judged ? `${Math.round((1000 * passed) / judged) / 10}%` : "—");
const LANG: Record<string, Said> = {
  gu: { en: "Gujarati", gu: "ગુજરાતી", hi: "गुजराती" },
  hi: { en: "Hindi", gu: "હિન્દી", hi: "हिंदी" },
  en: { en: "English", gu: "અંગ્રેજી", hi: "अंग्रेज़ी" },
  any: { en: "Not set", gu: "નક્કી નથી", hi: "तय नहीं" },
};
const langName = (k: string, lang: Lang) => (LANG[k] ? say(LANG[k], lang) : k);
const REASON: Record<string, Said> = {
  wrong_answer: { en: "Wrong answer", gu: "ખોટો જવાબ", hi: "गलत जवाब" },
  wrong_project: { en: "Wrong project", gu: "ખોટો પ્રોજેક્ટ", hi: "गलत प्रोजेक्ट" },
  should_have_found: { en: "Should have found it", gu: "મળવું જોઈતું હતું", hi: "मिलना चाहिए था" },
  not_relevant: { en: "Not what was asked", gu: "જે પૂછ્યું હતું તે નથી", hi: "जो पूछा था वह नहीं" },
  unclear: { en: "Hard to understand", gu: "સમજવામાં મુશ્કેલ", hi: "समझने में कठिन" },
  wrong_language: { en: "Wrong language", gu: "ખોટી ભાષા", hi: "गलत भाषा" },
  other: { en: "Other", gu: "અન્ય", hi: "अन्य" },
  none: { en: "No reason", gu: "કોઈ કારણ નથી", hi: "कोई कारण नहीं" },
};
const TEMPLATE = "question,lang,role,expect_intent,must_contain,must_not_contain,expected_source,category,note\n" +
  "\"મંગલ સ્ક્વેર નું પઝેશન ક્યારે મળશે?\",gu,citizen,possession,,could not find,,possession,\n" +
  "\"Projects under scrutiny in Ahmedabad\",en,officer,analytics,,,,officer reports,The department's expected answer\n";

/** Accuracy by one dimension, as bars with the share passed. */
const Breakdown: React.FC<{ title: string; data: Record<string, { total: number; judged: number; passed: number }>; label?: (k: string) => string }> = ({ title, data, label }) => {
  const { lang } = useSaathi();
  return (
    <div className="warm-card p-4">
      <h4 className="text-xs font-semibold text-muted uppercase tracking-wide">{title}</h4>
      <ul className="mt-2 flex flex-col gap-2">
        {Object.entries(data).sort((a, b) => b[1].total - a[1].total).map(([k, v]) => {
          const share = v.judged ? v.passed / v.judged : 0;
          const left = v.total - v.judged;
          return (
            <li key={k} className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-2 text-xs">
              <span className="text-body truncate" title={k}>{label ? label(k) : k}</span>
              <span className="h-2 rounded-full bg-subtle overflow-hidden" aria-hidden="true">
                <span className="block h-full rounded-full" style={{ width: `${100 * share}%`, background: share >= 0.9 ? "#0ca30c" : share >= 0.7 ? "#fab219" : "#d03b3b" }} />
              </span>
              <span className="tabular-nums text-body">{pct(v.passed, v.judged)} <span className="text-muted">({v.passed}/{v.judged}{v.total > v.judged ? say({ en: `, ${left} to review`, gu: `, ${left} તપાસવાના બાકી`, hi: `, ${left} जाँचने बाकी` }, lang) : ""})</span></span>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

const FeedbackRow: React.FC<{ f: FeedbackItem; token: string; onDone: () => void; onError: (e: unknown) => void }> = ({ f, token, onDone, onError }) => {
  const { lang } = useSaathi();
  const [mustContain, setMustContain] = useState("");
  const [mustNot, setMustNot] = useState(f.reason === "should_have_found" ? "could not find" : "");
  const act = async (fn: () => Promise<unknown>) => { try { await fn(); onDone(); } catch (e) { onError(e); } };
  const reason = REASON[f.reason ?? "none"];
  return (
    <li className="py-3 flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="px-2 py-0.5 rounded-full border border-red-300 bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-200 dark:border-red-900 font-semibold">{reason ? say(reason, lang) : f.reason}</span>
        <span className="text-muted">{f.at.replace("T", " ")} · {f.role} · {f.surface}{f.lang ? ` · ${langName(f.lang, lang)}` : ""}</span>
      </div>
      <div className="text-sm text-body"><b>{say({ en: "Q:", gu: "પ્ર:", hi: "प्र:" }, lang)}</b> {f.question}</div>
      <div className="text-xs text-muted line-clamp-3"><b>{say({ en: "Answer given:", gu: "આપેલો જવાબ:", hi: "दिया गया जवाब:" }, lang)}</b> {f.answer}</div>
      {f.comment && <div className="text-xs text-body"><b>{say({ en: "User said:", gu: "વપરાશકર્તાએ કહ્યું:", hi: "उपयोगकर्ता ने कहा:" }, lang)}</b> “{f.comment}”</div>}
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-[11px] text-muted flex flex-col gap-1">{say({ en: "A right answer must contain (separate with ;)", gu: "સાચા જવાબમાં આ હોવું જોઈએ (; થી અલગ કરો)", hi: "सही जवाब में यह होना चाहिए (; से अलग करें)" }, lang)}
          <input value={mustContain} onChange={(e) => setMustContain(e.target.value)} className="rounded-md border border-warm-border bg-card text-body text-xs px-2 py-1 w-64" />
        </label>
        <label className="text-[11px] text-muted flex flex-col gap-1">{say({ en: "…and must not contain", gu: "…અને આ ન હોવું જોઈએ", hi: "…और यह नहीं होना चाहिए" }, lang)}
          <input value={mustNot} onChange={(e) => setMustNot(e.target.value)} className="rounded-md border border-warm-border bg-card text-body text-xs px-2 py-1 w-48" />
        </label>
        <button type="button" onClick={() => void act(() => feedbackToTest(token, f.id, { must_contain: mustContain, must_not_contain: mustNot }))}
          className="px-3 py-1.5 rounded-lg bg-brand text-on-brand text-xs font-bold">{say({ en: "Add to test set", gu: "ટેસ્ટ સેટમાં ઉમેરો", hi: "टेस्ट सेट में जोड़ें" }, lang)}</button>
        <button type="button" onClick={() => void act(() => dismissFeedback(token, f.id))}
          className="px-3 py-1.5 rounded-lg border border-warm-border text-body text-xs">{say({ en: "Dismiss", gu: "રદ કરો", hi: "खारिज करें" }, lang)}</button>
      </div>
    </li>
  );
};

export const AccuracyPage: React.FC = () => {
  const { user, token, logout, lang } = useSaathi();
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

  if (!allowed) return <div className="max-w-3xl mx-auto px-4 py-8 text-sm text-muted">{say({ en: "The accuracy console is for state-level GUJRERA officers.", gu: "ચોકસાઈ કન્સોલ રાજ્ય સ્તરના GUJRERA અધિકારીઓ માટે છે.", hi: "सटीकता कंसोल राज्य स्तर के GUJRERA अधिकारियों के लिए है।" }, lang)}</div>;

  const act = async (fn: () => Promise<string | void>) => {
    setBusy(true); setError(null); setMsg(null);
    try { const m = await fn(); if (m) setMsg(m); await loadAll(); } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const latest = runs.find((r) => r.status === "done");
  const r0 = detail?.run;
  const s = latest?.summary;
  const trend = [...runs].filter((r) => r.status === "done" && r.accuracy !== null).reverse()
    .map((r) => ({ label: `#${r.id}`, value: r.accuracy as number }));
  const active = tests ? n(tests.active) : "…";

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <section className="hero-band p-6">
        <p className="text-xs font-semibold uppercase tracking-wider text-accent-amber-strong">{say({ en: "Administration", gu: "વહીવટ", hi: "प्रशासन" }, lang)}</p>
        <h2 className="mt-1 font-heading text-2xl font-bold text-body">{say({ en: "Accuracy", gu: "ચોકસાઈ", hi: "सटीकता" }, lang)}</h2>
        <p className="mt-1 text-sm text-muted max-w-3xl">
          {say({
            en: "Measure how often the assistants answer correctly, on a test set you control: questions generated from the registry, the department's own test set, and questions users marked 👎. Each run scores every question by language, category and role, and keeps the history, so accuracy can be reported week by week.",
            gu: "તમારા નિયંત્રણ હેઠળના ટેસ્ટ સેટ પર સહાયકો કેટલી વાર સાચો જવાબ આપે છે તે માપો: રજિસ્ટ્રીમાંથી બનાવેલા પ્રશ્નો, વિભાગનો પોતાનો ટેસ્ટ સેટ, અને વપરાશકર્તાઓએ 👎 કરેલા પ્રશ્નો. દરેક વખતે ચલાવતાં દરેક પ્રશ્નને ભાષા, શ્રેણી અને ભૂમિકા પ્રમાણે તપાસવામાં આવે છે અને ઇતિહાસ સચવાય છે, જેથી ચોકસાઈનો દર અઠવાડિયે રિપોર્ટ આપી શકાય.",
            hi: "आपके नियंत्रण वाले टेस्ट सेट पर सहायक कितनी बार सही जवाब देते हैं, यह मापें: रजिस्ट्री से बनाए गए प्रश्न, विभाग का अपना टेस्ट सेट, और उपयोगकर्ताओं द्वारा 👎 किए गए प्रश्न। हर बार चलाने पर हर प्रश्न को भाषा, श्रेणी और भूमिका के अनुसार जाँचा जाता है और इतिहास सहेजा जाता है, ताकि सटीकता की हर सप्ताह रिपोर्ट दी जा सके।",
          }, lang)}
        </p>
      </section>

      {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 dark:bg-red-950/40 dark:text-red-200 dark:border-red-900 p-3 text-sm">{error}</div>}
      {msg && <div role="status" className="rounded-xl border border-emerald-300 bg-emerald-50 text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-900 p-3 text-sm">{msg}</div>}

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        {[
          [say({ en: "Accuracy, latest run", gu: "ચોકસાઈ, છેલ્લી વાર ચલાવ્યું ત્યારે", hi: "सटीकता, पिछली बार चलाने पर" }, lang), latest ? pct(latest.passed, latest.judged) : "—"],
          [say({ en: "Questions scored", gu: "તપાસાયેલા પ્રશ્નો", hi: "जाँचे गए प्रश्न" }, lang), latest ? `${n(latest.passed)} / ${n(latest.judged)}` : "—"],
          [say({ en: "To review by hand", gu: "જાતે તપાસવાના", hi: "हाथ से जाँचने के लिए" }, lang), latest ? n(latest.unjudged) : "—"],
          [say({ en: "Response time, 95th percentile", gu: "જવાબનો સમય, 95મો પર્સેન્ટાઇલ", hi: "जवाब का समय, 95वाँ पर्सेंटाइल" }, lang), s ? `${n(s.latency_ms.p95)} ms` : "—"],
          [say({ en: "User 👎 waiting for review", gu: "તપાસની રાહ જોતા વપરાશકર્તાના 👎", hi: "जाँच की प्रतीक्षा में उपयोगकर्ताओं के 👎" }, lang), fb ? n(fb.counts.new ?? 0) : "—"],
        ].map(([label, value]) => (
          <div key={label} className="warm-card p-3"><div className="font-heading text-2xl font-bold text-body tabular-nums">{value}</div><div className="text-xs text-muted leading-snug">{label}</div></div>
        ))}
      </div>

      {token && <PocMeasures token={token} refreshKey={latest?.id} onError={fail} />}

      {/* Test set and run */}
      <section className="warm-card p-5 flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="font-heading text-sm font-bold text-body">{say({ en: `Test set: ${active} active questions`, gu: `ટેસ્ટ સેટ: ${active} સક્રિય પ્રશ્નો`, hi: `टेस्ट सेट: ${active} सक्रिय प्रश्न` }, lang)}</h3>
            {tests && (
              <p className="text-xs text-muted mt-0.5">
                {Object.entries(tests.by_origin).map(([k, v]) => `${n(v)} ${k}`).join(" · ")}
                {" · "}{Object.entries(tests.by_lang).map(([k, v]) => `${langName(k, lang)} ${n(v)}`).join(", ")}
                {" · "}{Object.entries(tests.by_role).map(([k, v]) => `${k} ${n(v)}`).join(", ")}
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={busy || running} onClick={() => void act(async () => { const r = await generateTests(token!); return say({ en: `Generated ${r.generated} questions from the registry.`, gu: `રજિસ્ટ્રીમાંથી ${r.generated} પ્રશ્નો બનાવ્યા.`, hi: `रजिस्ट्री से ${r.generated} प्रश्न बनाए गए।` }, lang); })}
              className="text-xs px-3 py-1.5 rounded-lg border border-warm-border text-body hover:border-brand disabled:opacity-50">{say({ en: "Generate from the registry", gu: "રજિસ્ટ્રીમાંથી બનાવો", hi: "रजिस्ट्री से बनाएँ" }, lang)}</button>
            <label className={`text-xs px-3 py-1.5 rounded-lg border border-warm-border text-body hover:border-brand cursor-pointer ${busy || running ? "opacity-50 pointer-events-none" : ""}`}>
              {say({ en: "Import the department's test set", gu: "વિભાગનો ટેસ્ટ સેટ આયાત કરો", hi: "विभाग का टेस्ट सेट आयात करें" }, lang)}
              <input type="file" accept=".csv,.json" className="sr-only" onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void act(async () => {
                  const r = await importTests(token!, f);
                  const errs = (row: string) => r.errors.slice(0, 2).map((x) => `${row} ${x.row}: ${x.error}`).join("; ");
                  return say({
                    en: `Imported ${r.added} questions${r.rejected ? `, ${r.rejected} rows rejected (${errs("row")})` : ""}.`,
                    gu: `${r.added} પ્રશ્નો આયાત કર્યા${r.rejected ? `, ${r.rejected} પંક્તિઓ નકારી (${errs("પંક્તિ")})` : ""}.`,
                    hi: `${r.added} प्रश्न आयात किए गए${r.rejected ? `, ${r.rejected} पंक्तियाँ अस्वीकार (${errs("पंक्ति")})` : ""}।`,
                  }, lang);
                });
              }} />
            </label>
            <a href={`data:text/csv;charset=utf-8,${encodeURIComponent("﻿" + TEMPLATE)}`} download="gujrera_test_set_template.csv"
              className="text-xs px-3 py-1.5 rounded-lg border border-warm-border text-body hover:border-brand">{say({ en: "CSV template", gu: "CSV નમૂનો", hi: "CSV नमूना" }, lang)}</a>
            <button type="button" disabled={busy || running || !tests?.active} onClick={() => void act(async () => { await startTestRun(token!); })}
              className="text-xs px-4 py-1.5 rounded-lg bg-brand text-on-brand font-bold disabled:opacity-50">{running ? say({ en: "Running…", gu: "ચાલી રહ્યું છે…", hi: "चल रहा है…" }, lang) : say({ en: "Run the test set", gu: "ટેસ્ટ સેટ ચલાવો", hi: "टेस्ट सेट चलाएँ" }, lang)}</button>
          </div>
        </div>
        {running && r0 && (
          <div className="flex items-center gap-3 text-xs text-muted" role="status">
            <span className="flex-1 h-2 rounded-full bg-subtle overflow-hidden"><span className="block h-full bg-brand" style={{ width: `${(100 * r0.done) / Math.max(1, r0.total)}%` }} /></span>
            {n(r0.done)} / {n(r0.total)} · {say({ en: `${n(r0.passed)} passed so far`, gu: `અત્યાર સુધી ${n(r0.passed)} પાસ`, hi: `अब तक ${n(r0.passed)} पास` }, lang)}
          </div>
        )}
      </section>

      {s && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Breakdown title={say({ en: "By language", gu: "ભાષા પ્રમાણે", hi: "भाषा के अनुसार" }, lang)} data={s.lang} label={(k) => langName(k, lang)} />
          <Breakdown title={say({ en: "By role", gu: "ભૂમિકા પ્રમાણે", hi: "भूमिका के अनुसार" }, lang)} data={s.role} />
          <Breakdown title={say({ en: "By source of the question", gu: "પ્રશ્નના સ્ત્રોત પ્રમાણે", hi: "प्रश्न के स्रोत के अनुसार" }, lang)} data={s.origin} />
          <div className="lg:col-span-2"><Breakdown title={say({ en: "By category", gu: "શ્રેણી પ્રમાણે", hi: "श्रेणी के अनुसार" }, lang)} data={s.category} label={(k) => k.replace(/_/g, " ")} /></div>
          {trend.length > 0 && (
            <ChartCard title={say({ en: "Accuracy by run (%)", gu: "દરેક રનની ચોકસાઈ (%)", hi: "हर रन की सटीकता (%)" }, lang)} sub={say({ en: "Each completed run of the test set.", gu: "ટેસ્ટ સેટનો દરેક પૂરો થયેલો રન.", hi: "टेस्ट सेट का हर पूरा हुआ रन।" }, lang)}>
              <ColumnChart data={trend} head={[say({ en: "Run", gu: "રન", hi: "रन" }, lang), say({ en: "Accuracy %", gu: "ચોકસાઈ %", hi: "सटीकता %" }, lang)]} height={160} unit="%" />
            </ChartCard>
          )}
        </div>
      )}

      {/* Failures and review */}
      {detail && detail.run.status === "done" && (
        <section className="warm-card p-5 flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-heading text-sm font-bold text-body mr-2">{say({ en: "Run", gu: "રન", hi: "रन" }, lang)} #{detail.run.id}, {detail.run.finished_at?.replace("T", " ")}</h3>
            {(["failed", "unjudged"] as const).map((k) => {
              const failed = n(detail.run.judged - detail.run.passed);
              const unjudged = n(detail.run.unjudged);
              return (
                <button key={k} type="button" onClick={() => setShow(k)} aria-pressed={show === k}
                  className={`text-xs px-2.5 py-1 rounded-md font-semibold ${show === k ? "bg-brand-soft text-body ring-1 ring-brand" : "text-muted hover:text-body"}`}>
                  {k === "failed"
                    ? say({ en: `Failed (${failed})`, gu: `નિષ્ફળ (${failed})`, hi: `विफल (${failed})` }, lang)
                    : say({ en: `To review by hand (${unjudged})`, gu: `જાતે તપાસવાના (${unjudged})`, hi: `हाथ से जाँचने के लिए (${unjudged})` }, lang)}
                </button>
              );
            })}
            <button type="button" onClick={() => void downloadTestRunCsv(token!, detail.run.id).catch(fail)}
              className="ml-auto text-xs px-3 py-1.5 rounded-lg bg-primary-bg text-primary-text font-semibold">{say({ en: "All results (CSV)", gu: "બધાં પરિણામો (CSV)", hi: "सभी परिणाम (CSV)" }, lang)}</button>
          </div>
          {detail.results.length === 0 ? (
            <p className="text-sm text-muted">{show === "failed"
              ? say({ en: "No failures in this run.", gu: "આ રનમાં કોઈ નિષ્ફળતા નથી.", hi: "इस रन में कोई विफलता नहीं।" }, lang)
              : say({ en: "Nothing to review by hand.", gu: "જાતે તપાસવા માટે કંઈ નથી.", hi: "हाथ से जाँचने के लिए कुछ नहीं।" }, lang)}</p>
          ) : (
            <ul className="divide-y divide-warm-border">
              {detail.results.map((x) => (
                <li key={x.case_id} className="py-2.5 text-xs flex flex-col gap-1">
                  <div className="flex flex-wrap gap-2 text-muted">
                    <span>#{x.case_id}</span><span>{langName(x.lang ?? "any", lang)}</span><span>{x.role}</span><span>{x.category}</span><span>{x.origin}</span><span>{x.ms} ms</span>
                  </div>
                  <div className="text-sm text-body"><b>{say({ en: "Q:", gu: "પ્ર:", hi: "प्र:" }, lang)}</b> {x.question}</div>
                  {x.problems.length > 0 && <div className="text-red-700 dark:text-red-300">{x.problems.join(" · ")}</div>}
                  {x.expected.note && <div className="text-body"><b>{say({ en: "Expected (department):", gu: "અપેક્ષિત (વિભાગ):", hi: "अपेक्षित (विभाग):" }, lang)}</b> {x.expected.note}</div>}
                  <div className="text-muted line-clamp-3"><b>{say({ en: "Answer:", gu: "જવાબ:", hi: "जवाब:" }, lang)}</b> {x.answer}</div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {/* Feedback queue */}
      <section className="warm-card p-5">
        <h3 className="font-heading text-sm font-bold text-body">{say({ en: "User feedback to review", gu: "તપાસવાનો વપરાશકર્તા પ્રતિસાદ", hi: "जाँचने के लिए उपयोगकर्ता प्रतिक्रिया" }, lang)}</h3>
        {fb && (() => {
          const up = n(fb.ratings.up ?? 0), down = n(fb.ratings.down ?? 0), added = n(fb.counts.added ?? 0), dismissed = n(fb.counts.dismissed ?? 0);
          return <p className="text-xs text-muted mt-0.5">{say({
            en: `👍 ${up} · 👎 ${down} · added to the test set ${added} · dismissed ${dismissed}`,
            gu: `👍 ${up} · 👎 ${down} · ટેસ્ટ સેટમાં ઉમેર્યા ${added} · રદ કર્યા ${dismissed}`,
            hi: `👍 ${up} · 👎 ${down} · टेस्ट सेट में जोड़े ${added} · खारिज ${dismissed}`,
          }, lang)}</p>;
        })()}
        {fb && fb.feedback.length === 0 ? (
          <p className="mt-2 text-sm text-muted">{say({
            en: "No 👎 waiting. Users mark answers under each reply in Ask Saathi and under officer reports.",
            gu: "કોઈ 👎 બાકી નથી. વપરાશકર્તાઓ Ask Saathi માં દરેક જવાબ નીચે અને અધિકારી રિપોર્ટ નીચે જવાબો ચિહ્નિત કરે છે.",
            hi: "कोई 👎 बाकी नहीं। उपयोगकर्ता Ask Saathi में हर जवाब के नीचे और अधिकारी रिपोर्ट के नीचे जवाबों को चिह्नित करते हैं।",
          }, lang)}</p>
        ) : (
          <ul className="divide-y divide-warm-border">{fb?.feedback.map((f) => <FeedbackRow key={f.id} f={f} token={token!} onDone={() => void loadAll()} onError={fail} />)}</ul>
        )}
      </section>
    </div>
  );
};
