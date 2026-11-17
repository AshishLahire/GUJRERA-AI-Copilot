import React, { useState } from "react";
import { reportAd } from "../api/gujrera";
import { Icon } from "./Brand";
import { useSaathi } from "./context";
import { En } from "./En";
import { tr } from "./strings";

/** Verdicts a citizen can report (the server re-checks the ad and decides). */
export const REPORTABLE = new Set(["not_found", "no_rera_number", "lapsed_or_revoked", "mismatch", "registered_with_warnings"]);

/** "Report this ad to GUJRERA": consent line, one button, then a receipt. */
export const ReportAd: React.FC<{ text: string; channel: "text" | "upload" | "chat"; compact?: boolean }> = ({ text, channel, compact }) => {
  const { lang, token } = useSaathi();
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [msg, setMsg] = useState<string | null>(null);

  const send = async () => {
    setState("sending");
    try {
      const r = await reportAd(text, channel, token);
      setMsg(r.duplicate ? `${r.receipt} · already reported` : r.receipt);
      setState("sent");
    } catch (e) {
      setMsg((e as Error).message);
      setState("error");
    }
  };

  if (state === "sent") {
    return (
      <div className={`flex items-center gap-2 ${compact ? "mt-2 text-xs" : "text-sm"} text-body`}>
        <span className="w-5 h-5 rounded-full bg-brand-soft text-brand-strong flex items-center justify-center"><Icon name="flag" className="w-3 h-3" /></span>
        <span>{tr("reportSent", lang)} <span className="text-muted font-mono">{msg}</span></span>
      </div>
    );
  }
  return (
    <div className={compact ? "mt-2 pt-2 border-t border-warm-border" : "rounded-xl border border-warm-border bg-card p-4"}>
      <button
        type="button"
        onClick={() => void send()}
        disabled={state === "sending" || text.trim().length < 20}
        className={`inline-flex items-center gap-2 rounded-lg bg-primary-bg text-primary-text font-semibold leading-tight disabled:opacity-40 ${compact ? "px-3 py-1.5 text-xs" : "px-4 py-2 text-sm"}`}
      >
        <Icon name="flag" className="w-4 h-4" />
        <span className="text-left">
          {state === "sending" ? "…" : tr("reportTitle", lang)}
          {state !== "sending" && <En k="reportTitle" className="font-normal" />}
        </span>
      </button>
      <p className={`mt-2 text-muted leading-snug ${compact ? "text-[11px]" : "text-xs"}`}>
        {tr("reportConsent", lang)}
        {lang !== "en" && <span lang="en" className="block opacity-80">{tr("reportConsent", "en")}</span>}
      </p>
      {state === "error" && <p role="alert" className="mt-1 text-xs text-red-700 dark:text-red-300">{msg}</p>}
    </div>
  );
};
