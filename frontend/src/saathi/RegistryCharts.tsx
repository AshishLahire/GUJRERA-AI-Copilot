import React from "react";
import { Lang, Overview } from "../api/gujrera";
import { ChartCard, ColumnChart, HBarChart, Part, STATUS, SegmentedBar } from "./Charts";

type L3 = { en: string; gu: string; hi: string };
const t = (s: L3, lang: Lang) => s[lang] ?? s.en;

const T = {
  section: { en: "The registry in pictures", gu: "રજિસ્ટ્રી ચિત્રોમાં", hi: "रजिस्ट्री चित्रों में" },
  standing: { en: "Where registered projects stand today", gu: "નોંધાયેલા પ્રોજેક્ટ આજે ક્યાં છે", hi: "पंजीकृत प्रोजेक्ट आज कहाँ हैं" },
  standingSub: {
    en: "Before you book, check which group your project is in. A passed completion date with no completion on record is the most common problem.",
    gu: "બુકિંગ પહેલાં તમારો પ્રોજેક્ટ કયા જૂથમાં છે તે તપાસો. પૂર્ણતા તારીખ વીતી ગઈ હોય અને પૂર્ણતા નોંધાયેલ ન હોય એ સૌથી સામાન્ય સમસ્યા છે.",
    hi: "बुकिंग से पहले देखें कि आपका प्रोजेक्ट किस समूह में है। पूर्णता तिथि बीतना और पूर्णता दर्ज न होना सबसे आम समस्या है।",
  },
  onSchedule: { en: "Ongoing, completion date ahead", gu: "ચાલુ, પૂર્ણતા તારીખ આગળ", hi: "चालू, पूर्णता तिथि आगे" },
  ending: { en: "Registration ends within 90 days", gu: "90 દિવસમાં નોંધણી પૂરી થાય છે", hi: "90 दिनों में पंजीकरण समाप्त" },
  past: { en: "Completion date passed, no completion recorded", gu: "પૂર્ણતા તારીખ વીતી, પૂર્ણતા નોંધાયેલ નથી", hi: "पूर्णता तिथि बीती, पूर्णता दर्ज नहीं" },
  completed: { en: "Completed", gu: "પૂર્ણ", hi: "पूरे" },
  lapsed: { en: "Lapsed or revoked", gu: "રદ કે મુદત પૂરી", hi: "समाप्त या रद्द" },
  years: { en: "Projects by start year", gu: "શરૂઆતના વર્ષ પ્રમાણે પ્રોજેક્ટ", hi: "शुरुआत के वर्ष के अनुसार प्रोजेक्ट" },
  yearsSub: { en: "Start date as registered with GUJRERA. The current year is to date.", gu: "GUJRERA માં નોંધાયેલી શરૂઆતની તારીખ. ચાલુ વર્ષ આજ સુધીનું.", hi: "GUJRERA में दर्ज शुरुआत की तारीख। चालू वर्ष आज तक।" },
  age: { en: "How long ago the completion date passed", gu: "પૂર્ણતા તારીખ કેટલા સમય પહેલાં વીતી", hi: "पूर्णता तिथि कितने समय पहले बीती" },
  ageSub: { en: "Projects past their date with no completion on record. Recent ones are still worth chasing for completion or an extension.", gu: "પૂર્ણતા નોંધ વિનાના, તારીખ વીતી ગયેલા પ્રોજેક્ટ. તાજેતરના પ્રોજેક્ટમાં પૂર્ણતા કે મુદત વધારા માટે પૂછવું હજી ઉપયોગી છે.", hi: "बिना पूर्णता रिकॉर्ड के, तिथि बीते प्रोजेक्ट। हाल वालों में पूर्णता या विस्तार के लिए पूछना अभी उपयोगी है।" },
  types: { en: "Projects by type", gu: "પ્રકાર પ્રમાણે પ્રોજેક્ટ", hi: "प्रकार के अनुसार प्रोजेक्ट" },
  year: { en: "Year", gu: "વર્ષ", hi: "वर्ष" },
  projects: { en: "Projects", gu: "પ્રોજેક્ટ", hi: "प्रोजेक्ट" },
  ageCol: { en: "Time since the date", gu: "તારીખ પછીનો સમય", hi: "तिथि के बाद का समय" },
  typeCol: { en: "Type", gu: "પ્રકાર", hi: "प्रकार" },
} satisfies Record<string, L3>;

const AGES: Record<string, L3> = {
  under_6_months: { en: "Under 6 months", gu: "6 મહિનાથી ઓછું", hi: "6 महीने से कम" },
  "6_to_12_months": { en: "6–12 months", gu: "6–12 મહિના", hi: "6–12 महीने" },
  "1_to_2_years": { en: "1–2 years", gu: "1–2 વર્ષ", hi: "1–2 साल" },
  "2_to_4_years": { en: "2–4 years", gu: "2–4 વર્ષ", hi: "2–4 साल" },
  over_4_years: { en: "Over 4 years", gu: "4 વર્ષથી વધુ", hi: "4 साल से अधिक" },
};
const TYPES: Record<string, L3> = {
  residential: { en: "Residential", gu: "રહેણાંક", hi: "आवासीय" },
  mixed: { en: "Mixed use", gu: "મિશ્ર ઉપયોગ", hi: "मिश्रित उपयोग" },
  commercial: { en: "Commercial", gu: "વાણિજ્યિક", hi: "वाणिज्यिक" },
  plotted: { en: "Plotted", gu: "પ્લોટ", hi: "प्लॉट" },
};

export const RegistryCharts: React.FC<{ data: Overview; lang: Lang }> = ({ data, lang }) => {
  const c = data.charts;
  if (!c) return null;
  const st = c.standing;
  const parts: Part[] = [
    { key: "on", label: t(T.onSchedule, lang), value: st.on_schedule, color: STATUS.good },
    { key: "end", label: t(T.ending, lang), value: st.ending_90_days, color: STATUS.warning },
    { key: "past", label: t(T.past, lang), value: st.past_date, color: STATUS.serious },
    { key: "done", label: t(T.completed, lang), value: st.completed, color: STATUS.neutral },
    { key: "lapsed", label: t(T.lapsed, lang), value: st.lapsed_or_revoked, color: STATUS.critical },
  ];
  const total = parts.reduce((a, p) => a + p.value, 0);
  const thisYear = String(new Date().getFullYear());
  return (
    <section aria-labelledby="registry-charts" className="flex flex-col gap-4">
      <h2 id="registry-charts" className="font-heading text-base font-bold text-body"><span className="inline-block w-1 h-4 rounded-full bg-brand mr-2 align-[-2px]" aria-hidden="true" />{t(T.section, lang)}</h2>
      <ChartCard title={t(T.standing, lang)} sub={t(T.standingSub, lang)}>
        <SegmentedBar parts={parts} total={total} />
      </ChartCard>
      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title={t(T.years, lang)} sub={t(T.yearsSub, lang)}>
          <ColumnChart head={[t(T.year, lang), t(T.projects, lang)]}
            data={c.start_years.map((y) => ({ label: y.year === "up to 2012" ? "≤2012" : y.year === thisYear ? `${y.year}*` : y.year, value: y.count }))} />
        </ChartCard>
        <ChartCard title={t(T.age, lang)} sub={t(T.ageSub, lang)}>
          <HBarChart head={[t(T.ageCol, lang), t(T.projects, lang)]}
            data={Object.entries(c.past_age).map(([k, v]) => ({ label: t(AGES[k], lang), value: v }))} />
        </ChartCard>
      </div>
      <ChartCard title={t(T.types, lang)}>
        <HBarChart head={[t(T.typeCol, lang), t(T.projects, lang)]}
          data={c.types.map((x) => ({ label: TYPES[x.type] ? t(TYPES[x.type], lang) : x.type, value: x.count }))} />
      </ChartCard>
    </section>
  );
};
