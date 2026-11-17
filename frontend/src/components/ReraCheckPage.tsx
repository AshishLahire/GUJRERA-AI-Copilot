import React, { useEffect, useRef, useState } from "react";
import {
  Lang,
  TrustCheck,
  TrustReport,
  TrustSample,
  TrustVerdict,
  checkTrustText,
  checkTrustUpload,
  fetchTrustSamples,
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

const VERDICT_LABEL: Record<TrustVerdict, string> = {
  verified: "Verified",
  registered_with_warnings: "Registered, with warnings",
  mismatch: "Mismatch",
  not_found: "Not found",
  lapsed_or_revoked: "Lapsed or revoked",
  no_rera_number: "No RERA number",
  unreadable: "Unreadable",
};

const SAMPLE_LABEL: Record<string, string> = {
  "genuine-en": "Genuine ad",
  "genuine-gu": "Genuine ad · ગુજરાતી",
  "not_found-en": "Fake RERA number",
  "lapsed_or_revoked-en": "Lapsed registration",
  "promoter_mismatch-en": "Wrong promoter",
  "possession_late-en": "Late possession promise",
  "no_number-en": "No RERA number",
  "booking_over_limit-en": "25% booking demand",
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
  const project = report.records.find((r) => r.source.type === "project");
  const card = report.records.find((r) => r.source.type === "promoter_scorecard");
  const agent = report.records.find((r) => r.source.type === "agent");
  if (!project && !agent) return null;
  return (
    <section className="rounded-card border border-warm-border bg-card p-4 shadow-xs">
      <h3 className="font-heading text-sm font-bold text-body mb-3">GUJRERA registry record</h3>
      {project && (
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-xs">
          <div className="sm:col-span-2">
            <dt className="text-muted">Registration number</dt>
            <dd className="font-mono text-body break-all">{fmt(project.rera_no)}</dd>
          </div>
          <div>
            <dt className="text-muted">Project</dt>
            <dd className="text-body font-semibold">{fmt(project.name)}</dd>
          </div>
          <div>
            <dt className="text-muted">Promoter</dt>
            <dd className="text-body">{fmt(project.promoter_name)}</dd>
          </div>
          <div>
            <dt className="text-muted">District</dt>
            <dd className="text-body">{fmt(project.district)}</dd>
          </div>
          <div>
            <dt className="text-muted">Status</dt>
            <dd className="text-body capitalize">{fmt(project.status)}</dd>
          </div>
          <div>
            <dt className="text-muted">Valid until</dt>
            <dd className="text-body">{fmt(project.reg_valid_until)}</dd>
          </div>
          <div>
            <dt className="text-muted">Delay vs original date</dt>
            <dd className="text-body">{Number(project.delay_days) > 0 ? `${project.delay_days} days` : "None"}</dd>
          </div>
        </dl>
      )}
      {card && (
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2">
          {[
            ["Projects", card.projects],
            ["Delayed", card.delayed_projects],
            ["Open complaints", card.complaints_open],
            ["Adverse orders", card.adverse_orders],
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
  const [samples, setSamples] = useState<TrustSample[]>([]);
  const [text, setText] = useState("");
  const [lang, setLang] = useState<Lang>("gu");
  const [report, setReport] = useState<TrustReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchTrustSamples()
      .then((r) => setSamples(r.items))
      .catch((e: Error) => setError(e.message));
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
          <h2 className="font-heading text-lg font-bold text-body">RERA trust check</h2>
          <p className="text-sm text-muted mt-1">
            Paste a property ad, brochure text or WhatsApp offer, or upload a photo. We check the RERA number,
            promoter and dates against the GUJRERA registry.
          </p>
        </div>

        {samples.length > 0 && (
          <div>
            <div className="text-[11px] font-bold uppercase tracking-wider text-muted mb-2">Try a sample</div>
            <div className="flex flex-wrap gap-2">
              {samples.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => onSample(s)}
                  className="text-xs px-3 py-1.5 rounded-full border border-warm-border bg-subtle text-body hover:border-accent-amber transition"
                >
                  {SAMPLE_LABEL[`${s.kind}-${s.lang}`] ?? s.label}
                </button>
              ))}
            </div>
          </div>
        )}

        <label className="flex flex-col gap-1.5">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted">Ad or message text</span>
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
            {loading ? "Checking…" : "Check"}
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={() => fileRef.current?.click()}
            className="px-4 py-2 rounded-lg border border-warm-border text-body text-sm font-semibold hover:bg-subtle disabled:opacity-50"
          >
            Upload photo or PDF
          </button>
          <input ref={fileRef} type="file" accept=".png,.jpg,.jpeg,.webp,.pdf" className="hidden" onChange={onFile} />
        </div>
        <p className="text-[11px] text-muted">
          Prototype: registry data is demo data (registration codes start with MOCK). Uploaded files are deleted
          after reading.
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
            {loading ? "Checking against the registry…" : "Pick a sample or paste an ad to see the result here."}
          </div>
        )}

        {report && tone && (
          <>
            <div className={`rounded-card border p-5 shadow-xs ${tone.box}`}>
              <div className="flex flex-wrap items-center gap-2 mb-3">
                <span className={`text-[11px] font-bold uppercase px-2.5 py-1 rounded-full ${tone.badge}`}>
                  {VERDICT_LABEL[report.verdict]}
                </span>
                {report.is_mock && (
                  <span className="text-[11px] font-semibold px-2.5 py-1 rounded-full border border-current opacity-80">
                    Demo data
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
              <p className="text-sm mt-3 leading-relaxed">{report.next_steps}</p>
            </div>

            <RegistryCard report={report} />

            <section className="rounded-card border border-warm-border bg-card p-4 shadow-xs">
              <h3 className="font-heading text-sm font-bold text-body mb-3">Checks</h3>
              <ul className="flex flex-col divide-y divide-warm-border">
                {report.checks.map((c, i) => (
                  <li key={`${c.id}-${i}`} className="py-2.5 flex gap-3">
                    <span
                      className={`w-2.5 h-2.5 rounded-full mt-1.5 shrink-0 ${STATUS_STYLE[c.status].dot}`}
                      aria-label={STATUS_STYLE[c.status].label}
                    />
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-body">{c.title}</div>
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
