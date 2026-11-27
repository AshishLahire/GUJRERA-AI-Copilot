import React, { useCallback, useEffect, useState } from "react";
import {
  AuthExpiredError,
  CircularRec,
  circularPdfLink,
  deleteCircular,
  fetchAdminCirculars,
  navigateTo,
  updateCircular,
  uploadCircular,
} from "../api/gujrera";
import { Icon } from "./Brand";
import { Said, say, useSaathi } from "./context";

const LANG_LABEL: Record<string, Said> = {
  gu: { en: "Gujarati", gu: "ગુજરાતી", hi: "गुजराती" },
  en: { en: "English", gu: "અંગ્રેજી", hi: "अंग्रेज़ी" },
  hi: { en: "Hindi", gu: "હિન્દી", hi: "हिंदी" },
  mixed: { en: "Mixed", gu: "મિશ્ર", hi: "मिश्रित" },
};

/** One circular: its details, editable before (and after) publishing. */
const Row: React.FC<{ c: CircularRec; token: string; onChange: () => void; onError: (e: unknown) => void }> = ({ c, token, onChange, onError }) => {
  const { lang } = useSaathi();
  const [number, setNumber] = useState(c.number ?? "");
  const [subject, setSubject] = useState(c.subject ?? "");
  const [date, setDate] = useState(c.issued_on ?? "");
  const [busy, setBusy] = useState(false);
  const dirty = number !== (c.number ?? "") || subject !== (c.subject ?? "") || date !== (c.issued_on ?? "");
  const save = async (status?: "draft" | "published") => {
    setBusy(true);
    try {
      await updateCircular(token, c.id, {
        number, subject, ...(date ? { issued_on: date } : { clear_date: !!c.issued_on }), ...(status ? { status } : {}),
      });
      onChange();
    } catch (e) { onError(e); } finally { setBusy(false); }
  };
  const remove = async () => {
    const name = c.number || c.filename;
    if (!window.confirm(say({
      en: `Delete ${name}? It is removed from search and the PDF is deleted.`,
      gu: `${name} કાઢી નાખવું છે? તે શોધમાંથી દૂર થશે અને PDF કાઢી નખાશે.`,
      hi: `${name} हटाएँ? यह खोज से हट जाएगा और PDF हटा दी जाएगी।`,
    }, lang))) return;
    try { await deleteCircular(token, c.id); onChange(); } catch (e) { onError(e); }
  };
  const published = c.status === "published";
  const langLabel = LANG_LABEL[c.language] ? say(LANG_LABEL[c.language], lang) : c.language;
  return (
    <li className={`warm-card p-4 flex flex-col gap-3 border-l-4 ${published ? "border-l-emerald-600" : "border-l-brand"}`}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className={`px-2 py-0.5 rounded-full border font-semibold ${published ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-900" : "border-accent-border bg-accent-surface text-accent-amber-strong"}`}>
          {published
            ? say({ en: "Published: citizens and officers can ask about it", gu: "પ્રકાશિત: નાગરિકો અને અધિકારીઓ તેના વિશે પૂછી શકે છે", hi: "प्रकाशित: नागरिक और अधिकारी इसके बारे में पूछ सकते हैं" }, lang)
            : say({ en: "Draft: check the details, then publish", gu: "ડ્રાફ્ટ: વિગતો તપાસો, પછી પ્રકાશિત કરો", hi: "ड्राफ़्ट: विवरण जाँचें, फिर प्रकाशित करें" }, lang)}
        </span>
        <span className="text-muted">{c.filename} · {c.pages} {c.pages === 1
          ? say({ en: "page", gu: "પાનું", hi: "पृष्ठ" }, lang)
          : say({ en: "pages", gu: "પાનાં", hi: "पृष्ठ" }, lang)}{c.ocr_pages
          ? ` · ${say({ en: `${c.ocr_pages} read with OCR`, gu: `${c.ocr_pages} OCR થી વાંચ્યાં`, hi: `${c.ocr_pages} OCR से पढ़े गए` }, lang)}`
          : ""} · {langLabel}</span>
        <a href={circularPdfLink(c, token)} target="_blank" rel="noopener noreferrer" className="ml-auto font-semibold text-brand-strong">{say({ en: "Open PDF", gu: "PDF ખોલો", hi: "PDF खोलें" }, lang)}</a>
      </div>
      <div className="grid gap-2 md:grid-cols-[220px_150px_1fr]">
        <label className="text-[11px] text-muted flex flex-col gap-1">{say({ en: "Circular number", gu: "પરિપત્ર નંબર", hi: "परिपत्र संख्या" }, lang)}
          <input value={number} onChange={(e) => setNumber(e.target.value)} placeholder={say({ en: "as printed", gu: "છાપેલ મુજબ", hi: "जैसा छपा है" }, lang)}
            className="rounded-lg border border-warm-border bg-card text-body text-sm px-2.5 py-1.5" />
        </label>
        <label className="text-[11px] text-muted flex flex-col gap-1">{say({ en: "Date", gu: "તારીખ", hi: "तारीख" }, lang)}
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
            className="rounded-lg border border-warm-border bg-card text-body text-sm px-2.5 py-1.5" />
        </label>
        <label className="text-[11px] text-muted flex flex-col gap-1">{say({ en: "Subject", gu: "વિષય", hi: "विषय" }, lang)}
          <input value={subject} onChange={(e) => setSubject(e.target.value)}
            className="rounded-lg border border-warm-border bg-card text-body text-sm px-2.5 py-1.5" />
        </label>
      </div>
      {c.preview && c.preview[0] && (
        <details className="text-xs text-muted">
          <summary className="cursor-pointer">{say({ en: "Text read from page 1", gu: "પાનું 1 માંથી વાંચેલું લખાણ", hi: "पृष्ठ 1 से पढ़ा गया पाठ" }, lang)}</summary>
          <pre className="mt-1 p-2 rounded bg-subtle border border-warm-border whitespace-pre-wrap font-sans text-[11px] text-body max-h-40 overflow-auto">{c.preview[0]}</pre>
        </details>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {!published && (
          <button type="button" disabled={busy || (!number.trim() && !subject.trim())} onClick={() => void save("published")}
            className="px-4 py-1.5 rounded-lg bg-brand text-on-brand text-xs font-bold disabled:opacity-50">{say({ en: "Publish", gu: "પ્રકાશિત કરો", hi: "प्रकाशित करें" }, lang)}</button>
        )}
        {dirty && (
          <button type="button" disabled={busy} onClick={() => void save()}
            className="px-4 py-1.5 rounded-lg bg-primary-bg text-primary-text text-xs font-semibold disabled:opacity-50">{say({ en: "Save details", gu: "વિગતો સાચવો", hi: "विवरण सहेजें" }, lang)}</button>
        )}
        {published && (
          <>
            <button type="button" disabled={busy} onClick={() => void save("draft")}
              className="px-3 py-1.5 rounded-lg border border-warm-border text-body text-xs hover:border-brand">{say({ en: "Unpublish", gu: "પ્રકાશન રદ કરો", hi: "प्रकाशन हटाएँ" }, lang)}</button>
            <button type="button" onClick={() => navigateTo("ask")}
              className="px-3 py-1.5 rounded-lg border border-warm-border text-body text-xs hover:border-brand">{say({ en: "Ask Saathi about it", gu: "તેના વિશે સાથીને પૂછો", hi: "इसके बारे में साथी से पूछें" }, lang)}</button>
          </>
        )}
        <button type="button" onClick={() => void remove()} className="ml-auto text-xs text-red-700 dark:text-red-300">{say({ en: "Delete", gu: "કાઢી નાખો", hi: "हटाएँ" }, lang)}</button>
        <span className="w-full text-[10px] text-muted">{say({
          en: `Uploaded by ${c.uploaded_by ?? "—"} on ${c.uploaded_at.replace("T", " ")}`,
          gu: `${c.uploaded_by ?? "—"} દ્વારા ${c.uploaded_at.replace("T", " ")} ના રોજ અપલોડ`,
          hi: `${c.uploaded_by ?? "—"} द्वारा ${c.uploaded_at.replace("T", " ")} को अपलोड`,
        }, lang)}{c.published_at ? ` · ${say({
          en: `published ${c.published_at.replace("T", " ")}`,
          gu: `પ્રકાશિત ${c.published_at.replace("T", " ")}`,
          hi: `प्रकाशित ${c.published_at.replace("T", " ")}`,
        }, lang)}` : ""}</span>
      </div>
    </li>
  );
};

export const CircularsPage: React.FC = () => {
  const { user, token, lang, logout } = useSaathi();
  const allowed = user?.role === "officer" && !user.district_scope;
  const [list, setList] = useState<CircularRec[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [queue, setQueue] = useState<string[]>([]);
  const [fresh, setFresh] = useState<Record<number, CircularRec>>({});
  const fail = useCallback((e: unknown) => {
    if (e instanceof AuthExpiredError) logout();
    setError((e as Error).message);
  }, [logout]);
  const load = useCallback(() => {
    if (token && allowed) fetchAdminCirculars(token).then((r) => setList(r.circulars)).catch(fail);
  }, [token, allowed, fail]);
  useEffect(load, [load]);

  if (!allowed) return <div className="max-w-3xl mx-auto px-4 py-8 text-sm text-muted">{say({
    en: "Managing circulars is for state-level GUJRERA officers.",
    gu: "પરિપત્રોનું સંચાલન રાજ્ય કક્ષાના GUJRERA અધિકારીઓ માટે છે.",
    hi: "परिपत्रों का प्रबंधन राज्य स्तर के GUJRERA अधिकारियों के लिए है।",
  }, lang)}</div>;

  const onFiles = async (files: FileList | null) => {
    if (!files || !token) return;
    setError(null);
    for (const f of Array.from(files)) {
      setQueue((q) => [...q, f.name]);
      try {
        const r = await uploadCircular(token, f);
        setFresh((x) => ({ ...x, [r.circular.id]: r.circular }));
      } catch (e) { fail(e); } finally { setQueue((q) => q.filter((n) => n !== f.name)); }
    }
    load();
  };
  const drafts = list.filter((c) => c.status === "draft");
  const published = list.filter((c) => c.status === "published");
  const stats: [Said, number][] = [
    [{ en: "Published", gu: "પ્રકાશિત", hi: "प्रकाशित" }, published.length],
    [{ en: "Drafts to check", gu: "તપાસવાના ડ્રાફ્ટ", hi: "जाँचने के लिए ड्राफ़्ट" }, drafts.length],
    [{ en: "Pages read with OCR", gu: "OCR થી વાંચેલાં પાનાં", hi: "OCR से पढ़े गए पृष्ठ" }, list.reduce((a, c) => a + c.ocr_pages, 0)],
  ];

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <section className="hero-band p-6">
        <p className="text-xs font-semibold uppercase tracking-wider text-accent-amber-strong">{say({ en: "Administration", gu: "વહીવટ", hi: "प्रशासन" }, lang)}</p>
        <h2 className="mt-1 font-heading text-2xl font-bold text-body">{say({ en: "Circulars", gu: "પરિપત્રો", hi: "परिपत्र" }, lang)}</h2>
        <p className="mt-1 text-sm text-muted max-w-3xl">
          {say({
            en: "Upload the department's circular PDFs, in Gujarati or English, typed or scanned. The text is read (scanned pages with OCR), the number, date and subject are filled in for you to check, and once published, Ask Saathi answers questions from it, quoting the circular with its number, date and page.",
            gu: "વિભાગના પરિપત્રોની PDF અપલોડ કરો, ગુજરાતી કે અંગ્રેજીમાં, ટાઇપ કરેલી કે સ્કેન કરેલી. લખાણ વંચાય છે (સ્કેન કરેલાં પાનાં OCR થી), નંબર, તારીખ અને વિષય તમારે તપાસવા માટે ભરાઈ જાય છે, અને પ્રકાશિત થયા પછી સાથીને પૂછો તેમાંથી પ્રશ્નોના જવાબ આપે છે, પરિપત્રનો નંબર, તારીખ અને પાનું ટાંકીને.",
            hi: "विभाग के परिपत्रों की PDF अपलोड करें, गुजराती या अंग्रेज़ी में, टाइप की हुई या स्कैन की हुई। पाठ पढ़ा जाता है (स्कैन किए गए पृष्ठ OCR से), संख्या, तारीख और विषय आपके जाँचने के लिए भर दिए जाते हैं, और प्रकाशित होने के बाद साथी से पूछें इससे सवालों के जवाब देता है, परिपत्र की संख्या, तारीख और पृष्ठ बताते हुए।",
          }, lang)}
        </p>
      </section>

      <div className="grid grid-cols-3 gap-3">
        {stats.map(([l, v]) => (
          <div key={l.en} className="warm-card p-3"><div className="font-heading text-2xl font-bold text-body">{v}</div><div className="text-xs text-muted">{say(l, lang)}</div></div>
        ))}
      </div>

      {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 dark:bg-red-950/40 dark:text-red-200 dark:border-red-900 p-3 text-sm">{error}</div>}

      <label className="warm-card flex flex-col items-center justify-center gap-2 px-4 py-8 text-center cursor-pointer border-2 border-dashed hover:border-brand"
        onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); void onFiles(e.dataTransfer.files); }}>
        <span className="w-10 h-10 rounded-lg bg-brand-soft text-brand-strong flex items-center justify-center"><Icon name="doc" /></span>
        <span className="text-sm font-semibold text-body">{queue.length
          ? say({ en: `Reading ${queue.join(", ")}…`, gu: `${queue.join(", ")} વાંચી રહ્યા છીએ…`, hi: `${queue.join(", ")} पढ़ी जा रही है…` }, lang)
          : say({ en: "Drop circular PDFs here, or click to choose", gu: "પરિપત્રોની PDF અહીં મૂકો, અથવા પસંદ કરવા ક્લિક કરો", hi: "परिपत्रों की PDF यहाँ छोड़ें, या चुनने के लिए क्लिक करें" }, lang)}</span>
        <span className="text-xs text-muted">{say({
          en: "PDF, up to 30 MB and 60 pages each. Scanned pages take a few seconds each to read.",
          gu: "PDF, દરેક 30 MB અને 60 પાનાં સુધી. સ્કેન કરેલું દરેક પાનું વાંચવામાં થોડી સેકન્ડ લાગે છે.",
          hi: "PDF, हर एक 30 MB और 60 पृष्ठ तक। स्कैन किया गया हर पृष्ठ पढ़ने में कुछ सेकंड लगते हैं।",
        }, lang)}</span>
        <input type="file" accept="application/pdf,.pdf" multiple className="sr-only" onChange={(e) => void onFiles(e.target.files)} />
      </label>

      {drafts.length > 0 && (
        <section className="flex flex-col gap-3">
          <h3 className="font-heading text-sm font-bold text-body">{say({ en: "Drafts: check the details, then publish", gu: "ડ્રાફ્ટ: વિગતો તપાસો, પછી પ્રકાશિત કરો", hi: "ड्राफ़्ट: विवरण जाँचें, फिर प्रकाशित करें" }, lang)}</h3>
          <ul className="flex flex-col gap-3">{drafts.map((c) => <Row key={c.id} c={fresh[c.id] ? { ...c, preview: fresh[c.id].preview } : c} token={token!} onChange={load} onError={fail} />)}</ul>
        </section>
      )}
      <section className="flex flex-col gap-3">
        <h3 className="font-heading text-sm font-bold text-body">{say({ en: "Published", gu: "પ્રકાશિત", hi: "प्रकाशित" }, lang)} ({published.length})</h3>
        {published.length === 0
          ? <p className="text-sm text-muted">{say({
            en: "None yet. Published circulars are searchable in Ask Saathi straight away.",
            gu: "હજી કોઈ નથી. પ્રકાશિત પરિપત્રો તરત જ સાથીને પૂછો માં શોધી શકાય છે.",
            hi: "अभी कोई नहीं। प्रकाशित परिपत्र तुरंत साथी से पूछें में खोजे जा सकते हैं।",
          }, lang)}</p>
          : <ul className="flex flex-col gap-3">{published.map((c) => <Row key={c.id} c={c} token={token!} onChange={load} onError={fail} />)}</ul>}
      </section>
    </div>
  );
};
