import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AuthExpiredError,
  ImportBody,
  ImportHistory,
  ImportKind,
  ImportResult,
  ImportSheet,
  ImportUpload,
  Lang,
  describeImport,
  downloadRejected,
  fetchImports,
  navigateTo,
  runImport,
  uploadImport,
} from "../api/gujrera";
import { Icon } from "./Brand";
import { useSaathi } from "./context";
import { LoginPrompt } from "./RolePages";

type L3 = { en: string; gu: string; hi: string };
const t3 = (s: L3, lang: Lang) => s[lang] ?? s.en;
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
} satisfies Record<string, L3>;

const STEPS = ["Upload", "Match columns", "Check", "Load"];

const Stepper: React.FC<{ step: number }> = ({ step }) => (
  <ol className="flex flex-wrap items-center gap-2 text-xs" aria-label="Steps">
    {STEPS.map((label, i) => {
      const done = i < step, now = i === step;
      return (
        <li key={label} className="flex items-center gap-2">
          <span className={`w-6 h-6 rounded-full flex items-center justify-center font-bold ${done ? "bg-brand text-on-brand" : now ? "bg-primary-bg text-primary-text" : "bg-subtle text-muted border border-warm-border"}`}
            aria-current={now ? "step" : undefined}>{done ? "✓" : i + 1}</span>
          <span className={now ? "font-semibold text-body" : "text-muted"}>{label}</span>
          {i < STEPS.length - 1 && <span className="w-6 h-px bg-warm-strong" aria-hidden="true" />}
        </li>
      );
    })}
  </ol>
);

const Tile: React.FC<{ label: string; value: number; tone?: "good" | "warn" | "bad" | "plain" }> = ({ label, value, tone = "plain" }) => {
  const ring = { good: "border-l-emerald-600", warn: "border-l-brand", bad: "border-l-red-600", plain: "border-l-warm-strong" }[tone];
  return (
    <div className={`warm-card p-3 border-l-4 ${ring}`}>
      <div className="font-heading text-2xl font-bold text-body tabular-nums">{n(value)}</div>
      <div className="text-xs text-muted">{label}</div>
    </div>
  );
};

const ResultPanel: React.FC<{ r: ImportResult; onDownload: () => void }> = ({ r, onDownload }) => (
  <div className="flex flex-col gap-3">
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <Tile label={r.saved ? "New records added" : "New records"} value={r.inserted} tone="good" />
      <Tile label={r.saved ? "Records updated" : "Would change"} value={r.updated} tone="warn" />
      <Tile label="Already up to date" value={r.unchanged} />
      <Tile label="Rejected rows" value={r.rejected} tone={r.rejected ? "bad" : "plain"} />
    </div>
    {r.no_promoter > 0 && (
      <p className="text-xs text-muted">{n(r.no_promoter)} project rows have no promoter name; they are listed under “Promoter not in imported records”.</p>
    )}
    {r.errors.length > 0 && (
      <div className="warm-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-sm font-semibold text-body">Why rows were rejected</h4>
          {r.saved && (
            <button type="button" onClick={onDownload} className="text-xs px-3 py-1.5 rounded-full border border-warm-border text-body hover:border-brand">
              Download rejected rows (CSV) to fix and load again
            </button>
          )}
        </div>
        <table className="mt-2 w-full text-xs">
          <thead><tr className="text-muted text-left"><th className="py-1 font-medium w-16">Row</th><th className="py-1 font-medium">Reason</th></tr></thead>
          <tbody>
            {r.errors.slice(0, 25).map((e) => (
              <tr key={e.row} className="border-t border-warm-border align-top"><td className="py-1 tabular-nums text-body">{e.row}</td><td className="py-1 text-body break-words">{e.error}</td></tr>
            ))}
          </tbody>
        </table>
        {(r.errors.length > 25 || r.errors_truncated) && (
          <p className="mt-1 text-[11px] text-muted">Showing 25 of {n(r.rejected)}. {r.saved ? "The CSV has them all." : "Load to get the full list as a CSV."}</p>
        )}
      </div>
    )}
  </div>
);

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
        <p className="text-sm text-muted">Loading data is for state-level GUJRERA officers (the data admins). District officers see their district's data in the work queue.</p>
        {!user && <LoginPrompt k="loginNeededOfficer" />}
      </div>
    );
  }

  const step = loaded ? 4 : check ? 3 : up ? 1 : 0;
  const spec = sheet ? sheet.kinds[kind] : null;
  const missing = spec ? spec.fields.filter((f) => f.required && !mapping[f.key]).map((f) => f.label) : [];
  const estimate = sheet ? Math.max(2, Math.round(sheet.rows / 500)) : 0;

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <section className="hero-band p-6">
        <p className="text-xs font-semibold uppercase tracking-wider text-accent-amber-strong">{t3(UI.eyebrow, lang)}</p>
        <h2 className="mt-1 font-heading text-2xl font-bold text-body">{t3(UI.title, lang)}</h2>
        <p className="mt-1 text-sm text-muted max-w-3xl">{t3(UI.lead, lang)}</p>
        <div className="mt-4"><Stepper step={step} /></div>
      </section>

      {hist && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Tile label="Projects in the registry" value={hist.registry.projects} />
          <Tile label="Agents in the registry" value={hist.registry.agents} />
          <Tile label="Projects with a site address" value={hist.registry.with_address} />
          <Tile label="Projects with a locality (area)" value={hist.registry.with_locality} />
        </div>
      )}

      {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 dark:bg-red-950/40 dark:text-red-200 dark:border-red-900 p-3 text-sm">{error}</div>}

      {/* 1. Upload */}
      <section className="warm-card p-5">
        <h3 className="font-heading text-sm font-bold text-body">1. Upload a data file</h3>
        <label
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); void onFile(e.dataTransfer.files[0]); }}
          className={`mt-3 flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center cursor-pointer transition-colors ${drag ? "border-brand bg-brand-soft" : "border-warm-strong bg-subtle/60 hover:border-brand"}`}>
          <span className="w-10 h-10 rounded-lg bg-brand-soft text-brand-strong flex items-center justify-center"><Icon name="doc" /></span>
          <span className="text-sm font-semibold text-body">{busy === "upload" ? "Reading the file…" : "Drop a file here, or click to choose"}</span>
          <span className="text-xs text-muted">.csv, .xlsx or .json, up to 25 MB. Only the columns you match are read; others (phone numbers, e-mails) are ignored.</span>
          <input type="file" accept=".csv,.xlsx,.xlsm,.json" className="sr-only" disabled={busy !== ""} onChange={(e) => void onFile(e.target.files?.[0])} />
        </label>
        {up && (
          <p className="mt-2 text-xs text-muted">
            <b className="text-body">{up.run.filename}</b> · {n(up.run.rows)} rows · {(up.run.size_bytes / 1024).toFixed(0)} KB
          </p>
        )}
      </section>

      {/* 2. Match columns */}
      {up && sheet && spec && (
        <section className="warm-card p-5 flex flex-col gap-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <h3 className="font-heading text-sm font-bold text-body">2. What is in this file, and which column is which</h3>
            {up.sheets.length > 1 && (
              <select value={sheet.name} onChange={(e) => choose(up, e.target.value)} aria-label="Sheet"
                className="rounded-lg border border-warm-border bg-card text-body text-xs px-2 py-1.5">
                {up.sheets.map((s) => <option key={s.name} value={s.name}>{s.name} ({n(s.rows)} rows)</option>)}
              </select>
            )}
          </div>
          <div className="grid gap-2 md:grid-cols-3" role="radiogroup" aria-label="Kind of records">
            {(Object.keys(sheet.kinds) as ImportKind[]).map((k) => (
              <button key={k} type="button" role="radio" aria-checked={kind === k}
                onClick={() => { setKind(k); setMapping({ ...sheet.kinds[k].mapping }); setCheck(null); setLoaded(null); }}
                className={`text-left rounded-xl border p-3 text-xs transition ${kind === k ? "border-brand bg-brand-soft ring-1 ring-brand" : "border-warm-border bg-card hover:border-warm-strong"}`}>
                <span className="block font-semibold text-body text-sm">{sheet.kinds[k].label}</span>
                {sheet.suggested_kind === k && <span className="mt-1 inline-block rounded-full bg-card border border-accent-border px-2 py-0.5 text-[10px] font-semibold text-accent-amber-strong">Suggested for this file</span>}
              </button>
            ))}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[560px]">
              <thead>
                <tr className="text-muted text-left border-b border-warm-border">
                  <th className="py-2 font-medium">Registry field</th>
                  <th className="py-2 font-medium">Column in the file</th>
                  <th className="py-2 font-medium">First row</th>
                </tr>
              </thead>
              <tbody>
                {spec.fields.map((f) => {
                  const col = mapping[f.key] ?? "";
                  return (
                    <tr key={f.key} className="border-b border-warm-border last:border-0">
                      <td className="py-1.5 pr-3 text-body">
                        {f.label}{f.required && <span className="ml-1 text-red-700 dark:text-red-300" title="Required">*</span>}
                        {f.hint && <span className="block text-[10px] text-muted">{f.hint}</span>}
                      </td>
                      <td className="py-1.5 pr-3">
                        <select value={col} aria-label={`Column for ${f.label}`}
                          onChange={(e) => { setMapping((m) => ({ ...m, [f.key]: e.target.value })); setCheck(null); setLoaded(null); }}
                          className={`w-full max-w-[240px] rounded-md border bg-card text-body px-2 py-1 ${col ? "border-warm-border" : f.required ? "border-red-400" : "border-warm-border text-muted"}`}>
                          <option value="">— not in this file —</option>
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
            <p className="text-xs text-muted">Not read: {spec.unused.filter((h) => !Object.values(mapping).includes(h)).map((h) => (
              <span key={h} className="inline-block mr-1 mb-1 px-2 py-0.5 rounded-full bg-subtle border border-warm-border">{h}</span>
            ))}</p>
          )}
          {kind !== "project_update" && (
            <label className="text-xs text-muted flex flex-col gap-1 max-w-xl">
              Source link cited in answers for rows without their own link
              <input value={source} onChange={(e) => setSource(e.target.value)} className="rounded-md border border-warm-border bg-card text-body px-2 py-1.5" />
            </label>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" disabled={busy !== "" || missing.length > 0} onClick={() => void go("check")}
              className="px-5 py-2.5 rounded-xl bg-primary-bg text-primary-text text-sm font-semibold disabled:opacity-50">
              {busy === "check" ? `Checking ${n(sheet.rows)} rows… about ${estimate} s` : "3. Check every row (saves nothing)"}
            </button>
            {missing.length > 0 && <span className="text-xs text-red-700 dark:text-red-300">Match a column for: {missing.join(", ")}</span>}
          </div>
        </section>
      )}

      {/* 3. Check result and 4. Load */}
      {check && !loaded && up && (
        <section className="warm-card p-5 flex flex-col gap-4">
          <h3 className="font-heading text-sm font-bold text-body">3. Check result: nothing has been saved yet</h3>
          <ResultPanel r={check} onDownload={() => undefined} />
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" disabled={busy !== "" || check.inserted + check.updated === 0} onClick={() => void go("load")}
              className="px-5 py-2.5 rounded-xl bg-brand text-on-brand text-sm font-bold shadow-sm disabled:opacity-50">
              {busy === "load" ? "Loading…" : `4. Load ${n(check.inserted)} new and ${n(check.updated)} changed records`}
            </button>
            <span className="text-xs text-muted">Rejected rows are skipped; every load is recorded with your name.</span>
          </div>
        </section>
      )}
      {loaded && up && token && (
        <section className="warm-card p-5 flex flex-col gap-4 border-l-4 border-l-emerald-600">
          <h3 className="font-heading text-sm font-bold text-body flex items-center gap-2"><Icon name="shield" className="w-4 h-4 text-emerald-700" /> Loaded. The assistants now answer from these records.</h3>
          <ResultPanel r={loaded} onDownload={() => void downloadRejected(token, up.run.id, up.run.filename).catch(fail)} />
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => navigateTo("ask")} className="text-xs px-3 py-1.5 rounded-full bg-primary-bg text-primary-text font-semibold">Ask Saathi about them</button>
            <button type="button" onClick={() => navigateTo("report")} className="text-xs px-3 py-1.5 rounded-full border border-warm-border text-body hover:border-brand">Open a project record</button>
            {loaded.sample_new.length > 0 && <span className="text-xs text-muted self-center">New, for example: {loaded.sample_new.join(", ")}</span>}
          </div>
        </section>
      )}

      {/* History */}
      {hist && (
        <section className="warm-card p-5">
          <h3 className="font-heading text-sm font-bold text-body">Import history</h3>
          {hist.runs.length === 0 ? (
            <p className="mt-2 text-sm text-muted">No files loaded through the console yet.</p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-xs min-w-[760px]">
                <thead>
                  <tr className="text-muted text-left border-b border-warm-border">
                    <th className="py-2 font-medium">File</th><th className="py-2 font-medium">Kind</th>
                    <th className="py-2 font-medium text-right">Rows</th><th className="py-2 font-medium text-right">New</th>
                    <th className="py-2 font-medium text-right">Changed</th><th className="py-2 font-medium text-right">Rejected</th>
                    <th className="py-2 font-medium">Status</th><th className="py-2 font-medium">By, when</th><th className="py-2" />
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
                        {r.status !== "loaded" && <button type="button" onClick={() => void resume(r.id)} className="text-[11px] font-semibold text-brand-strong mr-2">Continue</button>}
                        {r.status === "loaded" && r.rejected > 0 && token && (
                          <button type="button" onClick={() => void downloadRejected(token, r.id, r.filename).catch(fail)} className="text-[11px] font-semibold text-brand-strong">Rejected rows</button>
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
