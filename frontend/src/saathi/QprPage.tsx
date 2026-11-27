import React, { useEffect, useState } from "react";
import { AuthExpiredError, QprDraft, QprInput, QprIssue, QprProject, checkQpr, fetchQprDraft, fetchQprOverview, submitQpr } from "../api/gujrera";
import { Icon } from "./Brand";
import { say, uiLocale, useSaathi } from "./context";
import { En } from "./En";
import { LoginPrompt } from "./RolePages";
import { tr } from "./strings";

const fmt = (iso: string) => new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString(uiLocale(), { day: "numeric", month: "short", year: "numeric" });
const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(/[,\s₹]/g, "")));
const inputCls = "w-full rounded-lg border border-warm-border bg-card text-body px-3 py-2 text-sm focus:outline-none focus:border-brand focus:ring-2 focus:ring-brand/30";

const Field: React.FC<{ label: string; hint?: string; children: React.ReactNode }> = ({ label, hint, children }) => (
  <label className="block text-xs font-semibold text-body">
    {label}
    {hint && <span className="block font-normal text-muted">{hint}</span>}
    <div className="mt-1">{children}</div>
  </label>
);

const Form: React.FC<{ d: QprDraft; onFiled: () => void }> = ({ d, onFiled }) => {
  const { token, lang } = useSaathi();
  const pf = d.prefill;
  const s = (v: number | null) => (v == null ? "" : String(v));
  const [pct, setPct] = useState(s(pf.percent_complete));
  const [units, setUnits] = useState(s(pf.units_booked));
  const [garages, setGarages] = useState(s(pf.garages_booked));
  const [collected, setCollected] = useState(s(pf.collected_total));
  const [deposited, setDeposited] = useState(s(pf.deposited_total));
  const [withdrawn, setWithdrawn] = useState(s(pf.withdrawn_total));
  const [cost, setCost] = useState(s(pf.project_cost));
  const [pending, setPending] = useState<string[]>(pf.approvals.filter((a) => a.status !== "granted").map((a) => a.kind));
  const [note, setNote] = useState("");
  const [issues, setIssues] = useState<QprIssue[] | null>(null);
  const [receipt, setReceipt] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const data = (): QprInput => ({
    percent_complete: num(pct), units_booked: num(units), garages_booked: num(garages), collected_total: num(collected),
    deposited_total: num(deposited), withdrawn_total: num(withdrawn), project_cost: num(cost), approvals_pending: pending,
    status_note: note || null,
  });
  const run = async (file: boolean) => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      if (file) {
        const r = await submitQpr(token, d.project.id, d.quarter, data());
        setIssues(r.issues);
        if (r.filed) { setReceipt(r.receipt ?? null); onFiled(); }
      } else {
        setIssues((await checkQpr(token, d.project.id, d.quarter, data())).issues);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const errors = (issues ?? []).filter((i) => i.level === "error");

  if (receipt) {
    return (
      <div className="p-6 flex flex-col items-start gap-3">
        <span className="w-10 h-10 rounded-lg bg-brand-soft text-brand-strong flex items-center justify-center"><Icon name="doc" /></span>
        <div className="text-sm text-body">{say({ en: "Report for", gu: "અહેવાલ", hi: "रिपोर्ट" }, lang)} <b>{d.quarter}</b> {say({ en: "filed. Receipt", gu: "ભર્યો. રસીદ", hi: "दाखिल। रसीद" }, lang)} <span className="font-mono">{receipt}</span></div>
        {(issues ?? []).length > 0 && <ul className="text-xs text-muted list-disc pl-5">{issues!.map((i) => <li key={i.code}>{i.text}</li>)}</ul>}
      </div>
    );
  }
  return (
    <div className="p-5 flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-heading font-bold text-body">{d.project.name} · {d.quarter}</h3>
          <div className="text-xs text-muted">{say({ en: "Due", gu: "બાકી તારીખ", hi: "देय तिथि" }, lang)} {fmt(d.due_on)}{d.late ? say({ en: " · late", gu: " · મોડો", hi: " · देर से" }, lang) : ""} · {say({ en: "last report", gu: "છેલ્લો અહેવાલ", hi: "पिछली रिपोर्ट" }, lang)} {d.previous ? `${d.previous.percent}% (${d.previous.quarter})` : say({ en: "none", gu: "કોઈ નહીં", hi: "कोई नहीं" }, lang)}</div>
        </div>
        <span className="text-[11px] text-muted">{say({ en: "Section 11(1) · Section 4(2)(l)(D)", gu: "કલમ 11(1) · કલમ 4(2)(l)(D)", hi: "धारा 11(1) · धारा 4(2)(l)(D)" }, lang)}</span>
      </div>

      <fieldset className="grid sm:grid-cols-3 gap-3">
        <Field label={say({ en: "Completion %", gu: "પૂર્ણતા %", hi: "पूर्णता %" }, lang)} hint={d.previous ? say({ en: `was ${d.previous.percent}%`, gu: `પહેલાં ${d.previous.percent}%`, hi: `पहले ${d.previous.percent}%` }, lang) : undefined}>
          <input inputMode="decimal" value={pct} onChange={(e) => setPct(e.target.value)} className={inputCls} />
        </Field>
        <Field label={say({ en: "Units booked", gu: "બુક થયેલા એકમ", hi: "बुक की गई इकाइयाँ" }, lang)} hint={say({ en: `of ${d.project.units} (11(1)(b))`, gu: `${d.project.units} માંથી (11(1)(b))`, hi: `${d.project.units} में से (11(1)(b))` }, lang)}>
          <input inputMode="numeric" value={units} onChange={(e) => setUnits(e.target.value)} className={inputCls} />
        </Field>
        <Field label={say({ en: "Garages booked", gu: "બુક થયેલા ગેરેજ", hi: "बुक किए गए गैराज" }, lang)} hint="11(1)(c)">
          <input inputMode="numeric" value={garages} onChange={(e) => setGarages(e.target.value)} className={inputCls} />
        </Field>
      </fieldset>

      <fieldset>
        <legend className="text-xs font-semibold text-body mb-1">{say({ en: "Approvals still pending", gu: "હજી બાકી મંજૂરીઓ", hi: "अभी लंबित अनुमोदन" }, lang)} <span className="font-normal text-muted">(11(1)(d))</span></legend>
        <div className="flex flex-wrap gap-2">
          {d.prefill.approvals.map((a) => (
            <label key={a.id} className="inline-flex items-center gap-1.5 text-xs rounded-full border border-warm-border px-2.5 py-1">
              <input type="checkbox" checked={pending.includes(a.kind)} className="accent-[var(--brand)]"
                onChange={(e) => setPending((p) => (e.target.checked ? [...p, a.kind] : p.filter((x) => x !== a.kind)))} />
              {a.kind} · {a.authority}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="grid sm:grid-cols-2 gap-3">
        <legend className="col-span-full text-xs font-semibold text-body">{say({ en: "Project account to date (₹)", gu: "આજ સુધીનું પ્રોજેક્ટ ખાતું (₹)", hi: "आज तक का प्रोजेक्ट खाता (₹)" }, lang)} <span className="font-normal text-muted">· {say({ en: "Section 4(2)(l)(D)", gu: "કલમ 4(2)(l)(D)", hi: "धारा 4(2)(l)(D)" }, lang)}</span></legend>
        <Field label={say({ en: "Collected from buyers", gu: "ખરીદદારો પાસેથી મળેલ", hi: "ख़रीदारों से प्राप्त" }, lang)}><input inputMode="numeric" value={collected} onChange={(e) => setCollected(e.target.value)} className={inputCls} /></Field>
        <Field label={say({ en: "Deposited in the separate account", gu: "અલગ ખાતામાં જમા", hi: "अलग खाते में जमा" }, lang)} hint={say({ en: "at least 70% of collections", gu: "મળેલી રકમના ઓછામાં ઓછા 70%", hi: "प्राप्त राशि का कम से कम 70%" }, lang)}><input inputMode="numeric" value={deposited} onChange={(e) => setDeposited(e.target.value)} className={inputCls} /></Field>
        <Field label={say({ en: "Withdrawn from it", gu: "તેમાંથી ઉપાડેલ", hi: "उसमें से निकाला गया" }, lang)} hint={say({ en: "in proportion to completion, certified", gu: "પૂર્ણતાના પ્રમાણમાં, પ્રમાણિત", hi: "पूर्णता के अनुपात में, प्रमाणित" }, lang)}><input inputMode="numeric" value={withdrawn} onChange={(e) => setWithdrawn(e.target.value)} className={inputCls} /></Field>
        <Field label={say({ en: "Estimated project cost", gu: "અંદાજિત પ્રોજેક્ટ ખર્ચ", hi: "अनुमानित प्रोजेक्ट लागत" }, lang)}><input inputMode="numeric" value={cost} onChange={(e) => setCost(e.target.value)} className={inputCls} /></Field>
      </fieldset>

      <Field label={say({ en: "Status of the project", gu: "પ્રોજેક્ટની સ્થિતિ", hi: "प्रोजेक्ट की स्थिति" }, lang)} hint={say({ en: "11(1)(e): short note, e.g. slab work on floors 6-8", gu: "11(1)(e): ટૂંકી નોંધ, દા.ત. માળ 6-8 પર સ્લેબનું કામ", hi: "11(1)(e): छोटा नोट, जैसे मंज़िल 6-8 पर स्लैब का काम" }, lang)}>
        <input value={note} onChange={(e) => setNote(e.target.value)} className={inputCls} />
      </Field>

      {issues && (
        <ul className="flex flex-col gap-1.5" aria-live="polite">
          {issues.length === 0 && <li className="text-sm text-emerald-700 dark:text-emerald-300">{say({ en: "No problems found.", gu: "કોઈ સમસ્યા મળી નથી.", hi: "कोई समस्या नहीं मिली।" }, lang)}</li>}
          {issues.map((i) => (
            <li key={i.code} className={`text-sm rounded-md px-3 py-2 border ${i.level === "error"
              ? "bg-red-50 text-red-900 border-red-200 dark:bg-red-950/40 dark:text-red-200 dark:border-red-900"
              : "bg-accent-surface text-accent-amber-strong border-accent-border"}`}>
              <b className="uppercase text-[10px] tracking-wide mr-1">{i.level === "error" ? say({ en: "error", gu: "ભૂલ", hi: "त्रुटि" }, lang) : i.level === "warning" ? say({ en: "warning", gu: "ચેતવણી", hi: "चेतावनी" }, lang) : i.level}</b>{i.text}
            </li>
          ))}
        </ul>
      )}
      {error && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>}
      <div className="flex gap-2">
        <button type="button" disabled={busy} onClick={() => void run(false)} className="px-4 py-2 rounded-lg border border-warm-strong text-sm font-semibold text-body leading-tight">
          {tr("qprCheck", lang)}<En k="qprCheck" className="font-normal" />
        </button>
        <button type="button" disabled={busy || issues === null || errors.length > 0} onClick={() => void run(true)}
          className="px-4 py-2 rounded-lg bg-primary-bg text-primary-text text-sm font-semibold leading-tight disabled:opacity-40">
          {tr("qprFile", lang)}<En k="qprFile" className="font-normal" />
        </button>
      </div>
      <p className="text-[11px] text-muted">{say({ en: "Check first; filing is enabled when there are no errors. Warnings are filed with the report.", gu: "પહેલાં તપાસો; કોઈ ભૂલ ન હોય ત્યારે જ અહેવાલ ભરી શકાય છે. ચેતવણીઓ અહેવાલ સાથે ભરાય છે.", hi: "पहले जाँचें; कोई त्रुटि न होने पर ही रिपोर्ट दाखिल की जा सकती है। चेतावनियाँ रिपोर्ट के साथ दाखिल होती हैं।" }, lang)}</p>
    </div>
  );
};

export const QprPage: React.FC = () => {
  const { user, token, lang, logout } = useSaathi();
  const allowed = user?.role === "developer";
  const [projects, setProjects] = useState<QprProject[] | null>(null);
  const [sel, setSel] = useState<{ pid: number; q: string } | null>(null);
  const [draft, setDraft] = useState<QprDraft | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    if (!allowed || !token) return;
    fetchQprOverview(token).then((o) => {
      setProjects(o.projects);
      const first = o.projects.find((p) => p.to_file.length);
      setSel((s) => s ?? (first ? { pid: first.project_id, q: first.to_file[0] } : null));
    }).catch((e) => { if (e instanceof AuthExpiredError) logout(); setError((e as Error).message); });
  };
  useEffect(load, [allowed, token]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!sel || !token) return;
    setDraft(null);
    fetchQprDraft(token, sel.pid, sel.q).then(setDraft).catch((e) => setError((e as Error).message));
  }, [sel, token]);

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <div className="max-w-3xl">
        <p className="text-sm text-muted leading-relaxed">{tr("qprIntro", lang)}</p>
        {lang !== "en" && <p lang="en" className="text-xs text-muted opacity-80 mt-0.5">{tr("qprIntro", "en")}</p>}
      </div>
      {!allowed && <LoginPrompt k="loginNeededQpr" />}
      {allowed && error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 p-4 text-sm">{error}</div>}
      {allowed && projects && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] items-start">
          <ul className="flex flex-col gap-3">
            {projects.map((p) => (
              <li key={p.project_id} className="rounded-xl border border-warm-border bg-card p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold text-body">{lang === "gu" && p.name_gu ? p.name_gu : p.name}</div>
                    <div className="text-[11px] text-muted">{p.district} · {say({ en: "last filed", gu: "છેલ્લો ભર્યો", hi: "पिछली दाखिल" }, lang)} {p.last_filed ? `${p.last_filed.percent}% (${p.last_filed.quarter})` : "—"}</div>
                  </div>
                  {p.overdue.length > 0
                    ? <span className="rounded-full border px-2 py-0.5 text-[11px] font-semibold bg-red-50 text-red-800 border-red-200 dark:bg-red-950/50 dark:text-red-200 dark:border-red-900">{p.overdue.length} {say({ en: "overdue", gu: "મુદત વીતી", hi: "समय सीमा पार" }, lang)}</span>
                    : <span className="rounded-full border px-2 py-0.5 text-[11px] font-semibold bg-subtle text-muted border-warm-border">{say({ en: "up to date", gu: "અદ્યતન", hi: "अद्यतन" }, lang)}</span>}
                </div>
                {p.to_file.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {p.to_file.map((q) => (
                      <button key={q} type="button" onClick={() => setSel({ pid: p.project_id, q })}
                        className={`text-[11px] font-mono rounded border px-2 py-0.5 ${sel?.pid === p.project_id && sel.q === q ? "border-brand bg-brand-soft text-body" : "border-warm-border hover:border-warm-strong"}`}>
                        {q}
                      </button>
                    ))}
                  </div>
                )}
                <div className="mt-2 text-[11px] text-muted">
                  {say({ en: "Next:", gu: "આગળનો:", hi: "अगली:" }, lang)} {p.next_due.quarter} {say({ en: "due", gu: "બાકી તારીખ", hi: "देय तिथि" }, lang)} {fmt(p.next_due.due_on)}
                  {p.penalties_pending.length > 0 && say({
                    en: ` · ${p.penalties_pending.length} late-filing penalty notice(s) unpaid`,
                    gu: ` · મોડો અહેવાલ ભરવા બદલ ${p.penalties_pending.length} દંડ નોટિસ ચૂકવવાની બાકી`,
                    hi: ` · देर से दाखिल करने की ${p.penalties_pending.length} जुर्माना सूचना(एँ) अदत्त`,
                  }, lang)}
                </div>
              </li>
            ))}
            {projects.length === 0 && <li className="text-sm text-muted">{say({ en: "No ongoing projects.", gu: "કોઈ ચાલુ પ્રોજેક્ટ નથી.", hi: "कोई चालू प्रोजेक्ट नहीं।" }, lang)}</li>}
          </ul>
          <div className="rounded-xl border border-warm-border bg-card lg:sticky lg:top-20">
            {draft ? <Form key={`${draft.project.id}-${draft.quarter}`} d={draft} onFiled={load} />
              : <div className="p-6 text-sm text-muted">{sel ? "…" : say({ en: "All reports are filed. The next one opens when the quarter ends.", gu: "બધા અહેવાલ ભર્યા છે. ત્રિમાસિક પૂરું થાય ત્યારે આગળનો અહેવાલ ખુલશે.", hi: "सभी रिपोर्ट दाखिल हैं। तिमाही समाप्त होने पर अगली रिपोर्ट खुलेगी।" }, lang)}</div>}
          </div>
        </div>
      )}
    </div>
  );
};
