import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ComplaintDoc,
  ComplaintView,
  addComplaintDocument,
  fetchMyComplaints,
  lookupComplaint,
  navigateTo,
  openComplaintDocument,
  takeComplaintPrefill,
} from "../api/gujrera";
import type { Lang } from "../api/gujrera";
import { Icon } from "./Brand";
import { useSaathi } from "./context";

type Text = Record<Lang, string>;
const T: Record<string, Text> = {
  title: { en: "My complaint", gu: "મારી ફરિયાદ", hi: "मेरी शिकायत" },
  intro: {
    en: "See where your complaint stands, when the hearing is, and add your documents: the agreement, payment receipts, letters from the builder or photos.",
    gu: "તમારી ફરિયાદ ક્યાં પહોંચી, સુનાવણી ક્યારે છે તે જુઓ અને દસ્તાવેજ ઉમેરો: કરાર, ચુકવણીની રસીદો, બિલ્ડરના પત્રો કે ફોટા.",
    hi: "देखें आपकी शिकायत कहाँ पहुँची, सुनवाई कब है, और दस्तावेज़ जोड़ें: अनुबंध, भुगतान रसीदें, बिल्डर के पत्र या फ़ोटो।",
  },
  mine: { en: "Complaints you filed", gu: "તમે નોંધાવેલી ફરિયાદો", hi: "आपकी दर्ज शिकायतें" },
  open: { en: "Open a complaint", gu: "ફરિયાદ ખોલો", hi: "शिकायत खोलें" },
  openHint: {
    en: "Enter the reference number and the 6-digit tracking code you were given when you filed.",
    gu: "ફરિયાદ નોંધાવતી વખતે મળેલો સંદર્ભ નંબર અને 6 અંકનો ટ્રેકિંગ કોડ લખો.",
    hi: "शिकायत दर्ज करते समय मिला संदर्भ नंबर और 6 अंकों का ट्रैकिंग कोड लिखें।",
  },
  ref: { en: "Reference number", gu: "સંદર્ભ નંબર", hi: "संदर्भ नंबर" },
  code: { en: "Tracking code", gu: "ટ્રેકિંગ કોડ", hi: "ट्रैकिंग कोड" },
  show: { en: "Show", gu: "બતાવો", hi: "दिखाएँ" },
  filed: { en: "Filed", gu: "નોંધાઈ", hi: "दर्ज" },
  form: { en: "Form", gu: "ફોર્મ", hi: "फॉर्म" },
  status: { en: "Status", gu: "સ્થિતિ", hi: "स्थिति" },
  hearing: { en: "Hearing", gu: "સુનાવણી", hi: "सुनवाई" },
  noHearing: { en: "No hearing date has been fixed yet.", gu: "હજુ સુનાવણીની તારીખ નક્કી થઈ નથી.", hi: "अभी सुनवाई की तारीख तय नहीं हुई है।" },
  timeline: { en: "What has happened", gu: "અત્યાર સુધી શું થયું", hi: "अब तक क्या हुआ" },
  documents: { en: "Documents", gu: "દસ્તાવેજ", hi: "दस्तावेज़" },
  noDocs: { en: "No documents yet.", gu: "હજુ કોઈ દસ્તાવેજ નથી.", hi: "अभी कोई दस्तावेज़ नहीं।" },
  you: { en: "You", gu: "તમે", hi: "आप" },
  gujrera: { en: "GUJRERA", gu: "GUJRERA", hi: "GUJRERA" },
  add: { en: "Add a document", gu: "દસ્તાવેજ ઉમેરો", hi: "दस्तावेज़ जोड़ें" },
  addHint: {
    en: "PDF, JPG or PNG, up to 10 MB each, at most 10 per complaint.",
    gu: "PDF, JPG કે PNG, દરેક 10 MB સુધી, એક ફરિયાદમાં વધુમાં વધુ 10.",
    hi: "PDF, JPG या PNG, हर एक 10 MB तक, एक शिकायत में अधिकतम 10।",
  },
  note: { en: "What is it? (optional)", gu: "આ શું છે? (વૈકલ્પિક)", hi: "यह क्या है? (वैकल्पिक)" },
  choose: { en: "Choose file and add", gu: "ફાઇલ પસંદ કરી ઉમેરો", hi: "फ़ाइल चुनें और जोड़ें" },
  added: { en: "Added", gu: "ઉમેર્યું", hi: "जोड़ा गया" },
  closed: { en: "This complaint is closed, so documents can no longer be added.", gu: "આ ફરિયાદ બંધ છે, તેથી હવે દસ્તાવેજ ઉમેરી શકાય નહીં.", hi: "यह शिकायत बंद है, इसलिए अब दस्तावेज़ नहीं जोड़े जा सकते।" },
  file: { en: "File a complaint", gu: "ફરિયાદ નોંધાવો", hi: "शिकायत दर्ज करें" },
  demo: { en: "Demo complaint: not sent to GUJRERA.", gu: "ડેમો ફરિયાદ: GUJRERA ને મોકલાઈ નથી.", hi: "डेमो शिकायत: GUJRERA को नहीं भेजी गई।" },
};
const kb = (n: number) => (n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`);

const ComplaintCard: React.FC<{ c: ComplaintView; code: string | null; onChanged: () => void }> = ({ c, code, onChanged }) => {
  const { lang, token } = useSaathi();
  const t = (k: string) => T[k][lang];
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const h = c.hearing;

  const upload = async (file: File) => {
    setBusy(true); setMsg(null);
    try {
      const d = await addComplaintDocument(token, c.ref_no, code, file, note.trim() || undefined);
      setMsg({ ok: true, text: `${t("added")}: ${d.filename}` });
      setNote("");
      onChanged();
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }); } finally { setBusy(false); }
  };
  const open = (d: ComplaintDoc) => { openComplaintDocument(token, c.ref_no, code, d).catch((e) => setMsg({ ok: false, text: (e as Error).message })); };

  return (
    <article className="warm-card p-5 flex flex-col gap-4" aria-label={c.ref_no}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-mono text-sm font-bold text-body">{c.ref_no}</div>
          <div className="text-sm text-body mt-0.5">{c.project ? c.project.name : ""} <span className="text-muted">· {c.category_label} · {t("form")} {c.form}</span></div>
          <div className="text-xs text-muted mt-0.5">{t("filed")}: {c.filed_text}</div>
        </div>
        <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-brand-soft text-body capitalize">{c.status_label}</span>
      </header>

      <section aria-label={t("hearing")} className={`rounded-xl p-3 text-sm ${h?.upcoming ? "border-2 border-accent-border bg-brand-soft" : "border border-warm-border bg-subtle"}`}>
        <div className="flex items-center gap-2 font-semibold text-body"><Icon name="calendar" className="w-4 h-4" /> {t("hearing")}</div>
        <p className="mt-1 text-body">{h ? h.text : t("noHearing")}</p>
      </section>

      <section aria-label={t("timeline")}>
        <h4 className="text-xs font-semibold text-muted uppercase tracking-wide">{t("timeline")}</h4>
        <ol className="mt-2 relative border-l border-warm-border ml-1.5 flex flex-col gap-2">
          {c.events.map((e, i) => (
            <li key={i} className="ml-3 text-xs">
              <span className={`absolute -left-[5px] mt-1 w-2.5 h-2.5 rounded-full ${i === c.events.length - 1 ? "bg-accent-amber" : "bg-muted/50"}`} />
              <div className="font-semibold text-body capitalize">{e.status_label}</div>
              <div className="text-muted">{e.at}{e.note ? ` · ${e.note}` : ""}</div>
            </li>
          ))}
        </ol>
      </section>

      <section aria-label={t("documents")}>
        <h4 className="text-xs font-semibold text-muted uppercase tracking-wide">{t("documents")} ({c.documents.length})</h4>
        {c.documents.length === 0 ? <p className="mt-1 text-xs text-muted">{t("noDocs")}</p> : (
          <ul className="mt-2 divide-y divide-warm-border">
            {c.documents.map((d) => (
              <li key={d.id} className="py-2 flex flex-wrap items-center gap-2 text-xs">
                <Icon name="doc" className="w-4 h-4 text-muted" />
                <button type="button" onClick={() => open(d)} className="font-semibold text-body underline decoration-dotted underline-offset-2 hover:text-brand-strong break-all text-left">{d.filename}</button>
                <span className="text-muted">{kb(d.size)} · {d.added_by === "officer" ? t("gujrera") : t("you")} · {d.added_at.replace("T", " ")}</span>
                {d.note && <span className="w-full text-muted">{d.note}</span>}
              </li>
            ))}
          </ul>
        )}
        {c.can_add_documents ? (
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <label className="text-[11px] text-muted flex flex-col gap-1">{t("note")}
              <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={200}
                className="rounded-md border border-warm-border bg-card text-body text-xs px-2 py-1.5 w-60" />
            </label>
            <label className={`text-xs px-3 py-2 rounded-lg bg-brand text-on-brand font-bold cursor-pointer ${busy ? "opacity-50 pointer-events-none" : ""}`}>
              {t("choose")}
              <input type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" className="sr-only"
                onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(f); }} />
            </label>
            <span className="w-full text-[11px] text-muted">{t("addHint")}</span>
          </div>
        ) : c.status !== "filed" && <p className="mt-2 text-xs text-muted">{c.documents.length >= 10 ? T.addHint[lang] : t("closed")}</p>}
        {msg && <p role={msg.ok ? "status" : "alert"} className={`mt-2 text-xs ${msg.ok ? "text-emerald-700 dark:text-emerald-300" : "text-red-700 dark:text-red-300"}`}>{msg.text}</p>}
      </section>
      {c.is_mock && <p className="text-[11px] text-muted">{t("demo")}</p>}
    </article>
  );
};

export const MyComplaintPage: React.FC = () => {
  const { lang, token, user } = useSaathi();
  const t = (k: string) => T[k][lang];
  const buyer = user?.role === "citizen" && !!token;
  const [mine, setMine] = useState<ComplaintView[] | null>(null);
  const [ref, setRef] = useState("");
  const [code, setCode] = useState("");
  const [opened, setOpened] = useState<{ view: ComplaintView; code: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadMine = useCallback(() => {
    if (buyer) fetchMyComplaints(token!, lang).then((d) => setMine(d.complaints)).catch((e) => setError((e as Error).message));
  }, [buyer, token, lang]);
  useEffect(() => { loadMine(); }, [loadMine]);

  const show = useCallback(async (r: string, c: string | null) => {
    setBusy(true); setError(null);
    try { setOpened({ view: await lookupComplaint(token, r.trim(), c, lang), code: c }); }
    catch (e) { setOpened(null); setError((e as Error).message); } finally { setBusy(false); }
  }, [token, lang]);

  useEffect(() => {  // opened from the chat, just after filing
    const p = takeComplaintPrefill();
    if (p) { setRef(p.ref); setCode(p.code ?? ""); void show(p.ref, p.code); }
  }, [show]);
  const refresh = () => { if (opened) void show(opened.view.ref_no, opened.code); loadMine(); };
  const openedRef = useRef(opened);
  openedRef.current = opened;
  useEffect(() => {  // a new language: show the open complaint again in it
    const o = openedRef.current;
    if (o) void show(o.view.ref_no, o.code);
  }, [show]);

  return (
    <div className="max-w-4xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-5">
      <section className="hero-band p-6">
        <h2 className="font-heading text-2xl font-bold text-body">{t("title")}</h2>
        <p className="mt-1 text-sm text-muted max-w-2xl">{t("intro")}</p>
      </section>

      <form aria-label={t("open")} className="warm-card p-5 flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); void show(ref, code.trim() || null); }}>
        <h3 className="font-heading text-sm font-bold text-body">{t("open")}</h3>
        <p className="text-xs text-muted">{t("openHint")}</p>
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-[11px] text-muted flex flex-col gap-1">{t("ref")}
            <input value={ref} onChange={(e) => setRef(e.target.value)} placeholder="MOCK-CMP-2026-00001" required maxLength={40} aria-label={t("ref")}
              className="rounded-md border border-warm-border bg-card text-body text-sm px-2.5 py-1.5 w-60 font-mono" />
          </label>
          <label className="text-[11px] text-muted flex flex-col gap-1">{t("code")}
            <input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" autoComplete="off" aria-label={t("code")}
              placeholder="••••••" className="rounded-md border border-warm-border bg-card text-body text-sm px-2.5 py-1.5 w-32 font-mono tracking-widest" />
          </label>
          <button type="submit" disabled={busy || !ref.trim()} className="px-4 py-2 rounded-lg bg-brand text-on-brand text-sm font-bold disabled:opacity-50">{t("show")}</button>
          <button type="button" onClick={() => navigateTo("ask")} className="ml-auto text-xs px-3 py-2 rounded-lg border border-warm-border text-body">{t("file")}</button>
        </div>
        {error && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>}
      </form>

      {opened && <ComplaintCard c={opened.view} code={opened.code} onChanged={refresh} />}

      {buyer && mine && mine.length > 0 && (
        <section className="flex flex-col gap-3">
          <h3 className="font-heading text-sm font-bold text-body">{t("mine")}</h3>
          {mine.filter((c) => c.ref_no !== opened?.view.ref_no).map((c) => <ComplaintCard key={c.ref_no} c={c} code={null} onChanged={refresh} />)}
        </section>
      )}
    </div>
  );
};
