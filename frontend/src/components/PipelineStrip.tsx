import React from "react";
import { OCRResult } from "../types";

interface PipelineStripProps {
  extractionCompleted: boolean;
  result?: OCRResult | null;
}

export const PipelineStrip: React.FC<PipelineStripProps> = ({
  extractionCompleted,
  result,
}) => {
  const hasOcr = Boolean(extractionCompleted || (result && result.valid));
  const hasForensics = Boolean(result?.forensics);
  const hasClaim = Boolean(
    result?.claim && (result.claim.canonical_claim_en || result.claim.status_note)
  );
  const hasMatches = Boolean(result?.matches);
  const hasVerdict = Boolean(result?.verdict);

  const steps = [
    { num: 1, name: "Extraction", done: hasOcr },
    { num: 2, name: "Forensics", done: hasForensics },
    { num: 3, name: "Claim", done: hasClaim },
    { num: 4, name: "Retrieval", done: hasMatches },
    { num: 5, name: "Verdict", done: hasVerdict },
  ];

  return (
    <div
      aria-label="Verification pipeline progress"
      className="py-1 px-3 bg-subtle/70 rounded-lg border border-warm-border flex items-center justify-between text-[11px] overflow-x-auto gap-2"
    >
      <div className="flex items-center gap-1.5 flex-1 min-w-0">
        {steps.map((step, idx) => {
          const isDone = step.done;
          return (
            <React.Fragment key={step.num}>
              <div
                className={`inline-flex items-center gap-1.5 shrink-0 transition-colors ${
                  isDone ? "text-body font-semibold" : "text-muted"
                }`}
              >
                <span
                  className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-mono font-bold shrink-0 ${
                    isDone
                      ? "bg-emerald-600 text-white dark:bg-emerald-500"
                      : "bg-muted/20 text-muted"
                  }`}
                >
                  {isDone ? "✓" : step.num}
                </span>
                <span className="truncate">{step.name}</span>
              </div>
              {idx < steps.length - 1 && (
                <div
                  className={`h-px flex-1 min-w-[12px] ${
                    steps[idx + 1].done ? "bg-emerald-500/50" : "bg-warm-border"
                  }`}
                  aria-hidden="true"
                />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};
