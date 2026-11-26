import React, { useEffect, useState } from "react";
import { Outcomes, PocMetrics, Times, fetchPocMetrics, setManualReportMinutes } from "../api/gujrera";

const n = (v: number) => v.toLocaleString("en-IN");
const secs = (ms: number) => (ms < 1000 ? `${n(ms)} ms` : `${(ms / 1000).toFixed(1)} s`);

/** Green when the target is met, amber otherwise; grey when there is nothing to judge yet. */
const Badge: React.FC<{ ok: boolean | null; children: React.ReactNode }> = ({ ok, children }) => (
  <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${ok === null ? "border-warm-border text-muted"
    : ok ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-900"
      : "border-amber-300 bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200 dark:border-amber-900"}`}>{children}</span>
);

const Measure: React.FC<{ title: string; value: string; sub: React.ReactNode; badge?: React.ReactNode }> = ({ title, value, sub, badge }) => (
  <div className="warm-card p-4 flex flex-col gap-1.5">
    <div className="flex items-start justify-between gap-2">
      <h4 className="text-xs font-semibold text-muted uppercase tracking-wide">{title}</h4>
      {badge}
    </div>
    <div className="font-heading text-2xl font-bold text-body tabular-nums">{value}</div>
    <div className="text-xs text-muted leading-snug">{sub}</div>
  </div>
);

const split = (o: Outcomes | undefined) => o && o.total
  ? `${n(o.answered)} answered · ${n(o.clarified)} asked the user to clarify · ${n(o.unanswered)} could not answer`
  : "No questions yet.";

/** The POC scope's measures, from real use (the audit log) and from the latest test run. */
export const PocMeasures: React.FC<{ token: string; refreshKey: unknown; onError: (e: unknown) => void }> = ({ token, refreshKey, onError }) => {
  const [m, setM] = useState<PocMetrics | null>(null);
  const [minutes, setMinutes] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchPocMetrics(token).then((x) => { setM(x); setMinutes(x.manual_report_minutes ? String(x.manual_report_minutes) : ""); }).catch(onError);
  }, [token, refreshKey, onError]);
  if (!m) return null;

  const save = async () => {
    setSaving(true);
    try { const x = await setManualReportMinutes(token, minutes.trim() ? Number(minutes) : null); setM(x); } catch (e) { onError(e); } finally { setSaving(false); }
  };
  const live = m.live.outcomes.all;
  const test = m.test_run.outcomes?.all;
  const citizen: Times | undefined = m.live.response_ms.citizen ?? m.test_run.latency_by_role?.citizen ?? undefined;
  const citizenFrom = m.live.response_ms.citizen ? "real use" : "the latest test run";
  const cons = m.test_run.consistency;
  const r = m.live.reports;
  const officerTest = m.test_run.latency_by_role?.officer;

  return (
    <section className="flex flex-col gap-3" aria-labelledby="poc-measures">
      <div>
        <h3 id="poc-measures" className="font-heading text-sm font-bold text-body">POC measures</h3>
        <p className="text-xs text-muted mt-0.5">
          The measures in the POC scope. "Real use" is every question asked in the last {m.days} days (only the outcome and time are kept,
          never the question). "Test run" is the latest run of the test set{m.test_run.finished_at ? `, ${m.test_run.finished_at.replace("T", " ")}` : ""}.
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Measure
          title="Answered without a person"
          value={live?.total ? `${live.self_served_pct}%` : test?.total ? `${test.self_served_pct}%` : "—"}
          sub={<>
            <span className="block">Real use: {live?.total ? `${n(live.total)} questions. ${split(live)}.` : "no questions yet."}</span>
            <span className="block mt-1">Test run: {test?.total ? `${test.self_served_pct}% of ${n(test.total)}. ${split(test)}.` : "not run yet."}</span>
            <span className="block mt-1">"Could not answer" includes a correct "not in the registry" for a project that does not exist.</span>
          </>}
        />
        <Measure
          title="Citizen response time (95th percentile)"
          value={citizen?.n ? secs(citizen.p95) : "—"}
          badge={citizen?.n ? <Badge ok={citizen.p95 <= m.targets.citizen_p95_ms}>Target ≤ {secs(m.targets.citizen_p95_ms)}</Badge> : undefined}
          sub={citizen?.n ? <>From {citizenFrom}: {n(citizen.n)} answers, median {secs(citizen.p50)}, slowest {secs(citizen.max)}.
            {m.live.understood_by_ai > 0 && ` ${n(m.live.understood_by_ai)} of the real questions needed the AI model to understand them; those are the slow ones.`}</> : "No answers yet."}
        />
        <Measure
          title="Officer report time"
          value={r.n ? secs(r.p50) : officerTest?.n ? secs(officerTest.p50) : "—"}
          badge={m.manual_report_minutes ? <Badge ok={m.report_speedup !== null ? m.report_speedup > 1 : null}>vs {n(m.manual_report_minutes)} min by hand</Badge> : undefined}
          sub={<>
            <span className="block">{r.n ? `Median of ${n(r.n)} reports in real use; 95th percentile ${secs(r.p95)}.` : officerTest?.n ? `Median of ${n(officerTest.n)} officer questions in the test run.` : "No reports yet."}</span>
            <label className="mt-2 flex flex-wrap items-center gap-2">
              <span>Same report by hand (department's figure):</span>
              <input type="number" min={1} value={minutes} onChange={(e) => setMinutes(e.target.value)} placeholder="minutes"
                aria-label="Minutes to prepare a report by hand"
                className="w-20 rounded-md border border-warm-border bg-card text-body text-xs px-2 py-1" />
              <span>min</span>
              <button type="button" disabled={saving} onClick={() => void save()}
                className="px-2.5 py-1 rounded-md bg-brand text-on-brand text-[11px] font-bold disabled:opacity-50">Save</button>
            </label>
          </>}
        />
        <Measure
          title="Same answer when asked again"
          value={cons?.checked ? `${cons.pct}%` : "—"}
          badge={cons?.checked ? <Badge ok={(cons.pct ?? 0) >= m.targets.consistency_pct}>Target ≥ {m.targets.consistency_pct}%</Badge> : undefined}
          sub={cons?.checked
            ? <>{n(cons.same)} of {n(cons.checked)} questions from the test set, asked a second time, gave the same answer word for word.
              {cons.differing.length > 0 && ` Different: test cases ${cons.differing.map((x) => `#${x}`).join(", ")}.`}</>
            : "Run the test set to measure this."}
        />
      </div>
    </section>
  );
};
