import React, { useEffect, useRef, useState } from "react";
import { REPORTABLE, ReportAd } from "../saathi/ReportAd";
import { Said, say, useUiLang } from "../saathi/context";
import {
  Lang,
  TrustCheck,
  TrustReport,
  TrustSample,
  TrustVerdict,
  checkTrustText,
  checkTrustUpload,
  fetchHealth,
  fetchTrustSamples,
  openReport,
} from "../api/gujrera";

const TONES: Record<string, { box: string; badge: string }> = {
  red: {
    box: "border-red-300 dark:border-red-800 bg-red-50/90 dark:bg-red-950/40 text-red-950 dark:text-red-100",
    badge: "bg-red-600 text-white dark:bg-red-500",
  },
  amber: {
    box: "border-amber-300 dark:border-amber-800 bg-amber-50/90 dark:bg-amber-950/40 text-amber-950 dark:text-amber-100",
    badge: "bg-amber-600 text-white dark:bg-amber-500",
  },
  green: {
    box: "border-emerald-300 dark:border-emerald-800 bg-emerald-50/90 dark:bg-emerald-950/40 text-emerald-950 dark:text-emerald-100",
    badge: "bg-emerald-600 text-white dark:bg-emerald-500",
  },
  neutral: {
    box: "border-warm-border bg-subtle text-body",
    badge: "bg-slate-600 text-white",
  },
};

const VERDICT_TONE: Record<TrustVerdict, keyof typeof TONES> = {
  verified: "green",
  registered_with_warnings: "amber",
  mismatch: "red",
  not_found: "red",
  lapsed_or_revoked: "red",
  no_rera_number: "red",
  unreadable: "neutral",
};

const T = {
  title: { en: "RERA trust check", gu: "RERA વિશ્વસનીયતા તપાસ", hi: "RERA विश्वसनीयता जाँच" },
  intro: {
    en: "Paste a property ad, brochure text or WhatsApp offer, or upload a photo. We check the RERA number, promoter and dates against the GUJRERA registry.",
    gu: "મિલકતની જાહેરાત, બ્રોશરનું લખાણ કે WhatsApp ઓફર પેસ્ટ કરો, અથવા ફોટો અપલોડ કરો. અમે RERA નંબર, પ્રમોટર અને તારીખો GUJRERA રજિસ્ટ્રી સાથે મેળવીએ છીએ.",
    hi: "संपत्ति का विज्ञापन, ब्रोशर का पाठ या WhatsApp ऑफ़र पेस्ट करें, या फ़ोटो अपलोड करें। हम RERA नंबर, प्रमोटर और तारीखें GUJRERA रजिस्ट्री से मिलाते हैं।",
  },
  sample: { en: "Try a sample", gu: "નમૂનો અજમાવો", hi: "नमूना आज़माएँ" },
  adText: { en: "Ad or message text", gu: "જાહેરાત કે સંદેશનું લખાણ", hi: "विज्ञापन या संदेश का पाठ" },
  check: { en: "Check", gu: "તપાસો", hi: "जाँचें" },
  checking: { en: "Checking…", gu: "તપાસી રહ્યા છીએ…", hi: "जाँच रहे हैं…" },
  upload: { en: "Upload photo or PDF", gu: "ફોટો કે PDF અપલોડ કરો", hi: "फ़ोटो या PDF अपलोड करें" },
  footDemo: {
    en: "Prototype: registry data is demo data (registration codes start with MOCK).",
    gu: "પ્રોટોટાઇપ: રજિસ્ટ્રી ડેટા ડેમો ડેટા છે (નોંધણી કોડ MOCK થી શરૂ થાય છે).",
    hi: "प्रोटोटाइप: रजिस्ट्री डेटा डेमो डेटा है (पंजीकरण कोड MOCK से शुरू होते हैं)।",
  },
  footPublic: {
    en: "Checked against public GUJRERA records imported from the portal.",
    gu: "પોર્ટલ પરથી લીધેલા જાહેર GUJRERA રેકોર્ડ સાથે તપાસ્યું.",
    hi: "पोर्टल से लिए गए सार्वजनिक GUJRERA रिकॉर्ड से जाँचा गया।",
  },
  deleted: { en: "Uploaded files are deleted after reading.", gu: "અપલોડ કરેલી ફાઇલો વાંચ્યા પછી કાઢી નાખવામાં આવે છે.", hi: "अपलोड की गई फ़ाइलें पढ़ने के बाद हटा दी जाती हैं।" },
  empty: { en: "Pick a sample or paste an ad to see the result here.", gu: "પરિણામ અહીં જોવા નમૂનો પસંદ કરો અથવા જાહેરાત પેસ્ટ કરો.", hi: "परिणाम यहाँ देखने के लिए नमूना चुनें या विज्ञापन पेस्ट करें।" },
  checkingRegistry: { en: "Checking against the registry…", gu: "રજિસ્ટ્રી સાથે તપાસી રહ્યા છીએ…", hi: "रजिस्ट्री से जाँच रहे हैं…" },
  demo: { en: "Demo data", gu: "ડેમો ડેટા", hi: "डेमो डेटा" },
  checks: { en: "Checks", gu: "તપાસ", hi: "जाँच" },
  record: { en: "GUJRERA registry record", gu: "GUJRERA રજિસ્ટ્રી રેકોર્ડ", hi: "GUJRERA रजिस्ट्री रिकॉर्ड" },
  regNo: { en: "Registration number", gu: "નોંધણી નંબર", hi: "पंजीकरण संख्या" },
  project: { en: "Project", gu: "પ્રોજેક્ટ", hi: "प्रोजेक्ट" },
  promoter: { en: "Promoter", gu: "પ્રમોટર", hi: "प्रमोटर" },
  district: { en: "District", gu: "જિલ્લો", hi: "जिला" },
  status: { en: "Status", gu: "સ્થિતિ", hi: "स्थिति" },
  validUntil: { en: "Valid until", gu: "ક્યાં સુધી માન્ય", hi: "कब तक मान्य" },
  delay: { en: "Delay vs original date", gu: "મૂળ તારીખથી વિલંબ", hi: "मूल तारीख से देरी" },
  days: { en: "days", gu: "દિવસ", hi: "दिन" },
  none: { en: "None", gu: "કોઈ નહીં", hi: "कोई नहीं" },
  openRecord: { en: "Open the full registry record →", gu: "સંપૂર્ણ રજિસ્ટ્રી રેકોર્ડ ખોલો →", hi: "पूरा रजिस्ट्री रिकॉर्ड खोलें →" },
  projects: { en: "Projects", gu: "પ્રોજેક્ટ", hi: "प्रोजेक्ट" },
  delayed: { en: "Delayed", gu: "વિલંબિત", hi: "विलंबित" },
  openComplaints: { en: "Open complaints", gu: "ખુલ્લી ફરિયાદો", hi: "खुली शिकायतें" },
  adverse: { en: "Adverse orders", gu: "પ્રતિકૂળ આદેશો", hi: "प्रतिकूल आदेश" },
} satisfies Record<string, Said>;

const VERDICT_TEXT: Record<TrustVerdict, Said> = {
  verified: { en: "Verified", gu: "ખાતરી થઈ", hi: "सत्यापित" },
  registered_with_warnings: { en: "Registered, with warnings", gu: "નોંધાયેલ, ચેતવણીઓ સાથે", hi: "पंजीकृत, चेतावनियों के साथ" },
  mismatch: { en: "Mismatch", gu: "મેળ નથી", hi: "मेल नहीं" },
  not_found: { en: "Not found", gu: "મળ્યું નથી", hi: "नहीं मिला" },
  lapsed_or_revoked: { en: "Lapsed or revoked", gu: "મુદત પૂરી કે રદ", hi: "समाप्त या रद्द" },
  no_rera_number: { en: "No RERA number", gu: "RERA નંબર નથી", hi: "RERA नंबर नहीं" },
  unreadable: { en: "Unreadable", gu: "વાંચી શકાયું નથી", hi: "पढ़ा नहीं जा सका" },
};

const SAMPLE_TEXT: Record<string, Said> = {
  "genuine-en": { en: "Genuine ad", gu: "સાચી જાહેરાત", hi: "असली विज्ञापन" },
  "genuine-gu": { en: "Genuine ad · ગુજરાતી", gu: "સાચી જાહેરાત · ગુજરાતી", hi: "असली विज्ञापन · ગુજરાતી" },
  "not_found-en": { en: "Fake RERA number", gu: "નકલી RERA નંબર", hi: "नकली RERA नंबर" },
  "lapsed_or_revoked-en": { en: "Lapsed registration", gu: "મુદત પૂરી થયેલી નોંધણી", hi: "समाप्त पंजीकरण" },
  "promoter_mismatch-en": { en: "Wrong promoter", gu: "ખોટો પ્રમોટર", hi: "गलत प्रमोटर" },
  "possession_late-en": { en: "Late possession promise", gu: "મોડા પઝેશનનું વચન", hi: "देर से कब्ज़े का वादा" },
  "no_number-en": { en: "No RERA number", gu: "RERA નંબર નથી", hi: "RERA नंबर नहीं" },
  "booking_over_limit-en": { en: "25% booking demand", gu: "25% બુકિંગની માગણી", hi: "25% बुकिंग की माँग" },
};

const STATUS_STYLE: Record<TrustCheck["status"], { dot: string; label: string }> = {
  fail: { dot: "bg-red-600", label: "Problem" },
  warn: { dot: "bg-amber-500", label: "Warning" },
  pass: { dot: "bg-emerald-600", label: "OK" },
  info: { dot: "bg-slate-400", label: "Note" },
};

const LANGS: { id: Lang; label: string }[] = [
  { id: "gu", label: "ગુજરાતી" },
  { id: "hi", label: "हिन्दी" },
  { id: "en", label: "English" },
];

function fmt(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

const RegistryCard: React.FC<{ report: TrustReport }> = ({ report }) => {
  const ui = useUiLang();
  const t = (k: keyof typeof T) => say(T[k], ui);
  const project = report.records.find((r) => r.source.type === "project");
  const card = report.records.find((r) => r.source.type === "promoter_scorecard");
  const agent = report.records.find((r) => r.source.type === "agent");
  if (!project && !agent) return null;
  return (
    <section className="rounded-card border border-warm-border bg-card p-4 shadow-xs">
      <h3 className="font-heading text-sm font-bold text-body mb-3">{t("record")}</h3>
      {project && (
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-xs">
          <div className="sm:col-span-2">
            <dt className="text-muted">{t("regNo")}</dt>
            <dd className="font-mono text-body break-all">{fmt(project.rera_no)}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("project")}</dt>
            <dd className="text-body font-semibold">{fmt(project.name)}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("promoter")}</dt>
            <dd className="text-body">{fmt(project.promoter_name)}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("district")}</dt>
            <dd className="text-body">{fmt(project.district)}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("status")}</dt>
            <dd className="text-body capitalize">{fmt(project.status)}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("validUntil")}</dt>
            <dd className="text-body">{fmt(project.reg_valid_until)}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("delay")}</dt>
            <dd className="text-body">{Number(project.delay_days) > 0 ? `${project.delay_days} ${t("days")}` : t("none")}</dd>
          </div>
        </dl>
      )}
      {project && Number(project.id) > 0 && (
        <button type="button" onClick={() => openReport(Number(project.id))}
          className="mt-3 inline-flex items-center gap-1 rounded-full border border-warm-border px-3 py-1 text-xs font-semibold text-body hover:border-warm-strong">
          {t("openRecord")}
        </button>
      )}
      {card && (
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2">
          {[
            [t("projects"), card.projects],
            [t("delayed"), card.delayed_projects],
            [t("openComplaints"), card.complaints_open],
            [t("adverse"), card.adverse_orders],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-lg border border-warm-border bg-subtle px-3 py-2">
              <div className="text-[11px] text-muted">{String(label)}</div>
              <div className="font-heading text-lg font-bold text-body">{fmt(value)}</div>
            </div>
          ))}
        </div>
      )}
      {agent && (
        <p className="mt-3 text-xs text-body">
          Agent: <span className="font-semibold">{fmt(agent.name)}</span> · {fmt(agent.status)} · valid until{" "}
          {fmt(agent.valid_until)}
        </p>
      )}
    </section>
  );
};

export const ReraCheckPage: React.FC = () => {
  const ui = useUiLang();
  const t = (k: keyof typeof T) => say(T[k], ui);
  const [samples, setSamples] = useState<TrustSample[]>([]);
  const [text, setText] = useState("");
  const [lang, setLang] = useState<Lang>(ui === "en" ? "gu" : ui);  // the answer opens in the interface language (Gujarati when English)
  const [report, setReport] = useState<TrustReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Samples are optional (demo data only): a failure to load them is not an error for the user.
  const [demo, setDemo] = useState(true);
  useEffect(() => {
    fetchTrustSamples()
      .then((r) => setSamples(r.items))
      .catch(() => setSamples([]));
    fetchHealth()
      .then((h) => setDemo(h.mock_projects > 0 || h.projects === 0))
      .catch(() => setDemo(true));
  }, []);

  const run = async (fn: () => Promise<TrustReport>) => {
    setLoading(true);
    setError(null);
    try {
      setReport(await fn());
    } catch (e) {
      setReport(null);
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const onSample = (s: TrustSample) => {
    setText(s.text);
    if (s.lang === "gu") setLang("gu");
    run(() => checkTrustText(s.text));
  };

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) run(() => checkTrustUpload(file));
  };

  const tone = report ? TONES[VERDICT_TONE[report.verdict]] : null;

  return (
    <div className="max-w-[1440px] w-full mx-auto px-4 sm:px-6 py-6 grid grid-cols-1 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] gap-6">
      {/* Input */}
      <section className="rounded-card border border-warm-border bg-card p-5 shadow-xs flex flex-col gap-4 h-fit">
        <div>
          <h2 className="font-heading text-lg font-bold text-body">{t("title")}</h2>
          <p className="text-sm text-muted mt-1">{t("intro")}</p>
        </div>

        {samples.length > 0 && (
          <div>
            <div className="text-[11px] font-bold uppercase tracking-wider text-muted mb-2">{t("sample")}</div>
            <div className="flex flex-wrap gap-2">
              {samples.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => onSample(s)}
                  className="text-xs px-3 py-1.5 rounded-full border border-warm-border bg-subtle text-body hover:border-accent-amber transition"
                >
                  {SAMPLE_TEXT[`${s.kind}-${s.lang}`] ? say(SAMPLE_TEXT[`${s.kind}-${s.lang}`], ui) : s.label}
                </button>
              ))}
            </div>
          </div>
        )}

        <label className="flex flex-col gap-1.5">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted">{t("adText")}</span>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={9}
            placeholder="e.g. Sabarmati Heights by … GujRERA Reg. No: PR/GJ/… Possession Dec 2027"
            className="w-full rounded-lg border border-warm-border bg-page text-body text-sm p-3 font-sans focus:outline-none focus:ring-2 focus:ring-accent-amber"
          />
        </label>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={loading || !text.trim()}
            onClick={() => run(() => checkTrustText(text))}
            className="px-4 py-2 rounded-lg bg-primary-bg text-primary-text text-sm font-semibold disabled:opacity-50"
          >
            {loading ? t("checking") : t("check")}
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={() => fileRef.current?.click()}
            className="px-4 py-2 rounded-lg border border-warm-border text-body text-sm font-semibold hover:bg-subtle disabled:opacity-50"
          >
            {t("upload")}
          </button>
          <input ref={fileRef} type="file" accept=".png,.jpg,.jpeg,.webp,.pdf" className="hidden" onChange={onFile} />
        </div>
        <p className="text-[11px] text-muted">
          {demo ? t("footDemo") : t("footPublic")} {t("deleted")}
        </p>
      </section>

      {/* Result */}
      <section className="flex flex-col gap-4 min-w-0" aria-live="polite">
        {error && (
          <div role="alert" className={`rounded-card border p-4 text-sm ${TONES.red.box}`}>
            {error}
          </div>
        )}

        {!report && !error && (
          <div className="rounded-card border border-dashed border-warm-border p-8 text-center text-sm text-muted">
            {loading ? t("checkingRegistry") : t("empty")}
          </div>
        )}

        {report && tone && (
          <>
            <div className={`rounded-card border p-5 shadow-xs ${tone.box}`}>
              <div className="flex flex-wrap items-center gap-2 mb-3">
                <span className={`text-[11px] font-bold uppercase px-2.5 py-1 rounded-full ${tone.badge}`}>
                  {say(VERDICT_TEXT[report.verdict], ui)}
                </span>
                {report.is_mock && (
                  <span className="text-[11px] font-semibold px-2.5 py-1 rounded-full border border-current opacity-80">
                    {t("demo")}
                  </span>
                )}
                <div className="ml-auto flex gap-1" role="group" aria-label="Answer language">
                  {LANGS.map((l) => (
                    <button
                      key={l.id}
                      type="button"
                      onClick={() => setLang(l.id)}
                      aria-pressed={lang === l.id}
                      className={`text-[11px] px-2 py-0.5 rounded-md border border-current ${
                        lang === l.id ? "font-bold" : "opacity-60"
                      }`}
                    >
                      {l.label}
                    </button>
                  ))}
                </div>
              </div>
              <p className="font-heading text-lg sm:text-xl font-bold leading-snug">{report.headline[lang]}</p>
              {lang !== "en" && <p className="text-sm opacity-80 mt-1">{report.headline.en}</p>}
              <p className="text-sm mt-3 leading-relaxed">{report.next_steps_i18n?.[lang] ?? report.next_steps}</p>
            </div>

            {REPORTABLE.has(report.verdict) && (report.ocr?.text || text).trim().length >= 20 && (
              <ReportAd key={report.ocr?.text || text} text={report.ocr?.text || text} channel={report.ocr ? "upload" : "text"} />
            )}

            <RegistryCard report={report} />

            <section className="rounded-card border border-warm-border bg-card p-4 shadow-xs">
              <h3 className="font-heading text-sm font-bold text-body mb-3">{t("checks")}</h3>
              <ul className="flex flex-col divide-y divide-warm-border">
                {report.checks.map((c, i) => (
                  <li key={`${c.id}-${i}`} className="py-2.5 flex gap-3">
                    <span
                      className={`w-2.5 h-2.5 rounded-full mt-1.5 shrink-0 ${STATUS_STYLE[c.status].dot}`}
                      aria-label={STATUS_STYLE[c.status].label}
                    />
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-body">{c.title_i18n?.[lang] ?? c.title}</div>
                      <div className="text-xs text-muted leading-relaxed">{c.detail}</div>
                      {c.evidence && (
                        <div className="mt-1 text-[11px] font-mono text-body bg-subtle rounded px-2 py-1 break-words">
                          “{c.evidence}”
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </section>

            {report.ocr && (
              <details
                open={!!report.ocr.low_confidence}
                className="rounded-card border border-warm-border bg-card p-4 text-sm"
              >
                <summary className="cursor-pointer font-semibold text-body">
                  Text read from the document ({report.ocr.engine}
                  {report.ocr.confidence != null ? ` · ${Math.round(report.ocr.confidence)}% confidence` : ""})
                </summary>
                {report.ocr.note && (
                  <p className={`mt-2 text-xs ${report.ocr.low_confidence ? "text-amber-700 dark:text-amber-300" : "text-muted"}`}>
                    {report.ocr.note}
                  </p>
                )}
                <pre className="mt-2 whitespace-pre-wrap text-xs text-muted font-sans">{report.ocr.text}</pre>
              </details>
            )}
          </>
        )}
      </section>
    </div>
  );
};
