import React, { useEffect, useState } from "react";
import { HealthResponse, PRODUCT_NAME, PRODUCT_SUBTITLE } from "../types";

interface TopBarProps {
  health: HealthResponse | null;
  healthError: boolean;
  darkMode: boolean;
  onToggleDarkMode: () => void;
  activeNavTab: "verification" | "narratives" | "evaluation";
  onSelectNavTab: (tab: "verification" | "narratives" | "evaluation") => void;
  presenterMode: boolean;
  onTogglePresenterMode: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  health,
  healthError,
  darkMode,
  onToggleDarkMode,
  activeNavTab,
  onSelectNavTab,
  presenterMode,
  onTogglePresenterMode,
}) => {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => {
      setScrolled(window.scrollY > 4);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const engineLabel = health
    ? health.ollama_enabled
      ? (health.ollama_reachable === false ? "Local OCR (Offline)" : "Local OCR (Qwen3-VL)")
      : health.gemini_configured
      ? "Cloud OCR (Gemini)"
      : "No Engine"
    : healthError
    ? "Backend Offline"
    : "Connecting…";

  return (
    <header
      className={`sticky top-0 z-30 h-16 bg-card transition-all duration-150 ${
        scrolled
          ? "border-b border-warm-strong shadow-xs"
          : "border-b border-warm-border"
      }`}
    >
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 h-full flex items-center justify-between gap-4">
        {/* Left: Pramaan Identity */}
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-xl bg-accent-surface border border-accent-border flex items-center justify-center shrink-0"
            aria-hidden="true"
          >
            {/* Minimal document-with-check inline SVG */}
            <svg
              className="w-5 h-5"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M7 3.75H13.5L18.25 8.5V18.25C18.25 19.3546 17.3546 20.25 16.25 20.25H7C5.89543 20.25 5 19.3546 5 18.25V5.75C5 4.64543 5.89543 3.75 7 3.75Z"
                className="stroke-body"
                strokeWidth="1.75"
                strokeLinejoin="round"
              />
              <path
                d="M13 3.75V8.5H18"
                className="stroke-body"
                strokeWidth="1.75"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path
                d="M8.75 13.75L10.75 15.75L14.75 11.75"
                className="stroke-amber-600 dark:stroke-amber-400"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-heading text-base font-bold tracking-tight text-body leading-tight">
                {PRODUCT_NAME}
              </span>
            </div>
            <p className="text-[11px] text-muted leading-tight hidden sm:block">
              {PRODUCT_SUBTITLE}
            </p>
          </div>
        </div>

        {/* Navigation Tabs: Verify · Narratives · Evaluation */}
        <nav
          aria-label="Main navigation"
          className="flex items-center gap-1 rounded-xl border border-warm-border p-1 bg-subtle text-xs"
        >
          <button
            type="button"
            onClick={() => onSelectNavTab("verification")}
            className={`px-3.5 py-1.5 rounded-lg font-semibold transition-all ${
              activeNavTab === "verification"
                ? "bg-card text-body shadow-xs"
                : "text-muted hover:text-body"
            }`}
          >
            Verify
          </button>
          <button
            type="button"
            onClick={() => onSelectNavTab("narratives")}
            className={`px-3.5 py-1.5 rounded-lg font-semibold transition-all ${
              activeNavTab === "narratives"
                ? "bg-card text-body shadow-xs"
                : "text-muted hover:text-body"
            }`}
          >
            Narratives
          </button>
          <button
            type="button"
            onClick={() => onSelectNavTab("evaluation")}
            className={`px-3.5 py-1.5 rounded-lg font-semibold transition-all ${
              activeNavTab === "evaluation"
                ? "bg-card text-body shadow-xs"
                : "text-muted hover:text-body"
            }`}
          >
            Evaluation
          </button>
        </nav>

        {/* Right Controls: Presenter Toggle, Quota, Engine, Theme */}
        <div className="flex items-center gap-2 sm:gap-3">
          {/* Presenter Toggle */}
          <button
            type="button"
            onClick={onTogglePresenterMode}
            title={presenterMode ? "Presenter mode ON: Technical tabs hidden" : "Enable presenter mode"}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
              presenterMode
                ? "bg-amber-100 text-amber-900 border-amber-300 dark:bg-amber-950/70 dark:text-amber-200 dark:border-amber-700 shadow-xs"
                : "bg-card text-muted hover:text-body border-warm-border hover:bg-subtle"
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                presenterMode ? "bg-amber-600 animate-pulse" : "bg-muted/40"
              }`}
            />
            <span>Presenter</span>
          </button>

          {/* Fully Offline Badge when OFFLINE_MODE is on */}
          {health?.offline_mode ? (
            <div
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 dark:bg-emerald-950/80 dark:text-emerald-200 border border-emerald-300 dark:border-emerald-800 shadow-xs"
              role="status"
              aria-label="Fully offline mode active"
              data-testid="fully-offline-badge"
            >
              <span className="w-2 h-2 rounded-full bg-emerald-600 animate-pulse" />
              <span>Fully offline</span>
            </div>
          ) : (
            /* Engine Status Pill */
            <div
              className="hidden md:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-subtle text-body border border-warm-border"
              role="status"
              aria-label="OCR engine status"
            >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                healthError
                  ? "bg-red-600"
                  : health
                  ? "bg-emerald-600"
                  : "bg-amber-600"
              }`}
            />
            <span className="truncate max-w-[180px]">{engineLabel}</span>
          </div>
          )}

          {/* Quota Indicator */}
          {health && (
            <div
              className="hidden lg:inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-mono bg-subtle text-muted border border-warm-border"
              aria-label="Daily API quota usage"
            >
              <span>Calls:</span>
              <span className="font-semibold text-body">
                {health.daily_api_calls_used}/{health.daily_api_call_limit}
              </span>
            </div>
          )}

          {/* Theme Toggle */}
          <button
            type="button"
            onClick={onToggleDarkMode}
            aria-label={darkMode ? "Switch to light theme" : "Switch to dark theme"}
            className="p-2 rounded-lg border border-warm-border bg-card text-muted hover:text-body hover:bg-subtle focus-amber transition-colors"
          >
            {darkMode ? (
              <svg className="w-4 h-4 text-accent-amber" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 9.002-5.998Z" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </header>
  );
};
