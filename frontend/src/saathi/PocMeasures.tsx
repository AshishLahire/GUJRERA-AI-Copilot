import React, { useEffect, useState } from "react";
import { Lang, Outcomes, PocMetrics, Times, fetchPocMetrics, setManualReportMinutes } from "../api/gujrera";
import { say, useSaathi } from "./context";

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

const split = (o: Outcomes | undefined, lang: Lang) => o && o.total
  ? say({
    en: `${n(o.answered)} answered · ${n(o.clarified)} asked the user to clarify · ${n(o.unanswered)} could not answer`,
    gu: `${n(o.answered)} ના જવાબ આપ્યા · ${n(o.clarified)} માં વપરાશકર્તાને સ્પષ્ટતા પૂછી · ${n(o.unanswered)} ના જવાબ ન આપી શક્યા`,
    hi: `${n(o.answered)} के जवाब दिए · ${n(o.clarified)} में उपयोगकर्ता से स्पष्टता पूछी · ${n(o.unanswered)} के जवाब नहीं दे सके`,
  }, lang)
  : say({ en: "No questions yet.", gu: "હજી કોઈ પ્રશ્ન નથી.", hi: "अभी कोई प्रश्न नहीं।" }, lang);

/** The POC scope's measures, from real use (the audit log) and from the latest test run. */
export const PocMeasures: React.FC<{ token: string; refreshKey: unknown; onError: (e: unknown) => void }> = ({ token, refreshKey, onError }) => {
  const { lang } = useSaathi();
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
  const citizenFrom = m.live.response_ms.citizen
    ? say({ en: "real use", gu: "વાસ્તવિક ઉપયોગ", hi: "वास्तविक उपयोग" }, lang)
    : say({ en: "the latest test run", gu: "છેલ્લો ટેસ્ટ રન", hi: "पिछला टेस्ट रन" }, lang);
  const cons = m.test_run.consistency;
  const r = m.live.reports;
  const officerTest = m.test_run.latency_by_role?.officer;
  const fin = m.test_run.finished_at ? `, ${m.test_run.finished_at.replace("T", " ")}` : "";

  return (
    <section className="flex flex-col gap-3" aria-labelledby="poc-measures">
      <div>
        <h3 id="poc-measures" className="font-heading text-sm font-bold text-body">{say({ en: "POC measures", gu: "POC માપદંડ", hi: "POC मापदंड" }, lang)}</h3>
        <p className="text-xs text-muted mt-0.5">
          {say({
            en: `The measures in the POC scope. "Real use" is every question asked in the last ${m.days} days (only the outcome and time are kept, never the question). "Test run" is the latest run of the test set${fin}.`,
            gu: `POC કાર્યક્ષેત્રના માપદંડ. "વાસ્તવિક ઉપયોગ" એટલે છેલ્લા ${m.days} દિવસમાં પૂછાયેલો દરેક પ્રશ્ન (ફક્ત પરિણામ અને સમય સચવાય છે, પ્રશ્ન ક્યારેય નહીં). "ટેસ્ટ રન" એટલે ટેસ્ટ સેટનો છેલ્લો રન${fin}.`,
            hi: `POC दायरे के मापदंड। "वास्तविक उपयोग" यानी पिछले ${m.days} दिनों में पूछा गया हर प्रश्न (केवल परिणाम और समय रखा जाता है, प्रश्न कभी नहीं)। "टेस्ट रन" यानी टेस्ट सेट का पिछला रन${fin}।`,
          }, lang)}
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Measure
          title={say({ en: "Answered without a person", gu: "વ્યક્તિની મદદ વિના જવાબ", hi: "बिना किसी व्यक्ति के जवाब" }, lang)}
          value={live?.total ? `${live.self_served_pct}%` : test?.total ? `${test.self_served_pct}%` : "—"}
          sub={<>
            <span className="block">{live?.total
              ? say({ en: `Real use: ${n(live.total)} questions. ${split(live, lang)}.`, gu: `વાસ્તવિક ઉપયોગ: ${n(live.total)} પ્રશ્નો. ${split(live, lang)}.`, hi: `वास्तविक उपयोग: ${n(live.total)} प्रश्न। ${split(live, lang)}।` }, lang)
              : say({ en: "Real use: no questions yet.", gu: "વાસ્તવિક ઉપયોગ: હજી કોઈ પ્રશ્ન નથી.", hi: "वास्तविक उपयोग: अभी कोई प्रश्न नहीं।" }, lang)}</span>
            <span className="block mt-1">{test?.total
              ? say({ en: `Test run: ${test.self_served_pct}% of ${n(test.total)}. ${split(test, lang)}.`, gu: `ટેસ્ટ રન: ${n(test.total)} માંથી ${test.self_served_pct}%. ${split(test, lang)}.`, hi: `टेस्ट रन: ${n(test.total)} में से ${test.self_served_pct}%। ${split(test, lang)}।` }, lang)
              : say({ en: "Test run: not run yet.", gu: "ટેસ્ટ રન: હજી ચલાવ્યો નથી.", hi: "टेस्ट रन: अभी चलाया नहीं गया।" }, lang)}</span>
            <span className="block mt-1">{say({
              en: "\"Could not answer\" includes a correct \"not in the registry\" for a project that does not exist.",
              gu: "\"જવાબ ન આપી શક્યા\" માં, અસ્તિત્વમાં ન હોય તેવા પ્રોજેક્ટ માટેનો સાચો \"રજિસ્ટ્રીમાં નથી\" જવાબ પણ ગણાય છે.",
              hi: "\"जवाब नहीं दे सके\" में, जो प्रोजेक्ट मौजूद नहीं है उसके लिए सही \"रजिस्ट्री में नहीं\" जवाब भी शामिल है।",
            }, lang)}</span>
          </>}
        />
        <Measure
          title={say({ en: "Citizen response time (95th percentile)", gu: "નાગરિક માટે જવાબનો સમય (95મો પર્સેન્ટાઇલ)", hi: "नागरिक के लिए जवाब का समय (95वाँ पर्सेंटाइल)" }, lang)}
          value={citizen?.n ? secs(citizen.p95) : "—"}
          badge={citizen?.n ? <Badge ok={citizen.p95 <= m.targets.citizen_p95_ms}>{say({ en: `Target ≤ ${secs(m.targets.citizen_p95_ms)}`, gu: `લક્ષ્ય ≤ ${secs(m.targets.citizen_p95_ms)}`, hi: `लक्ष्य ≤ ${secs(m.targets.citizen_p95_ms)}` }, lang)}</Badge> : undefined}
          sub={citizen?.n ? <>{say({
            en: `From ${citizenFrom}: ${n(citizen.n)} answers, median ${secs(citizen.p50)}, slowest ${secs(citizen.max)}.`,
            gu: `${citizenFrom} મુજબ: ${n(citizen.n)} જવાબો, મધ્યસ્થ ${secs(citizen.p50)}, સૌથી ધીમો ${secs(citizen.max)}.`,
            hi: `${citizenFrom} से: ${n(citizen.n)} जवाब, माध्यिका ${secs(citizen.p50)}, सबसे धीमा ${secs(citizen.max)}।`,
          }, lang)}
            {m.live.understood_by_ai > 0 && say({
              en: ` ${n(m.live.understood_by_ai)} of the real questions needed the AI model to understand them; those are the slow ones.`,
              gu: ` વાસ્તવિક પ્રશ્નોમાંથી ${n(m.live.understood_by_ai)} ને સમજવા માટે AI મોડેલની જરૂર પડી; ધીમા જવાબો એ જ છે.`,
              hi: ` वास्तविक प्रश्नों में से ${n(m.live.understood_by_ai)} को समझने के लिए AI मॉडल की ज़रूरत पड़ी; धीमे जवाब वही हैं।`,
            }, lang)}</> : say({ en: "No answers yet.", gu: "હજી કોઈ જવાબ નથી.", hi: "अभी कोई जवाब नहीं।" }, lang)}
        />
        <Measure
          title={say({ en: "Officer report time", gu: "અધિકારી રિપોર્ટનો સમય", hi: "अधिकारी रिपोर्ट का समय" }, lang)}
          value={r.n ? secs(r.p50) : officerTest?.n ? secs(officerTest.p50) : "—"}
          badge={m.manual_report_minutes ? <Badge ok={m.report_speedup !== null ? m.report_speedup > 1 : null}>{say({ en: `vs ${n(m.manual_report_minutes)} min by hand`, gu: `જાતે ${n(m.manual_report_minutes)} મિનિટ સામે`, hi: `हाथ से ${n(m.manual_report_minutes)} मिनट की तुलना में` }, lang)}</Badge> : undefined}
          sub={<>
            <span className="block">{r.n
              ? say({ en: `Median of ${n(r.n)} reports in real use; 95th percentile ${secs(r.p95)}.`, gu: `વાસ્તવિક ઉપયોગમાં ${n(r.n)} રિપોર્ટનો મધ્યસ્થ; 95મો પર્સેન્ટાઇલ ${secs(r.p95)}.`, hi: `वास्तविक उपयोग में ${n(r.n)} रिपोर्ट की माध्यिका; 95वाँ पर्सेंटाइल ${secs(r.p95)}।` }, lang)
              : officerTest?.n
                ? say({ en: `Median of ${n(officerTest.n)} officer questions in the test run.`, gu: `ટેસ્ટ રનમાં ${n(officerTest.n)} અધિકારી પ્રશ્નોનો મધ્યસ્થ.`, hi: `टेस्ट रन में ${n(officerTest.n)} अधिकारी प्रश्नों की माध्यिका।` }, lang)
                : say({ en: "No reports yet.", gu: "હજી કોઈ રિપોર્ટ નથી.", hi: "अभी कोई रिपोर्ट नहीं।" }, lang)}</span>
            <label className="mt-2 flex flex-wrap items-center gap-2">
              <span>{say({ en: "Same report by hand (department's figure):", gu: "એ જ રિપોર્ટ જાતે (વિભાગનો આંકડો):", hi: "वही रिपोर्ट हाथ से (विभाग का आँकड़ा):" }, lang)}</span>
              <input type="number" min={1} value={minutes} onChange={(e) => setMinutes(e.target.value)} placeholder={say({ en: "minutes", gu: "મિનિટ", hi: "मिनट" }, lang)}
                aria-label={say({ en: "Minutes to prepare a report by hand", gu: "રિપોર્ટ જાતે તૈયાર કરવાની મિનિટ", hi: "रिपोर्ट हाथ से तैयार करने के मिनट" }, lang)}
                className="w-20 rounded-md border border-warm-border bg-card text-body text-xs px-2 py-1" />
              <span>{say({ en: "min", gu: "મિનિટ", hi: "मिनट" }, lang)}</span>
              <button type="button" disabled={saving} onClick={() => void save()}
                className="px-2.5 py-1 rounded-md bg-brand text-on-brand text-[11px] font-bold disabled:opacity-50">{say({ en: "Save", gu: "સાચવો", hi: "सहेजें" }, lang)}</button>
            </label>
          </>}
        />
        <Measure
          title={say({ en: "Same answer when asked again", gu: "ફરી પૂછતાં એ જ જવાબ", hi: "दोबारा पूछने पर वही जवाब" }, lang)}
          value={cons?.checked ? `${cons.pct}%` : "—"}
          badge={cons?.checked ? <Badge ok={(cons.pct ?? 0) >= m.targets.consistency_pct}>{say({ en: `Target ≥ ${m.targets.consistency_pct}%`, gu: `લક્ષ્ય ≥ ${m.targets.consistency_pct}%`, hi: `लक्ष्य ≥ ${m.targets.consistency_pct}%` }, lang)}</Badge> : undefined}
          sub={cons?.checked
            ? <>{say({
              en: `${n(cons.same)} of ${n(cons.checked)} questions from the test set, asked a second time, gave the same answer word for word.`,
              gu: `ટેસ્ટ સેટના ${n(cons.checked)} માંથી ${n(cons.same)} પ્રશ્નોએ બીજી વાર પૂછતાં શબ્દશઃ એ જ જવાબ આપ્યો.`,
              hi: `टेस्ट सेट के ${n(cons.checked)} में से ${n(cons.same)} प्रश्नों ने दूसरी बार पूछने पर शब्दशः वही जवाब दिया।`,
            }, lang)}
              {cons.differing.length > 0 && (() => {
                const list = cons.differing.map((x) => `#${x}`).join(", ");
                return say({ en: ` Different: test cases ${list}.`, gu: ` અલગ: ટેસ્ટ કેસ ${list}.`, hi: ` अलग: टेस्ट केस ${list}।` }, lang);
              })()}</>
            : say({ en: "Run the test set to measure this.", gu: "આ માપવા માટે ટેસ્ટ સેટ ચલાવો.", hi: "इसे मापने के लिए टेस्ट सेट चलाएँ।" }, lang)}
        />
      </div>
    </section>
  );
};
