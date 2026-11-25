import React, { useCallback, useEffect, useState } from "react";
import {
  AuthExpiredError,
  DeskItem,
  DeskResponse,
  DeskReview,
  Lang,
  fetchOfficerDashboard,
  navigateTo,
  openReport,
  reviewDeskItem,
} from "../api/gujrera";
import { Icon } from "./Brand";
import { useSaathi } from "./context";
import { LoginPrompt } from "./RolePages";

type L3 = { en: string; gu: string; hi: string };
const t3 = (s: L3, lang: Lang) => s[lang] ?? s.en;

type SectionKey = keyof DeskResponse["sections"];
const SECTIONS: { key: SectionKey; icon: string; title: L3; why: L3; empty: L3; open?: { page: string; label: L3 } }[] = [
  {
    key: "expiring", icon: "clock",
    title: { en: "Registrations ending in the next 90 days", gu: "આગામી 90 દિવસમાં પૂરી થતી નોંધણીઓ", hi: "अगले 90 दिनों में समाप्त होने वाले पंजीकरण" },
    why: { en: "Remind the promoter to apply for an extension (Section 6) or file completion, before the registration lapses.",
      gu: "નોંધણી રદ થાય તે પહેલાં પ્રમોટરને મુદત વધારા (કલમ 6) અથવા પૂર્ણતા માટે યાદ અપાવો.",
      hi: "पंजीकरण समाप्त होने से पहले प्रमोटर को विस्तार (धारा 6) या पूर्णता के लिए याद दिलाएँ।" },
    empty: { en: "No registration ends in the next 90 days.", gu: "આગામી 90 દિવસમાં કોઈ નોંધણી પૂરી થતી નથી.", hi: "अगले 90 दिनों में कोई पंजीकरण समाप्त नहीं होता।" },
  },
  {
    key: "overdue", icon: "alert",
    title: { en: "Past completion date, no completion on record", gu: "પૂર્ણતા તારીખ વીતી ગઈ, પૂર્ણતા નોંધાયેલ નથી", hi: "पूर्णता तिथि बीत गई, पूर्णता दर्ज नहीं" },
    why: { en: "Ask for the completion or occupancy certificate, or an extension application (Sections 6 and 7). Newest first: these are the ones still worth chasing.",
      gu: "પૂર્ણતા અથવા વપરાશ પ્રમાણપત્ર, અથવા મુદત વધારાની અરજી માંગો (કલમ 6 અને 7). નવા પહેલાં: તેમનો પીછો કરવો હજી ઉપયોગી છે.",
      hi: "पूर्णता या अधिभोग प्रमाणपत्र, या विस्तार आवेदन माँगें (धारा 6 और 7)। नए पहले: इनका पीछा करना अभी उपयोगी है।" },
    empty: { en: "Nothing overdue.", gu: "કંઈ બાકી નથી.", hi: "कुछ भी बकाया नहीं।" },
  },
  {
    key: "extensions", icon: "calendar",
    title: { en: "Extended two or more times", gu: "બે કે વધુ વખત મુદત લંબાવેલ", hi: "दो या अधिक बार बढ़ाए गए" },
    why: { en: "Repeated extensions point to chronic delay: check progress, buyer complaints and the reasons given.",
      gu: "વારંવાર મુદત વધારો લાંબા વિલંબનો સંકેત છે: પ્રગતિ, ખરીદદારોની ફરિયાદો અને કારણો તપાસો.",
      hi: "बार-बार विस्तार लंबी देरी का संकेत है: प्रगति, खरीदारों की शिकायतें और कारण जाँचें।" },
    empty: { en: "No project has been extended twice.", gu: "કોઈ પ્રોજેક્ટ બે વખત લંબાવાયો નથી.", hi: "कोई प्रोजेक्ट दो बार नहीं बढ़ाया गया।" },
  },
  {
    key: "unknown_numbers", icon: "shield",
    title: { en: "RERA numbers citizens checked that do not exist", gu: "નાગરિકોએ તપાસેલા એવા RERA નંબર જે અસ્તિત્વમાં નથી", hi: "नागरिकों द्वारा जाँचे गए RERA नंबर जो मौजूद नहीं हैं" },
    why: { en: "Likely a fake project or ad using an invented number. Verify, and act under Sections 3 and 59.",
      gu: "સંભવતઃ બનાવટી નંબર વાપરતો નકલી પ્રોજેક્ટ કે જાહેરાત. ચકાસો અને કલમ 3 અને 59 હેઠળ કાર્યવાહી કરો.",
      hi: "संभवतः नकली नंबर वाला फ़र्ज़ी प्रोजेक्ट या विज्ञापन। जाँचें और धारा 3 और 59 के तहत कार्रवाई करें।" },
    empty: { en: "No unknown numbers in the last 90 days. They appear here when citizens check an ad or ask about a number.",
      gu: "છેલ્લા 90 દિવસમાં કોઈ અજાણ્યો નંબર નથી. નાગરિકો જાહેરાત તપાસે કે નંબર પૂછે ત્યારે અહીં દેખાય છે.",
      hi: "पिछले 90 दिनों में कोई अज्ञात नंबर नहीं। नागरिक विज्ञापन जाँचते या नंबर पूछते हैं तो यहाँ दिखते हैं।" },
  },
  {
    key: "ad_cases", icon: "flag",
    title: { en: "Ads reported by citizens", gu: "નાગરિકોએ નોંધાવેલી જાહેરાતો", hi: "नागरिकों द्वारा रिपोर्ट किए गए विज्ञापन" },
    why: { en: "Unregistered projects, lapsed registrations and misleading claims, grouped into cases.",
      gu: "નોંધણી વગરના પ્રોજેક્ટ, રદ નોંધણી અને ભ્રામક દાવા, કેસમાં જૂથબદ્ધ.",
      hi: "बिना पंजीकरण प्रोजेक्ट, समाप्त पंजीकरण और भ्रामक दावे, मामलों में समूहित।" },
    empty: { en: "No open reports. Citizens report an ad from the ad check with one click.", gu: "કોઈ ખુલ્લો રિપોર્ટ નથી. નાગરિકો જાહેરાત તપાસમાંથી એક ક્લિકમાં રિપોર્ટ કરે છે.", hi: "कोई खुली रिपोर्ट नहीं। नागरिक विज्ञापन जाँच से एक क्लिक में रिपोर्ट करते हैं।" },
    open: { page: "enforce", label: { en: "Open ad enforcement", gu: "જાહેરાત અમલીકરણ ખોલો", hi: "विज्ञापन प्रवर्तन खोलें" } },
  },
  {
    key: "complaints", icon: "complaint",
    title: { en: "Open complaints, oldest first", gu: "ખુલ્લી ફરિયાદો, જૂની પહેલાં", hi: "खुली शिकायतें, पुरानी पहले" },
    why: { en: "Section 29(4): complaints should be decided within 60 days.", gu: "કલમ 29(4): ફરિયાદનો 60 દિવસમાં નિકાલ થવો જોઈએ.", hi: "धारा 29(4): शिकायतों का 60 दिनों में निपटारा होना चाहिए।" },
    empty: { en: "No open complaints. Complaints citizens file in the app appear here.", gu: "કોઈ ખુલ્લી ફરિયાદ નથી. નાગરિકો એપમાં ફરિયાદ કરે તે અહીં દેખાય છે.", hi: "कोई खुली शिकायत नहीं। नागरिक ऐप में जो शिकायतें दर्ज करते हैं वे यहाँ दिखती हैं।" },
    open: { page: "desk", label: { en: "Open complaint desk", gu: "ફરિયાદ ડેસ્ક ખોલો", hi: "शिकायत डेस्क खोलें" } },
  },
];

const AGE: Record<string, L3> = {
  under_6_months: { en: "under 6 months", gu: "6 મહિનાથી ઓછા", hi: "6 महीने से कम" },
  "6_to_24_months": { en: "6–24 months", gu: "6–24 મહિના", hi: "6–24 महीने" },
  over_2_years: { en: "over 2 years", gu: "2 વર્ષથી વધુ", hi: "2 साल से अधिक" },
};
const REVIEW: Record<DeskReview["status"], L3> = {
  reviewed: { en: "Reviewed", gu: "જોયું", hi: "देखा" },
  actioned: { en: "Action taken", gu: "કાર્યવાહી કરી", hi: "कार्रवाई की" },
  dismissed: { en: "Not an issue", gu: "મુદ્દો નથી", hi: "मुद्दा नहीं" },
};
const UI = {
  title: { en: "My work queue", gu: "મારી કાર્યસૂચિ", hi: "मेरी कार्य सूची" } as L3,
  scope: { en: "district", gu: "જિલ્લો", hi: "जिला" } as L3,
  statewide: { en: "All districts", gu: "બધા જિલ્લા", hi: "सभी जिले" } as L3,
  lead: { en: "What needs your action, from the GUJRERA registry and what citizens check and report in this app.",
    gu: "તમારી કાર્યવાહી જરૂરી હોય તે, GUJRERA રજિસ્ટ્રી અને નાગરિકો આ એપમાં જે તપાસે અને રિપોર્ટ કરે તેના પરથી.",
    hi: "जिन पर आपकी कार्रवाई चाहिए, GUJRERA रजिस्ट्री और नागरिक इस ऐप में जो जाँचते और रिपोर्ट करते हैं उससे।" } as L3,
  projects: { en: "projects registered", gu: "નોંધાયેલા પ્રોજેક્ટ", hi: "पंजीकृत प्रोजेक्ट" } as L3,
  started: { en: "started in the last 90 days", gu: "છેલ્લા 90 દિવસમાં શરૂ", hi: "पिछले 90 दिनों में शुरू" } as L3,
  open: { en: "Open record", gu: "રેકોર્ડ ખોલો", hi: "रिकॉर्ड खोलें" } as L3,
  note: { en: "Note (optional)", gu: "નોંધ (વૈકલ્પિક)", hi: "नोट (वैकल्पिक)" } as L3,
  more: { en: "Show all", gu: "બધું બતાવો", hi: "सब दिखाएँ" } as L3,
  of: { en: "showing", gu: "બતાવ્યા", hi: "दिखाए" } as L3,
};

const fmt = (iso?: string) => (iso ? new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "");

const detail = (it: DeskItem, lang: Lang): string => {
  const days = (n: number, en: string, gu: string, hi: string) => (lang === "gu" ? `${n} ${gu}` : lang === "hi" ? `${n} ${hi}` : `${n} ${en}`);
  switch (it.type) {
    case "expiring":
      return `${fmt(it.completion)} · ${days(it.days_left ?? 0, "days left", "દિવસ બાકી", "दिन बाकी")}`;
    case "overdue":
      return `${fmt(it.completion)} · ${days(it.days_over ?? 0, "days past", "દિવસ વીતી ગયા", "दिन बीते")}`;
    case "extensions":
      return `${days(it.extensions ?? 0, "extensions", "વખત લંબાવેલ", "बार बढ़ाया")} · ${fmt(it.completion)}`;
    case "unknown_number":
      return `${days(it.lookups ?? 0, "checks", "તપાસ", "जाँच")} · ${fmt(it.first_seen)} – ${fmt(it.last_seen)} · ${it.channels ?? ""}`;
    case "ad_case":
      return `${it.kind ?? ""} · ${it.claimed_rera ?? "—"} · ${fmt(it.opened_on)}`;
    case "complaint":
      return `${it.category ?? ""} · ${it.status ?? ""} · ${days(it.age_days ?? 0, "days old", "દિવસ જૂની", "दिन पुरानी")}`;
  }
};

const ItemRow: React.FC<{ it: DeskItem; onReview: (it: DeskItem, s: DeskReview["status"], note: string) => Promise<void> }> = ({ it, onReview }) => {
  const { lang } = useSaathi();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const title = it.name ?? it.number ?? it.title ?? it.ref_no ?? it.key;
  const act = async (s: DeskReview["status"]) => {
    setBusy(true);
    try { await onReview(it, s, note); } finally { setBusy(false); }
  };
  return (
    <li className={`py-3 flex flex-col gap-2 ${it.review ? "opacity-70" : ""}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-semibold text-body text-sm break-words">{title}</div>
          {it.rera_no && it.rera_no !== title && <div className="text-[11px] text-muted font-mono break-all">{it.rera_no}</div>}
          <div className="text-xs text-muted mt-0.5">{[it.taluka && it.taluka !== it.district ? it.taluka : null, it.district].filter(Boolean).join(", ")}{(it.taluka || it.district) ? " · " : ""}{detail(it, lang)}</div>
        </div>
        {it.project_id && (
          <button type="button" onClick={() => openReport(it.project_id!)} className="text-xs px-2.5 py-1 rounded-full border border-warm-border text-body hover:border-warm-strong shrink-0">
            {t3(UI.open, lang)}
          </button>
        )}
      </div>
      {it.review ? (
        <div className="text-xs text-muted">
          <span className="px-2 py-0.5 rounded-full bg-subtle border border-warm-border font-semibold text-body">{t3(REVIEW[it.review.status], lang)}</span>{" "}
          {it.review.by} · {it.review.at.replace("T", " ")}{it.review.note ? ` · “${it.review.note}”` : ""}
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-1.5">
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t3(UI.note, lang)} aria-label={t3(UI.note, lang)}
            className="flex-1 min-w-[160px] rounded-md border border-warm-border bg-page text-body text-xs px-2 py-1" />
          {(["actioned", "reviewed", "dismissed"] as const).map((s) => (
            <button key={s} type="button" disabled={busy} onClick={() => void act(s)}
              className={`text-xs px-2.5 py-1 rounded-full border disabled:opacity-50 ${s === "actioned" ? "bg-primary-bg text-primary-text border-transparent" : "border-warm-border text-body hover:border-warm-strong"}`}>
              {t3(REVIEW[s], lang)}
            </button>
          ))}
        </div>
      )}
    </li>
  );
};

export const OfficerDeskPage: React.FC = () => {
  const { user, token, lang, logout } = useSaathi();
  const [data, setData] = useState<DeskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [all, setAll] = useState<Record<string, boolean>>({});
  const allowed = user?.role === "officer";

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setData(await fetchOfficerDashboard(token));
      setError(null);
    } catch (e) {
      if (e instanceof AuthExpiredError) logout();
      setError((e as Error).message);
    }
  }, [token, logout]);

  useEffect(() => { if (allowed) void load(); }, [allowed, load]);

  const onReview = async (it: DeskItem, status: DeskReview["status"], note: string) => {
    if (!token) return;
    await reviewDeskItem(token, it.type, it.key, status, note);
    await load();
  };

  if (!allowed) return <div className="max-w-3xl mx-auto px-4 py-8"><LoginPrompt k="loginNeededOfficer" /></div>;

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <div>
        <h2 className="font-heading text-xl font-bold text-body">
          {t3(UI.title, lang)} · {data?.district ? `${data.district} ${t3(UI.scope, lang)}` : t3(UI.statewide, lang)}
        </h2>
        <p className="text-sm text-muted mt-1 max-w-3xl">{t3(UI.lead, lang)}{data ? ` ${fmt(data.as_of)}.` : ""}</p>
      </div>
      {error && <div role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</div>}
      {data && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3">
            {SECTIONS.map((sec) => (
              <a key={sec.key} href={`#desk-${sec.key}`} className="rounded-xl border border-warm-border bg-card p-3 hover:border-warm-strong">
                <div className="flex items-center gap-2 text-muted"><Icon name={sec.icon} className="w-4 h-4" /></div>
                <div className="font-heading text-2xl font-bold text-body mt-1">{data.sections[sec.key].count.toLocaleString("en-IN")}</div>
                <div className="text-xs text-muted leading-snug">{t3(sec.title, lang)}</div>
              </a>
            ))}
          </div>
          <p className="text-xs text-muted">
            {data.total_projects.toLocaleString("en-IN")} {t3(UI.projects, lang)} · {data.new_registrations.last_90_days} {t3(UI.started, lang)}
          </p>
          {SECTIONS.map((sec) => {
            const s = data.sections[sec.key];
            const items = all[sec.key] ? s.items : s.items.slice(0, 8);
            return (
              <section key={sec.key} id={`desk-${sec.key}`} className="rounded-2xl border border-warm-border bg-card p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="font-heading font-bold text-body flex items-center gap-2">
                      <Icon name={sec.icon} className="w-4 h-4 text-brand-strong" /> {t3(sec.title, lang)}
                      <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-accent-surface border border-accent-border text-accent-amber-strong">{s.count.toLocaleString("en-IN")}</span>
                    </h3>
                    <p className="text-xs text-muted mt-1 max-w-3xl">{t3(sec.why, lang)}</p>
                    {s.age && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {Object.entries(s.age).map(([k, n]) => (
                          <span key={k} className="text-[11px] px-2 py-0.5 rounded-full bg-subtle border border-warm-border text-body">{t3(AGE[k], lang)}: {n.toLocaleString("en-IN")}</span>
                        ))}
                      </div>
                    )}
                  </div>
                  {sec.open && (
                    <button type="button" onClick={() => navigateTo(sec.open!.page)} className="text-xs px-3 py-1.5 rounded-lg border border-warm-border text-body hover:border-warm-strong shrink-0">
                      {t3(sec.open.label, lang)}
                    </button>
                  )}
                </div>
                {s.items.length === 0 ? (
                  <p className="text-sm text-muted mt-3">{t3(sec.empty, lang)}</p>
                ) : (
                  <>
                    <ul className="divide-y divide-warm-border mt-2">
                      {items.map((it) => <ItemRow key={`${it.type}:${it.key}`} it={it} onReview={onReview} />)}
                    </ul>
                    {s.items.length > items.length && (
                      <button type="button" onClick={() => setAll((a) => ({ ...a, [sec.key]: true }))} className="mt-2 text-xs font-semibold text-brand-strong">
                        {t3(UI.more, lang)} ({s.items.length})
                      </button>
                    )}
                    {s.count > s.items.length && (
                      <p className="text-[11px] text-muted mt-1">{t3(UI.of, lang)} {s.items.length} / {s.count.toLocaleString("en-IN")}</p>
                    )}
                  </>
                )}
              </section>
            );
          })}
        </>
      )}
    </div>
  );
};
