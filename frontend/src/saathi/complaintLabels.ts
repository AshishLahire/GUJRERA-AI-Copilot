import type { Lang } from "../api/gujrera";
import { Said, say } from "./context";

/** Complaint categories and reliefs, the same words the chat uses (gujrera/complaints/strings.py). */
export const COMPLAINT_LABEL: Record<string, Said> = {
  agent_misconduct: { en: "Agent misconduct", gu: "એજન્ટનું ગેરવર્તન", hi: "एजेंट का दुर्व्यवहार" },
  agreement_violation: { en: "Breach of agreement or extra charges", gu: "કરારનો ભંગ અથવા વધારાના ચાર્જ", hi: "अनुबंध का उल्लंघन या अतिरिक्त शुल्क" },
  amenities_not_provided: { en: "Amenities not provided", gu: "સુવિધાઓ આપી નથી", hi: "सुविधाएँ नहीं दी गईं" },
  false_advertisement: { en: "False advertisement", gu: "ખોટી જાહેરાત", hi: "झूठा विज्ञापन" },
  other: { en: "Other", gu: "અન્ય", hi: "अन्य" },
  plan_deviation: { en: "Change from approved plan", gu: "મંજૂર પ્લાનમાં ફેરફાર", hi: "स्वीकृत नक्शे में बदलाव" },
  possession_delay: { en: "Delay in possession", gu: "પઝેશનમાં વિલંબ", hi: "कब्जे में देरी" },
  structural_defect: { en: "Structural defect", gu: "બાંધકામમાં ખામી", hi: "निर्माण में खराबी" },
  refund: { en: "Refund", gu: "રિફંડ", hi: "रिफंड" },
  refund_with_interest: { en: "Refund with interest", gu: "વ્યાજ સાથે રિફંડ", hi: "ब्याज सहित रिफंड" },
  possession_with_interest: { en: "Possession, with interest for the delay", gu: "વિલંબ માટે વ્યાજ સાથે પઝેશન", hi: "देरी के ब्याज के साथ कब्जा" },
  compensation: { en: "Compensation", gu: "વળતર", hi: "मुआवजा" },
  rectification: { en: "Repair or correction of defects", gu: "ખામીઓનું સમારકામ", hi: "खराबियों की मरम्मत" },
  filed: { en: "filed", gu: "નોંધાયેલ", hi: "दर्ज" },
  under_scrutiny: { en: "under scrutiny", gu: "ચકાસણી હેઠળ", hi: "जाँच में" },
  hearing_scheduled: { en: "hearing scheduled", gu: "સુનાવણી નક્કી", hi: "सुनवाई तय" },
  order_reserved: { en: "order reserved", gu: "આદેશ અનામત", hi: "आदेश सुरक्षित" },
  disposed: { en: "disposed", gu: "નિકાલ", hi: "निपटारा" },
  withdrawn: { en: "withdrawn", gu: "પાછી ખેંચી", hi: "वापस ली गई" },
};

/** A category or relief in the interface language; an unknown key is shown readably in English. */
export function complaintLabel(key: string | null | undefined, lang: Lang): string {
  if (!key) return "";
  const t = COMPLAINT_LABEL[key];
  return t ? say(t, lang) : key.replace(/_/g, " ");
}
