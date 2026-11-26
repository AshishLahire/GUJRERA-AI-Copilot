import React, { useEffect, useState } from "react";
import { AgreementFinding, AgreementReport, checkAgreement, fetchAgreementSamples, uploadAgreement } from "../api/gujrera";
import { Icon } from "./Brand";
import { say, useSaathi } from "./context";
import { En } from "./En";
import { StringKey, tr } from "./strings";

const STYLE: Record<AgreementFinding["status"], { dot: string; box: string; label: string }> = {
  fail: { dot: "bg-red-600", box: "border-red-200 dark:border-red-900", label: "Problem" },
  warn: { dot: "bg-brand", box: "border-accent-border", label: "Check" },
  pass: { dot: "bg-emerald-600", box: "border-warm-border", label: "In order" },
};

const Finding: React.FC<{ f: AgreementFinding }> = ({ f }) => {
  const { lang } = useSaathi();
  return (
    <li className={`rounded-xl border bg-card p-4 ${STYLE[f.status].box}`}>
      <div className="flex items-start gap-2.5">
        <span className={`mt-1.5 w-2.5 h-2.5 shrink-0 rounded-full ${STYLE[f.status].dot}`} aria-label={STYLE[f.status].label} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h4 className="text-sm font-semibold text-body">
              {f.title}
              {lang !== "en" && <span className="ml-1.5 font-normal text-muted text-xs">{f.title_en}</span>}
            </h4>
            <span className="text-[10px] text-muted">{f.citations.map((c) => c.id.replace("Gujarat RERA General Rules, 2017, ", "").replace("RERA Act, 2016, ", "")).join(" · ")}</span>
          </div>
          <p className="mt-1 text-sm text-body leading-relaxed">{f.detail}</p>
          {f.excerpt && <blockquote className="mt-2 text-xs text-muted border-l-2 border-warm-strong pl-3 italic">“{f.excerpt}”</blockquote>}
          {f.ask && f.status !== "pass" && <p className="mt-2 text-xs font-semibold text-body">{say({ en: "What to ask:", gu: "શું પૂછવું:", hi: "क्या पूछें:" }, lang)} <span className="font-normal">{f.ask}</span></p>}
        </div>
      </div>
    </li>
  );
};

export const AgreementPage: React.FC = () => {
  const { lang } = useSaathi();
  const [text, setText] = useState("");
  const [res, setRes] = useState<AgreementReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [samples, setSamples] = useState<{ one_sided: string; fair: string; note?: string | null } | null>(null);

  useEffect(() => { fetchAgreementSamples().then(setSamples).catch(() => setSamples(null)); }, []);

  const run = async (fn: () => Promise<AgreementReport>) => {
    setBusy(true);
    setError(null);
    try {
      setRes(await fn());
    } catch (e) {
      setRes(null);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (f) void run(() => uploadAgreement(f, lang));
  };

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <div className="max-w-3xl">
        <p className="text-sm text-muted leading-relaxed">{tr("agrIntro", lang)}</p>
        {lang !== "en" && <p lang="en" className="text-xs text-muted opacity-80 mt-0.5">{tr("agrIntro", "en")}</p>}
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] items-start">
        <section className="rounded-xl border border-warm-border bg-card p-5 flex flex-col gap-3">
          <label htmlFor="agr-text" className="text-xs font-semibold text-body">{tr("agrPaste", lang)}<En k="agrPaste" className="font-normal text-muted" /></label>
          <textarea id="agr-text" value={text} onChange={(e) => setText(e.target.value)} rows={14}
            placeholder="AGREEMENT FOR SALE ..."
            className="w-full rounded-lg border border-warm-border bg-card text-body px-3 py-2 text-xs font-mono focus:outline-none focus:border-brand focus:ring-2 focus:ring-brand/30" />
          {samples && (
            <div className="flex flex-wrap gap-2 text-xs">
              <span className="text-muted">{say({ en: "Try:", gu: "અજમાવો:", hi: "आज़माएँ:" }, lang)}</span>
              <button type="button" onClick={() => { setText(samples.one_sided); void run(() => checkAgreement(samples.one_sided, lang)); }}
                className="rounded-full border border-warm-border px-2.5 py-1 hover:border-warm-strong">{say({ en: "One-sided sample", gu: "એકતરફી નમૂનો", hi: "एकतरफ़ा नमूना" }, lang)}</button>
              <button type="button" onClick={() => { setText(samples.fair); void run(() => checkAgreement(samples.fair, lang)); }}
                className="rounded-full border border-warm-border px-2.5 py-1 hover:border-warm-strong">{say({ en: "Fair sample", gu: "યોગ્ય નમૂનો", hi: "संतुलित नमूना" }, lang)}</button>
              {samples.note && <span className="w-full text-[11px] text-muted">{say({ en: samples.note, gu: "નમૂનામાં કાલ્પનિક પ્રોજેક્ટ છે, તેથી નોંધણી તપાસ કહે છે કે તે રજિસ્ટ્રીમાં નથી. તમારા પ્રોજેક્ટ માટે તમારો કરાર પેસ્ટ કરો.", hi: "नमूने में काल्पनिक प्रोजेक्ट है, इसलिए पंजीकरण जाँच बताती है कि वह रजिस्ट्री में नहीं है। अपने प्रोजेक्ट के लिए अपना अनुबंध पेस्ट करें।" }, lang)}</span>}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" disabled={busy || text.trim().length < 200} onClick={() => void run(() => checkAgreement(text, lang))}
              className="px-4 py-2 rounded-lg bg-primary-bg text-primary-text text-sm font-semibold leading-tight disabled:opacity-40">
              {busy ? "…" : <>{tr("agrCheck", lang)}<En k="agrCheck" className="font-normal" /></>}
            </button>
            <label className="text-xs font-semibold text-body cursor-pointer inline-flex items-center gap-1.5">
              <Icon name="doc" className="w-4 h-4" />
              {tr("agrUpload", lang)}
              <input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.txt" onChange={onFile} className="sr-only" />
            </label>
          </div>
          <p className="text-[11px] text-muted">{say({ en: "The text is checked and not kept. This points out what to ask the promoter to change; it is not legal advice.", gu: "લખાણ તપાસીને રાખવામાં આવતું નથી. આ પ્રમોટર પાસે શું બદલાવવું તે બતાવે છે; આ કાનૂની સલાહ નથી.", hi: "पाठ जाँचा जाता है, रखा नहीं जाता। यह बताता है कि प्रमोटर से क्या बदलवाना है; यह कानूनी सलाह नहीं है।" }, lang)}</p>
          {error && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>}
        </section>

        <section className="flex flex-col gap-4" aria-live="polite">
          {!res ? (
            <div className="rounded-xl border border-dashed border-warm-strong p-8 text-center text-sm text-muted">
              <span className="inline-flex w-10 h-10 rounded-lg bg-brand-soft text-brand-strong items-center justify-center mb-3"><Icon name="doc" /></span>
              <p>{say({ en: "Paste or upload an agreement, or try a sample.", gu: "કરાર પેસ્ટ કે અપલોડ કરો, અથવા નમૂનો અજમાવો.", hi: "अनुबंध पेस्ट या अपलोड करें, या नमूना आज़माएँ।" }, lang)}</p>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-3">
                {([["agrProblems", res.counts.fail, "text-red-700 dark:text-red-300"], ["agrToCheck", res.counts.warn, "text-accent-amber-strong"], ["agrOk", res.counts.pass, "text-emerald-700 dark:text-emerald-300"]] as [StringKey, number, string][]).map(([k, v, cls]) => (
                  <div key={k} className="rounded-xl border border-warm-border bg-card p-4">
                    <div className="text-xs text-muted">{tr(k, lang)}<En k={k} /></div>
                    <div className={`mt-1 font-heading text-2xl font-bold tabular-nums ${cls}`}>{v}</div>
                  </div>
                ))}
              </div>
              {res.project && (
                <p className="text-xs text-muted">{say({ en: "Project in the agreement:", gu: "કરારમાં પ્રોજેક્ટ:", hi: "अनुबंध में प्रोजेक्ट:" }, lang)} <b className="text-body">{res.project.name}</b> · {res.project.rera_no} · {res.project.status}{res.read_as ? ` · read as ${res.read_as}` : ""}</p>
              )}
              <ul className="flex flex-col gap-3">{res.findings.map((f) => <Finding key={f.id} f={f} />)}</ul>
              <p className="text-[11px] text-muted">{say({ en: "Compared with the model agreement for sale in the Gujarat RERA General Rules, 2017 (Annexure A) and the RERA Act, 2016.", gu: "ગુજરાત RERA સામાન્ય નિયમો, 2017 (પરિશિષ્ટ A) ના મોડેલ વેચાણ કરાર અને RERA કાયદો, 2016 સાથે સરખાવ્યું.", hi: "गुजरात RERA सामान्य नियम, 2017 (अनुलग्नक A) के मॉडल बिक्री अनुबंध और RERA अधिनियम, 2016 से तुलना की गई।" }, lang)}</p>
            </>
          )}
        </section>
      </div>
    </div>
  );
};
