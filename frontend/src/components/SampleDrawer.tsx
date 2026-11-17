import React, { useState } from "react";
import { SampleGroup, SampleItem, TestItem, TestLabel } from "../types";
import { TEST_LABEL_TEXT } from "./TestSetCard";

interface SampleDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  samples: SampleItem[];
  selectedSampleId: string | null;
  onSelectSample: (sample: SampleItem, unseen?: boolean) => void;
  testItems: TestItem[];
  selectedTestId: string | null;
  onRunTestItem: (item: TestItem, unseen: boolean) => void;
  simulateUnseen: boolean;
  onToggleSimulateUnseen: (val: boolean) => void;
  allowFallback: boolean;
  onToggleFallback: (val: boolean) => void;
  loading?: boolean;
  offlineMode?: boolean;
}

const TEST_GROUPS: { key: "fake" | "real" | "synthetic"; label: string; match: (l: TestLabel) => boolean }[] = [
  { key: "fake", label: "Fake", match: (l) => l === "fake" },
  { key: "real", label: "Real", match: (l) => l === "real" },
  { key: "synthetic", label: "Synthetic", match: (l) => l.startsWith("synthetic") },
];

export const SampleDrawer: React.FC<SampleDrawerProps> = ({
  isOpen,
  onClose,
  samples,
  selectedSampleId,
  onSelectSample,
  testItems,
  selectedTestId,
  onRunTestItem,
  simulateUnseen,
  onToggleSimulateUnseen,
  allowFallback,
  onToggleFallback,
  offlineMode,
}) => {
  const [activeMainTab, setActiveMainTab] = useState<"demo" | "testset">("demo");
  const [demoFilter, setDemoFilter] = useState<"all" | SampleGroup>("all");
  const [testGroup, setTestGroup] = useState<"fake" | "real" | "synthetic">("fake");
  const [testUnseen, setTestUnseen] = useState<boolean>(false);

  if (!isOpen) return null;

  const filteredSamples = samples.filter((s) =>
    demoFilter === "all" ? true : s.group === demoFilter
  );

  const activeTestGroup = TEST_GROUPS.find((g) => g.key === testGroup)!;
  const filteredTestItems = testItems.filter((it) => activeTestGroup.match(it.label));
  const inIndexCount = testItems.filter((it) => Boolean(it.in_index || it.in_official_index)).length;
  const freshCount = testItems.length - inIndexCount;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden" role="dialog" aria-modal="true">
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="fixed inset-0 bg-black/40 backdrop-blur-xs transition-opacity"
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-md bg-card border-l border-warm-border shadow-2xl flex flex-col">
          {/* Drawer Header */}
          <div className="p-4 border-b border-warm-border flex items-center justify-between">
            <div>
              <h2 className="font-heading text-base font-bold text-body">
                Document & Benchmark Drawer
              </h2>
              <p className="text-xs text-muted">
                Select from the 20-sample demo set or 35 held-out test cases.
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-muted hover:text-body hover:bg-subtle focus-amber"
              aria-label="Close drawer"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Drawer Top Tabs (Demo Set vs Held-out Test Set) */}
          <div className="p-3 border-b border-warm-border bg-subtle/50">
            <div className="grid grid-cols-2 gap-1.5 p-1 bg-subtle rounded-lg border border-warm-border">
              <button
                type="button"
                onClick={() => setActiveMainTab("demo")}
                className={`py-1.5 text-xs font-semibold rounded-md transition-all ${
                  activeMainTab === "demo"
                    ? "bg-card text-body shadow-xs"
                    : "text-muted hover:text-body"
                }`}
              >
                Demo Set (20)
              </button>
              <button
                type="button"
                onClick={() => setActiveMainTab("testset")}
                className={`py-1.5 text-xs font-semibold rounded-md transition-all ${
                  activeMainTab === "testset"
                    ? "bg-card text-body shadow-xs"
                    : "text-muted hover:text-body"
                }`}
              >
                Held-out Test Set (35)
              </button>
            </div>
          </div>

          {/* Drawer Body */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {activeMainTab === "demo" ? (
              <>
                {/* Simulation Mode Toggle for Demo */}
                <div className="p-3 rounded-lg border border-warm-border bg-subtle/40">
                  <label className="flex items-start justify-between gap-3 cursor-pointer select-none">
                    <div className="space-y-0.5">
                      <span className="text-xs font-semibold text-body block">
                        Hide this document&apos;s own fact-check
                      </span>
                      <span className="text-[11px] text-muted block leading-snug">
                        Simulates an unindexed zero-day forgery. Excludes the sample&apos;s own debunk record; sister debunks remain active.
                      </span>
                    </div>
                    <input
                      type="checkbox"
                      checked={simulateUnseen}
                      onChange={(e) => onToggleSimulateUnseen(e.target.checked)}
                      className="mt-0.5 w-4 h-4 accent-amber-600 rounded"
                      aria-label="Hide this document's own fact-check"
                    />
                  </label>
                </div>

                {/* Filter Pills */}
                <div className="flex items-center gap-1.5 flex-wrap">
                  {(["all", "fake", "genuine", "synthetic"] as const).map((grp) => (
                    <button
                      key={grp}
                      type="button"
                      onClick={() => setDemoFilter(grp)}
                      className={`text-[11px] font-semibold px-2.5 py-1 rounded-full border transition-all ${
                        demoFilter === grp
                          ? "bg-primary-bg text-primary-text border-transparent"
                          : "border-warm-border bg-subtle text-muted hover:text-body"
                      }`}
                    >
                      {grp === "all" ? "All (20)" : grp.charAt(0).toUpperCase() + grp.slice(1)}
                    </button>
                  ))}
                </div>

                {/* Items List */}
                <div className="space-y-2">
                  {filteredSamples.map((s) => {
                    const isSelected = selectedSampleId === s.id;
                    return (
                      <div
                        key={s.id}
                        onClick={() => {
                          onSelectSample(s);
                          onClose();
                        }}
                        className={`p-3 rounded-xl border text-left cursor-pointer transition-all ${
                          isSelected
                            ? "border-accent-amber bg-accent-surface/30 shadow-xs"
                            : "border-warm-border hover:border-warm-strong bg-card"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                          <span className="font-mono text-xs font-bold text-body">
                            {s.id}
                          </span>
                          <span
                            className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border ${
                              s.label === "fake"
                                ? "bg-red-50 text-red-800 border-red-300 dark:bg-red-950/60 dark:text-red-300"
                                : s.label === "genuine"
                                ? "bg-emerald-50 text-emerald-800 border-emerald-300 dark:bg-emerald-950/60 dark:text-emerald-300"
                                : "bg-blue-50 text-blue-800 border-blue-300 dark:bg-blue-950/60 dark:text-blue-300"
                            }`}
                          >
                            {s.label}
                          </span>
                        </div>
                        <p className="text-xs font-semibold text-body truncate">
                          {s.expected_issuer || s.filename}
                        </p>
                        <p className="text-[11px] text-muted line-clamp-2 mt-0.5 leading-snug">
                          {s.talking_point || s.note || "Curated benchmark case"}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </>
            ) : (
              <>
                {/* Test Set Subhead & Unseen Toggle */}
                <div className="p-3 rounded-lg border border-warm-border bg-subtle/40 space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-body">Held-out Evaluation Set</span>
                    <span className="text-[11px] text-muted font-mono">
                      {testItems.length} items ({freshCount} fresh · {inIndexCount} in index)
                    </span>
                  </div>
                  <label className="flex items-start justify-between gap-3 cursor-pointer select-none pt-1 border-t border-warm-border">
                    <div className="space-y-0.5">
                      <span className="text-xs font-semibold text-body block">
                        Hide all fact-checks
                      </span>
                      <span className="text-[11px] text-muted block leading-snug">
                        Judges strictly on forensic document checks and official registry.
                      </span>
                    </div>
                    <input
                      type="checkbox"
                      checked={testUnseen}
                      onChange={(e) => setTestUnseen(e.target.checked)}
                      className="mt-0.5 w-4 h-4 accent-amber-600 rounded"
                      aria-label="Hide all fact-checks"
                    />
                  </label>
                </div>

                {/* Test Set Group Tabs */}
                <div className="flex items-center gap-1.5 p-1 bg-subtle rounded-lg border border-warm-border">
                  {TEST_GROUPS.map((g) => (
                    <button
                      key={g.key}
                      type="button"
                      onClick={() => setTestGroup(g.key)}
                      className={`flex-1 text-xs py-1 px-2 rounded font-medium transition-all ${
                        testGroup === g.key
                          ? "bg-card text-body shadow-xs font-semibold"
                          : "text-muted hover:text-body"
                      }`}
                    >
                      {g.label} ({testItems.filter((it) => g.match(it.label)).length})
                    </button>
                  ))}
                </div>

                {/* Test Items List */}
                <div className="space-y-2">
                  {filteredTestItems.map((it) => {
                    const isSelected = selectedTestId === it.id;
                    const inIndex = Boolean(it.in_index || it.in_official_index);
                    return (
                      <div
                        key={it.id}
                        onClick={() => {
                          onRunTestItem(it, testUnseen);
                          onClose();
                        }}
                        className={`p-3 rounded-xl border text-left cursor-pointer transition-all ${
                          isSelected
                            ? "border-accent-amber bg-accent-surface/30 shadow-xs"
                            : "border-warm-border hover:border-warm-strong bg-card"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-1.5 mb-1">
                          <span className="font-mono text-xs font-bold text-body">
                            {it.id}
                          </span>
                          <div className="flex items-center gap-1">
                            {inIndex && (
                              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded border bg-blue-50 text-blue-800 border-blue-200 dark:bg-blue-950/60 dark:text-blue-300">
                                In index
                              </span>
                            )}
                            <span
                              className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border ${
                                it.label === "fake" || it.label === "synthetic_forged"
                                  ? "bg-red-50 text-red-800 border-red-300 dark:bg-red-950/60 dark:text-red-300"
                                  : "bg-emerald-50 text-emerald-800 border-emerald-300 dark:bg-emerald-950/60 dark:text-emerald-300"
                              }`}
                            >
                              {TEST_LABEL_TEXT[it.label] || it.label}
                            </span>
                          </div>
                        </div>
                        <p className="text-xs text-muted truncate">
                          {it.title || (inIndex ? "RBI circular (in official index)" : "Circular (not indexed)")}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>

          {/* Drawer Footer Settings */}
          <div className="p-4 border-t border-warm-border bg-subtle/50 flex items-center justify-between text-xs">
            {!offlineMode ? (
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={allowFallback}
                  onChange={(e) => onToggleFallback(e.target.checked)}
                  className="w-4 h-4 accent-amber-600 rounded"
                />
                <span className="text-body font-medium">Cloud OCR fallback</span>
              </label>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                Fully offline (cloud disabled)
              </span>
            )}
            <span className="text-muted text-[11px]">
              YellowSense Decision Support
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
