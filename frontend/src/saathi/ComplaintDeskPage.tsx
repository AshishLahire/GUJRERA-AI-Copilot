import { complaintLabel } from "./complaintLabels";
import React, { useCallback, useEffect, useState } from "react";
import { AuthExpiredError, ComplaintBrief, OrderStatus, TriageResponse, UpcomingHearing, fetchBrief, fetchOrdersToEnforce, fetchTriage, fetchUpcomingHearings,
  officerAddDocument, openOfficerDocument, updateComplaintStatus, updateCompliance } from "../api/gujrera";
import { OrderCard } from "./OrderTrackerPage";
import { Icon } from "./Brand";
import { Said, say, uiLocale, useSaathi } from "./context";
import { En } from "./En";
import { LoginPrompt } from "./RolePages";
import { StringKey, tr } from "./strings";

const BAND_STYLE: Record<string, string> = {
  urgent: "bg-red-50 text-red-800 border-red-200 dark:bg-red-950/50 dark:text-red-200 dark:border-red-900",
  high: "bg-accent-surface text-accent-amber-strong border-accent-border",
  normal: "bg-subtle text-muted border-warm-border",
};
const BAND: Record<string, Said> = {
  urgent: { en: "urgent", gu: "તાત્કાલિક", hi: "तत्काल" },
  high: { en: "high", gu: "ઊંચી", hi: "उच्च" },
  normal: { en: "normal", gu: "સામાન્ય", hi: "सामान्य" },
};
const TONE_DOT: Record<string, string> = { good: "bg-emerald-600", warn: "bg-brand", bad: "bg-red-600" };
const NEXT: Record<string, string[]> = {
  filed: ["under_scrutiny", "hearing_scheduled", "withdrawn"],
  under_scrutiny: ["hearing_scheduled", "order_reserved", "disposed", "withdrawn"],
  hearing_scheduled: ["hearing_scheduled", "order_reserved", "disposed", "withdrawn"],
  order_reserved: ["disposed"],
};
const LABEL: Record<string, Said> = {
  filed: { en: "Filed", gu: "નોંધાઈ", hi: "दर्ज" },
  under_scrutiny: { en: "Under scrutiny", gu: "ચકાસણી હેઠળ", hi: "जाँच के अधीन" },
  hearing_scheduled: { en: "Hearing scheduled", gu: "સુનાવણી નક્કી", hi: "सुनवाई तय" },
  order_reserved: { en: "Order reserved", gu: "આદેશ અનામત", hi: "आदेश सुरक्षित" },
  disposed: { en: "Disposed", gu: "નિકાલ", hi: "निपटारा" },
  withdrawn: { en: "Withdrawn", gu: "પાછી ખેંચી", hi: "वापस ली गई" },
};
const OUTCOMES = ["allowed", "partly_allowed", "dismissed", "settled"];
const OUTCOME_LABEL: Record<string, Said> = {
  allowed: { en: "allowed", gu: "મંજૂર", hi: "स्वीकृत" },
  partly_allowed: { en: "partly allowed", gu: "અંશતઃ મંજૂર", hi: "आंशिक रूप से स्वीकृत" },
  dismissed: { en: "dismissed", gu: "નામંજૂર", hi: "खारिज" },
  settled: { en: "settled", gu: "સમાધાન", hi: "समझौता" },
};
const nice = (s: string) => s.replace(/_/g, " ");
const fmt = (iso: string) => new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString(uiLocale(), { day: "numeric", month: "short", year: "numeric" });

const Clock: React.FC<{ left: number }> = ({ left }) => {
  const { lang } = useSaathi();
  return (
    <span className={`text-[11px] font-semibold whitespace-nowrap ${left < 0 ? "text-red-700 dark:text-red-300" : left <= 15 ? "text-accent-amber-strong" : "text-muted"}`}>
      {left < 0
        ? say({ en: `${-left} days over`, gu: `${-left} દિવસ મુદત વીતી`, hi: `${-left} दिन समय सीमा पार` }, lang)
        : say({ en: `${left} days left`, gu: `${left} દિવસ બાકી`, hi: `${left} दिन शेष` }, lang)}
    </span>
  );
};

const Brief: React.FC<{ id: number; onChanged: () => void }> = ({ id, onChanged }) => {
  const { token, lang, logout } = useSaathi();
  const [b, setB] = useState<ComplaintBrief | null>(null);
  const [status, setStatus] = useState("");
  const [hearing, setHearing] = useState("");
  const [place, setPlace] = useState("");
  const [outcome, setOutcome] = useState("");
  const [docNote, setDocNote] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    fetchBrief(token, id, lang).then((x) => { setB(x); setStatus(""); setMsg(null); })
      .catch((e) => { if (e instanceof AuthExpiredError) logout(); setMsg((e as Error).message); });
  }, [id, token, lang, logout]);
  useEffect(() => { setB(null); load(); }, [load]);

  const save = async () => {
    if (!token || !b || !status) return;
    setBusy(true);
    setMsg(null);
    try {
      await updateComplaintStatus(token, b.complaint.id, { status, note: note || undefined, hearing_on: hearing || undefined,
        hearing_place: place.trim() || undefined, outcome: outcome || undefined });
      setNote(""); setHearing(""); setPlace(""); setOutcome("");
      load();
      onChanged();
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const addDoc = async (file: File) => {
    if (!token || !b) return;
    setMsg(null);
    try { await officerAddDocument(token, b.complaint.id, file, docNote.trim() || undefined); setDocNote(""); load(); }
    catch (e) { setMsg((e as Error).message); }
  };

  if (!b) return <div className="p-6 text-sm text-muted">{msg ?? "…"}</div>;
  const c = b.complaint;
  const outcomes = b.precedents.category_outcomes;
  const decided = b.precedents.category_decided || 1;
  const label = (s: string) => (LABEL[s] ? say(LABEL[s], lang) : s);
  const outcomeName = (o: string) => (OUTCOME_LABEL[o] ? say(OUTCOME_LABEL[o], lang) : nice(o));
  return (
    <article className="report-sheet flex flex-col gap-5 p-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs text-muted">{tr("deskBrief", lang)}{lang !== "en" ? ` · ${tr("deskBrief", "en")}` : ""}</div>
          <h3 className="font-heading text-lg font-bold text-body">{c.ref_no}</h3>
          <div className="text-xs text-muted">{say({
            en: `Form ${c.form} · ${complaintLabel(c.category, lang)} · filed ${fmt(c.filed_on)} via ${c.channel}`,
            gu: `ફોર્મ ${c.form} · ${complaintLabel(c.category, lang)} · ${fmt(c.filed_on)} ના રોજ ${c.channel} દ્વારા નોંધાઈ`,
            hi: `फ़ॉर्म ${c.form} · ${complaintLabel(c.category, lang)} · ${fmt(c.filed_on)} को ${c.channel} से दर्ज`,
          }, lang)} · {label(c.status)}</div>
        </div>
        <div className="text-right">
          <Clock left={c.days_left} />
          <div className="text-[11px] text-muted">{say({ en: "60-day date:", gu: "60 દિવસની તારીખ:", hi: "60 दिन की तिथि:" }, lang)} {fmt(c.due_by)}</div>
          <button type="button" onClick={() => window.print()} className="print:hidden mt-1 inline-flex items-center gap-1 text-xs font-semibold text-body hover:underline">
            <Icon name="printer" className="w-3.5 h-3.5" /> {say({ en: "Print brief", gu: "સાર છાપો", hi: "सार प्रिंट करें" }, lang)}
          </button>
        </div>
      </header>

      <section>
        <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">{say({ en: "Complaint", gu: "ફરિયાદ", hi: "शिकायत" }, lang)}</h4>
        <p className="text-sm text-body bg-subtle rounded-md p-3">{c.summary}</p>
        {c.relief && <p className="text-xs text-muted mt-1">{say({ en: "Relief sought:", gu: "માંગેલી રાહત:", hi: "माँगी गई राहत:" }, lang)} {complaintLabel(c.relief, lang)}</p>}
      </section>

      {b.hearing && (
        <section className={`rounded-lg p-3 text-sm ${b.hearing.upcoming ? "border-2 border-accent-border bg-brand-soft" : "border border-warm-border"}`}>
          <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">{say({ en: "Hearing", gu: "સુનાવણી", hi: "सुनवाई" }, lang)}</h4>
          <p className="text-body">{b.hearing.text}</p>
        </section>
      )}

      <section>
        <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">{say({ en: "Documents", gu: "દસ્તાવેજો", hi: "दस्तावेज़" }, lang)} ({b.documents.length})</h4>
        {b.documents.length === 0 ? <p className="text-xs text-muted">{say({ en: "The buyer has not added any documents.", gu: "ખરીદનારે કોઈ દસ્તાવેજ ઉમેર્યો નથી.", hi: "खरीदार ने कोई दस्तावेज़ नहीं जोड़ा है।" }, lang)}</p> : (
          <ul className="text-xs flex flex-col gap-1">
            {b.documents.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center gap-2">
                <Icon name="doc" className="w-3.5 h-3.5 text-muted" />
                <button type="button" onClick={() => void openOfficerDocument(token!, c.id, d).catch((e) => setMsg((e as Error).message))}
                  className="font-semibold text-body underline decoration-dotted underline-offset-2 break-all text-left">{d.filename}</button>
                <span className="text-muted">{d.added_by === "officer" ? "GUJRERA" : say({ en: "buyer", gu: "ખરીદનાર", hi: "खरीदार" }, lang)} · {d.added_at.replace("T", " ")}{d.note ? ` · ${d.note}` : ""}</span>
              </li>
            ))}
          </ul>
        )}
        <div className="print:hidden mt-2 flex flex-wrap items-center gap-2">
          <input value={docNote} onChange={(e) => setDocNote(e.target.value)} maxLength={200}
            placeholder={say({ en: "e.g. Hearing notice", gu: "દા.ત. સુનાવણીની નોટિસ", hi: "जैसे सुनवाई का नोटिस" }, lang)}
            className="rounded-md border border-warm-border bg-card text-body text-xs px-2 py-1.5 w-48"
            aria-label={say({ en: "What the document is", gu: "દસ્તાવેજ શું છે", hi: "दस्तावेज़ क्या है" }, lang)} />
          <label className="text-xs px-3 py-1.5 rounded-md border border-warm-border text-body cursor-pointer hover:border-warm-strong">
            {say({ en: "Add a document for the buyer", gu: "ખરીદનાર માટે દસ્તાવેજ ઉમેરો", hi: "खरीदार के लिए दस्तावेज़ जोड़ें" }, lang)}
            <input type="file" accept=".pdf,.jpg,.jpeg,.png" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void addDoc(f); }} />
          </label>
        </div>
      </section>

      <section>
        <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">{say({ en: "Law", gu: "કાયદો", hi: "कानून" }, lang)}</h4>
        <ul className="text-sm text-body flex flex-col gap-0.5">
          {b.sections.map((s) => <li key={s.section}><b>{say({ en: "Section", gu: "કલમ", hi: "धारा" }, lang)} {s.section}</b> · {s.title}</li>)}
        </ul>
        <p className="text-xs text-muted mt-1">{b.forum === "adjudicating_officer"
          ? say({ en: "Adjudicating officer", gu: "નિર્ણાયક અધિકારી", hi: "न्यायनिर्णायक अधिकारी" }, lang)
          : say({ en: "Authority", gu: "ઓથોરિટી", hi: "प्राधिकरण" }, lang)}: {b.forum_law}</p>
      </section>

      {b.project && (
        <section>
          <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">{say({ en: "Project record", gu: "પ્રોજેક્ટ રેકોર્ડ", hi: "प्रोजेक्ट रिकॉर्ड" }, lang)} · {b.project.project.name}</h4>
          <ul className="text-sm flex flex-col gap-1">
            {b.project.glance.map((g, i) => (
              <li key={i} className="flex gap-2"><span className={`mt-1.5 w-2 h-2 shrink-0 rounded-full ${TONE_DOT[g.tone]}`} />{g.text}</li>
            ))}
          </ul>
          {b.risk && (
            <p className="text-xs text-muted mt-2">{say({ en: "Risk watchlist:", gu: "જોખમ યાદી:", hi: "जोखिम सूची:" }, lang)} <b className="text-body">{b.risk.score} ({b.risk.band})</b> · {b.risk.signals.slice(0, 2).join(" ")}</p>
          )}
        </section>
      )}

      <section>
        <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">{say({ en: "How similar complaints were decided", gu: "સમાન ફરિયાદોનો નિર્ણય કેવી રીતે થયો", hi: "समान शिकायतों का निर्णय कैसे हुआ" }, lang)}</h4>
        <div className="flex h-2.5 rounded-full overflow-hidden bg-subtle" role="img" aria-label={say({ en: "Outcomes", gu: "પરિણામો", hi: "परिणाम" }, lang)}>
          {[["allowed", "bg-emerald-600"], ["partly_allowed", "bg-emerald-400"], ["settled", "bg-brand"], ["dismissed", "bg-warm-strong"]].map(([k, cls]) => (
            <span key={k} className={cls} style={{ width: `${(100 * (outcomes[k] ?? 0)) / decided}%` }} />
          ))}
        </div>
        <p className="text-xs text-muted mt-1">
          {complaintLabel(c.category, lang)}, {b.precedents.category_decided} {say({ en: "decided", gu: "નિર્ણય થયા", hi: "निर्णीत" }, lang)}: {OUTCOMES.map((o) => `${outcomeName(o)} ${outcomes[o] ?? 0}`).join(" · ")}
        </p>
        {b.precedents.related.length > 0 && (
          <ul className="mt-2 text-xs flex flex-col gap-1">
            {b.precedents.related.map((r) => (
              <li key={r.ref_no}><span className="font-mono">{r.ref_no}</span> · {complaintLabel(r.category, lang)} · <b>{outcomeName(r.outcome)}</b>{r.same_project
                ? say({ en: " · same project", gu: " · એ જ પ્રોજેક્ટ", hi: " · वही प्रोजेक्ट" }, lang)
                : say({ en: " · same promoter", gu: " · એ જ પ્રમોટર", hi: " · वही प्रमोटर" }, lang)}</li>
            ))}
          </ul>
        )}
      </section>

      {b.other_open.length > 0 && (
        <section>
          <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">{say({
            en: `Other open complaints on this project (${b.other_open.length}): hear together?`,
            gu: `આ પ્રોજેક્ટ પરની અન્ય ખુલ્લી ફરિયાદો (${b.other_open.length}): સાથે સુનાવણી કરવી?`,
            hi: `इस प्रोजेक्ट पर अन्य खुली शिकायतें (${b.other_open.length}): साथ में सुनवाई करें?`,
          }, lang)}</h4>
          <p className="text-xs text-body">{b.other_open.map((o) => `${o.ref_no} (${complaintLabel(o.category, lang)})`).join(", ")}</p>
        </section>
      )}

      <section>
        <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">{say({ en: "Points to put to the promoter", gu: "પ્રમોટર સમક્ષ મૂકવાના મુદ્દા", hi: "प्रमोटर के सामने रखने के बिंदु" }, lang)}</h4>
        <ul className="text-sm flex flex-col gap-1">
          {b.points_to_put.map((p, i) => (
            <li key={i} className="flex gap-2"><span className="mt-0.5 w-3.5 h-3.5 shrink-0 rounded border border-warm-strong" />{p}</li>
          ))}
        </ul>
      </section>

      <section>
        <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">{say({ en: "Timeline", gu: "સમયરેખા", hi: "समयरेखा" }, lang)}</h4>
        <ol className="text-xs flex flex-col gap-0.5">
          {b.timeline.map((e, i) => <li key={i}><span className="tabular-nums text-muted">{fmt(e.at)}</span> · {label(e.status)}{e.note ? ` · ${e.note}` : ""}</li>)}
        </ol>
      </section>

      {NEXT[c.status] && (
        <section className="print:hidden rounded-lg border border-warm-border p-4 grid gap-3">
          <div className="grid sm:grid-cols-3 gap-3">
            <label className="text-xs text-muted">{say({ en: "Next step", gu: "આગળનું પગલું", hi: "अगला कदम" }, lang)}
              <select value={status} onChange={(e) => setStatus(e.target.value)} className="mt-1 w-full rounded-md border border-warm-border bg-card text-body text-sm px-2 py-1.5">
                <option value="">—</option>
                {NEXT[c.status].map((s) => <option key={s} value={s}>{label(s)}</option>)}
              </select>
            </label>
            {status === "hearing_scheduled" && (<>
              <label className="text-xs text-muted">{say({ en: "Hearing date", gu: "સુનાવણીની તારીખ", hi: "सुनवाई की तिथि" }, lang)}
                <input type="date" value={hearing} onChange={(e) => setHearing(e.target.value)} className="mt-1 w-full rounded-md border border-warm-border bg-card text-body text-sm px-2 py-1.5" />
              </label>
              <label className="text-xs text-muted">{say({ en: "Where (shown to the buyer)", gu: "ક્યાં (ખરીદનારને દેખાશે)", hi: "कहाँ (खरीदार को दिखेगा)" }, lang)}
                <input value={place} onChange={(e) => setPlace(e.target.value)} maxLength={200}
                  placeholder={say({ en: "GujRERA office, Gandhinagar, Court 2", gu: "GujRERA કચેરી, ગાંધીનગર, કોર્ટ 2", hi: "GujRERA कार्यालय, गांधीनगर, कोर्ट 2" }, lang)}
                  className="mt-1 w-full rounded-md border border-warm-border bg-card text-body text-sm px-2 py-1.5" />
              </label>
            </>)}
            {status === "disposed" && (
              <label className="text-xs text-muted">{say({ en: "Outcome", gu: "પરિણામ", hi: "परिणाम" }, lang)}
                <select value={outcome} onChange={(e) => setOutcome(e.target.value)} className="mt-1 w-full rounded-md border border-warm-border bg-card text-body text-sm px-2 py-1.5">
                  <option value="">—</option>
                  {OUTCOMES.map((o) => <option key={o} value={o}>{outcomeName(o)}</option>)}
                </select>
              </label>
            )}
          </div>
          <input value={note} onChange={(e) => setNote(e.target.value)}
            placeholder={say({ en: "Note (optional, shown in the buyer's tracking)", gu: "નોંધ (વૈકલ્પિક, ખરીદનારના ટ્રેકિંગમાં દેખાશે)", hi: "टिप्पणी (वैकल्पिक, खरीदार की ट्रैकिंग में दिखेगी)" }, lang)}
            className="rounded-md border border-warm-border bg-card text-body text-sm px-3 py-2" />
          <div className="flex items-center gap-3">
            <button type="button" disabled={!status || busy} onClick={() => void save()}
              className="px-4 py-2 rounded-lg bg-primary-bg text-primary-text text-sm font-semibold disabled:opacity-40">{busy ? "…" : say({ en: "Update", gu: "અપડેટ કરો", hi: "अपडेट करें" }, lang)}</button>
            {msg && <span role="alert" className="text-xs text-red-700 dark:text-red-300">{msg}</span>}
          </div>
        </section>
      )}
    </article>
  );
};

const ORDER_STATUSES: [string, Said][] = [
  ["complied", { en: "Complied", gu: "પાલન થયું", hi: "अनुपालन हुआ" }],
  ["partly_complied", { en: "Partly done", gu: "અંશતઃ થયું", hi: "आंशिक रूप से हुआ" }],
  ["not_complied", { en: "Not complied", gu: "પાલન થયું નથી", hi: "अनुपालन नहीं हुआ" }],
  ["recovery", { en: "Recovery started (Section 40)", gu: "વસૂલાત શરૂ (કલમ 40)", hi: "वसूली शुरू (धारा 40)" }],
  ["pending", { en: "Pending", gu: "બાકી", hi: "लंबित" }],
];

const OrderAction: React.FC<{ o: OrderStatus; onChanged: () => void }> = ({ o, onChanged }) => {
  const { token, lang } = useSaathi();
  const [status, setStatus] = useState("");
  const [date, setDate] = useState("");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const save = async () => {
    if (!token || !status) return;
    setMsg(null);
    try {
      await updateCompliance(token, o.order_id, { status, complied_on: date || undefined, note: note || undefined });
      setStatus(""); setDate(""); setNote("");
      onChanged();
    } catch (e) {
      setMsg((e as Error).message);
    }
  };
  return (
    <div className="p-5 flex flex-col gap-4">
      <ul><OrderCard o={o} /></ul>
      <div className="rounded-lg border border-warm-border p-4 grid gap-3">
        <div className="grid sm:grid-cols-2 gap-3">
          <label className="text-xs text-muted">{say({ en: "Compliance", gu: "પાલન", hi: "अनुपालन" }, lang)}
            <select value={status} onChange={(e) => setStatus(e.target.value)} className="mt-1 w-full rounded-md border border-warm-border bg-card text-body text-sm px-2 py-1.5">
              <option value="">—</option>
              {ORDER_STATUSES.map(([v, l]) => <option key={v} value={v}>{say(l, lang)}</option>)}
            </select>
          </label>
          {status === "complied" && (
            <label className="text-xs text-muted">{say({ en: "Complied on", gu: "પાલનની તારીખ", hi: "अनुपालन की तिथि" }, lang)}
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="mt-1 w-full rounded-md border border-warm-border bg-card text-body text-sm px-2 py-1.5" />
            </label>
          )}
        </div>
        <input value={note} onChange={(e) => setNote(e.target.value)}
          placeholder={status === "partly_complied"
            ? say({ en: "What is done and what is left (required)", gu: "શું થયું અને શું બાકી છે (જરૂરી)", hi: "क्या हुआ और क्या बाकी है (आवश्यक)" }, lang)
            : say({ en: "Note (optional)", gu: "નોંધ (વૈકલ્પિક)", hi: "टिप्पणी (वैकल्पिक)" }, lang)}
          className="rounded-md border border-warm-border bg-card text-body text-sm px-3 py-2" />
        <div className="flex items-center gap-3">
          <button type="button" disabled={!status} onClick={() => void save()} className="px-4 py-2 rounded-lg bg-primary-bg text-primary-text text-sm font-semibold disabled:opacity-40">{say({ en: "Update", gu: "અપડેટ કરો", hi: "अपडेट करें" }, lang)}</button>
          {msg && <span role="alert" className="text-xs text-red-700 dark:text-red-300">{msg}</span>}
        </div>
      </div>
    </div>
  );
};

export const ComplaintDeskPage: React.FC = () => {
  const { user, token, lang, logout } = useSaathi();
  const allowed = user?.role === "officer";
  const [data, setData] = useState<TriageResponse | null>(null);
  const [category, setCategory] = useState("");
  const [tab, setTab] = useState<"queue" | "groups" | "orders">("queue");
  const [orders, setOrders] = useState<{ counts: Record<string, number>; items: OrderStatus[] } | null>(null);
  const [orderSel, setOrderSel] = useState<number | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hearings, setHearings] = useState<UpcomingHearing[]>([]);

  const load = useCallback(() => {
    if (!allowed || !token) return;
    fetchUpcomingHearings(token).then((d) => setHearings(d.items)).catch(() => setHearings([]));
    fetchTriage(token, lang, { category })
      .then((d) => { setData(d); setSelected((s) => s ?? d.items[0]?.id ?? null); })
      .catch((e) => { if (e instanceof AuthExpiredError) logout(); setError((e as Error).message); });
  }, [allowed, token, lang, category, logout]);
  useEffect(load, [load]);
  const loadOrders = useCallback(() => {
    if (!allowed || !token) return;
    fetchOrdersToEnforce(token, lang).then((d) => { setOrders(d); setOrderSel((s) => s ?? d.items[0]?.order_id ?? null); })
      .catch((e) => { if (e instanceof AuthExpiredError) logout(); setError((e as Error).message); });
  }, [allowed, token, lang, logout]);
  useEffect(() => { if (tab === "orders") loadOrders(); }, [tab, loadOrders]);

  const s = data?.summary;
  const byRef = new Map((data?.items ?? []).map((i) => [i.ref_no, i.id]));
  const hearingsTitle = say({ en: "Hearings in the next 14 days", gu: "આગામી 14 દિવસની સુનાવણીઓ", hi: "अगले 14 दिनों की सुनवाइयाँ" }, lang);
  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6 print:p-0">
      <div className="max-w-3xl print:hidden">
        <p className="text-sm text-muted leading-relaxed">{tr("deskIntro", lang)}</p>
        {lang !== "en" && <p lang="en" className="text-xs text-muted opacity-80 mt-0.5">{tr("deskIntro", "en")}</p>}
      </div>
      {!allowed && <LoginPrompt k="loginNeededDesk" />}
      {allowed && error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 p-4 text-sm">{error}</div>}
      {allowed && s && (
        <>
          {s.open === 0 && (
            <p className="rounded-xl border border-dashed border-warm-strong p-4 text-sm text-muted print:hidden">
              {{ en: "No open complaints in your area. Complaints that citizens file through Ask Saathi appear here, ranked by the 60-day deadline.",
                 gu: "તમારા વિસ્તારમાં કોઈ ખુલ્લી ફરિયાદ નથી. નાગરિકો આસ્ક સાથી દ્વારા કરેલી ફરિયાદો 60 દિવસની મર્યાદા પ્રમાણે અહીં દેખાય છે.",
                 hi: "आपके क्षेत्र में कोई खुली शिकायत नहीं। नागरिक आस्क साथी से जो शिकायतें दर्ज करते हैं, वे 60 दिन की सीमा के अनुसार यहाँ दिखती हैं।" }[lang]}
            </p>
          )}
          <div className="grid gap-4 grid-cols-2 lg:grid-cols-4 print:hidden">
            {([["deskOpen", s.open, "complaint"], ["deskOverdue", s.overdue, "alert"], ["deskDue", s.due_15, "clock"], ["deskGroups", s.groups, "user"]] as [StringKey, number, string][]).map(([k, v, icon]) => (
              <div key={k} className="rounded-xl border border-warm-border bg-card p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="text-xs font-medium text-muted">{tr(k, lang)}<En k={k} /></div>
                  <span className="w-8 h-8 rounded-lg bg-brand-soft text-brand-strong flex items-center justify-center"><Icon name={icon} className="w-4 h-4" /></span>
                </div>
                <div className="mt-3 font-heading text-2xl font-bold text-body tabular-nums">{v}</div>
              </div>
            ))}
          </div>

          {hearings.length > 0 && (
            <section className="rounded-xl border border-accent-border bg-brand-soft p-4 print:hidden" aria-label={hearingsTitle}>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-body flex items-center gap-1.5"><Icon name="calendar" className="w-4 h-4" /> {hearingsTitle} ({hearings.length})</h3>
              <ul className="mt-2 flex flex-wrap gap-2">
                {hearings.map((h) => (
                  <li key={h.id}>
                    <button type="button" onClick={() => { setSelected(h.id); setTab("queue"); }}
                      className="text-left rounded-lg border border-warm-border bg-card px-3 py-1.5 text-xs hover:border-warm-strong">
                      <span className="font-semibold text-body">{fmt(h.on)}{h.days_to === 0
                        ? say({ en: " · today", gu: " · આજે", hi: " · आज" }, lang)
                        : say({ en: ` · in ${h.days_to} days`, gu: ` · ${h.days_to} દિવસમાં`, hi: ` · ${h.days_to} दिन में` }, lang)}</span>
                      <span className="block text-muted"><span className="font-mono">{h.ref_no}</span> · {h.project ?? complaintLabel(h.category, lang)}{h.place ? ` · ${h.place}` : ""}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <div className="flex flex-wrap items-center gap-3 print:hidden">
            <div className="flex rounded-lg border border-warm-border p-0.5" role="tablist">
              {(["queue", "groups", "orders"] as const).map((t) => (
                <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                  className={`px-3 py-1.5 rounded-md text-xs font-semibold ${tab === t ? "bg-subtle text-body ring-1 ring-warm-strong" : "text-muted hover:text-body"}`}>
                  {t === "queue" ? `${tr("deskQueue", lang)} (${data!.items.length})` : t === "groups" ? `${tr("deskGroups", lang)} (${data!.groups.length})` : `${tr("ordEnforce", lang)}${orders ? ` (${orders.items.length})` : ""}`}
                </button>
              ))}
            </div>
            <select aria-label={say({ en: "Category", gu: "પ્રકાર", hi: "श्रेणी" }, lang)} value={category} onChange={(e) => { setCategory(e.target.value); setSelected(null); }}
              className="rounded-lg border border-warm-border bg-card text-body text-sm px-3 py-2">
              <option value="">{say({ en: "All categories", gu: "બધા પ્રકાર", hi: "सभी श्रेणियाँ" }, lang)}</option>
              {Object.keys(s.by_category).map((c) => <option key={c} value={c}>{complaintLabel(c, lang)} ({s.by_category[c]})</option>)}
            </select>
            {data!.district_scope && <span className="text-sm text-muted">{data!.district_scope}</span>}
          </div>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] items-start">
            <div className="rounded-xl border border-warm-border bg-card overflow-hidden print:hidden">
              {tab === "orders" ? (
                <ul className="divide-y divide-warm-border max-h-[70vh] overflow-auto">
                  {(orders?.items ?? []).map((o) => (
                    <li key={o.order_id}>
                      <button type="button" onClick={() => setOrderSel(o.order_id)}
                        className={`relative w-full text-left px-4 py-3 hover:bg-subtle ${orderSel === o.order_id ? "bg-subtle" : ""}`}>
                        {orderSel === o.order_id && <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full bg-brand" />}
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-semibold text-body font-mono">{o.order_no}</div>
                            <div className="text-[11px] text-muted truncate">{o.project ?? "—"} · {o.promoter} · {say({ en: "due", gu: "મુદત", hi: "देय" }, lang)} {o.due_on}</div>
                          </div>
                          <span className="text-[11px] font-semibold whitespace-nowrap">{(() => {
                            const st = ORDER_STATUSES.find(([v]) => v === o.state)?.[1];
                            return st ? say(st, lang) : o.state?.replace(/_/g, " ");
                          })()}</span>
                        </div>
                      </button>
                    </li>
                  ))}
                  {orders && orders.items.length === 0 && <li className="px-4 py-6 text-sm text-muted text-center">{say({ en: "No orders waiting for compliance.", gu: "પાલનની રાહ જોતો કોઈ આદેશ નથી.", hi: "अनुपालन की प्रतीक्षा में कोई आदेश नहीं।" }, lang)}</li>}
                </ul>
              ) : tab === "queue" ? (
                <ul className="divide-y divide-warm-border max-h-[70vh] overflow-auto">
                  {data!.items.map((i) => (
                    <li key={i.id}>
                      <button type="button" onClick={() => setSelected(i.id)} aria-current={selected === i.id ? "true" : undefined}
                        className={`relative w-full text-left px-4 py-3 hover:bg-subtle ${selected === i.id ? "bg-subtle" : ""}`}>
                        {selected === i.id && <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full bg-brand" />}
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-semibold text-body"><span className="font-mono text-xs">{i.ref_no}</span> · {complaintLabel(i.category, lang)}</div>
                            <div className="text-[11px] text-muted truncate">{i.project ?? "—"} · {i.district}{i.group_size > 1
                              ? say({ en: ` · ${i.group_size} on project`, gu: ` · પ્રોજેક્ટ પર ${i.group_size}`, hi: ` · प्रोजेक्ट पर ${i.group_size}` }, lang)
                              : ""}</div>
                          </div>
                          <div className="text-right shrink-0">
                            <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold ${BAND_STYLE[i.band]}`}>{BAND[i.band] ? say(BAND[i.band], lang) : i.band} · {i.score}</span>
                            <div><Clock left={i.days_left} /></div>
                          </div>
                        </div>
                        {i.reasons[0] && <div className="mt-1 text-[11px] text-muted line-clamp-1">{i.reasons.map((r) => `+${r.points} ${r.code.replace(/_/g, " ")}`).join(" · ")}</div>}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <ul className="divide-y divide-warm-border max-h-[70vh] overflow-auto">
                  {data!.groups.map((g) => (
                    <li key={g.project_id} className="px-4 py-3">
                      <div className="text-sm font-semibold text-body">{g.project} <span className="text-muted font-normal">· {g.district}</span></div>
                      <div className="text-[11px] text-muted">{say({
                        en: `${g.complaints.length} open · oldest ${g.oldest_days} days`,
                        gu: `${g.complaints.length} ખુલ્લી · સૌથી જૂની ${g.oldest_days} દિવસ`,
                        hi: `${g.complaints.length} खुली · सबसे पुरानी ${g.oldest_days} दिन`,
                      }, lang)} · {Object.entries(g.categories).map(([k, n]) => `${complaintLabel(k, lang)} ${n}`).join(", ")}</div>
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {g.complaints.map((ref) => (
                          <button key={ref} type="button" disabled={!byRef.has(ref)} onClick={() => { setSelected(byRef.get(ref)!); setTab("queue"); }}
                            className="font-mono text-[11px] rounded border border-warm-border px-1.5 py-0.5 hover:border-warm-strong disabled:opacity-50">{ref}</button>
                        ))}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="rounded-xl border border-warm-border bg-card lg:sticky lg:top-20 print:border-0">
              {tab === "orders"
                ? (orders?.items.find((o) => o.order_id === orderSel)
                  ? <OrderAction o={orders!.items.find((o) => o.order_id === orderSel)!} onChanged={loadOrders} />
                  : <div className="p-6 text-sm text-muted">{say({ en: "Select an order.", gu: "આદેશ પસંદ કરો.", hi: "आदेश चुनें।" }, lang)}</div>)
                : selected ? <Brief id={selected} onChanged={load} /> : <div className="p-6 text-sm text-muted">{say({ en: "Select a complaint.", gu: "ફરિયાદ પસંદ કરો.", hi: "शिकायत चुनें।" }, lang)}</div>}
            </div>
          </div>
        </>
      )}
    </div>
  );
};
