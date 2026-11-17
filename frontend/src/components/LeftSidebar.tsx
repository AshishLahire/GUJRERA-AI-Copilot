import React, { useRef, useState } from "react";
import { resolveApiUrl } from "../api/client";
import {
  formatNarrativeLabel,
  SampleGroup,
  SampleItem,
} from "../types";

interface LeftSidebarProps {
  samples: SampleItem[];
  selectedSampleId: string | null;
  onSelectSample: (sample: SampleItem) => void;
  onUploadFile: (file: File) => void;
  onUploadAudio: (file: File) => void;
  onCheckText: (text: string) => void;
  offlineMode?: boolean;
  allowFallback: boolean;
  onToggleFallback: (next: boolean) => void;
  simulateUnseen: boolean;
  onToggleSimulateUnseen: (next: boolean) => void;
  ollamaEnabled: boolean | null;
  loading: boolean;
  footer?: React.ReactNode;
}

// Typical WhatsApp forwards (from the members_4_5 claim-extraction console).
const TEXT_SAMPLES: { label: string; text: string }[] = [
  {
    label: "English: RBI ₹500 notes",
    text:
      "BREAKING: Reserve Bank of India has announced that all Rs 500 notes will be withdrawn " +
      "from circulation from 1 November 2026. Exchange them at any bank before 30 November. Forward to all!",
  },
  {
    label: "Hindi: free gas cylinder",
    text:
      "सरकार ने घोषणा की है कि 1 नवंबर से सभी राशन कार्ड धारकों को मुफ्त गैस सिलेंडर मिलेगा। " +
      "अपना आधार कार्ड तुरंत अपडेट कराएं।",
  },
  {
    label: "Hinglish: Aadhaar deadline",
    text:
      "Urgent! UIDAI ne bola hai ki 31 December ke baad Aadhaar card bina update kiye band ho jayega. " +
      "Jaldi se is link pe click karke update karo.",
  },
  {
    label: "English: Mudra loan fee",
    text:
      "Congratulations! Your loan of Rs 5,00,000 under Pradhan Mantri Mudra Yojana has been approved. " +
      "Pay a processing fee of Rs 2,100 to account no. 3456789012 to release the amount within 24 hours.",
  },
];

const TABS: { key: SampleGroup; label: string }[] = [
  { key: "fake", label: "Fake notices" },
  { key: "genuine", label: "Genuine" },
  { key: "synthetic", label: "Synthetic" },
];

export const LeftSidebar: React.FC<LeftSidebarProps> = ({
  samples,
  selectedSampleId,
  onSelectSample,
  onUploadFile,
  onUploadAudio,
  onCheckText,
  offlineMode = false,
  allowFallback,
  onToggleFallback,
  simulateUnseen,
  onToggleSimulateUnseen,
  ollamaEnabled,
  loading,
  footer,
}) => {
  const [activeTab, setActiveTab] = useState<SampleGroup>("fake");
  const [uploadMode, setUploadMode] = useState<"document" | "audio" | "text">("document");
  const [messageText, setMessageText] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const AUDIO_EXTS = new Set(["mp3", "ogg", "opus", "wav", "m4a"]);

  const selectedSample = samples.find((s) => s.id === selectedSampleId) || null;
  const isSelectedFakeDemo = Boolean(
    selectedSample && selectedSample.group === "fake"
  );

  const filteredSamples = samples
    .filter((s) => s.group === activeTab)
    .sort((a, b) => (a.demo_order ?? 9999) - (b.demo_order ?? 9999));

  const handleIncomingFile = (file: File) => {
    const ext = file.name.toLowerCase().split(".").pop() || "";
    if (AUDIO_EXTS.has(ext)) {
      onUploadAudio(file);
    } else {
      onUploadFile(file);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (loading) return;
    const file = e.dataTransfer.files?.[0];
    if (file) {
      handleIncomingFile(file);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleIncomingFile(file);
      e.target.value = "";
    }
  };

  return (
    <aside className="w-full lg:w-[340px] xl:w-[360px] shrink-0 flex flex-col gap-4">
      {/* Compact Upload Card */}
      <div className="warm-card p-4">
        {/* Document vs Audio Tabs */}
        <div className="flex items-center gap-1.5 p-1 bg-subtle rounded-lg border border-warm-border mb-3">
          <button
            type="button"
            onClick={() => setUploadMode("document")}
            className={`flex-1 text-xs py-1 px-2 rounded-md font-medium transition-all ${
              uploadMode === "document"
                ? "bg-card shadow-sm text-body font-semibold"
                : "text-muted hover:text-body"
            }`}
          >
            Document (≤10 MB)
          </button>
          <button
            type="button"
            onClick={() => setUploadMode("audio")}
            className={`flex-1 text-xs py-1 px-2 rounded-md font-medium transition-all ${
              uploadMode === "audio"
                ? "bg-card shadow-sm text-body font-semibold"
                : "text-muted hover:text-body"
            }`}
          >
            Voice Note (≤25 MB)
          </button>
          <button
            type="button"
            onClick={() => setUploadMode("text")}
            className={`flex-1 text-xs py-1 px-2 rounded-md font-medium transition-all ${
              uploadMode === "text"
                ? "bg-card shadow-sm text-body font-semibold"
                : "text-muted hover:text-body"
            }`}
          >
            Text
          </button>
        </div>

        <div className="flex items-center justify-between mb-2">
          <h2 className="font-heading text-xs font-semibold uppercase tracking-wider text-muted">
            {uploadMode === "document"
              ? "Upload Document"
              : uploadMode === "audio"
              ? "Upload Voice Note"
              : "Paste Message"}
          </h2>
          <span className="text-[11px] text-muted">
            {uploadMode === "document"
              ? "PNG, JPG, PDF ≤ 10 MB"
              : uploadMode === "audio"
              ? "MP3, OGG, WAV ≤ 25 MB"
              : `${messageText.length.toLocaleString()} / 5,000`}
          </span>
        </div>

        {uploadMode === "text" ? (
          <div className="flex flex-col gap-2">
            <select
              aria-label="Load a sample message"
              value=""
              onChange={(e) => {
                const found = TEXT_SAMPLES.find((s) => s.label === e.target.value);
                if (found) setMessageText(found.text);
              }}
              className="text-xs rounded-md border border-warm-border bg-card px-2 py-1.5 text-body focus-amber"
            >
              <option value="">Load a sample forward…</option>
              {TEXT_SAMPLES.map((s) => (
                <option key={s.label} value={s.label}>
                  {s.label}
                </option>
              ))}
            </select>
            <textarea
              value={messageText}
              onChange={(e) => setMessageText(e.target.value.slice(0, 5000))}
              rows={6}
              placeholder="Paste a WhatsApp forward in English, Hindi, Hinglish or another Indian language…"
              className="w-full text-xs rounded-lg border border-warm-strong bg-subtle/60 px-3 py-2 text-body placeholder:text-muted resize-y focus-amber"
            />
            <button
              type="button"
              disabled={loading || !messageText.trim()}
              onClick={() => onCheckText(messageText)}
              className="w-full text-xs font-semibold py-2 rounded-md bg-accent-amber text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
            >
              {loading ? "Checking…" : "Check message"}
            </button>
            <p className="text-[11px] text-muted">
              Claim extraction needs cloud fallback (or a cached result); forensics and source
              matching run locally.
            </p>
          </div>
        ) : (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setDragActive(true);
          }}
          onDragLeave={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setDragActive(false);
          }}
          onDrop={handleDrop}
          onClick={() => !loading && fileInputRef.current?.click()}
          onKeyDown={(e) => {
            if ((e.key === "Enter" || e.key === " ") && !loading) {
              e.preventDefault();
              fileInputRef.current?.click();
            }
          }}
          tabIndex={0}
          role="button"
          aria-label={
            uploadMode === "document"
              ? "Upload document image or PDF for OCR extraction"
              : "Upload voice note audio for speech transcription"
          }
          className={`cursor-pointer rounded-lg border border-dashed px-3.5 py-3 text-center transition-all duration-150 focus-amber ${
            dragActive
              ? "border-accent-amber bg-accent-surface"
              : "border-warm-strong bg-subtle/60 hover:border-accent-amber hover:bg-accent-surface/50"
          } ${loading ? "opacity-60 pointer-events-none" : ""}`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={
              uploadMode === "document"
                ? ".png,.jpg,.jpeg,.pdf"
                : ".mp3,.ogg,.opus,.wav,.m4a"
            }
            onChange={handleFileChange}
            className="hidden"
          />
          <div className="flex items-center justify-center gap-2.5">
            {uploadMode === "document" ? (
              <svg
                className="w-4 h-4 text-accent-amber shrink-0"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 16.5V9.75m0 0 3 3m-3-3-3 3M6.75 19.5a4.5 4.5 0 0 1-1.41-8.775 5.25 5.25 0 0 1 10.233-2.33 3 3 0 0 1 3.758 3.848A3.752 3.752 0 0 1 18 19.5H6.75Z"
                />
              </svg>
            ) : (
              <svg
                className="w-4 h-4 text-accent-amber shrink-0"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 18.75a6 6 0 0 0 6-6v-1.5m-6 7.5a6 6 0 0 1-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15a3 3 0 0 1-3-3V4.5a3 3 0 1 1 6 0v7.5a3 3 0 0 1-3 3Z"
                />
              </svg>
            )}
            <div className="text-left">
              <p className="text-xs font-medium text-body">
                {uploadMode === "document" ? (
                  <>
                    Drop circular or{" "}
                    <span className="text-accent-strong underline font-semibold">
                      browse file
                    </span>
                  </>
                ) : (
                  <>
                    Drop voice note or{" "}
                    <span className="text-accent-strong underline font-semibold">
                      browse audio
                    </span>
                  </>
                )}
              </p>
              <p className="text-[11px] text-muted">
                {uploadMode === "document"
                  ? "Hindi (Devanagari) & English OCR"
                  : "Whisper ASR: 22 Indian languages + English"}
              </p>
            </div>
          </div>
        </div>
        )}

        {/* Cloud Fallback Toggle (hidden when offlineMode is on) */}
        {!offlineMode && (
        <div className="mt-3 pt-3 border-t border-warm-border">
          <label className="flex items-center justify-between gap-3 cursor-pointer select-none">
            <div>
              <span className="text-xs font-medium text-body block">
                Allow cloud fallback
              </span>
              {ollamaEnabled === false ? (
                <span className="text-[11px] text-accent-strong font-medium block mt-0.5">
                  Local model off: using cloud OCR
                </span>
              ) : (
                <span className="text-[11px] text-muted block mt-0.5">
                  Use Gemini OCR if local VLM is unavailable
                </span>
              )}
            </div>
            <input
              type="checkbox"
              checked={allowFallback}
              onChange={(e) => onToggleFallback(e.target.checked)}
              aria-label="Allow cloud fallback"
              className="sr-only peer"
            />
            <div className="w-9 h-5 bg-warm-strong peer-focus-visible:ring-2 peer-focus-visible:ring-accent-amber rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all relative peer-checked:bg-accent-amber shrink-0" />
          </label>
        </div>
        )}
      </div>

      {/* Demo Samples Card */}
      <div className="warm-card p-4 flex flex-col flex-1">
        <div className="flex items-center justify-between mb-2.5">
          <h2 className="font-heading text-xs font-semibold uppercase tracking-wider text-muted">
            Demo Samples
          </h2>
          <span className="text-[11px] font-mono text-muted">
            {samples.length} items
          </span>
        </div>

        {/* Simulate Unseen Forgery Toggle (shown only for demo fake samples) */}
        {isSelectedFakeDemo && (
          <div className="mb-3 p-2.5 rounded-lg bg-accent-surface/80 border border-accent-border">
            <label className="flex items-center justify-between gap-2.5 cursor-pointer select-none">
              <div className="min-w-0">
                <span className="text-xs font-semibold text-body block">
                  Hide this document&apos;s own fact-check
                </span>
                <span className="text-[11px] text-muted block mt-0.5">
                  Simulates a new copy of a known scam: other fact-checks of the same scam still count.
                </span>
              </div>
              <input
                type="checkbox"
                checked={simulateUnseen}
                onChange={(e) => onToggleSimulateUnseen(e.target.checked)}
                aria-label="Hide this document's own fact-check"
                className="sr-only peer"
              />
              <div className="w-9 h-5 bg-warm-strong peer-focus-visible:ring-2 peer-focus-visible:ring-accent-amber rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all relative peer-checked:bg-accent-amber shrink-0" />
            </label>
          </div>
        )}

        {/* Group Tabs */}
        <div
          className="grid grid-cols-3 gap-1 p-1 rounded-lg bg-subtle border border-warm-border mb-3"
          role="tablist"
          aria-label="Demo sample categories"
        >
          {TABS.map((tab) => {
            const count = samples.filter((s) => s.group === tab.key).length;
            const isSelected = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={isSelected}
                onClick={() => setActiveTab(tab.key)}
                className={`whitespace-nowrap py-1.5 px-1.5 rounded-md text-[11px] font-medium transition-all duration-150 focus-amber ${
                  isSelected
                    ? "bg-accent-surface text-body font-semibold border border-accent-border shadow-sm"
                    : "text-muted hover:text-body"
                }`}
              >
                <span>{tab.label}</span>
                <span className="text-[10px] font-mono opacity-75 ml-0.5">
                  ({count})
                </span>
              </button>
            );
          })}
        </div>

        {/* Compact Sample Rows */}
        <div className="space-y-1.5 overflow-y-auto max-h-[500px] pr-1">
          {filteredSamples.map((sample) => {
            const isActive = selectedSampleId === sample.id;
            const readableLabel = formatNarrativeLabel(
              sample.narrative,
              sample.expected_issuer_id || sample.expected_issuer || sample.label
            );
            return (
              <button
                key={sample.id}
                type="button"
                disabled={loading}
                title={sample.note || `${sample.id} — ${readableLabel}`}
                onClick={() => onSelectSample(sample)}
                className={`w-full text-left flex items-center gap-2.5 p-2 rounded-lg border transition-all duration-150 focus-amber ${
                  isActive
                    ? "bg-accent-surface border-accent-border border-l-4 border-l-accent-amber"
                    : "border-warm-border bg-card hover:bg-subtle hover:border-warm-strong"
                } ${loading ? "opacity-60 cursor-wait" : ""}`}
              >
                <div className="w-9 h-11 rounded bg-subtle border border-warm-border overflow-hidden shrink-0 flex items-center justify-center">
                  <img
                    src={resolveApiUrl(sample.thumbnail_url)}
                    alt={sample.id}
                    loading="lazy"
                    className="w-full h-full object-cover"
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-1.5">
                    <span className="font-mono text-xs font-semibold text-body truncate">
                      {sample.id}
                    </span>
                    <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded bg-subtle border border-warm-border text-muted shrink-0">
                      {sample.language.toUpperCase()}
                    </span>
                  </div>
                  <p className="text-xs text-muted truncate mt-0.5">
                    {readableLabel}
                  </p>
                  {isActive && sample.talking_point && (
                    <p
                      data-testid="sample-talking-point"
                      className="text-[11px] leading-snug text-accent-strong font-medium mt-1.5 pt-1.5 border-t border-accent-border/70 whitespace-normal"
                    >
                      {sample.talking_point}
                    </p>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>
      {footer}
    </aside>
  );
};
