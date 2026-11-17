import React, { useEffect, useRef, useState } from "react";
import { fetchLanguages } from "../api/client";
import {
  ForensicFinding,
  LanguageOption,
  MatchItem,
  OCRResult,
  VerdictColor,
} from "../types";
import { ForensicCard } from "./ForensicCard";
import { buildPlainSummary, buildReport, downloadFile, maskPrivateNames } from "../report";
import { REGION_STYLES } from "./DocumentViewer";
import { PipelineStrip } from "./PipelineStrip";

const VERDICT_BANNER_STYLES: Record<
  VerdictColor,
  { container: string; badge: string; text: string }
> = {
  red: {
    container:
      "border-red-300 dark:border-red-800 bg-red-50/90 dark:bg-red-950/40 text-red-950 dark:text-red-100",
    badge: "bg-red-600 text-white dark:bg-red-500",
    text: "text-red-700 dark:text-red-300",
  },
  green: {
    container:
      "border-emerald-300 dark:border-emerald-800 bg-emerald-50/90 dark:bg-emerald-950/40 text-emerald-950 dark:text-emerald-100",
    badge: "bg-emerald-600 text-white dark:bg-emerald-500",
    text: "text-emerald-700 dark:text-emerald-300",
  },
  amber: {
    container:
      "border-amber-300 dark:border-amber-800 bg-amber-50/90 dark:bg-amber-950/40 text-amber-950 dark:text-amber-100",
    badge: "bg-amber-600 text-white dark:bg-amber-500",
    text: "text-amber-700 dark:text-amber-300",
  },
  grey: {
    container:
      "border-warm-strong bg-subtle/80 text-body",
    badge: "bg-primary-bg text-primary-text",
    text: "text-muted",
  },
};

function formatClaimType(claimType?: string | null): string {
  if (!claimType) return "Presented as: unspecified";
  const clean = claimType.replace(/_/g, " ");
  return `Presented as: ${clean}`;
}

function renderMatchBadge(item: MatchItem) {
  const confLabel =
    item.confidence_label ||
    (item.exact_reference_match
      ? "Exact reference"
      : item.label === "strong"
      ? "Strong"
      : "Related");

  if (confLabel === "Exact reference") {
    return (
      <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-950/80 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-700">
        Exact reference
      </span>
    );
  }
  if (confLabel === "Strong") {
    return (
      <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-800 dark:bg-indigo-950/80 dark:text-indigo-300 border border-indigo-300 dark:border-indigo-700">
        Strong
      </span>
    );
  }
  return (
    <div className="inline-flex items-center gap-1.5 flex-wrap">
      <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 dark:bg-amber-950/80 dark:text-amber-200 border border-amber-300 dark:border-amber-700">
        Related
      </span>
      {item.relation_note && (
        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-card text-muted border border-warm-border">
          {item.relation_note}
        </span>
      )}
    </div>
  );
}

interface ResultPanelProps {
  result: OCRResult;
  onRetranscribe?: (jobId: string, language: string) => Promise<void>;
  loading?: boolean;
  presenterMode?: boolean;
  talkingPoint?: string | null;
  simulateUnseen?: boolean;
}

export const ResultPanel: React.FC<ResultPanelProps> = ({
  result,
  onRetranscribe,
  loading,
  presenterMode = false,
  talkingPoint,
  simulateUnseen = false,
}) => {
  const [activeTab, setActiveTab] = useState<
    "summary" | "evidence" | "checks" | "text" | "technical"
  >("summary");
  const [copied, setCopied] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [showRelatedEvidence, setShowRelatedEvidence] = useState(false);
  const [activeFindingIndex, setActiveFindingIndex] = useState<number | null>(null);
  const [highlightSpan, setHighlightSpan] = useState<{ start: number; end: number } | null>(null);
  const [languages, setLanguages] = useState<LanguageOption[]>([]);
  const [selectedLanguage, setSelectedLanguage] = useState<string>("");
  const [retranscribing, setRetranscribing] = useState<boolean>(false);
  const textBoxRef = useRef<HTMLPreElement | null>(null);
  const markRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (result.is_audio) {
      void fetchLanguages()
        .then((res) => setLanguages(res.languages || []))
        .catch(() => {});
      if (result.transcription) {
        setSelectedLanguage(result.transcription.language || "hi");
      }
    }
  }, [result.is_audio, result.transcription]);

  useEffect(() => {
    if (markRef.current && textBoxRef.current) {
      markRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [highlightSpan]);

  const verdict = result.verdict;
  const color = verdict?.color || "grey";
  const bannerStyle = VERDICT_BANNER_STYLES[color];

  const handleCopySummary = async () => {
    try {
      const summary = buildPlainSummary(result);
      await navigator.clipboard.writeText(summary);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard fallback
    }
  };

  const handleExportJson = () => {
    const report = buildReport(result);
    downloadFile(
      `pramaan-report-${result.image_hash || "result"}.json`,
      JSON.stringify(report, null, 2),
      "application/json"
    );
    setExportOpen(false);
  };

  const handleExportText = () => {
    const textReport = buildPlainSummary(result);
    downloadFile(
      `pramaan-summary-${result.image_hash || "result"}.txt`,
      textReport,
      "text/plain"
    );
    setExportOpen(false);
  };

  const handleSelectFinding = (finding: ForensicFinding, index: number) => {
    setActiveFindingIndex(index);
    if (finding.evidence && result.final_text) {
      const pos = result.final_text.indexOf(finding.evidence);
      if (pos >= 0) {
        setHighlightSpan({ start: pos, end: pos + finding.evidence.length });
        setActiveTab("text");
        return;
      }
    }
    setHighlightSpan(null);
  };

  const handleLanguageChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newLang = e.target.value;
    setSelectedLanguage(newLang);
    if (!result.job_id || !onRetranscribe) return;
    setRetranscribing(true);
    try {
      await onRetranscribe(result.job_id, newLang);
    } finally {
      setRetranscribing(false);
    }
  };

  // Evidence groupings
  const officialMatches = result.matches?.official || [];
  const debunkMatches = result.matches?.debunks || [];

  const strongOfficial = officialMatches.filter(
    (m) => m.exact_reference_match || m.label === "strong"
  );
  const relatedOfficial = officialMatches.filter(
    (m) => !m.exact_reference_match && m.label !== "strong"
  );

  const strongDebunks = debunkMatches.filter((m) => m.label === "strong");
  const relatedDebunks = debunkMatches.filter((m) => m.label !== "strong");

  const topEvidence = strongOfficial[0] || strongDebunks[0] || null;

  const nearDuplicateRefs = result.fields?.near_duplicate_references || [];
  const suspiciousDomains = result.fields?.suspicious_domains || [];

  return (
    <div className="flex flex-col gap-5 w-full">
      {/* 1. Presenter Talking Point Banner (Presenter Mode only) */}
      {presenterMode && talkingPoint && (
        <div className="p-3.5 rounded-xl border border-amber-300 dark:border-amber-700 bg-amber-50/90 dark:bg-amber-950/60 shadow-xs flex items-start gap-2.5">
          <span className="w-2 h-2 rounded-full bg-amber-600 mt-1.5 shrink-0 animate-pulse" />
          <div className="space-y-0.5">
            <span className="text-[11px] font-bold uppercase tracking-wider text-amber-900 dark:text-amber-200 block">
              Presenter Talking Point
            </span>
            <p className="text-xs text-amber-950 dark:text-amber-100 font-medium leading-relaxed">
              {talkingPoint}
            </p>
          </div>
        </div>
      )}

      {/* 2. Hero Verdict Card (Only large visual element) */}
      {verdict && (
        <section
          aria-label="Verification verdict hero"
          data-testid="verdict-banner"
          className={`warm-card p-6 border-2 shadow-sm rounded-xl transition-all ${bannerStyle.container}`}
        >
          {/* Top row: Status Tag + Simulation Tag */}
          <div className="flex items-center justify-between gap-2 flex-wrap mb-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className={`font-heading text-xs font-bold uppercase tracking-wider px-3 py-1 rounded-full shadow-xs ${bannerStyle.badge}`}
              >
                {verdict.title}
              </span>
              {simulateUnseen && (
                <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full border border-amber-300 bg-amber-100 text-amber-900 dark:bg-amber-900/60 dark:text-amber-200">
                  Simulation: Hide own fact-check
                </span>
              )}
              {/* Language badge */}
              {(result.language || result.claim?.claim_language || result.transcription?.language) && (() => {
                const langCode = result.primary_language || result.language || result.claim?.claim_language || result.transcription?.language || "en";
                const isUncertain = result.is_language_uncertain || (result.language_confidence !== undefined && result.language_confidence !== null && result.language_confidence < 0.60);
                
                // If mixed language (e.g. Hindi + English) or uncertain, use badge string
                let displayLabel = result.language_badge;
                if (!displayLabel) {
                  if (isUncertain) {
                    displayLabel = "language uncertain";
                  } else if (result.languages_present && result.languages_present.length >= 2 && result.languages_present[1].share >= 0.20) {
                    displayLabel = `${result.languages_present[0].language_name} + ${result.languages_present[1].language_name}`;
                  } else {
                    displayLabel = result.language_name || (langCode === "hi" ? "Hindi" : langCode === "hi-Latn" ? "Hinglish" : langCode === "ur" ? "Urdu" : langCode.toUpperCase());
                  }
                }

                const script = result.script ? ` · ${result.script}` : "";
                const isRTL = result.text_direction === "rtl" || langCode === "ur";
                const tooltipShares = result.languages_present && result.languages_present.length > 0
                  ? " (" + result.languages_present.map((s) => `${s.language_name} ${Math.round(s.share * 100)}%`).join(", ") + ")"
                  : "";

                return (
                  <span
                    data-testid="language-badge"
                    title={`Detected: ${displayLabel}${tooltipShares}${script}${isRTL ? " (RTL)" : ""}`}
                    className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-0.5 rounded-full border shadow-xs ${
                      isUncertain
                        ? "border-amber-300 bg-amber-50 text-amber-900 dark:bg-amber-950/60 dark:text-amber-200"
                        : "border-warm-border bg-card text-body"
                    }`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${isUncertain ? "bg-amber-500" : "bg-accent-amber"}`} />
                    <span>{displayLabel}</span>
                    {!isUncertain && <span className="font-mono text-[10px] text-muted">({langCode})</span>}
                    {isRTL && (
                      <span className="text-[9px] uppercase font-bold text-amber-700 dark:text-amber-300 ml-0.5">
                        RTL
                      </span>
                    )}
                  </span>
                );
              })()}
              {/* Engine badge showing which ran */}
              {result.engine_used && (() => {
                const eng = result.engine_used.toLowerCase();
                const isLocal = eng.includes("ollama") || eng.includes("qwen");
                const isCloud = eng.includes("gemini");
                const label = isLocal ? "Local OCR (Qwen3-VL)" : isCloud ? "Cloud OCR (Gemini)" : result.engine_used;
                return (
                  <span
                    data-testid="engine-badge"
                    title={`OCR Engine: ${result.engine_used}`}
                    className="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-0.5 rounded-full border border-warm-border bg-card text-body shadow-xs"
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${isLocal ? "bg-emerald-500" : "bg-blue-500"}`} />
                    <span>{label}</span>
                  </span>
                );
              })()}
            </div>

            {/* Actions: Export Report + Copy Summary */}
            <div className="relative flex items-center gap-2">
              <button
                type="button"
                onClick={handleCopySummary}
                className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border border-warm-border bg-card text-body hover:bg-subtle transition-colors focus-amber shadow-xs"
              >
                {copied ? (
                  <>
                    <svg className="w-3.5 h-3.5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                    <span>Copied</span>
                  </>
                ) : (
                  <>
                    <svg className="w-3.5 h-3.5 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    <span>Copy Summary</span>
                  </>
                )}
              </button>

              <div className="relative">
                <button
                  type="button"
                  onClick={() => setExportOpen(!exportOpen)}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border border-warm-border bg-card text-body hover:bg-subtle transition-colors focus-amber shadow-xs"
                >
                  <svg className="w-3.5 h-3.5 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  <span>Export</span>
                  <span className="text-[10px]">▼</span>
                </button>

                {exportOpen && (
                  <div className="absolute right-0 mt-1 w-44 rounded-xl border border-warm-border bg-card shadow-lg p-1 z-20 text-xs">
                    <button
                      type="button"
                      onClick={handleExportJson}
                      className="w-full text-left px-3 py-2 rounded-lg text-body hover:bg-subtle font-medium flex items-center justify-between"
                    >
                      <span>JSON Audit Report</span>
                      <span className="text-[10px] text-muted">.json</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleExportText}
                      className="w-full text-left px-3 py-2 rounded-lg text-body hover:bg-subtle font-medium flex items-center justify-between"
                    >
                      <span>Text Summary</span>
                      <span className="text-[10px] text-muted">.txt</span>
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* One-Sentence Primary Reason */}
          <p className="text-sm font-medium leading-relaxed mb-5 text-body">
            {verdict.reason}
          </p>

          {/* Up to 4 Key Facts in a Row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-4 border-t border-warm-border/60 text-xs">
            {/* Fact 1: Matched source */}
            <div className="space-y-1">
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted block">
                Matched Source
              </span>
              {topEvidence ? (
                <div>
                  <span className="font-semibold text-body truncate block" title={topEvidence.title}>
                    {topEvidence.title}
                  </span>
                  {topEvidence.url && (
                    <a
                      href={topEvidence.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] text-accent-amber font-semibold hover:underline mt-0.5"
                    >
                      <span>Open official proof</span>
                      <span aria-hidden="true">↗</span>
                    </a>
                  )}
                </div>
              ) : (
                <span className="text-muted font-medium">None (unmatched)</span>
              )}
            </div>

            {/* Fact 2: Forensic Risk Level */}
            <div className="space-y-1">
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted block">
                Forensic Risk
              </span>
              {result.forensics ? (
                <div className="flex items-center gap-1.5">
                  <span
                    className={`text-xs font-bold ${
                      result.forensics.risk_level === "high"
                        ? "text-red-700 dark:text-red-400"
                        : result.forensics.risk_level === "medium"
                        ? "text-amber-700 dark:text-amber-400"
                        : "text-emerald-700 dark:text-emerald-400"
                    }`}
                  >
                    {result.forensics.risk_level.toUpperCase()}
                  </span>
                  <span className="font-mono text-[11px] text-muted">
                    ({result.forensics.risk_score}/100)
                  </span>
                </div>
              ) : (
                <span className="text-muted font-medium">—</span>
              )}
            </div>

            {/* Fact 3: Presented As (never bare badge) */}
            <div className="space-y-1">
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted block">
                Claim Formulation
              </span>
              <span className="text-xs font-medium text-body block truncate">
                {formatClaimType(result.claim?.claim_type)}
              </span>
            </div>

            {/* Fact 4: Scam Narrative */}
            <div className="space-y-1">
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted block">
                Scam Narrative
              </span>
              <span className="text-xs font-medium text-body block truncate" title={result.narrative_result?.narrative_name || "No known scam pattern"}>
                {result.narrative_result?.assigned && result.narrative_result.narrative_name
                  ? result.narrative_result.narrative_name
                  : "No known scam pattern"}
              </span>
            </div>
          </div>
        </section>
      )}

      {/* Fraud Warning (for FAKE & LIKELY FAKE) or Official Record Found (for GENUINE) */}
      {verdict && (() => {
        const isFake = verdict.verdict_key === "debunked" || verdict.verdict_key === "likely_forged";
        const isGenuineDoc = verdict.verdict_key === "matches_official";
        const proofLink = topEvidence?.url || verdict.evidence_links?.[0]?.url;
        const clarificationText =
          verdict.official_clarification ||
          topEvidence?.official_fact ||
          (isFake ? (topEvidence?.snippet || "This document shows strong signs of forgery and does not originate from an official source.") : "");
        const hasFinancialOrContactRisk =
          result.forensics?.findings?.some((f) =>
            ["fee_demand", "payment_to_account", "personal_contact", "lookalike_domain"].includes(f.cue_id) ||
            /fee|payment|bank|account|phone|contact|domain|qr|upi/i.test(f.title)
          ) ||
          (result.fields?.suspicious_domains && result.fields.suspicious_domains.length > 0);
        const officialRef =
          topEvidence?.reference_no ||
          result.fields?.reference_numbers?.[0] ||
          (topEvidence?.doc_id.startsWith("OFF-") ? topEvidence.doc_id : null);

        if (isFake) {
          return (
            <div
              role="alert"
              data-testid="fraud-warning-box"
              className="rounded-xl border-2 border-red-400 dark:border-red-800 bg-red-50/95 dark:bg-red-950/70 p-4 text-xs flex flex-col gap-2.5 shadow-xs"
            >
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-2">
                  <span className="text-red-700 dark:text-red-400 font-bold text-base">⚠️</span>
                  <h3 className="font-heading font-bold text-red-900 dark:text-red-200 text-xs uppercase tracking-wider">
                    Warning: this is a fraud
                  </h3>
                </div>
                {proofLink && (
                  <a
                    href={proofLink}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 font-semibold text-red-700 hover:text-red-900 dark:text-red-300 dark:hover:text-red-100 underline text-[11px]"
                  >
                    <span>Official proof link</span>
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                )}
              </div>
              {clarificationText && (
                <p className="text-red-950 dark:text-red-100 font-medium leading-relaxed">
                  {clarificationText}
                </p>
              )}
              {hasFinancialOrContactRisk && (
                <div className="pt-2 border-t border-red-200 dark:border-red-900/60 flex items-start gap-1.5 text-red-900 dark:text-red-200 font-semibold">
                  <span className="shrink-0">🛡️</span>
                  <p>
                    Do not pay any fee, call the number, or open the link. Do not forward this message.
                  </p>
                </div>
              )}
            </div>
          );
        }

        if (isGenuineDoc) {
          return (
            <div
              role="status"
              data-testid="genuine-record-box"
              className="rounded-xl border-2 border-emerald-400 dark:border-emerald-800 bg-emerald-50/95 dark:bg-emerald-950/70 p-4 text-xs flex flex-col gap-2 shadow-xs"
            >
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-emerald-700 dark:text-emerald-400 font-bold text-base">✅</span>
                  <h3 className="font-heading font-bold text-emerald-900 dark:text-emerald-200 text-xs uppercase tracking-wider">
                    Official record found
                  </h3>
                  {officialRef && (
                    <span className="font-mono text-[11px] font-semibold px-2 py-0.5 rounded bg-emerald-100 dark:bg-emerald-900/80 text-emerald-900 dark:text-emerald-100 border border-emerald-300 dark:border-emerald-700">
                      Ref: {officialRef}
                    </span>
                  )}
                </div>
                {proofLink && (
                  <a
                    href={proofLink}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 font-semibold text-emerald-700 hover:text-emerald-900 dark:text-emerald-300 dark:hover:text-emerald-100 underline text-[11px]"
                  >
                    <span>Official source document</span>
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                )}
              </div>
              <p className="text-emerald-950 dark:text-emerald-100 font-medium leading-relaxed">
                {topEvidence?.title || "Verified against the official publication record."}
              </p>
            </div>
          );
        }

        return null;
      })()}

      {/* 3. Slim Pipeline Stepper Line */}
      <PipelineStrip extractionCompleted={Boolean(result.valid)} result={result} />

      {/* Transliterated audio warning */}
      {(result.transcript_transliterated || result.transcription?.transcript_transliterated || result.forensics?.transcript_transliterated) && (
        <div
          role="alert"
          data-testid="transliterated-audio-warning"
          className="rounded-xl border border-amber-400 dark:border-amber-700 bg-amber-50/80 dark:bg-amber-950/60 p-3.5 text-xs font-medium text-amber-950 dark:text-amber-100 flex items-start gap-2.5 shadow-xs"
        >
          <span className="font-bold text-amber-600 shrink-0">⚠️</span>
          <div>
            <p className="font-semibold text-amber-900 dark:text-amber-200">
              Script Mismatch Warning
            </p>
            <p className="mt-0.5 leading-relaxed">
              Transcript is in a different script than the spoken language: checks may miss warning signs. Enable IndicConformer for this language.
            </p>
          </div>
        </div>
      )}

      {/* Warnings: Near-duplicate references & Suspicious domains */}
      {(nearDuplicateRefs.length > 0 || suspiciousDomains.length > 0) && (
        <div className="flex flex-col gap-2.5">
          {nearDuplicateRefs.length > 0 && (
            <div
              role="alert"
              className="rounded-xl border border-amber-400 dark:border-amber-700 bg-amber-50/80 dark:bg-amber-950/60 p-3.5 text-xs font-medium text-body flex items-start gap-2.5"
            >
              <span className="font-bold text-amber-600 shrink-0">⚠</span>
              <div>
                <p>
                  Two similar reference numbers found: possible OCR misread or
                  tampering. Check the document.
                </p>
                <p className="font-mono text-[11px] text-muted mt-1">
                  {nearDuplicateRefs
                    .map((pair) => pair.join(" vs "))
                    .join(" • ")}
                </p>
              </div>
            </div>
          )}

          {suspiciousDomains.length > 0 && (
            <div
              role="alert"
              className="rounded-xl border border-amber-400 dark:border-amber-700 bg-amber-50/80 dark:bg-amber-950/60 p-3.5 text-xs text-body flex flex-col gap-2"
            >
              <div className="flex items-center gap-2 font-semibold text-amber-900 dark:text-amber-200">
                <span className="text-amber-600">⚠</span>
                <span>Lookalike or non-official domain: verify</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {suspiciousDomains.map((dom) => (
                  <span
                    key={dom}
                    className="inline-flex items-center gap-1.5 font-mono text-xs font-semibold px-2.5 py-1 rounded-md bg-amber-100/90 dark:bg-amber-950/80 text-amber-900 dark:text-amber-200 border border-amber-400 dark:border-amber-700"
                  >
                    {dom}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 4. Tab Navigation */}
      <div className="border-b border-warm-border flex items-center justify-between gap-2 overflow-x-auto">
        <div className="flex items-center gap-1">
          {[
            { key: "summary", label: "Summary" },
            { key: "evidence", label: `Evidence (${officialMatches.length + debunkMatches.length})` },
            { key: "checks", label: `Document Checks (${result.forensics?.findings.length || 0})` },
            { key: "text", label: "Extracted Text" },
            ...(!presenterMode ? [{ key: "technical", label: "Technical" }] : []),
          ].map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setActiveTab(t.key as any)}
              className={`px-3.5 py-2 text-xs font-semibold border-b-2 transition-all whitespace-nowrap ${
                activeTab === t.key
                  ? "border-accent-amber text-body font-bold"
                  : "border-transparent text-muted hover:text-body"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Audio language selector if audio */}
        {result.is_audio && (
          <div className="flex items-center gap-1.5 shrink-0 text-xs text-muted mb-1">
            <span>Audio lang:</span>
            <select
              value={selectedLanguage}
              onChange={handleLanguageChange}
              disabled={retranscribing || loading}
              className="px-2 py-0.5 text-xs rounded border border-warm-border bg-card text-body"
            >
              {languages.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* 5. Tab Panels */}

      {/* TAB 1: SUMMARY */}
      {activeTab === "summary" && (
        <div className="space-y-4">
          {/* Claim card */}
          <div className="warm-card p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted block">
                Extracted Canonical Claim
              </span>
              {result.claim?.status_note && (
                <span className="text-[10px] text-muted font-medium">
                  {result.claim.status_note.includes("older")
                    ? "Cached (older claim settings)"
                    : result.claim.status_note}
                </span>
              )}
            </div>
            {result.claim?.canonical_claim_en ? (
              <p className="text-xs font-semibold text-body bg-subtle/70 p-3 rounded-lg border border-warm-border leading-relaxed">
                {maskPrivateNames(result.claim.canonical_claim_en)}
              </p>
            ) : (
              <p className="text-xs text-muted italic">
                {result.claim?.status_note || "Claim extraction needs cloud access"}
              </p>
            )}
          </div>

          {/* Top Decisive Evidence */}
          <div className="warm-card p-4 space-y-2.5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-muted block">
              Decisive Evidence Match
            </span>
            {topEvidence ? (
              <div className="p-3.5 rounded-xl border border-warm-border bg-subtle/50 space-y-2">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-2">
                    {renderMatchBadge(topEvidence)}
                    <span className="font-mono text-[11px] font-semibold text-body">
                      {topEvidence.doc_id}
                    </span>
                  </div>
                  {topEvidence.score !== undefined && (
                    <span className="font-mono text-[11px] text-muted">
                      Score: {topEvidence.score.toFixed(3)}
                    </span>
                  )}
                </div>
                <h4 className="text-xs font-bold text-body">
                  {topEvidence.title}
                </h4>
                {topEvidence.snippet && (
                  <p className="text-[11px] text-muted leading-relaxed line-clamp-3">
                    {topEvidence.snippet}
                  </p>
                )}
                {topEvidence.url && (
                  <div className="pt-1">
                    <a
                      href={topEvidence.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs font-semibold text-accent-amber hover:underline"
                    >
                      <span>View official source document</span>
                      <span aria-hidden="true">↗</span>
                    </a>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs text-muted py-2">
                No decisive match found in the official registry or PIB debunk repository.
              </p>
            )}
          </div>

          {/* Top 3 Forensic Findings */}
          {result.forensics && result.forensics.findings.length > 0 && (
            <div className="warm-card p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted">
                  Top Forensic Findings
                </span>
                <button
                  type="button"
                  onClick={() => setActiveTab("checks")}
                  className="text-[11px] text-accent-amber font-semibold hover:underline"
                >
                  View all {result.forensics.findings.length} findings →
                </button>
              </div>

              <div className="space-y-2">
                {result.forensics.findings.slice(0, 3).map((f, idx) => (
                  <div
                    key={`${f.cue_id}-${idx}`}
                    onClick={() => handleSelectFinding(f, idx)}
                    className="p-3 rounded-lg border border-warm-border bg-subtle/40 hover:bg-subtle transition-colors cursor-pointer text-xs"
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="font-semibold text-body">{f.title}</span>
                      <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-card border border-warm-border">
                        {f.severity}
                      </span>
                    </div>
                    {f.evidence && (
                      <p className="text-[11px] text-muted font-mono bg-card/60 p-1.5 rounded border border-warm-border/50 truncate">
                        &ldquo;{f.evidence}&rdquo;
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: EVIDENCE */}
      {activeTab === "evidence" && (
        <div className="space-y-4">
          {/* Official Clarification */}
          {verdict?.official_clarification && (
            <div className="p-3.5 rounded-xl border border-emerald-300 dark:border-emerald-800 bg-emerald-50/80 dark:bg-emerald-950/40 text-xs">
              <strong className="text-emerald-900 dark:text-emerald-200 block mb-1 font-semibold">
                Official Clarification Note
              </strong>
              <p className="text-emerald-950 dark:text-emerald-100 leading-relaxed">
                {verdict.official_clarification}
              </p>
            </div>
          )}

          {/* Official Records Group */}
          <div className="warm-card p-4 space-y-3">
            <h3 className="font-heading text-xs font-bold uppercase tracking-wider text-body flex items-center justify-between">
              <span>Official Registry Records ({officialMatches.length})</span>
            </h3>

            {strongOfficial.length > 0 ? (
              <div className="space-y-2.5">
                {strongOfficial.map((m) => (
                  <div key={m.doc_id} className="p-3.5 rounded-xl border border-warm-border bg-subtle/50 space-y-1.5">
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <div className="flex items-center gap-2">
                        {renderMatchBadge(m)}
                        <span className="font-mono text-xs font-bold text-body">{m.doc_id}</span>
                      </div>
                      {m.score !== undefined && (
                        <span className="font-mono text-[11px] text-muted">
                          Similarity: {m.score.toFixed(3)}
                        </span>
                      )}
                    </div>
                    <h4 className="text-xs font-bold text-body">{m.title}</h4>
                    {m.snippet && <p className="text-[11px] text-muted leading-relaxed">{m.snippet}</p>}
                    {m.url && (
                      <a href={m.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs font-semibold text-accent-amber hover:underline pt-1">
                        <span>Open official proof</span> ↗
                      </a>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted">No strong official circular matches.</p>
            )}

            {/* Related Official Records Collapsible */}
            {relatedOfficial.length > 0 && (
              <div className="pt-2 border-t border-warm-border">
                <button
                  type="button"
                  onClick={() => setShowRelatedEvidence(!showRelatedEvidence)}
                  className="text-xs font-semibold text-muted hover:text-body flex items-center gap-1.5 py-1"
                >
                  <span>{showRelatedEvidence ? "Hide" : "Show"} {relatedOfficial.length} related circulars (same issuer, different circular)</span>
                  <span className="text-[10px]">{showRelatedEvidence ? "▲" : "▼"}</span>
                </button>

                {showRelatedEvidence && (
                  <div className="space-y-2 mt-2">
                    {relatedOfficial.map((m) => (
                      <div key={m.doc_id} className="p-3 rounded-lg border border-warm-border bg-card space-y-1 text-xs">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono font-semibold text-body">{m.doc_id}</span>
                          <span className="text-[10px] font-semibold text-muted bg-subtle px-2 py-0.5 rounded border border-warm-border">
                            {m.relation_note || "Same issuer, different circular"}
                          </span>
                        </div>
                        <p className="text-body font-medium">{m.title}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* PIB Fact-Check Debunks Group */}
          <div className="warm-card p-4 space-y-3">
            <h3 className="font-heading text-xs font-bold uppercase tracking-wider text-body">
              Fact-Check Debunk Records ({debunkMatches.length})
            </h3>

            {strongDebunks.length > 0 ? (
              <div className="space-y-2.5">
                {strongDebunks.map((m) => (
                  <div key={m.doc_id} className="p-3.5 rounded-xl border border-red-200 dark:border-red-800 bg-red-50/60 dark:bg-red-950/30 space-y-1.5">
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <div className="flex items-center gap-2">
                        {renderMatchBadge(m)}
                        <span className="font-mono text-xs font-bold text-body">{m.doc_id}</span>
                      </div>
                      {m.score !== undefined && (
                        <span className="font-mono text-[11px] text-muted">
                          Score: {m.score.toFixed(3)}
                        </span>
                      )}
                    </div>
                    <h4 className="text-xs font-bold text-body">{m.title}</h4>
                    {m.snippet && <p className="text-[11px] text-muted leading-relaxed">{m.snippet}</p>}
                    {m.url && (
                      <a href={m.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs font-semibold text-red-700 dark:text-red-400 hover:underline pt-1">
                        <span>View PIB Debunk Record</span> ↗
                      </a>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted">No strong PIB debunk matches.</p>
            )}

            {relatedDebunks.length > 0 && (
              <div className="pt-2 border-t border-warm-border space-y-2">
                <span className="text-[11px] font-semibold text-muted block">Related Debunks:</span>
                {relatedDebunks.map((m) => (
                  <div key={m.doc_id} className="p-2.5 rounded-lg border border-warm-border bg-card text-xs flex items-center justify-between gap-2">
                    <span className="text-body font-medium truncate">{m.title}</span>
                    <span className="font-mono text-[11px] text-muted shrink-0">{m.doc_id}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: DOCUMENT CHECKS */}
      {activeTab === "checks" && (
        <div className="space-y-4">
          {/* Visual Check Observations */}
          {result.visual && result.visual.analysed && (
            <div className="warm-card p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted">
                  Visual Document Check (OpenCV)
                </span>
                <span className="text-[11px] text-muted">0 automated risk points</span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                <div className="p-2.5 rounded-lg bg-subtle/60 border border-warm-border">
                  <span className="text-[10px] text-muted uppercase block">Seal / Stamp</span>
                  <span className={`font-semibold ${result.visual.has_seal ? "text-indigo-600 dark:text-indigo-400" : "text-muted"}`}>
                    {result.visual.has_seal ? "Present" : "Not detected"}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-subtle/60 border border-warm-border">
                  <span className="text-[10px] text-muted uppercase block">Signature Area</span>
                  <span className={`font-semibold ${result.visual.has_signature ? "text-emerald-600 dark:text-emerald-400" : "text-muted"}`}>
                    {result.visual.has_signature ? "Detected" : "None detected"}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-subtle/60 border border-warm-border">
                  <span className="text-[10px] text-muted uppercase block">Letterhead Emblem</span>
                  <span className={`font-semibold ${result.visual.has_emblem ? "text-amber-600 dark:text-amber-400" : "text-muted"}`}>
                    {result.visual.has_emblem ? "Found" : "None"}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-subtle/60 border border-warm-border">
                  <span className="text-[10px] text-muted uppercase block">Editing Software</span>
                  <span className={`font-semibold ${result.visual.editing_software ? "text-red-600 dark:text-red-400" : "text-muted"}`}>
                    {result.visual.editing_software || "None (clean)"}
                  </span>
                </div>
              </div>

              {result.visual.regions.length > 0 && (
                <div className="flex items-center gap-2 flex-wrap text-[11px] text-muted pt-1">
                  <span>Detected regions:</span>
                  {Array.from(new Set(result.visual.regions.map((r) => r.kind))).map((k) => (
                    <span key={k} className="inline-flex items-center gap-1">
                      <span className={`w-2.5 h-2.5 rounded-xs ${REGION_STYLES[k].chip}`} />
                      {REGION_STYLES[k].label}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Reference Numbers & Extracted Entities */}
          <div className="warm-card p-4 space-y-3">
            <span className="text-[10px] font-bold uppercase tracking-wider text-muted block">
              Reference Numbers &amp; Entities
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-lg bg-subtle/60 border border-warm-border space-y-1">
                <span className="text-[10px] text-muted uppercase block">Extracted Reference Numbers</span>
                {result.fields?.reference_numbers?.length ? (
                  <div className="space-y-1">
                    {result.fields.reference_numbers.map((ref) => (
                      <span key={ref} className="font-mono text-body font-semibold block">
                        {ref}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="text-muted italic">No reference number found</span>
                )}
              </div>

              <div className="p-3 rounded-lg bg-subtle/60 border border-warm-border space-y-1">
                <span className="text-[10px] text-muted uppercase block">Issuer &amp; Dates</span>
                <span className="text-body font-semibold block truncate">
                  Issuer: {result.claim?.claimed_issuer || result.forensics?.detected_issuer?.name || result.forensics?.detected_issuer?.issuer_id || "Unspecified"}
                </span>
                <span className="text-muted block">
                  Date: {result.claim?.effective_date || result.fields?.dates?.[0] || "None"}
                </span>
              </div>
            </div>
          </div>

          {/* Full Forensic Findings */}
          {result.forensics && (
            <ForensicCard
              forensics={result.forensics}
              activeFindingIndex={activeFindingIndex}
              onSelectFinding={handleSelectFinding}
              isGenuine={verdict?.verdict_key === "matches_official"}
            />
          )}
        </div>
      )}

      {/* TAB 4: EXTRACTED TEXT */}
      {activeTab === "text" && (
        <div className="warm-card p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-muted">
              Document Text (Overlay Filtered)
            </span>
            <span className="text-[11px] text-muted font-mono">
              {result.final_text?.length || 0} chars
            </span>
          </div>

          <pre
            ref={textBoxRef}
            className="w-full text-xs font-mono p-4 rounded-xl border border-warm-border bg-subtle/40 text-body whitespace-pre-wrap max-h-[500px] overflow-y-auto leading-relaxed select-text"
          >
            {highlightSpan && result.final_text ? (
              <>
                {result.final_text.slice(0, highlightSpan.start)}
                <mark
                  ref={markRef}
                  className="bg-accent-amber/30 text-amber-950 dark:text-amber-100 font-bold px-1 rounded-xs"
                >
                  {result.final_text.slice(highlightSpan.start, highlightSpan.end)}
                </mark>
                {result.final_text.slice(highlightSpan.end)}
              </>
            ) : (
              result.final_text || "No text extracted."
            )}
          </pre>
        </div>
      )}

      {/* TAB 5: TECHNICAL (Presenter Mode Hides This) */}
      {activeTab === "technical" && !presenterMode && (
        <div className="warm-card p-5 space-y-4 text-xs">
          <span className="text-[10px] font-bold uppercase tracking-wider text-muted block">
            Technical Audit &amp; Performance Metrics
          </span>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 rounded-lg bg-subtle/60 border border-warm-border">
              <span className="text-[10px] text-muted uppercase block">Engine</span>
              <span className="font-semibold text-body">
                {result.engine_used.toLowerCase().includes("ollama") || result.engine_used.toLowerCase().includes("qwen")
                  ? "Local OCR (Qwen3-VL)"
                  : result.engine_used.toLowerCase().includes("gemini")
                  ? "Cloud OCR (Gemini)"
                  : result.engine_used}
              </span>
            </div>
            <div className="p-3 rounded-lg bg-subtle/60 border border-warm-border">
              <span className="text-[10px] text-muted uppercase block">Extraction Time</span>
              <span className="font-mono font-semibold text-body">
                {result.time_ms ? `${result.time_ms.toFixed(0)} ms` : "Cached / instant"}
              </span>
            </div>
            <div className="p-3 rounded-lg bg-subtle/60 border border-warm-border">
              <span className="text-[10px] text-muted uppercase block">OCR Cache Status</span>
              <span className="font-semibold text-body">
                {result.older_ocr_settings
                  ? "Cached (older OCR settings)"
                  : result.from_cache
                  ? "Hit (SQLite)"
                  : "Fresh execution"}
              </span>
            </div>
            <div className="p-3 rounded-lg bg-subtle/60 border border-warm-border">
              <span className="text-[10px] text-muted uppercase block">Claim Cache Status</span>
              <span className="font-semibold text-body">
                {result.claim?.status_note?.includes("older") || result.claim?.status_note?.includes("Cached")
                  ? "Cached (older claim settings)"
                  : result.claim?.from_cache
                  ? "Hit (SQLite)"
                  : result.claim
                  ? "Fresh execution"
                  : "Not extracted"}
              </span>
            </div>
          </div>

          <div className="p-3.5 rounded-lg border border-warm-border bg-subtle/40 space-y-1.5 leading-relaxed">
            <span className="font-semibold text-body block">Calibrated Decision Thresholds</span>
            <p className="text-muted">
              Official Document Strong Match: <span className="font-mono font-bold text-body">0.88</span>.<br />
              PIB Debunk Strong Match: <span className="font-mono font-bold text-body">0.78</span>.<br />
              BM25 Possible Match: <span className="font-mono font-bold text-body">&ge; 18.0</span>.<br />
              Forensic Risk Level Cutoffs: Low &lt; 25, Medium 25–59, High &ge; 60.
            </p>
          </div>
        </div>
      )}
    </div>
  );
};
