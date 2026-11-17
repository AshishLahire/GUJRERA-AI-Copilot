import React from "react";
import { ForensicFinding, ForensicResult, RiskLevel } from "../types";

interface ForensicCardProps {
  forensics: ForensicResult;
  activeFindingIndex: number | null;
  onSelectFinding: (finding: ForensicFinding, index: number) => void;
  isGenuine?: boolean;
}

const RISK_BADGE_STYLES: Record<
  RiskLevel,
  { label: string; classes: string; dot: string }
> = {
  low: {
    label: "Low risk",
    classes:
      "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800",
    dot: "bg-emerald-600 dark:bg-emerald-400",
  },
  medium: {
    label: "Medium risk",
    classes:
      "bg-amber-100/90 text-amber-900 dark:bg-amber-950/70 dark:text-amber-200 border-amber-400 dark:border-amber-700",
    dot: "bg-amber-600 dark:bg-amber-400",
  },
  high: {
    label: "High risk",
    classes:
      "bg-red-50 text-red-800 dark:bg-red-950/70 dark:text-red-300 border-red-300 dark:border-red-800",
    dot: "bg-red-600 dark:bg-red-400",
  },
};

const SEVERITY_STYLES: Record<
  ForensicFinding["severity"],
  { badge: string; label: string }
> = {
  critical: {
    badge:
      "bg-red-50 text-red-800 dark:bg-red-950/70 dark:text-red-300 border-red-300 dark:border-red-800",
    label: "Critical",
  },
  warning: {
    badge:
      "bg-amber-100/80 text-amber-900 dark:bg-amber-950/60 dark:text-amber-200 border-amber-300 dark:border-amber-800",
    label: "Warning",
  },
  info: {
    badge: "bg-subtle text-muted border-warm-border",
    label: "Info",
  },
};

export const ForensicCard: React.FC<ForensicCardProps> = ({
  forensics,
  activeFindingIndex,
  onSelectFinding,
  isGenuine = false,
}) => {
  const riskMeta =
    RISK_BADGE_STYLES[forensics.risk_level] || RISK_BADGE_STYLES.low;
  const issuer = forensics.detected_issuer;
  const findings = forensics.findings || [];

  return (
    <section
      aria-label="Forensic check results"
      className="warm-card overflow-hidden"
    >
      {/* Header row: Title, Risk Level Badge + Score, Detected Issuer */}
      <div className="p-4 border-b border-warm-border flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <h3 className="font-heading text-xs font-bold uppercase tracking-wider text-body">
            Forensic Check
          </h3>
          <span
            className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-0.5 rounded-full border ${riskMeta.classes}`}
          >
            <span className={`w-2 h-2 rounded-full ${riskMeta.dot}`} />
            <span>{riskMeta.label}</span>
            <span className="font-mono font-bold ml-0.5">
              {forensics.risk_score} / 100
            </span>
          </span>
        </div>

        <div className="text-xs text-muted flex items-center gap-1.5">
          <span>Detected issuer:</span>
          {issuer ? (
            <span className="font-medium text-body">
              {issuer.name}{" "}
              <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-subtle border border-warm-border text-body">
                {issuer.issuer_id}
              </span>
            </span>
          ) : (
            <span className="italic text-muted">Not detected</span>
          )}
        </div>
      </div>

      {/* Findings list */}
      <div className="p-4 flex flex-col gap-2.5">
        {findings.length > 0 ? (
          findings.map((f, idx) => {
            const sevMeta = isGenuine
              ? { badge: "bg-subtle text-muted border-warm-border", label: "Observation" }
              : (SEVERITY_STYLES[f.severity] || SEVERITY_STYLES.info);
            const isSelected = activeFindingIndex === idx;
            const hasHighlightSpan = f.char_end > f.char_start;

            return (
              <button
                key={`${f.cue_id}-${idx}`}
                type="button"
                onClick={() => onSelectFinding(f, idx)}
                className={`w-full text-left rounded-lg border p-3 transition-colors duration-150 focus-amber ${
                  isSelected
                    ? "bg-accent-surface border-accent-amber"
                    : "bg-subtle/60 hover:bg-subtle border-warm-border"
                }`}
              >
                <div className="flex items-start justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className={`text-[11px] font-semibold px-2 py-0.5 rounded border ${sevMeta.badge}`}
                    >
                      {sevMeta.label}
                      {!isGenuine && f.points > 0 ? ` +${f.points}` : ""}
                    </span>
                    <span className="font-heading text-xs font-semibold text-body">
                      {f.title}
                    </span>
                    {f.rule_status === "unverified" && (
                      <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-card border border-warm-border text-muted">
                        unverified rule
                      </span>
                    )}
                  </div>
                  {hasHighlightSpan && (
                    <span className="text-[11px] text-accent-strong font-medium shrink-0">
                      Highlight in text ↓
                    </span>
                  )}
                </div>

                <p className="text-xs text-muted mt-1.5 leading-relaxed">
                  {f.explanation}
                </p>
                {isGenuine && (
                  <p className="text-[11px] text-muted italic mt-1">
                    Common in genuine circulars; not evidence of forgery on its own
                  </p>
                )}

                {f.evidence && (
                  <div className="mt-2 inline-flex items-center gap-1.5 max-w-full">
                    <span className="text-[11px] text-muted shrink-0">
                      Evidence:
                    </span>
                    <code className="font-mono text-xs px-2 py-0.5 rounded bg-card border border-warm-border text-body truncate">
                      {f.evidence}
                    </code>
                  </div>
                )}
              </button>
            );
          })
        ) : (
          <p className="text-xs text-muted italic py-1">
            No suspicious forensic indicators triggered on this document text.
          </p>
        )}

        {/* Required Footnote */}
        <p className="text-[11px] text-muted pt-2 border-t border-warm-border mt-1">
          Risk indicators, not a final verdict. The verdict combines these with
          the official-source match.
        </p>
      </div>
    </section>
  );
};
