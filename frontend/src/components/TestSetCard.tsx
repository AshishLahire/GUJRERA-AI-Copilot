import React, { useState } from "react";
import { resolveApiUrl } from "../api/client";
import { TestItem, TestLabel } from "../types";

interface TestSetCardProps {
  items: TestItem[];
  selectedId: string | null;
  onRun: (item: TestItem, unseen: boolean) => void;
  loading: boolean;
}

const GROUPS: { key: "real" | "fake" | "synthetic"; label: string; match: (l: TestLabel) => boolean }[] = [
  { key: "real", label: "Real", match: (l) => l === "real" },
  { key: "fake", label: "Fake", match: (l) => l === "fake" },
  { key: "synthetic", label: "Synthetic", match: (l) => l.startsWith("synthetic") },
];

export const TEST_LABEL_TEXT: Record<TestLabel, string> = {
  real: "Genuine",
  fake: "Fake (stamp removed)",
  synthetic_clean: "Synthetic clean",
  synthetic_forged: "Synthetic forged",
};

export const TestSetCard: React.FC<TestSetCardProps> = ({ items, selectedId, onRun, loading }) => {
  const [group, setGroup] = useState<"real" | "fake" | "synthetic">("fake");
  const [unseen, setUnseen] = useState(false);
  const inIndexCount = items.filter((it) => Boolean(it.in_index || it.in_official_index)).length;
  const freshCount = items.length - inIndexCount;
  const active = GROUPS.find((g) => g.key === group)!;
  const shown = items.filter((it) => active.match(it.label));

  if (items.length === 0) return null;

  return (
    <div className="warm-card p-4 flex flex-col" data-testid="testset-card">
      <div className="flex items-center justify-between mb-1">
        <h2 className="font-heading text-xs font-semibold uppercase tracking-wider text-muted">
          Held-out Test Set
        </h2>
        <span className="text-[11px] text-muted">
          {items.length} items ({freshCount} fresh · {inIndexCount} in index)
        </span>
      </div>
      <p className="text-[11px] text-muted mb-3 leading-snug">
        Not used to tune thresholds. Items marked &apos;In index&apos; also appear in the official corpus.
      </p>

      <div className="flex items-center gap-1.5 p-1 bg-subtle rounded-lg border border-warm-border mb-3">
        {GROUPS.map((g) => (
          <button
            key={g.key}
            type="button"
            onClick={() => setGroup(g.key)}
            className={`flex-1 text-xs py-1 px-2 rounded-md font-medium transition-all ${
              group === g.key ? "bg-card shadow-sm text-body font-semibold" : "text-muted hover:text-body"
            }`}
          >
            {g.label} ({items.filter((it) => g.match(it.label)).length})
          </button>
        ))}
      </div>

      <label className="flex items-center justify-between gap-3 cursor-pointer select-none mb-3">
        <span className="text-[11px] text-body leading-snug">
          Hide all fact-checks
          <span className="block text-muted">Judges only on document checks and official records.</span>
        </span>
        <input
          type="checkbox"
          checked={unseen}
          onChange={(e) => {
            setUnseen(e.target.checked);
            const current = items.find((it) => it.id === selectedId);
            if (current) onRun(current, e.target.checked);
          }}
          className="w-4 h-4 accent-[var(--accent-amber)]"
          aria-label="Hide all fact-checks"
        />
      </label>

      <div className="flex flex-col gap-1.5 max-h-[360px] overflow-y-auto pr-1">
        {shown.map((it) => {
          const isActive = selectedId === it.id;
          return (
            <button
              key={it.id}
              type="button"
              disabled={loading}
              onClick={() => onRun(it, unseen)}
              title={it.cleaning || it.note || it.title || it.id}
              className={`w-full text-left flex items-center gap-2.5 p-2 rounded-lg border transition-all duration-150 focus-amber ${
                isActive
                  ? "bg-accent-surface border-accent-border border-l-4 border-l-accent-amber"
                  : "border-warm-border bg-card hover:bg-subtle hover:border-warm-strong"
              } ${loading ? "opacity-60 cursor-wait" : ""}`}
            >
              <div className="w-9 h-11 rounded bg-subtle border border-warm-border overflow-hidden shrink-0">
                <img
                  src={resolveApiUrl(it.thumbnail_url)}
                  alt={it.id}
                  loading="lazy"
                  className="w-full h-full object-cover"
                />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-1.5">
                  <span className="font-mono text-xs font-semibold text-body truncate">{it.id}</span>
                  <div className="flex items-center gap-1 shrink-0">
                    {Boolean(it.in_index || it.in_official_index) && (
                      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded border bg-blue-50 text-blue-800 border-blue-200 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-800">
                        In index
                      </span>
                    )}
                    <span
                      className={`text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded border shrink-0 ${
                        it.label === "real" || it.label === "synthetic_clean"
                          ? "bg-emerald-50 text-emerald-800 border-emerald-300 dark:bg-emerald-950/60 dark:text-emerald-200 dark:border-emerald-800"
                          : "bg-red-50 text-red-800 border-red-300 dark:bg-red-950/60 dark:text-red-200 dark:border-red-800"
                      }`}
                    >
                      {it.label === "real" || it.label === "synthetic_clean" ? "genuine" : "fake"}
                    </span>
                  </div>
                </div>
                <p className="text-xs text-muted truncate mt-0.5">
                  {it.title || (it.in_official_index ? "RBI circular (in official index)" : "Circular (not indexed)")}
                </p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
