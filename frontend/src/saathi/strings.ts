import { Lang } from "../api/gujrera";

// Interface text for the GujRERA Saathi shell. Answers come from the backend in the user's language.
// Gujarati and Hindi need a native-speaker review before a public pilot.
const STRINGS = {
  brand: { en: "GujRERA Saathi", gu: "ગુજરેરા સાથી", hi: "गुजरेरा साथी" },
  tagline: {
    en: "Your companion for every home question",
    gu: "તમારા ઘરના દરેક પ્રશ્નનો સાથી",
    hi: "आपके घर के हर सवाल का साथी",
  },
  navHome: { en: "Home", gu: "હોમ", hi: "होम" },
  navAsk: { en: "Ask Saathi", gu: "સાથીને પૂછો", hi: "साथी से पूछें" },
  navCheck: { en: "Check an ad", gu: "જાહેરાત તપાસો", hi: "विज्ञापन जाँचें" },
  navPromoter: { en: "For promoters", gu: "પ્રમોટર માટે", hi: "प्रमोटर के लिए" },
  navOfficer: { en: "For officers", gu: "અધિકારીઓ માટે", hi: "अधिकारियों के लिए" },
  login: { en: "Log in", gu: "લોગિન", hi: "लॉगिन" },
  logout: { en: "Log out", gu: "લોગઆઉટ", hi: "लॉगआउट" },
  heroTitle: {
    en: "Check before you buy. Ask before you pay.",
    gu: "ખરીદતા પહેલાં તપાસો. ચૂકવતા પહેલાં પૂછો.",
    hi: "खरीदने से पहले जाँचें। भुगतान से पहले पूछें।",
  },
  heroBody: {
    en: "Ask about any registered project or builder, check a property ad, file a complaint or know your rights, in Gujarati, Hindi or English. Every answer shows the record it comes from.",
    gu: "કોઈ પણ નોંધાયેલ પ્રોજેક્ટ કે બિલ્ડર વિશે પૂછો, મિલકતની જાહેરાત તપાસો, ફરિયાદ નોંધાવો અથવા તમારા અધિકારો જાણો — ગુજરાતી, હિન્દી કે અંગ્રેજીમાં. દરેક જવાબ સાથે તેનો રેકોર્ડ દેખાય છે.",
    hi: "किसी भी पंजीकृत प्रोजेक्ट या बिल्डर के बारे में पूछें, संपत्ति का विज्ञापन जाँचें, शिकायत दर्ज करें या अपने अधिकार जानें — गुजराती, हिंदी या अंग्रेज़ी में। हर जवाब के साथ उसका रिकॉर्ड दिखता है।",
  },
  heroPlaceholder: {
    en: "e.g. When will I get possession of Mangal Square?",
    gu: "દા.ત. મંગલ સ્ક્વેર નું પઝેશન ક્યારે મળશે?",
    hi: "उदा. मंगल स्क्वेयर का पज़ेशन कब मिलेगा?",
  },
  ask: { en: "Ask", gu: "પૂછો", hi: "पूछें" },
  askIntro: {
    en: "Ask about a project, builder, agent, complaint or your rights, in Gujarati, Hindi or English. Every answer cites the record it comes from, or says it was not found.",
    gu: "પ્રોજેક્ટ, બિલ્ડર, એજન્ટ, ફરિયાદ કે તમારા અધિકારો વિશે ગુજરાતી, હિન્દી કે અંગ્રેજીમાં પૂછો. દરેક જવાબ તેનો રેકોર્ડ બતાવે છે, અથવા કહે છે કે મળ્યું નથી.",
    hi: "प्रोजेक्ट, बिल्डर, एजेंट, शिकायत या अपने अधिकारों के बारे में गुजराती, हिंदी या अंग्रेज़ी में पूछें। हर जवाब अपना रिकॉर्ड बताता है, या कहता है कि नहीं मिला।",
  },
  tileProjectTitle: { en: "Know a project or builder", gu: "પ્રોજેક્ટ કે બિલ્ડરને જાણો", hi: "प्रोजेक्ट या बिल्डर को जानें" },
  tileProjectBody: {
    en: "Registration, completion date, delays, complaints and orders.",
    gu: "નોંધણી, પૂર્ણતા તારીખ, વિલંબ, ફરિયાદો અને આદેશો.",
    hi: "पंजीकरण, पूरा होने की तारीख, देरी, शिकायतें और आदेश।",
  },
  tileCheckTitle: { en: "Check an ad before you pay", gu: "ચૂકવતા પહેલાં જાહેરાત તપાસો", hi: "भुगतान से पहले विज्ञापन जाँचें" },
  tileCheckBody: {
    en: "Upload a brochure, hoarding photo or WhatsApp offer. We match it with the registry.",
    gu: "બ્રોશર, હોર્ડિંગનો ફોટો અથવા વોટ્સએપ ઓફર મૂકો. અમે તેને રજિસ્ટ્રી સાથે મેળવીએ છીએ.",
    hi: "ब्रोशर, होर्डिंग की फोटो या व्हाट्सऐप ऑफर डालें। हम इसे रजिस्ट्री से मिलाते हैं।",
  },
  tileComplaintTitle: { en: "File or track a complaint", gu: "ફરિયાદ નોંધાવો કે તેની સ્થિતિ જાણો", hi: "शिकायत दर्ज करें या उसकी स्थिति जानें" },
  tileComplaintBody: {
    en: "Tell your problem in your words; Saathi fills the form and gives you a tracking code.",
    gu: "તમારી સમસ્યા તમારા શબ્દોમાં કહો; સાથી ફોર્મ ભરે છે અને ટ્રેકિંગ કોડ આપે છે.",
    hi: "अपनी समस्या अपने शब्दों में बताएँ; साथी फॉर्म भरता है और ट्रैकिंग कोड देता है।",
  },
  tileRightsTitle: { en: "Know your rights", gu: "તમારા અધિકારો જાણો", hi: "अपने अधिकार जानें" },
  tileRightsBody: {
    en: "Answers from the RERA Act and the Gujarat RERA Rules, with the section shown.",
    gu: "RERA કાયદા અને ગુજરાત RERA નિયમોમાંથી જવાબ, કલમ સાથે.",
    hi: "RERA अधिनियम और गुजरात RERA नियमों से जवाब, धारा के साथ।",
  },
  rolesTitle: { en: "One assistant for everyone", gu: "દરેક માટે એક સાથી", hi: "सबके लिए एक साथी" },
  roleBuyer: { en: "Home buyers", gu: "ઘર ખરીદનાર", hi: "घर खरीदार" },
  roleBuyerBody: {
    en: "Check projects and ads, ask in your language, file and track complaints.",
    gu: "પ્રોજેક્ટ અને જાહેરાતો તપાસો, તમારી ભાષામાં પૂછો, ફરિયાદ નોંધાવો અને ટ્રેક કરો.",
    hi: "प्रोजेक्ट और विज्ञापन जाँचें, अपनी भाषा में पूछें, शिकायत दर्ज करें और ट्रैक करें।",
  },
  rolePromoter: { en: "Promoters and agents", gu: "પ્રમોટર અને એજન્ટ", hi: "प्रमोटर और एजेंट" },
  rolePromoterBody: {
    en: "Your dues, notices, quarterly reports and registration deadlines in one place.",
    gu: "તમારી બાકી ચુકવણી, નોટિસ, ત્રિમાસિક અહેવાલ અને નોંધણીની મુદત એક જગ્યાએ.",
    hi: "आपके बकाया, नोटिस, तिमाही रिपोर्ट और पंजीकरण की समय-सीमा एक जगह।",
  },
  roleOfficer: { en: "GUJRERA officers", gu: "GUJRERA અધિકારીઓ", hi: "GUJRERA अधिकारी" },
  roleOfficerBody: {
    en: "Ask in plain language and get tables, charts and the query used.",
    gu: "સાદી ભાષામાં પૂછો અને કોષ્ટક, ચાર્ટ અને વપરાયેલી ક્વેરી મેળવો.",
    hi: "सरल भाषा में पूछें और तालिका, चार्ट और इस्तेमाल हुई क्वेरी पाएँ।",
  },
  trustTitle: { en: "Built to be trusted", gu: "ભરોસા માટે બનાવેલું", hi: "भरोसे के लिए बनाया गया" },
  trust1: {
    en: "Answers only from RERA records, with the source shown, or \"not found\".",
    gu: "જવાબ ફક્ત RERA રેકોર્ડમાંથી, સ્રોત સાથે — અથવા \"મળ્યું નથી\".",
    hi: "जवाब केवल RERA रिकॉर्ड से, स्रोत के साथ — या \"नहीं मिला\"।",
  },
  trust2: {
    en: "Self-hosted AI models: no data leaves the server, no per-question fees.",
    gu: "સ્વ-હોસ્ટેડ AI મોડેલ: ડેટા સર્વરની બહાર જતો નથી, પ્રશ્ન દીઠ કોઈ ફી નથી.",
    hi: "स्व-होस्टेड AI मॉडल: डेटा सर्वर से बाहर नहीं जाता, प्रति सवाल कोई शुल्क नहीं।",
  },
  trust3: {
    en: "Promoters see only their own data; officers' queries are read-only and logged.",
    gu: "પ્રમોટર ફક્ત પોતાનો ડેટા જુએ છે; અધિકારીઓની ક્વેરી ફક્ત વાંચવા માટે અને લોગ થાય છે.",
    hi: "प्रमोटर केवल अपना डेटा देखते हैं; अधिकारियों की क्वेरी केवल पढ़ने के लिए और लॉग होती है।",
  },
  footer: {
    en: "Prototype on demo data by YellowSense Technologies for the AI CoE Innovation Challenge. Not an official GUJRERA service.",
    gu: "AI CoE ઇનોવેશન ચેલેન્જ માટે YellowSense Technologies નો ડેમો ડેટા પરનો પ્રોટોટાઇપ. આ સત્તાવાર GUJRERA સેવા નથી.",
    hi: "AI CoE इनोवेशन चैलेंज के लिए YellowSense Technologies का डेमो डेटा पर प्रोटोटाइप। यह आधिकारिक GUJRERA सेवा नहीं है।",
  },
  loginNeededPromoter: {
    en: "Log in with a promoter or agent account to see your compliance dashboard.",
    gu: "તમારું અનુપાલન ડેશબોર્ડ જોવા પ્રમોટર અથવા એજન્ટ ખાતાથી લોગિન કરો.",
    hi: "अपना अनुपालन डैशबोर्ड देखने के लिए प्रमोटर या एजेंट खाते से लॉगिन करें।",
  },
  loginNeededOfficer: {
    en: "Log in with a GUJRERA officer account to use analytics.",
    gu: "એનાલિટિક્સ માટે GUJRERA અધિકારી ખાતાથી લોગિન કરો.",
    hi: "एनालिटिक्स के लिए GUJRERA अधिकारी खाते से लॉगिन करें।",
  },
  dashTitle: { en: "Compliance dashboard", gu: "અનુપાલન ડેશબોર્ડ", hi: "अनुपालन डैशबोर्ड" },
  dashAsk: { en: "Ask about your compliance", gu: "તમારા અનુપાલન વિશે પૂછો", hi: "अपने अनुपालन के बारे में पूछें" },
  analyticsTitle: { en: "Regulatory analytics", gu: "નિયમનકારી એનાલિટિક્સ", hi: "नियामक एनालिटिक्स" },
  analyticsPlaceholder: {
    en: "e.g. Which promoters in Surat have the most delayed projects?",
    gu: "દા.ત. સુરતમાં સૌથી વધુ વિલંબિત પ્રોજેક્ટ ધરાવતા બિલ્ડર કયા છે?",
    hi: "उदा. सूरत में सबसे ज़्यादा देरी वाले बिल्डर कौन से हैं?",
  },
  run: { en: "Run", gu: "ચલાવો", hi: "चलाएँ" },
  statDues: { en: "Pending dues", gu: "બાકી ચુકવણી", hi: "बकाया भुगतान" },
  statOverdue: { en: "Overdue", gu: "મુદત વીતી ગયેલી", hi: "नियत तारीख निकल चुकी" },
  statNotices: { en: "Notices to answer", gu: "જવાબ આપવાની નોટિસ", hi: "जवाब देने वाले नोटिस" },
  statEnding: { en: "Registrations ending ≤ 6 months", gu: "6 મહિનામાં પૂરી થતી નોંધણી", hi: "6 महीनों में समाप्त होने वाले पंजीकरण" },
  attention: { en: "What needs your attention", gu: "શેના પર ધ્યાન આપવું", hi: "किस पर ध्यान देना है" },
  qprNotFiled: { en: "Quarterly reports not filed", gu: "ફાઈલ ન થયેલા ત્રિમાસિક અહેવાલ", hi: "दाखिल न हुई तिमाही रिपोर्ट" },
  registrations: { en: "Registrations", gu: "નોંધણીઓ", hi: "पंजीकरण" },
  reports: { en: "Standard reports", gu: "પ્રમાણભૂત રિપોર્ટ", hi: "मानक रिपोर्ट" },
} as const;

export type StringKey = keyof typeof STRINGS;

export function tr(key: StringKey, lang: Lang): string {
  return STRINGS[key][lang] ?? STRINGS[key].en;
}
