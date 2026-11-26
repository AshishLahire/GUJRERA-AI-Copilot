import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  CalcProject,
  CalcRate,
  CalcResult,
  CalcSeed,
  calculateInterest,
  fetchCalcRate,
  searchCalcProjects,
} from "../api/gujrera";
import { Icon } from "./Brand";
import { say, useSaathi } from "./context";
import { En } from "./En";
import { StringKey, tr } from "./strings";

type Mode = "stay" | "withdraw";
type PaymentRow = { amount: string; paidOn: string };

const inr = (n: number) => `₹${Math.round(n).toLocaleString("en-IN")}`;
const LOCALE = { en: "en-IN", gu: "gu-IN", hi: "hi-IN" } as const;
// Dates in the interface language: "30 Nov 2026", "30 નવે, 2026", "30 नव॰ 2026"
const fmtDate = (iso: string, lang: keyof typeof LOCALE = "en") =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(LOCALE[lang], { day: "numeric", month: "short", year: "numeric" });

const Label: React.FC<{ k: StringKey; htmlFor?: string }> = ({ k, htmlFor }) => {
  const { lang } = useSaathi();
  return (
    <label htmlFor={htmlFor} className="block text-xs font-semibold text-body mb-1.5">
      {tr(k, lang)}
      <En k={k} className="font-normal text-muted" />
    </label>
  );
};

const inputCls =
  "w-full rounded-lg border border-warm-border bg-card text-body px-3 py-2 text-sm focus:outline-none focus:border-brand focus:ring-2 focus:ring-brand/30";

/** Project picker: search as you type by name (English or Gujarati) or RERA number. */
export const ProjectPicker: React.FC<{ value: CalcProject | null; onChange: (p: CalcProject | null) => void; initialText?: string; inputId?: string }> = ({
  value,
  onChange,
  initialText = "",
  inputId = "calc-project",
}) => {
  const { lang } = useSaathi();
  const [text, setText] = useState(initialText);
  const [items, setItems] = useState<CalcProject[]>([]);
  const [open, setOpen] = useState(false);
  const timer = useRef<number>();

  useEffect(() => {
    if (value) return;
    window.clearTimeout(timer.current);
    if (text.trim().length < 2) {
      setItems([]);
      return;
    }
    timer.current = window.setTimeout(() => {
      searchCalcProjects(text.trim()).then((r) => setItems(r.items)).catch(() => setItems([]));
    }, 200);
  }, [text, value]);

  if (value) {
    return (
      <div className="flex items-start justify-between gap-3 rounded-lg border border-warm-border bg-subtle px-3 py-2">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-body">{lang === "gu" && value.name_gu ? value.name_gu : value.name}</div>
          <div className="text-[11px] text-muted font-mono break-all">{value.rera_no}</div>
          <div className="text-[11px] text-muted">
            {value.district} · {say({ en: "promised", gu: "વચન", hi: "वादा" }, lang)} {fmtDate(value.promised, lang)}
          </div>
        </div>
        <button type="button" onClick={() => { onChange(null); setText(""); }} aria-label="Change project" className="text-muted hover:text-body mt-0.5">
          <Icon name="x" className="w-4 h-4" />
        </button>
      </div>
    );
  }
  return (
    <div className="relative">
      <input
        id={inputId}
        value={text}
        onChange={(e) => { setText(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        placeholder={tr("calcProjectHint", lang)}
        autoComplete="off"
        className={inputCls}
      />
      {open && items.length > 0 && (
        <ul className="absolute z-20 mt-1 w-full rounded-lg border border-warm-border bg-card shadow-lg max-h-72 overflow-auto">
          {items.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => { onChange(p); setOpen(false); }}
                className="w-full text-left px-3 py-2 hover:bg-subtle"
              >
                <div className="text-sm text-body">{p.name}{p.name_gu ? <span className="text-muted"> · {p.name_gu}</span> : null}</div>
                <div className="text-[11px] text-muted">{p.district} · {p.status}</div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export const CalculatorPage: React.FC<{ seed: CalcSeed | null; onAsk: (q: string) => void }> = ({ seed, onAsk }) => {
  const { lang } = useSaathi();
  const [project, setProject] = useState<CalcProject | null>(null);
  const [mode, setMode] = useState<Mode>(seed?.mode ?? "stay");
  const [payments, setPayments] = useState<PaymentRow[]>([{ amount: seed?.amount ? String(seed.amount) : "", paidOn: "" }]);
  const [useAgreementRate, setUseAgreementRate] = useState(false);
  const [agreementRate, setAgreementRate] = useState("");
  const [promisedOn, setPromisedOn] = useState("");
  const [until, setUntil] = useState("");
  const [rate, setRate] = useState<CalcRate | null>(null);
  const [result, setResult] = useState<CalcResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const autoRan = useRef(false);

  useEffect(() => {
    fetchCalcRate().then(setRate).catch(() => setRate(null));
  }, []);

  // Prefill from a chat card: resolve the project by id through the search endpoint.
  useEffect(() => {
    if (!seed) return;
    searchCalcProjects(seed.projectName)
      .then((r) => setProject(r.items.find((p) => p.id === seed.projectId) ?? r.items[0] ?? null))
      .catch(() => undefined);
  }, [seed]);

  const amounts = useMemo(
    () => payments.map((p) => ({ amount: Number(p.amount.replace(/[,\s₹]/g, "")), paid_on: p.paidOn || null })),
    [payments],
  );

  const run = async () => {
    if (!project) return;
    setBusy(true);
    setError(null);
    try {
      const res = await calculateInterest({
        project_id: project.id,
        mode,
        payments: amounts.filter((a) => a.amount > 0),
        promised_on: promisedOn || null,
        possession_on: until || null,
        rate: useAgreementRate && agreementRate ? Number(agreementRate) : null,
        lang,
      });
      setResult(res);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  // A seeded "stay" question with an amount is calculated straight away.
  useEffect(() => {
    if (project && seed?.amount && seed.mode === "stay" && !autoRan.current) {
      autoRan.current = true;
      void run();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project]);

  const canRun = !!project && amounts.some((a) => a.amount > 0) && (mode === "stay" || amounts.every((a) => !a.amount || a.paid_on));
  const r = result?.result;
  const sourceIds = result ? Array.from(new Set(result.sentences.flatMap((s) => s.citations.map((c) => c.id)))) : [];

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <div className="max-w-3xl">
        <p className="text-sm text-muted leading-relaxed">{tr("calcIntro", lang)}</p>
        {lang !== "en" && <p lang="en" className="text-xs text-muted opacity-80 mt-0.5">{tr("calcIntro", "en")}</p>}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] items-start">
        {/* Inputs */}
        <section className="rounded-xl border border-warm-border bg-card p-5 flex flex-col gap-5">
          <div>
            <Label k="calcProject" htmlFor="calc-project" />
            <ProjectPicker value={project} onChange={(p) => { setProject(p); setResult(null); }} initialText={seed?.projectName ?? ""} />
          </div>

          <div role="radiogroup" aria-label="What do you want" className="grid gap-2">
            {(["stay", "withdraw"] as Mode[]).map((m) => (
              <button
                key={m}
                type="button"
                role="radio"
                aria-checked={mode === m}
                onClick={() => { setMode(m); setResult(null); }}
                className={`flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-left text-sm ${
                  mode === m ? "border-body bg-subtle" : "border-warm-border hover:border-warm-strong"
                }`}
              >
                <span className={`mt-0.5 w-4 h-4 shrink-0 rounded-full border-2 ${mode === m ? "border-brand bg-brand" : "border-warm-strong"}`} />
                <span className="leading-snug text-body">
                  {tr(m === "stay" ? "calcStay" : "calcWithdraw", lang)}
                  <En k={m === "stay" ? "calcStay" : "calcWithdraw"} className="text-muted" />
                </span>
              </button>
            ))}
          </div>

          <div>
            <Label k="calcPayments" />
            <div className="flex flex-col gap-2">
              {payments.map((p, i) => (
                <div key={i} className="grid grid-cols-[1fr_1fr_auto] gap-2 items-center">
                  <input
                    inputMode="numeric"
                    aria-label={`${tr("calcAmount", "en")} ${i + 1}`}
                    placeholder={tr("calcAmount", lang)}
                    value={p.amount}
                    onChange={(e) => setPayments((ps) => ps.map((x, j) => (j === i ? { ...x, amount: e.target.value } : x)))}
                    className={inputCls}
                  />
                  <input
                    type="date"
                    aria-label={`${tr("calcPaidOn", "en")} ${i + 1}`}
                    required={mode === "withdraw"}
                    value={p.paidOn}
                    onChange={(e) => setPayments((ps) => ps.map((x, j) => (j === i ? { ...x, paidOn: e.target.value } : x)))}
                    className={inputCls}
                  />
                  <button
                    type="button"
                    aria-label="Remove payment"
                    disabled={payments.length === 1}
                    onClick={() => setPayments((ps) => ps.filter((_, j) => j !== i))}
                    className="w-8 h-8 rounded-md text-muted hover:text-body disabled:opacity-30 flex items-center justify-center"
                  >
                    <Icon name="x" className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
            <div className="mt-1.5 flex items-center justify-between text-[11px] text-muted">
              <span>
                {tr("calcPaidOn", lang)}: {mode === "withdraw" ? say({ en: "needed (interest runs from each payment, Rule 16(3))", gu: "જરૂરી (વ્યાજ દરેક ચુકવણીથી ગણાય, નિયમ 16(3))", hi: "ज़रूरी (ब्याज हर भुगतान से गिना जाता है, नियम 16(3))" }, lang) : say({ en: "optional", gu: "વૈકલ્પિક", hi: "वैकल्पिक" }, lang)}
              </span>
              <button
                type="button"
                onClick={() => setPayments((ps) => [...ps, { amount: "", paidOn: "" }])}
                className="inline-flex items-center gap-1 font-semibold text-body hover:underline"
              >
                <Icon name="plus" className="w-3.5 h-3.5" /> {tr("calcAddPayment", lang)}
              </button>
            </div>
          </div>

          <div>
            <Label k="calcRate" />
            <div className="flex flex-col gap-2 text-sm">
              <label className="flex items-start gap-2 cursor-pointer">
                <input type="radio" name="rate" checked={!useAgreementRate} onChange={() => setUseAgreementRate(false)} className="mt-1 accent-[var(--brand)]" />
                <span className="text-body">
                  {tr("calcRateDefault", lang)}: <b>{rate ? `${rate.rate}%` : "…"}</b>
                  {rate && (
                    <span className="block text-[11px] text-muted">
                      SBI MCLR {rate.mclr}% ({say({ en: "from", gu: "થી", hi: "से" }, lang)} {fmtDate(rate.mclr_as_of, lang)}) + 2%, {say({ en: "used when the agreement names no rate", gu: "કરારમાં દર ન હોય ત્યારે", hi: "जब अनुबंध में दर न हो" }, lang)}
                    </span>
                  )}
                </span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="radio" name="rate" checked={useAgreementRate} onChange={() => setUseAgreementRate(true)} className="accent-[var(--brand)]" />
                <span className="text-body">{tr("calcRateAgreement", lang)}</span>
                <input
                  inputMode="decimal"
                  aria-label="Agreement interest rate, % a year"
                  disabled={!useAgreementRate}
                  value={agreementRate}
                  onChange={(e) => setAgreementRate(e.target.value)}
                  placeholder="%"
                  className="w-20 rounded-md border border-warm-border bg-card text-body px-2 py-1 text-sm disabled:opacity-50"
                />
              </label>
            </div>
          </div>

          <details className="text-sm">
            <summary className="cursor-pointer text-xs font-semibold text-muted hover:text-body">{say({ en: "More dates (optional)", gu: "વધુ તારીખો (વૈકલ્પિક)", hi: "और तारीखें (वैकल्पिक)" }, lang)}</summary>
            <div className="mt-3 grid gap-3">
              <div>
                <Label k="calcPromisedOn" htmlFor="calc-promised" />
                <input id="calc-promised" type="date" value={promisedOn} onChange={(e) => setPromisedOn(e.target.value)} className={inputCls} />
              </div>
              <div>
                <Label k="calcUntil" htmlFor="calc-until" />
                <input id="calc-until" type="date" value={until} onChange={(e) => setUntil(e.target.value)} className={inputCls} />
              </div>
            </div>
          </details>

          <button
            type="button"
            disabled={!canRun || busy}
            onClick={() => void run()}
            className="rounded-lg bg-primary-bg text-primary-text px-4 py-2.5 text-sm font-semibold leading-tight disabled:opacity-40"
          >
            {busy ? "…" : <>{tr("calcGo", lang)}<En k="calcGo" className="font-normal" /></>}
          </button>
          {error && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>}
        </section>

        {/* Result */}
        <section className="flex flex-col gap-4" aria-live="polite">
          {!r ? (
            <div className="rounded-xl border border-dashed border-warm-strong p-8 text-center text-sm text-muted">
              <span className="inline-flex w-10 h-10 rounded-lg bg-brand-soft text-brand-strong items-center justify-center mb-3">
                <Icon name="calc" />
              </span>
              <p>{say({ en: "Choose a project and enter what you have paid.", gu: "પ્રોજેક્ટ પસંદ કરો અને તમે ચૂકવેલી રકમ લખો.", hi: "प्रोजेक्ट चुनें और आपने जो भुगतान किया वह लिखें।" }, lang)}</p>
            </div>
          ) : (
            <>
              <div className="grid gap-4 grid-cols-2 xl:grid-cols-3">
                <div className="rounded-xl border border-warm-border bg-card p-4 col-span-2 xl:col-span-1">
                  <div className="text-xs text-muted">
                    {tr(r.mode === "stay" ? "calcInterest" : "calcRefund", lang)}
                    <En k={r.mode === "stay" ? "calcInterest" : "calcRefund"} />
                  </div>
                  <div className="mt-2 font-heading text-3xl font-bold text-body tabular-nums">{inr(r.total)}</div>
                  {r.mode === "withdraw" && (
                    <div className="text-xs text-muted mt-1">{inr(r.principal)} + {inr(r.interest)} interest</div>
                  )}
                </div>
                <div className="rounded-xl border border-warm-border bg-card p-4">
                  <div className="text-xs text-muted">{tr("calcDelay", lang)}<En k="calcDelay" /></div>
                  <div className="mt-2 font-heading text-2xl font-bold text-body tabular-nums">{r.delay_days} days</div>
                  <div className="text-xs text-muted">{say({ en: "since", gu: "થી", hi: "से" }, lang)} {fmtDate(r.promised, lang)}</div>
                </div>
                <div className="rounded-xl border border-warm-border bg-card p-4">
                  <div className="text-xs text-muted">
                    {r.mode === "withdraw" ? <>{tr("calcDueBy", lang)}<En k="calcDueBy" /></> : <>{tr("calcRate", lang)}<En k="calcRate" /></>}
                  </div>
                  <div className="mt-2 font-heading text-2xl font-bold text-body tabular-nums">
                    {r.mode === "withdraw" && r.refund_due_by ? fmtDate(r.refund_due_by, lang) : `${r.rate_pct}%`}
                  </div>
                  <div className="text-xs text-muted">{r.mode === "withdraw" ? say({ en: "45 days, Rule 17", gu: "45 દિવસ, નિયમ 17", hi: "45 दिन, नियम 17" }, lang) : r.rate_source === "agreement" ? say({ en: "agreement rate", gu: "કરારનો દર", hi: "अनुबंध की दर" }, lang) : "SBI MCLR + 2%"}</div>
                </div>
              </div>

              <div className="rounded-xl border border-warm-border bg-card p-5 text-sm text-body leading-relaxed flex flex-col gap-2">
                {result!.sentences.map((s, i) => (
                  <p key={i} className={s.citations.length ? "" : "text-xs text-muted"}>
                    {s.text}
                    {s.citations.map((c) => (
                      <sup key={c.id} className="ml-0.5 text-[10px] font-semibold text-brand-strong">[{sourceIds.indexOf(c.id) + 1}]</sup>
                    ))}
                  </p>
                ))}
                <ol className="mt-2 pt-3 border-t border-warm-border text-xs text-muted list-decimal pl-5 space-y-0.5">
                  {sourceIds.map((id) => <li key={id} className="break-all">{id}</li>)}
                </ol>
              </div>

              <div className="rounded-xl border border-warm-border bg-card overflow-hidden">
                <h3 className="px-5 py-3 border-b border-warm-border text-sm font-bold text-body">
                  {tr("calcBreakdown", lang)}<En k="calcBreakdown" className="text-muted" />
                </h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-xs text-muted bg-subtle">
                      <tr>
                        <th className="text-left font-semibold px-5 py-2">{say({ en: "Amount", gu: "રકમ", hi: "राशि" }, lang)}</th>
                        <th className="text-left font-semibold px-3 py-2">{say({ en: "From", gu: "થી", hi: "से" }, lang)}</th>
                        <th className="text-left font-semibold px-3 py-2">{say({ en: "To", gu: "સુધી", hi: "तक" }, lang)}</th>
                        <th className="text-right font-semibold px-3 py-2">{say({ en: "Days", gu: "દિવસ", hi: "दिन" }, lang)}</th>
                        <th className="text-right font-semibold px-5 py-2">{say({ en: "Interest", gu: "વ્યાજ", hi: "ब्याज" }, lang)}</th>
                      </tr>
                    </thead>
                    <tbody className="tabular-nums">
                      {r.rows.map((row, i) => (
                        <tr key={i} className="border-t border-warm-border">
                          <td className="px-5 py-2">{inr(row.amount)}</td>
                          <td className="px-3 py-2 whitespace-nowrap">{fmtDate(row.from, lang)}</td>
                          <td className="px-3 py-2 whitespace-nowrap">{fmtDate(row.to, lang)}</td>
                          <td className="px-3 py-2 text-right">{row.days}</td>
                          <td className="px-5 py-2 text-right">{inr(row.interest)}</td>
                        </tr>
                      ))}
                      <tr className="border-t border-warm-strong font-semibold">
                        <td className="px-5 py-2">{inr(r.principal)}</td>
                        <td colSpan={3} className="px-3 py-2 text-muted font-normal text-xs">Simple interest at {r.rate_pct}% a year, days ÷ 365</td>
                        <td className="px-5 py-2 text-right">{inr(r.interest)}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() =>
                    onAsk(
                      { en: `I want to file a complaint about ${result!.project.name}. Possession is ${r.delay_days} days late.`,
                        gu: `મારે ${result!.project.name_gu || result!.project.name} વિશે ફરિયાદ નોંધાવવી છે. પઝેશન ${r.delay_days} દિવસ મોડું છે.`,
                        hi: `मुझे ${result!.project.name} के बारे में शिकायत दर्ज करनी है। पज़ेशन ${r.delay_days} दिन देर से है।` }[lang],
                    )
                  }
                  className="rounded-lg bg-primary-bg text-primary-text px-4 py-2 text-sm font-semibold leading-tight"
                >
                  {tr("calcFile", lang)}<En k="calcFile" className="font-normal" />
                </button>
                <button type="button" onClick={() => window.print()} className="rounded-lg border border-warm-border px-4 py-2 text-sm font-semibold text-body hover:bg-subtle">
                  Print / save PDF
                </button>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
};
