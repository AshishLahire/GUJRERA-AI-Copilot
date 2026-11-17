import React, { useRef, useState } from "react";
import { SampleItem } from "../types";
import { resolveApiUrl } from "../api/client";

interface StartHubProps {
  samples: SampleItem[];
  onSelectSample: (sample: SampleItem) => void;
  onUploadFile: (file: File) => void;
  onUploadAudio: (file: File, language?: string) => void;
  onCheckText: (text: string) => void;
  onOpenDrawer: () => void;
  loading: boolean;
}

// 6 Curated demo examples in demo_order
const CURATED_DEMO_IDS = [
  "FN-TG-01595",
  "FN-TG-01746",
  "FN-TG-00988",
  "OFF-4A2E01CE80__screenshot",
  "FN-PDF-0002",
  "FN-TG-00130",
];

export const StartHub: React.FC<StartHubProps> = ({
  samples,
  onSelectSample,
  onUploadFile,
  onUploadAudio,
  onCheckText,
  onOpenDrawer,
  loading,
}) => {
  const [activeTab, setActiveTab] = useState<"document" | "voice" | "text">("document");
  const [pastedText, setPastedText] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const audioInputRef = useRef<HTMLInputElement>(null);

  const curatedSamples = CURATED_DEMO_IDS.map((id) =>
    samples.find((s) => s.id === id)
  ).filter((s): s is SampleItem => Boolean(s));

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      const ext = file.name.toLowerCase().split(".").pop() || "";
      if (["mp3", "wav", "ogg", "m4a", "opus"].includes(ext)) {
        onUploadAudio(file);
      } else {
        onUploadFile(file);
      }
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      onUploadFile(e.target.files[0]);
    }
  };

  const handleAudioChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      onUploadAudio(e.target.files[0]);
    }
  };

  const handleTextSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (pastedText.trim()) {
      onCheckText(pastedText.trim());
    }
  };

  const insertSampleText = (text: string) => {
    setPastedText(text);
  };

  return (
    <div className="w-full max-w-5xl mx-auto py-8 px-4 sm:px-6 flex flex-col gap-10">
      {/* Hero Header */}
      <div className="text-center max-w-2xl mx-auto space-y-3">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-accent-surface border border-accent-border text-amber-900 dark:text-amber-200">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
          YellowSense Document & Claim Intelligence
        </div>
        <h1 className="font-heading text-3xl sm:text-4xl font-bold tracking-tight text-body">
          Verify Indian Official Documents & Claims
        </h1>
        <p className="text-sm text-muted leading-relaxed">
          Cross-check circulars, orders, recruitment notices, and WhatsApp forwards against
          official central & state registries, PIB fact-checks, and multi-spectral visual heuristics.
        </p>
      </div>

      {/* Main Centred Input Hub */}
      <div className="warm-card p-6 shadow-sm border border-warm-border">
        {/* Three Large Input Mode Option Pills */}
        <div className="grid grid-cols-3 gap-2 p-1.5 bg-subtle rounded-xl border border-warm-border mb-6">
          <button
            type="button"
            onClick={() => setActiveTab("document")}
            className={`flex items-center justify-center gap-2 py-3 px-4 rounded-lg text-xs sm:text-sm font-semibold transition-all ${
              activeTab === "document"
                ? "bg-card text-body shadow-sm border border-warm-border"
                : "text-muted hover:text-body"
            }`}
          >
            <svg className="w-4 h-4 text-accent-amber" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
            </svg>
            <span>Upload Document</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("voice")}
            className={`flex items-center justify-center gap-2 py-3 px-4 rounded-lg text-xs sm:text-sm font-semibold transition-all ${
              activeTab === "voice"
                ? "bg-card text-body shadow-sm border border-warm-border"
                : "text-muted hover:text-body"
            }`}
          >
            <svg className="w-4 h-4 text-accent-amber" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
            </svg>
            <span>Voice Note</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("text")}
            className={`flex items-center justify-center gap-2 py-3 px-4 rounded-lg text-xs sm:text-sm font-semibold transition-all ${
              activeTab === "text"
                ? "bg-card text-body shadow-sm border border-warm-border"
                : "text-muted hover:text-body"
            }`}
          >
            <svg className="w-4 h-4 text-accent-amber" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <span>Paste WhatsApp Text</span>
          </button>
        </div>

        {/* Input Content Panes */}
        {activeTab === "document" && (
          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-xl p-8 sm:p-12 text-center transition-all ${
              dragActive
                ? "border-accent-amber bg-accent-surface/50"
                : "border-warm-border hover:border-warm-strong bg-subtle/30"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.webp"
              onChange={handleFileChange}
              className="hidden"
            />
            <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-accent-surface border border-accent-border flex items-center justify-center text-amber-700 dark:text-amber-300">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
            </div>
            <h3 className="font-heading text-base font-semibold text-body mb-1">
              Drag & drop document here, or browse files
            </h3>
            <p className="text-xs text-muted max-w-sm mx-auto mb-5">
              Supports scanned or born-digital circulars: PDF, PNG, JPG, JPEG, WEBP up to 10 MB.
            </p>
            <button
              type="button"
              disabled={loading}
              onClick={() => fileInputRef.current?.click()}
              className="px-5 py-2.5 rounded-lg text-xs font-semibold bg-primary-bg text-primary-text hover:opacity-90 transition-opacity focus-amber shadow-sm"
            >
              Select Document
            </button>
          </div>
        )}

        {activeTab === "voice" && (
          <div className="border border-warm-border rounded-xl p-8 text-center bg-subtle/30">
            <input
              ref={audioInputRef}
              type="file"
              accept=".mp3,.ogg,.opus,.wav,.m4a"
              onChange={handleAudioChange}
              className="hidden"
            />
            <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-accent-surface border border-accent-border flex items-center justify-center text-amber-700 dark:text-amber-300">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
            </div>
            <h3 className="font-heading text-base font-semibold text-body mb-1">
              Upload a WhatsApp voice note or speech audio
            </h3>
            <p className="text-xs text-muted max-w-md mx-auto mb-5">
              Automatic Hindi / Indic speech transcription via Whisper / Gemini. Supports MP3, WAV, M4A, OGG up to 25 MB.
            </p>
            <div className="flex items-center justify-center gap-3">
              <button
                type="button"
                disabled={loading}
                onClick={() => audioInputRef.current?.click()}
                className="px-5 py-2.5 rounded-lg text-xs font-semibold bg-primary-bg text-primary-text hover:opacity-90 transition-opacity focus-amber shadow-sm"
              >
                Choose Audio File
              </button>
            </div>
          </div>
        )}

        {activeTab === "text" && (
          <form onSubmit={handleTextSubmit} className="space-y-4">
            <div className="relative">
              <textarea
                value={pastedText}
                onChange={(e) => setPastedText(e.target.value)}
                placeholder="Paste the forwarded claim text, WhatsApp message, or notice summary here..."
                rows={5}
                className="w-full text-xs p-4 rounded-xl border border-warm-border bg-subtle/40 text-body focus:bg-card focus:outline-none focus:ring-2 focus:ring-accent-amber/50 placeholder:text-muted"
              />
              <div className="absolute right-3 bottom-3 text-[11px] text-muted">
                {pastedText.length} characters
              </div>
            </div>

            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-[11px] text-muted">Quick test:</span>
                <button
                  type="button"
                  onClick={() =>
                    insertSampleText(
                      "Pay a processing fee of Rs 2,100 to account no. 3456789012 to release the loan amount within 24 hours under PM Mudra Yojana."
                    )
                  }
                  className="text-[11px] px-2 py-0.5 rounded border border-warm-border bg-subtle text-muted hover:text-body hover:bg-card transition-colors"
                >
                  Mudra fee scam
                </button>
                <button
                  type="button"
                  onClick={() =>
                    insertSampleText(
                      "RBI has banned all ₹500 currency notes with immediate effect from 10 November 2026. Exchange old notes at bank branches."
                    )
                  }
                  className="text-[11px] px-2 py-0.5 rounded border border-warm-border bg-subtle text-muted hover:text-body hover:bg-card transition-colors"
                >
                  RBI ₹500 rumour
                </button>
              </div>

              <button
                type="submit"
                disabled={!pastedText.trim() || loading}
                className="px-6 py-2.5 rounded-lg text-xs font-semibold bg-primary-bg text-primary-text hover:opacity-90 transition-opacity disabled:opacity-40 focus-amber shadow-sm"
              >
                Verify Claim Text
              </button>
            </div>
          </form>
        )}
      </div>

      {/* "Try an example" Gallery: 6 Curated Cards */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-heading text-lg font-bold text-body">
              Try an Example
            </h2>
            <p className="text-xs text-muted">
              Explore 6 curated real-world and synthetic Indian circular cases.
            </p>
          </div>
          <button
            type="button"
            onClick={onOpenDrawer}
            className="inline-flex items-center gap-2 text-xs font-semibold px-4 py-2 rounded-lg border border-warm-strong bg-card text-body hover:bg-subtle transition-colors focus-amber shadow-sm"
          >
            <svg className="w-4 h-4 text-accent-amber" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16m-7 6h7" />
            </svg>
            <span>Browse All 20 Samples & Test Set</span>
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {curatedSamples.map((sample) => (
            <div
              key={sample.id}
              onClick={() => onSelectSample(sample)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelectSample(sample);
                }
              }}
              className="warm-card p-4 flex flex-col justify-between hover:border-accent-border hover:shadow-md transition-all cursor-pointer group focus-amber text-left"
            >
              <div>
                <div className="flex items-center justify-between gap-2 mb-2.5">
                  <span className="font-mono text-xs font-bold text-body group-hover:text-amber-800 dark:group-hover:text-amber-300">
                    {sample.id}
                  </span>
                  <span
                    className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border ${
                      sample.label === "fake"
                        ? "bg-red-50 text-red-800 border-red-300 dark:bg-red-950/60 dark:text-red-300 dark:border-red-800"
                        : sample.label === "genuine"
                        ? "bg-emerald-50 text-emerald-800 border-emerald-300 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800"
                        : "bg-blue-50 text-blue-800 border-blue-300 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-800"
                    }`}
                  >
                    {sample.label}
                  </span>
                </div>

                <div className="flex gap-3 items-start mb-3">
                  <div className="w-14 h-18 shrink-0 rounded bg-subtle border border-warm-border overflow-hidden flex items-center justify-center">
                    <img
                      src={resolveApiUrl(sample.thumbnail_url)}
                      alt={sample.id}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                      loading="lazy"
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-body line-clamp-2 leading-snug">
                      {sample.expected_issuer || sample.filename}
                    </p>
                    <p className="text-[11px] text-muted line-clamp-3 mt-1 leading-relaxed">
                      {sample.talking_point || sample.note || "Curated benchmark case"}
                    </p>
                  </div>
                </div>
              </div>

              <div className="pt-2 border-t border-warm-border flex items-center justify-between text-[11px] text-accent-amber font-semibold group-hover:underline">
                <span>Run verification</span>
                <span aria-hidden="true">→</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
