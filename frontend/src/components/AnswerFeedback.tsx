import React, { useState } from "react";
import { sendFeedback } from "../api/gujrera";
import { useSaathi } from "../saathi/context";

const REASONS: { id: string; en: string; gu: string; hi: string }[] = [
  { id: "wrong_answer", en: "Wrong answer", gu: "ખોટો જવાબ", hi: "गलत जवाब" },
  { id: "wrong_project", en: "Wrong project", gu: "ખોટો પ્રોજેક્ટ", hi: "गलत प्रोजेक्ट" },
  { id: "should_have_found", en: "Should have found it", gu: "મળવું જોઈતું હતું", hi: "मिलना चाहिए था" },
  { id: "not_relevant", en: "Not what I asked", gu: "મેં પૂછ્યું તે નહીં", hi: "मैंने यह नहीं पूछा" },
  { id: "unclear", en: "Hard to understand", gu: "સમજવું અઘરું", hi: "समझना मुश्किल" },
  { id: "wrong_language", en: "Wrong language", gu: "ખોટી ભાષા", hi: "गलत भाषा" },
];

/** 👍 / 👎 under an answer. A 👎 asks why (one tap) and goes to the admin's review queue. */
export const AnswerFeedback: React.FC<{
  question: string; answer: string; intent?: string; lang?: string; sources?: string[]; surface?: "chat" | "report";
}> = ({ question, answer, intent, lang, sources, surface = "chat" }) => {
  const { token, lang: uiLang } = useSaathi();
  const [state, setState] = useState<"idle" | "asking" | "sent" | "error">("idle");
  const [reason, setReason] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const t = (en: string, gu: string, hi: string) => ({ en, gu, hi }[uiLang] ?? en);

  const send = async (rating: "up" | "down") => {
    try {
      await sendFeedback(token, { question, answer, rating, reason: rating === "down" ? reason : null,
        comment: rating === "down" ? comment : null, intent, lang, sources, surface });
      setState("sent");
    } catch {
      setState("error");
    }
  };

  if (state === "sent") {
    return <p className="mt-2 text-[11px] text-muted">{t("Thank you: this helps us improve the answers.", "આભાર: આનાથી જવાબો સુધારવામાં મદદ મળે છે.", "धन्यवाद: इससे जवाब बेहतर करने में मदद मिलती है।")}</p>;
  }
  return (
    <div className="mt-2 text-[11px] text-muted">
      {state !== "asking" ? (
        <span className="inline-flex items-center gap-1.5">
          {t("Was this helpful?", "શું આ ઉપયોગી હતું?", "क्या यह उपयोगी था?")}
          <button type="button" onClick={() => void send("up")} aria-label="Helpful"
            className="px-2 py-0.5 rounded-full border border-warm-border hover:border-brand">👍</button>
          <button type="button" onClick={() => setState("asking")} aria-label="Not helpful"
            className="px-2 py-0.5 rounded-full border border-warm-border hover:border-brand">👎</button>
          {state === "error" && <span className="text-red-700 dark:text-red-300">{t("Could not send.", "મોકલી શકાયું નહીં.", "भेजा नहीं जा सका।")}</span>}
        </span>
      ) : (
        <div className="flex flex-col gap-1.5 rounded-lg border border-warm-border bg-subtle/60 p-2">
          <span>{t("What was wrong?", "શું ખોટું હતું?", "क्या गलत था?")}</span>
          <div className="flex flex-wrap gap-1.5">
            {REASONS.map((r) => (
              <button key={r.id} type="button" onClick={() => setReason(r.id)} aria-pressed={reason === r.id}
                className={`px-2 py-0.5 rounded-full border ${reason === r.id ? "border-brand bg-brand-soft text-body" : "border-warm-border hover:border-brand"}`}>
                {t(r.en, r.gu, r.hi)}
              </button>
            ))}
          </div>
          <input value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500}
            placeholder={t("What should it have said? (optional)", "શું કહેવું જોઈતું હતું? (વૈકલ્પિક)", "क्या कहना चाहिए था? (वैकल्पिक)")}
            className="rounded-md border border-warm-border bg-card text-body px-2 py-1" />
          <div className="flex gap-1.5">
            <button type="button" onClick={() => void send("down")} className="px-2.5 py-1 rounded-md bg-primary-bg text-primary-text font-semibold">
              {t("Send", "મોકલો", "भेजें")}
            </button>
            <button type="button" onClick={() => setState("idle")} className="px-2.5 py-1 rounded-md border border-warm-border">
              {t("Cancel", "રદ કરો", "रद्द करें")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
