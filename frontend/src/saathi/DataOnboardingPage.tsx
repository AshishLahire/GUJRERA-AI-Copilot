import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AuthExpiredError,
  ImportBody,
  ImportHistory,
  ImportKind,
  ImportResult,
  ImportSheet,
  ImportUpload,
  describeImport,
  downloadRejected,
  fetchImports,
  navigateTo,
  runImport,
  uploadImport,
} from "../api/gujrera";
import { Icon } from "./Brand";
import { Said, say, useSaathi } from "./context";
import { LoginPrompt } from "./RolePages";

const n = (v: number) => v.toLocaleString("en-IN");
const DEFAULT_SOURCE = "https://gujrera.gujarat.gov.in/#/";

const UI = {
  eyebrow: { en: "State data admin", gu: "રાજ્ય ડેટા એડમિન", hi: "राज्य डेटा एडमिन" },
  title: { en: "Load the department's data", gu: "વિભાગનો ડેટા લોડ કરો", hi: "विभाग का डेटा लोड करें" },
  lead: {
    en: "Upload a CSV dump, Excel export or API JSON file. Match its columns, check every row without saving anything, then load. The assistants answer from the new records at once.",
    gu: "CSV ડમ્પ, Excel એક્સપોર્ટ કે API JSON ફાઇલ અપલોડ કરો. કૉલમ મેળવો, કંઈ સાચવ્યા વિના દરેક પંક્તિ તપાસો, પછી લોડ કરો. સહાયકો તરત નવા રેકોર્ડમાંથી જવાબ આપે છે.",
    hi: "CSV डंप, Excel एक्सपोर्ट या API JSON फ़ाइल अपलोड करें। कॉलम मिलाएँ, बिना सहेजे हर पंक्ति जाँचें, फिर लोड करें। सहायक तुरंत नए रिकॉर्ड से जवाब देते हैं।",
  },
} satisfies Record<string, Said>;

const STEPS: Said[] = [
  { en: "Upload", gu: "અપલોડ કરો", hi: "अपलोड करें" },
  { en: "Match columns", gu: "કૉલમ મેળવો", hi: "कॉलम मिलाएँ" },
  { en: "Check", gu: "તપાસો", hi: "जाँचें" },
  { en: "Load", gu: "લોડ કરો", hi: "लोड करें" },
];

const Stepper: React.FC<{ step: number }> = ({ step }) => {
  const { lang } = useSaathi();
  return (
    <ol className="flex flex-wrap items-center gap-2 text-xs" aria-label={say({ en: "Steps", gu: "પગલાં", hi: "चरण" }, lang)}>
      {STEPS.map((label, i) => {
        const done = i < step, now = i === step;
        return (
          <li key={label.en} className="flex items-center gap-2">
            <span className={`w-6 h-6 rounded-full flex items-center justify-center font-bold ${done ? "bg-brand text-on-brand" : now ? "bg-primary-bg text-primary-text" : "bg-subtle text-muted border border-warm-border"}`}
              aria-current={now ? "step" : undefined}>{done ? "✓" : i + 1}</span>
            <span className={now ? "font-semibold text-body" : "text-muted"}>{say(label, lang)}</span>
            {i < STEPS.length - 1 && <span className="w-6 h-px bg-warm-strong" aria-hidden="true" />}
          </li>
        );
      })}
    </ol>
  );
};

const Tile: React.FC<{ label: string; value: number; tone?: "good" | "warn" | "bad" | "plain" }> = ({ label, value, tone = "plain" }) => {
  const ring = { good: "border-l-emerald-600", warn: "border-l-brand", bad: "border-l-red-600", plain: "border-l-warm-strong" }[tone];
  return (
    <div className={`warm-card p-3 border-l-4 ${ring}`}>
      <div className="font-heading text-2xl font-bold text-body tabular-nums">{n(value)}</div>
      <div className="text-xs text-muted">{label}</div>
    </div>
  );
};

const ResultPanel: React.FC<{ r: ImportResult; onDownload: () => void }> = ({ r, onDownload }) => {
  const { lang } = useSaathi();
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Tile label={r.saved
          ? say({ en: "New records added", gu: "ઉમેરાયેલા નવા રેકોર્ડ", hi: "जोड़े गए नए रिकॉर्ड" }, lang)
          : say({ en: "New records", gu: "નવા રેકોર્ડ", hi: "नए रिकॉर्ड" }, lang)} value={r.inserted} tone="good" />
        <Tile label={r.saved
          ? say({ en: "Records updated", gu: "અપડેટ થયેલા રેકોર્ડ", hi: "अपडेट किए गए रिकॉर्ड" }, lang)
          : say({ en: "Would change", gu: "બદલાશે", hi: "बदलेंगे" }, lang)} value={r.updated} tone="warn" />
        <Tile label={say({ en: "Already up to date", gu: "પહેલેથી અદ્યતન", hi: "पहले से अद्यतन" }, lang)} value={r.unchanged} />
        <Tile label={say({ en: "Rejected rows", gu: "નકારાયેલ પંક્તિઓ", hi: "अस्वीकृत पंक्तियाँ" }, lang)} value={r.rejected} tone={r.rejected ? "bad" : "plain"} />
      </div>
      {r.no_promoter > 0 && (
        <p className="text-xs text-muted">{say({
          en: `${n(r.no_promoter)} project rows have no promoter name; they are listed under “Promoter not in imported records”.`,
          gu: `${n(r.no_promoter)} પ્રોજેક્ટ પંક્તિઓમાં પ્રમોટરનું નામ નથી; તે “આયાત કરેલા રેકોર્ડમાં પ્રમોટર નથી” હેઠળ દર્શાવેલ છે.`,
          hi: `${n(r.no_promoter)} प्रोजेक्ट पंक्तियों में प्रमोटर का नाम नहीं है; वे “आयात किए गए रिकॉर्ड में प्रमोटर नहीं” के अंतर्गत दिखाई गई हैं।`,
        }, lang)}</p>
      )}
      {r.errors.length > 0 && (
        <div className="warm-card p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h4 className="text-sm font-semibold text-body">{say({ en: "Why rows were rejected", gu: "પંક્તિઓ કેમ નકારાઈ", hi: "पंक्तियाँ क्यों अस्वीकृत हुईं" }, lang)}</h4>
            {r.saved && (
              <button type="button" onClick={onDownload} className="text-xs px-3 py-1.5 rounded-full border border-warm-border text-body hover:border-brand">
                {say({
                  en: "Download rejected rows (CSV) to fix and load again",
                  gu: "સુધારીને ફરી લોડ કરવા નકારાયેલ પંક્તિઓ (CSV) ડાઉનલોડ કરો",
                  hi: "सुधारकर फिर से लोड करने के लिए अस्वीकृत पंक्तियाँ (CSV) डाउनलोड करें",
                }, lang)}
              </button>
            )}
          </div>
          <table className="mt-2 w-full text-xs">
            <thead><tr className="text-muted text-left"><th className="py-1 font-medium w-16">{say({ en: "Row", gu: "પંક્તિ", hi: "पंक्ति" }, lang)}</th><th className="py-1 font-medium">{say({ en: "Reason", gu: "કારણ", hi: "कारण" }, lang)}</th></tr></thead>
            <tbody>
              {r.errors.slice(0, 25).map((e) => (
                <tr key={e.row} className="border-t border-warm-border align-top"><td className="py-1 tabular-nums text-body">{e.row}</td><td className="py-1 text-body break-words">{e.error}</td></tr>
              ))}
            </tbody>
          </table>
          {(r.errors.length > 25 || r.errors_truncated) && (
            <p className="mt-1 text-[11px] text-muted">
              {say({ en: `Showing 25 of ${n(r.rejected)}.`, gu: `${n(r.rejected)} માંથી 25 દર્શાવેલ છે.`, hi: `${n(r.rejected)} में से 25 दिखाई गई हैं।` }, lang)}{" "}
              {r.saved
                ? say({ en: "The CSV has them all.", gu: "CSV માં બધી છે.", hi: "CSV में सभी हैं।" }, lang)
                : say({ en: "Load to get the full list as a CSV.", gu: "પૂરી યાદી CSV તરીકે મેળવવા લોડ કરો.", hi: "पूरी सूची CSV के रूप में पाने के लिए लोड करें।" }, lang)}
            </p>
          )}
        </div>
      )}
    </div>
  );
};

export const DataOnboardingPage: React.FC = () => {
  const { user, token, lang, logout } = useSaathi();
  const allowed = user?.role === "officer" && !user.district_scope;
  const [hist, setHist] = useState<ImportHistory | null>(null);
  const [up, setUp] = useState<ImportUpload | null>(null);
  const [sheetName, setSheetName] = useState<string>("");
  const [kind, setKind] = useState<ImportKind>("project");
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [source, setSource] = useState(DEFAULT_SOURCE);
  const [check, setCheck] = useState<ImportResult | null>(null);
  const [loaded, setLoaded] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState<"" | "upload" | "check" | "load">("");
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);

  const fail = useCallback((e: unknown) => {
    if (e instanceof AuthExpiredError) logout();
    setError((e as Error).message);
  }, [logout]);

  const refresh = useCallback(() => {
    if (token && allowed) fetchImports(token).then(setHist).catch(fail);
  }, [token, allowed, fail]);
  useEffect(refresh, [refresh]);

  const sheet: ImportSheet | null = useMemo(() => up?.sheets.find((s) => s.name === sheetName) ?? up?.sheets[0] ?? null, [up, sheetName]);

  const choose = (u: ImportUpload, name?: string) => {
    const sh = u.sheets.find((s) => s.name === name) ?? u.sheets[0];
    setUp(u);
    setSheetName(sh.name);
    setKind(sh.suggested_kind);
    setMapping({ ...sh.kinds[sh.suggested_kind].mapping });
    setCheck(null);
    setLoaded(null);
  };

  const onFile = async (file: File | undefined) => {
    if (!file || !token) return;
    setError(null);
    setBusy("upload");
    try {
      choose(await uploadImport(token, file));
      refresh();
    } catch (e) { fail(e); } finally { setBusy(""); }
  };

  const body = (): ImportBody => ({ sheet: sheet!.name, kind, mapping, source_url: source });
  const go = async (step: "check" | "load") => {
    if (!token || !up || !sheet) return;
    setError(null);
    setBusy(step);
    try {
      const r = await runImport(token, up.run.id, step, body());
      if (step === "check") { setCheck(r); setLoaded(null); } else setLoaded(r);
      refresh();
    } catch (e) { fail(e); } finally { setBusy(""); }
  };

  const resume = async (id: string) => {
    if (!token) return;
    try { choose(await describeImport(token, id)); window.scrollTo({ top: 0, behavior: "smooth" }); } catch (e) { fail(e); }
  };

  if (!allowed) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-8 flex flex-col gap-3">
        <p className="text-sm text-muted">{say({
          en: "Loading data is for state-level GUJRERA officers (the data admins). District officers see their district's data in the work queue.",
          gu: "ડેટા લોડ કરવાનું કામ રાજ્ય કક્ષાના GUJRERA અધિકારીઓ (ડેટા એડમિન) માટે છે. જિલ્લા અધિકારીઓ તેમના જિલ્લાનો ડેટા કામની યાદીમાં જુએ છે.",
          hi: "डेटा लोड करना राज्य स्तर के GUJRERA अधिकारियों (डेटा एडमिन) के लिए है। जिला अधिकारी अपने जिले का डेटा कार्य सूची में देखते हैं।",
        }, lang)}</p>
        {!user && <LoginPrompt k="loginNeededOfficer" />}
      </div>
    );
  }

  const step = loaded ? 4 : check ? 3 : up ? 1 : 0;
  const spec = sheet ? sheet.kinds[kind] : null;
  const missing = spec ? spec.fields.filter((f) => f.required && !mapping[f.key]).map((f) => f.label_i18n?.[lang] ?? f.label) : [];
  const estimate = sheet ? Math.max(2, Math.round(sheet.rows / 500)) : 0;
  const rowsWord = say({ en: "rows", gu: "પંક્તિઓ", hi: "पंक्तियाँ" }, lang);

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <section className="hero-band p-6">
        <p className="text-xs font-semibold uppercase tracking-wider text-accent-amber-strong">{say(UI.eyebrow, lang)}</p>
        <h2 className="mt-1 font-heading text-2xl font-bold text-body">{say(UI.title, lang)}</h2>
        <p className="mt-1 text-sm text-muted max-w-3xl">{say(UI.lead, lang)}</p>
        <div className="mt-4"><Stepper step={step} /></div>
      </section>

      {hist && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Tile label={say({ en: "Projects in the registry", gu: "રજિસ્ટ્રીમાં પ્રોજેક્ટ", hi: "रजिस्ट्री में प्रोजेक्ट" }, lang)} value={hist.registry.projects} />
          <Tile label={say({ en: "Agents in the registry", gu: "રજિસ્ટ્રીમાં એજન્ટ", hi: "रजिस्ट्री में एजेंट" }, lang)} value={hist.registry.agents} />
          <Tile label={say({ en: "Projects with a site address", gu: "સાઇટ સરનામાવાળા પ્રોજેક્ટ", hi: "साइट पते वाले प्रोजेक्ट" }, lang)} value={hist.registry.with_address} />
          <Tile label={say({ en: "Projects with a locality (area)", gu: "વિસ્તાર ધરાવતા પ્રોજેક્ટ", hi: "इलाके (क्षेत्र) वाले प्रोजेक्ट" }, lang)} value={hist.registry.with_locality} />
        </div>
      )}

      {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 dark:bg-red-950/40 dark:text-red-200 dark:border-red-900 p-3 text-sm">{error}</div>}

      {/* 1. Upload */}
      <section className="warm-card p-5">
        <h3 className="font-heading text-sm font-bold text-body">{say({ en: "1. Upload a data file", gu: "1. ડેટા ફાઇલ અપલોડ કરો", hi: "1. डेटा फ़ाइल अपलोड करें" }, lang)}</h3>
        <label
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); void onFile(e.dataTransfer.files[0]); }}
          className={`mt-3 flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center cursor-pointer transition-colors ${drag ? "border-brand bg-brand-soft" : "border-warm-strong bg-subtle/60 hover:border-brand"}`}>
          <span className="w-10 h-10 rounded-lg bg-brand-soft text-brand-strong flex items-center justify-center"><Icon name="doc" /></span>
          <span className="text-sm font-semibold text-body">{busy === "upload"
            ? say({ en: "Reading the file…", gu: "ફાઇલ વાંચી રહ્યા છીએ…", hi: "फ़ाइल पढ़ी जा रही है…" }, lang)
            : say({ en: "Drop a file here, or click to choose", gu: "ફાઇલ અહીં મૂકો, અથવા પસંદ કરવા ક્લિક કરો", hi: "फ़ाइल यहाँ छोड़ें, या चुनने के लिए क्लिक करें" }, lang)}</span>
          <span className="text-xs text-muted">{say({
            en: ".csv, .xlsx or .json, up to 25 MB. Only the columns you match are read; others (phone numbers, e-mails) are ignored.",
            gu: ".csv, .xlsx કે .json, 25 MB સુધી. ફક્ત તમે મેળવેલી કૉલમ જ વંચાય છે; બાકીની (ફોન નંબર, ઈ-મેલ) અવગણાય છે.",
            hi: ".csv, .xlsx या .json, 25 MB तक। केवल आपके मिलाए गए कॉलम ही पढ़े जाते हैं; बाकी (फ़ोन नंबर, ई-मेल) अनदेखे किए जाते हैं।",
          }, lang)}</span>
          <input type="file" accept=".csv,.xlsx,.xlsm,.json" className="sr-only" disabled={busy !== ""} onChange={(e) => void onFile(e.target.files?.[0])} />
        </label>
        {up && (
          <p className="mt-2 text-xs text-muted">
            <b className="text-body">{up.run.filename}</b> · {n(up.run.rows)} {rowsWord} · {(up.run.size_bytes / 1024).toFixed(0)} KB
          </p>
        )}
      </section>

      {/* 2. Match columns */}
      {up && sheet && spec && (
        <section className="warm-card p-5 flex flex-col gap-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <h3 className="font-heading text-sm font-bold text-body">{say({
              en: "2. What is in this file, and which column is which",
              gu: "2. આ ફાઇલમાં શું છે, અને કઈ કૉલમ શું છે",
              hi: "2. इस फ़ाइल में क्या है, और कौन-सा कॉलम क्या है",
            }, lang)}</h3>
            {up.sheets.length > 1 && (
              <select value={sheet.name} onChange={(e) => choose(up, e.target.value)} aria-label={say({ en: "Sheet", gu: "શીટ", hi: "शीट" }, lang)}
                className="rounded-lg border border-warm-border bg-card text-body text-xs px-2 py-1.5">
                {up.sheets.map((s) => <option key={s.name} value={s.name}>{s.name} ({n(s.rows)} {rowsWord})</option>)}
              </select>
            )}
          </div>
          <div className="grid gap-2 md:grid-cols-3" role="radiogroup" aria-label={say({ en: "Kind of records", gu: "રેકોર્ડનો પ્રકાર", hi: "रिकॉर्ड का प्रकार" }, lang)}>
            {(Object.keys(sheet.kinds) as ImportKind[]).map((k) => (
              <button key={k} type="button" role="radio" aria-checked={kind === k}
                onClick={() => { setKind(k); setMapping({ ...sheet.kinds[k].mapping }); setCheck(null); setLoaded(null); }}
                className={`text-left rounded-xl border p-3 text-xs transition ${kind === k ? "border-brand bg-brand-soft ring-1 ring-brand" : "border-warm-border bg-card hover:border-warm-strong"}`}>
                <span className="block font-semibold text-body text-sm">{sheet.kinds[k].label_i18n?.[lang] ?? sheet.kinds[k].label}</span>
                {sheet.suggested_kind === k && <span className="mt-1 inline-block rounded-full bg-card border border-accent-border px-2 py-0.5 text-[10px] font-semibold text-accent-amber-strong">{say({ en: "Suggested for this file", gu: "આ ફાઇલ માટે સૂચવેલ", hi: "इस फ़ाइल के लिए सुझाया गया" }, lang)}</span>}
              </button>
            ))}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[560px]">
              <thead>
                <tr className="text-muted text-left border-b border-warm-border">
                  <th className="py-2 font-medium">{say({ en: "Registry field", gu: "રજિસ્ટ્રી ક્ષેત્ર", hi: "रजिस्ट्री फ़ील्ड" }, lang)}</th>
                  <th className="py-2 font-medium">{say({ en: "Column in the file", gu: "ફાઇલમાંની કૉલમ", hi: "फ़ाइल में कॉलम" }, lang)}</th>
                  <th className="py-2 font-medium">{say({ en: "First row", gu: "પહેલી પંક્તિ", hi: "पहली पंक्ति" }, lang)}</th>
                </tr>
              </thead>
              <tbody>
                {spec.fields.map((f) => {
                  const col = mapping[f.key] ?? "";
                  return (
                    <tr key={f.key} className="border-b border-warm-border last:border-0">
                      <td className="py-1.5 pr-3 text-body">
                        {f.label_i18n?.[lang] ?? f.label}{f.required && <span className="ml-1 text-red-700 dark:text-red-300" title={say({ en: "Required", gu: "જરૂરી", hi: "आवश्यक" }, lang)}>*</span>}
                        {f.hint && <span className="block text-[10px] text-muted">{f.hint_i18n?.[lang] ?? f.hint}</span>}
                      </td>
                      <td className="py-1.5 pr-3">
                        <select value={col} aria-label={say({ en: `Column for ${f.label}`, gu: `${f.label_i18n?.gu ?? f.label} માટે કૉલમ`, hi: `${f.label_i18n?.hi ?? f.label} के लिए कॉलम` }, lang)}
                          onChange={(e) => { setMapping((m) => ({ ...m, [f.key]: e.target.value })); setCheck(null); setLoaded(null); }}
                          className={`w-full max-w-[240px] rounded-md border bg-card text-body px-2 py-1 ${col ? "border-warm-border" : f.required ? "border-red-400" : "border-warm-border text-muted"}`}>
                          <option value="">{say({ en: "— not in this file —", gu: "— આ ફાઇલમાં નથી —", hi: "— इस फ़ाइल में नहीं —" }, lang)}</option>
                          {sheet.headers.map((h) => <option key={h} value={h}>{h}</option>)}
                        </select>
                      </td>
                      <td className="py-1.5 text-muted break-all">{col ? sheet.sample[0]?.[col] ?? "" : ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {spec.unused.length > 0 && (
            <p className="text-xs text-muted">{say({ en: "Not read:", gu: "વંચાયું નથી:", hi: "पढ़ा नहीं गया:" }, lang)} {spec.unused.filter((h) => !Object.values(mapping).includes(h)).map((h) => (
              <span key={h} className="inline-block mr-1 mb-1 px-2 py-0.5 rounded-full bg-subtle border border-warm-border">{h}</span>
            ))}</p>
          )}
          {kind !== "project_update" && (
            <label className="text-xs text-muted flex flex-col gap-1 max-w-xl">
              {say({
                en: "Source link cited in answers for rows without their own link",
                gu: "જે પંક્તિઓની પોતાની લિંક નથી, તેમના જવાબમાં ટાંકવાની સ્રોત લિંક",
                hi: "जिन पंक्तियों का अपना लिंक नहीं है, उनके जवाबों में दिया जाने वाला स्रोत लिंक",
              }, lang)}
              <input value={source} onChange={(e) => setSource(e.target.value)} className="rounded-md border border-warm-border bg-card text-body px-2 py-1.5" />
            </label>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" disabled={busy !== "" || missing.length > 0} onClick={() => void go("check")}
              className="px-5 py-2.5 rounded-xl bg-primary-bg text-primary-text text-sm font-semibold disabled:opacity-50">
              {busy === "check"
                ? say({
                  en: `Checking ${n(sheet.rows)} rows… about ${estimate} s`,
                  gu: `${n(sheet.rows)} પંક્તિઓ તપાસી રહ્યા છીએ… આશરે ${estimate} s`,
                  hi: `${n(sheet.rows)} पंक्तियाँ जाँची जा रही हैं… लगभग ${estimate} s`,
                }, lang)
                : say({ en: "3. Check every row (saves nothing)", gu: "3. દરેક પંક્તિ તપાસો (કંઈ સાચવાતું નથી)", hi: "3. हर पंक्ति जाँचें (कुछ सहेजा नहीं जाता)" }, lang)}
            </button>
            {missing.length > 0 && <span className="text-xs text-red-700 dark:text-red-300">{say({ en: "Match a column for:", gu: "આ માટે કૉલમ મેળવો:", hi: "इनके लिए कॉलम मिलाएँ:" }, lang)} {missing.join(", ")}</span>}
          </div>
        </section>
      )}

      {/* 3. Check result and 4. Load */}
      {check && !loaded && up && (
        <section className="warm-card p-5 flex flex-col gap-4">
          <h3 className="font-heading text-sm font-bold text-body">{say({
            en: "3. Check result: nothing has been saved yet",
            gu: "3. તપાસનું પરિણામ: હજી કંઈ સાચવાયું નથી",
            hi: "3. जाँच का परिणाम: अभी कुछ सहेजा नहीं गया है",
          }, lang)}</h3>
          <ResultPanel r={check} onDownload={() => undefined} />
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" disabled={busy !== "" || check.inserted + check.updated === 0} onClick={() => void go("load")}
              className="px-5 py-2.5 rounded-xl bg-brand text-on-brand text-sm font-bold shadow-sm disabled:opacity-50">
              {busy === "load"
                ? say({ en: "Loading…", gu: "લોડ થઈ રહ્યું છે…", hi: "लोड हो रहा है…" }, lang)
                : say({
                  en: `4. Load ${n(check.inserted)} new and ${n(check.updated)} changed records`,
                  gu: `4. ${n(check.inserted)} નવા અને ${n(check.updated)} બદલાયેલા રેકોર્ડ લોડ કરો`,
                  hi: `4. ${n(check.inserted)} नए और ${n(check.updated)} बदले हुए रिकॉर्ड लोड करें`,
                }, lang)}
            </button>
            <span className="text-xs text-muted">{say({
              en: "Rejected rows are skipped; every load is recorded with your name.",
              gu: "નકારાયેલ પંક્તિઓ છોડી દેવાય છે; દરેક લોડ તમારા નામ સાથે નોંધાય છે.",
              hi: "अस्वीकृत पंक्तियाँ छोड़ दी जाती हैं; हर लोड आपके नाम के साथ दर्ज होता है।",
            }, lang)}</span>
          </div>
        </section>
      )}
      {loaded && up && token && (
        <section className="warm-card p-5 flex flex-col gap-4 border-l-4 border-l-emerald-600">
          <h3 className="font-heading text-sm font-bold text-body flex items-center gap-2"><Icon name="shield" className="w-4 h-4 text-emerald-700" /> {say({
            en: "Loaded. The assistants now answer from these records.",
            gu: "લોડ થયું. સહાયકો હવે આ રેકોર્ડમાંથી જવાબ આપે છે.",
            hi: "लोड हो गया। सहायक अब इन रिकॉर्ड से जवाब देते हैं।",
          }, lang)}</h3>
          <ResultPanel r={loaded} onDownload={() => void downloadRejected(token, up.run.id, up.run.filename).catch(fail)} />
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => navigateTo("ask")} className="text-xs px-3 py-1.5 rounded-full bg-primary-bg text-primary-text font-semibold">{say({ en: "Ask Saathi about them", gu: "તેમના વિશે સાથીને પૂછો", hi: "इनके बारे में साथी से पूछें" }, lang)}</button>
            <button type="button" onClick={() => navigateTo("report")} className="text-xs px-3 py-1.5 rounded-full border border-warm-border text-body hover:border-brand">{say({ en: "Open a project record", gu: "પ્રોજેક્ટ રેકોર્ડ ખોલો", hi: "प्रोजेक्ट रिकॉर्ड खोलें" }, lang)}</button>
            {loaded.sample_new.length > 0 && <span className="text-xs text-muted self-center">{say({ en: "New, for example:", gu: "નવા, ઉદાહરણ તરીકે:", hi: "नए, उदाहरण के लिए:" }, lang)} {loaded.sample_new.join(", ")}</span>}
          </div>
        </section>
      )}

      {/* History */}
      {hist && (
        <section className="warm-card p-5">
          <h3 className="font-heading text-sm font-bold text-body">{say({ en: "Import history", gu: "આયાતનો ઇતિહાસ", hi: "आयात का इतिहास" }, lang)}</h3>
          {hist.runs.length === 0 ? (
            <p className="mt-2 text-sm text-muted">{say({
              en: "No files loaded through the console yet.",
              gu: "કન્સોલ દ્વારા હજી કોઈ ફાઇલ લોડ થઈ નથી.",
              hi: "कंसोल से अभी तक कोई फ़ाइल लोड नहीं हुई है।",
            }, lang)}</p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-xs min-w-[760px]">
                <thead>
                  <tr className="text-muted text-left border-b border-warm-border">
                    <th className="py-2 font-medium">{say({ en: "File", gu: "ફાઇલ", hi: "फ़ाइल" }, lang)}</th><th className="py-2 font-medium">{say({ en: "Kind", gu: "પ્રકાર", hi: "प्रकार" }, lang)}</th>
                    <th className="py-2 font-medium text-right">{say({ en: "Rows", gu: "પંક્તિઓ", hi: "पंक्तियाँ" }, lang)}</th><th className="py-2 font-medium text-right">{say({ en: "New", gu: "નવા", hi: "नए" }, lang)}</th>
                    <th className="py-2 font-medium text-right">{say({ en: "Changed", gu: "બદલાયેલા", hi: "बदले हुए" }, lang)}</th><th className="py-2 font-medium text-right">{say({ en: "Rejected", gu: "નકારાયેલ", hi: "अस्वीकृत" }, lang)}</th>
                    <th className="py-2 font-medium">{say({ en: "Status", gu: "સ્થિતિ", hi: "स्थिति" }, lang)}</th><th className="py-2 font-medium">{say({ en: "By, when", gu: "કોણે, ક્યારે", hi: "किसने, कब" }, lang)}</th><th className="py-2" />
                  </tr>
                </thead>
                <tbody>
                  {hist.runs.map((r) => (
                    <tr key={r.id} className="border-b border-warm-border last:border-0">
                      <td className="py-1.5 pr-2 text-body break-all">{r.filename}</td>
                      <td className="py-1.5 pr-2 text-muted">{r.kind ?? "—"}</td>
                      <td className="py-1.5 text-right tabular-nums">{n(r.rows)}</td>
                      <td className="py-1.5 text-right tabular-nums">{n(r.inserted)}</td>
                      <td className="py-1.5 text-right tabular-nums">{n(r.updated)}</td>
                      <td className="py-1.5 text-right tabular-nums">{n(r.rejected)}</td>
                      <td className="py-1.5 pl-3">
                        <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold ${r.status === "loaded" ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-900" : "border-accent-border bg-accent-surface text-accent-amber-strong"}`}>{r.status}</span>
                      </td>
                      <td className="py-1.5 text-muted">{r.loaded_by ?? r.uploaded_by ?? "—"}, {(r.loaded_at ?? r.uploaded_at).replace("T", " ")}</td>
                      <td className="py-1.5 text-right whitespace-nowrap">
                        {r.status !== "loaded" && <button type="button" onClick={() => void resume(r.id)} className="text-[11px] font-semibold text-brand-strong mr-2">{say({ en: "Continue", gu: "ચાલુ રાખો", hi: "जारी रखें" }, lang)}</button>}
                        {r.status === "loaded" && r.rejected > 0 && token && (
                          <button type="button" onClick={() => void downloadRejected(token, r.id, r.filename).catch(fail)} className="text-[11px] font-semibold text-brand-strong">{say({ en: "Rejected rows", gu: "નકારાયેલ પંક્તિઓ", hi: "अस्वीकृत पंक्तियाँ" }, lang)}</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
};
