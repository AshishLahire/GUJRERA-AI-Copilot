import React from "react";
import { Lang } from "../api/gujrera";
import { Icon } from "./Brand";
import { useSaathi } from "./context";
import type { Page } from "./HomePage";

type L3 = { en: string; gu: string; hi: string };
const t3 = (s: L3, lang: Lang) => s[lang] ?? s.en;

type Act = { label: L3; page?: Page; prompt?: L3 };
const STEPS: { icon: string; title: L3; problem: L3; acts: Act[] }[] = [
  {
    icon: "building",
    title: { en: "Find the project", gu: "પ્રોજેક્ટ શોધો", hi: "प्रोजेक्ट खोजें" },
    problem: {
      en: "Is it registered with GUJRERA, when is it due, and has its date passed? See the official record in plain language.",
      gu: "શું તે GUJRERA માં નોંધાયેલ છે, ક્યારે પૂરો થવાનો છે, અને તારીખ વીતી ગઈ છે? સત્તાવાર રેકોર્ડ સરળ ભાષામાં જુઓ.",
      hi: "क्या यह GUJRERA में पंजीकृत है, कब पूरा होना है, और क्या तारीख बीत गई? आधिकारिक रिकॉर्ड सरल भाषा में देखें।",
    },
    acts: [
      { label: { en: "Project record", gu: "પ્રોજેક્ટ રેકોર્ડ", hi: "प्रोजेक्ट रिकॉर्ड" }, page: "report" },
      { label: { en: "Ask about a project", gu: "પ્રોજેક્ટ વિશે પૂછો", hi: "प्रोजेक्ट के बारे में पूछें" }, page: "ask" },
    ],
  },
  {
    icon: "shield",
    title: { en: "Check the ad or the agent", gu: "જાહેરાત કે એજન્ટ તપાસો", hi: "विज्ञापन या एजेंट जाँचें" },
    problem: {
      en: "Ads quote invented or lapsed RERA numbers. Paste the ad text: we match it against the registry, and you can report it to GUJRERA in one click.",
      gu: "જાહેરાતો ખોટા કે રદ થયેલા RERA નંબર બતાવે છે. જાહેરાતનું લખાણ મૂકો: અમે રજિસ્ટ્રી સાથે મેળવીએ છીએ, અને તમે એક ક્લિકમાં GUJRERA ને રિપોર્ટ કરી શકો.",
      hi: "विज्ञापन नकली या समाप्त RERA नंबर दिखाते हैं। विज्ञापन का टेक्स्ट डालें: हम रजिस्ट्री से मिलाते हैं, और आप एक क्लिक में GUJRERA को रिपोर्ट कर सकते हैं।",
    },
    acts: [{ label: { en: "Check an ad", gu: "જાહેરાત તપાસો", hi: "विज्ञापन जाँचें" }, page: "check" }],
  },
  {
    icon: "law",
    title: { en: "Before you pay", gu: "ચૂકવણી પહેલાં", hi: "भुगतान से पहले" },
    problem: {
      en: "A builder cannot take more than 10% before a registered agreement (Section 13). Check your draft agreement for missing or one-sided clauses.",
      gu: "નોંધાયેલા કરાર પહેલાં બિલ્ડર 10% થી વધુ લઈ શકે નહીં (કલમ 13). તમારા ડ્રાફ્ટ કરારમાં ખૂટતી કે એકતરફી કલમો તપાસો.",
      hi: "पंजीकृत अनुबंध से पहले बिल्डर 10% से अधिक नहीं ले सकता (धारा 13)। अपने मसौदा अनुबंध में छूटी या एकतरफा शर्तें जाँचें।",
    },
    acts: [{ label: { en: "Check my agreement", gu: "મારો કરાર તપાસો", hi: "मेरा अनुबंध जाँचें" }, page: "agreement" }],
  },
  {
    icon: "eye",
    title: { en: "After booking: watch it", gu: "બુકિંગ પછી: નજર રાખો", hi: "बुकिंग के बाद: नज़र रखें" },
    problem: {
      en: "Get told when the completion date nears, the registration is extended or lapses, so you are not the last to know.",
      gu: "પૂર્ણતા તારીખ નજીક આવે, નોંધણી લંબાય કે રદ થાય ત્યારે જાણ મેળવો, જેથી તમે છેલ્લે જાણનાર ન બનો.",
      hi: "पूर्णता तिथि पास आए, पंजीकरण बढ़े या समाप्त हो तो सूचना पाएँ, ताकि आप सबसे आख़िर में न जानें।",
    },
    acts: [{ label: { en: "Watch my project", gu: "મારા પ્રોજેક્ટ પર નજર", hi: "मेरे प्रोजेक्ट पर नज़र" }, page: "watch" }],
  },
  {
    icon: "complaint",
    title: { en: "If it is delayed: get justice", gu: "વિલંબ થાય તો: ન્યાય મેળવો", hi: "देरी हो तो: न्याय पाएँ" },
    problem: {
      en: "Work out the interest the builder owes you for each month of delay (Section 18), file a complaint with that figure, then track it to a decision.",
      gu: "વિલંબના દરેક મહિના માટે બિલ્ડર તમને કેટલું વ્યાજ આપે તે ગણો (કલમ 18), તે રકમ સાથે ફરિયાદ કરો, અને નિર્ણય સુધી તેને ટ્રેક કરો.",
      hi: "देरी के हर महीने के लिए बिल्डर आपको कितना ब्याज देगा, गणना करें (धारा 18), उस राशि के साथ शिकायत करें, फिर निर्णय तक ट्रैक करें।",
    },
    acts: [
      { label: { en: "Delay interest", gu: "વિલંબ વ્યાજ", hi: "देरी ब्याज" }, page: "calc" },
      {
        label: { en: "File a complaint", gu: "ફરિયાદ કરો", hi: "शिकायत करें" },
        prompt: { en: "I want to file a complaint", gu: "મારે ફરિયાદ નોંધાવવી છે", hi: "मुझे शिकायत दर्ज करनी है" },
      },
      {
        label: { en: "Track my complaint", gu: "મારી ફરિયાદ ટ્રેક કરો", hi: "मेरी शिकायत ट्रैक करें" },
        prompt: { en: "What is the status of my complaint?", gu: "મારી ફરિયાદની સ્થિતિ શું છે?", hi: "मेरी शिकायत की स्थिति क्या है?" },
      },
    ],
  },
];

const HEAD: L3 = { en: "Buying a home: your five steps", gu: "ઘર ખરીદી: તમારાં પાંચ પગલાં", hi: "घर ख़रीदना: आपके पाँच कदम" };
const SUB: L3 = {
  en: "Each step answers a problem buyers in Gujarat actually face. Start wherever you are.",
  gu: "દરેક પગલું ગુજરાતના ખરીદદારોની ખરી સમસ્યાનો ઉકેલ છે. તમે જ્યાં છો ત્યાંથી શરૂ કરો.",
  hi: "हर कदम गुजरात के खरीदारों की असली समस्या का हल है। आप जहाँ हैं वहीं से शुरू करें।",
};

export const Journey: React.FC<{ onAsk: (q: string) => void; onNavigate: (p: Page) => void }> = ({ onAsk, onNavigate }) => {
  const { lang } = useSaathi();
  return (
    <section aria-labelledby="journey-h">
      <h2 id="journey-h" className="font-heading text-base font-bold text-body">{t3(HEAD, lang)}</h2>
      <p className="text-xs text-muted mt-0.5 mb-3">{t3(SUB, lang)}</p>
      <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {STEPS.map((s, i) => (
          <li key={i} className="rounded-xl border border-warm-border bg-card p-4 flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <span className="w-7 h-7 shrink-0 rounded-full bg-brand text-primary-text font-bold text-sm flex items-center justify-center" aria-hidden="true">{i + 1}</span>
              <span className="w-7 h-7 shrink-0 rounded-lg bg-brand-soft text-brand-strong flex items-center justify-center"><Icon name={s.icon} className="w-4 h-4" /></span>
            </div>
            <h3 className="text-sm font-semibold text-body leading-snug">{t3(s.title, lang)}</h3>
            <p className="text-xs text-muted leading-relaxed flex-1">{t3(s.problem, lang)}</p>
            <div className="flex flex-wrap gap-1.5 pt-1">
              {s.acts.map((a, j) => (
                <button
                  key={j}
                  type="button"
                  onClick={() => (a.prompt ? onAsk(t3(a.prompt, lang)) : a.page && onNavigate(a.page))}
                  className={`text-xs px-2.5 py-1 rounded-full border ${j === 0 ? "bg-primary-bg text-primary-text border-transparent" : "border-warm-border text-body hover:border-warm-strong"}`}
                >
                  {t3(a.label, lang)}
                </button>
              ))}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
};
