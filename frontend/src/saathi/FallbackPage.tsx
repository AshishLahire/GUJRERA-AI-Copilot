import React from "react";
import { Said, say, useUiLang } from "./context";

/**
 * Shown when the Saathi service cannot be reached: fixed answers to common questions and links to the
 * official GUJRERA portal, so a citizen is never left with only an error. Nothing here needs the server
 * or the AI model. The answers state the RERA Act only; anything about a particular project goes to the portal.
 */

const PORTAL = "https://gujrera.gujarat.gov.in/";

const T: Record<string, Said> = {
  title: { en: "GujRERA Saathi is not available right now", gu: "GujRERA સાથી અત્યારે ઉપલબ્ધ નથી", hi: "GujRERA साथी अभी उपलब्ध नहीं है" },
  lead: {
    en: "We could not reach the service. Answers to common questions are below, and the official GUJRERA portal has every project's record. This page checks again by itself.",
    gu: "સેવા સુધી પહોંચી શકાયું નથી. સામાન્ય પ્રશ્નોના જવાબ નીચે છે, અને દરેક પ્રોજેક્ટનો રેકોર્ડ સત્તાવાર GUJRERA પોર્ટલ પર છે. આ પાનું જાતે ફરી તપાસે છે.",
    hi: "सेवा तक पहुँच नहीं हो सकी। आम सवालों के जवाब नीचे हैं, और हर प्रोजेक्ट का रिकॉर्ड आधिकारिक GUJRERA पोर्टल पर है। यह पेज अपने आप फिर जाँचता है।",
  },
  retry: { en: "Try again", gu: "ફરી પ્રયાસ કરો", hi: "फिर कोशिश करें" },
  checking: { en: "Checking…", gu: "તપાસી રહ્યા છીએ…", hi: "जाँच रहे हैं…" },
  portal: { en: "Open the GUJRERA portal", gu: "GUJRERA પોર્ટલ ખોલો", hi: "GUJRERA पोर्टल खोलें" },
  faq: { en: "Common questions", gu: "સામાન્ય પ્રશ્નો", hi: "आम सवाल" },
  note: {
    en: "These answers summarise the Real Estate (Regulation and Development) Act, 2016. They are general information, not legal advice; for a particular project, check its record on the portal.",
    gu: "આ જવાબો રિયલ એસ્ટેટ (નિયમન અને વિકાસ) અધિનિયમ, 2016 નો સાર છે. તે સામાન્ય માહિતી છે, કાનૂની સલાહ નથી; કોઈ ચોક્કસ પ્રોજેક્ટ માટે પોર્ટલ પર તેનો રેકોર્ડ જુઓ.",
    hi: "ये जवाब रियल एस्टेट (विनियमन और विकास) अधिनियम, 2016 का सार हैं। यह सामान्य जानकारी है, कानूनी सलाह नहीं; किसी खास प्रोजेक्ट के लिए पोर्टल पर उसका रिकॉर्ड देखें।",
  },
};

const FAQ: { q: Said; a: Said }[] = [
  {
    q: { en: "How do I check whether a project is registered?", gu: "પ્રોજેક્ટ નોંધાયેલ છે કે નહીં તે કેવી રીતે તપાસું?", hi: "प्रोजेक्ट पंजीकृत है या नहीं, कैसे जाँचूँ?" },
    a: {
      en: "Search for the project or its RERA registration number on the GUJRERA portal. A project on land over 500 square metres, or with more than eight apartments, must be registered before it is advertised or sold (Section 3).",
      gu: "GUJRERA પોર્ટલ પર પ્રોજેક્ટ અથવા તેનો RERA નોંધણી નંબર શોધો. 500 ચોરસ મીટરથી વધુ જમીન પરનો અથવા આઠથી વધુ એપાર્ટમેન્ટવાળો પ્રોજેક્ટ જાહેરાત કે વેચાણ પહેલાં નોંધાયેલો હોવો જોઈએ (કલમ 3).",
      hi: "GUJRERA पोर्टल पर प्रोजेक्ट या उसका RERA पंजीकरण नंबर खोजें। 500 वर्ग मीटर से अधिक भूमि पर या आठ से अधिक अपार्टमेंट वाला प्रोजेक्ट विज्ञापन या बिक्री से पहले पंजीकृत होना चाहिए (धारा 3)।",
    },
  },
  {
    q: { en: "The builder has not given possession on time. What can I do?", gu: "બિલ્ડરે સમયસર પઝેશન આપ્યું નથી. હું શું કરી શકું?", hi: "बिल्डर ने समय पर पज़ेशन नहीं दिया। मैं क्या कर सकता हूँ?" },
    a: {
      en: "You may withdraw and get your money back with interest and compensation, or stay in the project and get interest for every month of delay until possession (Section 18).",
      gu: "તમે પ્રોજેક્ટમાંથી નીકળી વ્યાજ અને વળતર સાથે તમારા પૈસા પાછા મેળવી શકો છો, અથવા પ્રોજેક્ટમાં રહી પઝેશન સુધી વિલંબના દરેક મહિનાનું વ્યાજ મેળવી શકો છો (કલમ 18).",
      hi: "आप प्रोजेक्ट से हटकर ब्याज और मुआवज़े के साथ अपना पैसा वापस ले सकते हैं, या प्रोजेक्ट में रहकर पज़ेशन तक देरी के हर महीने का ब्याज ले सकते हैं (धारा 18)।",
    },
  },
  {
    q: { en: "How much can the builder take before the agreement for sale?", gu: "વેચાણ કરાર પહેલાં બિલ્ડર કેટલી રકમ લઈ શકે?", hi: "बिक्री अनुबंध से पहले बिल्डर कितनी राशि ले सकता है?" },
    a: {
      en: "Not more than 10% of the cost of the apartment, plot or building as an advance, unless a written agreement for sale is first registered (Section 13).",
      gu: "લેખિત વેચાણ કરાર પહેલાં નોંધાયા વિના એપાર્ટમેન્ટ, પ્લોટ કે મકાનની કિંમતના 10% થી વધુ એડવાન્સ નહીં (કલમ 13).",
      hi: "लिखित बिक्री अनुबंध पहले पंजीकृत किए बिना अपार्टमेंट, प्लॉट या भवन की कीमत के 10% से अधिक अग्रिम नहीं (धारा 13)।",
    },
  },
  {
    q: { en: "There are structural defects after possession. Who fixes them?", gu: "પઝેશન પછી બાંધકામમાં ખામી છે. કોણ સુધારશે?", hi: "पज़ेशन के बाद निर्माण में खराबी है। कौन ठीक करेगा?" },
    a: {
      en: "If you report a structural defect or poor workmanship within five years of possession, the builder must fix it free of charge within 30 days (Section 14(3)).",
      gu: "પઝેશનના પાંચ વર્ષની અંદર બાંધકામની ખામી કે નબળી કારીગરી જણાવો તો બિલ્ડરે તે 30 દિવસમાં વિના મૂલ્યે સુધારવી પડે (કલમ 14(3)).",
      hi: "पज़ेशन के पाँच साल के भीतर निर्माण दोष या खराब कारीगरी बताने पर बिल्डर को उसे 30 दिनों में मुफ़्त ठीक करना होगा (धारा 14(3))।",
    },
  },
  {
    q: { en: "How do I file a complaint?", gu: "ફરિયાદ કેવી રીતે કરું?", hi: "शिकायत कैसे करूँ?" },
    a: {
      en: "A buyer can file a complaint with the Authority against a promoter, allottee or agent (Section 31). File it on the GUJRERA portal; keep your agreement, payment receipts and letters ready.",
      gu: "ખરીદનાર પ્રમોટર, ફાળવણીદાર કે એજન્ટ સામે ઓથોરિટીમાં ફરિયાદ કરી શકે છે (કલમ 31). GUJRERA પોર્ટલ પર ફરિયાદ કરો; તમારો કરાર, ચુકવણીની રસીદો અને પત્રો તૈયાર રાખો.",
      hi: "खरीदार प्रमोटर, आवंटी या एजेंट के खिलाफ प्राधिकरण में शिकायत कर सकता है (धारा 31)। GUJRERA पोर्टल पर शिकायत करें; अपना अनुबंध, भुगतान रसीदें और पत्र तैयार रखें।",
    },
  },
];

export const FallbackPage: React.FC<{ onRetry: () => void; checking: boolean }> = ({ onRetry, checking }) => {
  const lang = useUiLang();
  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 py-8 flex flex-col gap-6">
      <section role="alert" className="rounded-xl border border-accent-border bg-accent-surface p-5">
        <h2 className="font-heading font-bold text-lg text-body">{say(T.title, lang)}</h2>
        <p className="mt-2 text-sm text-body leading-relaxed">{say(T.lead, lang)}</p>
        <div className="mt-4 flex flex-wrap gap-3">
          <button type="button" onClick={onRetry} disabled={checking}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-on-brand disabled:opacity-60">
            {checking ? say(T.checking, lang) : say(T.retry, lang)}
          </button>
          <a href={PORTAL} target="_blank" rel="noopener noreferrer"
            className="rounded-lg border border-warm-border bg-card px-4 py-2 text-sm font-semibold text-body underline-offset-2 hover:underline">
            {say(T.portal, lang)} <span aria-hidden="true">↗</span>
          </a>
        </div>
      </section>
      <section aria-labelledby="fallback-faq">
        <h2 id="fallback-faq" className="font-heading font-bold text-base text-body">{say(T.faq, lang)}</h2>
        <div className="mt-3 flex flex-col gap-2">
          {FAQ.map((f, i) => (
            <details key={i} className="rounded-lg border border-warm-border bg-card p-4" open={i === 0}>
              <summary className="cursor-pointer font-semibold text-sm text-body">{say(f.q, lang)}</summary>
              <p className="mt-2 text-sm text-body leading-relaxed">{say(f.a, lang)}</p>
            </details>
          ))}
        </div>
        <p className="mt-4 text-xs text-muted leading-relaxed">{say(T.note, lang)}</p>
      </section>
    </div>
  );
};
