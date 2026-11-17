import React, { useEffect, useState } from "react";
import { CalcSeed, Lang, NAVIGATE_EVENT, OPEN_CALC_EVENT, OPEN_REPORT_EVENT } from "../api/gujrera";
import { AccountBar } from "../components/AccountBar";
import { AskPage } from "../components/AskPage";
import { ReraCheckPage } from "../components/ReraCheckPage";
import { BrandMark, Icon } from "./Brand";
import { CalculatorPage } from "./CalculatorPage";
import { SaathiProvider, useSaathi } from "./context";
import { En } from "./En";
import { HomePage, Page } from "./HomePage";
import { OfficerPage, PromoterPage } from "./RolePages";
import { RiskPage } from "./RiskPage";
import { EnforcementPage } from "./EnforcementPage";
import { ReportPage } from "./ReportPage";
import { StringKey, tr } from "./strings";

const PAGES: Page[] = ["home", "ask", "check", "calc", "promoter", "officer", "risk", "enforce", "report"];
const NAV: { page: Page; key: StringKey; icon: string }[] = [
  { page: "home", key: "navOverview", icon: "grid" },
  { page: "ask", key: "navAsk", icon: "chat" },
  { page: "check", key: "navCheck", icon: "shield" },
  { page: "calc", key: "navCalc", icon: "calc" },
  { page: "report", key: "navReport", icon: "doc" },
  { page: "promoter", key: "navPromoter", icon: "briefcase" },
  { page: "officer", key: "navOfficer", icon: "chart" },
  { page: "risk", key: "navRisk", icon: "alert" },
  { page: "enforce", key: "navEnforce", icon: "flag" },
];
const LANGS: { id: Lang; label: string; name: string }[] = [
  { id: "gu", label: "ગુ", name: "Gujarati" },
  { id: "hi", label: "हि", name: "Hindi" },
  { id: "en", label: "EN", name: "English" },
];

function initialPage(): Page {
  const tab = new URLSearchParams(window.location.search).get("tab");
  if (tab === "rera") return "check";
  return PAGES.includes(tab as Page) ? (tab as Page) : "home";
}

function initialDark(): boolean {
  const theme = new URLSearchParams(window.location.search).get("theme");
  if (theme) return theme === "dark";
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch {
    return false;
  }
}

const Shell: React.FC = () => {
  const { lang, setLang } = useSaathi();
  const [page, setPage] = useState<Page>(initialPage);
  const [dark, setDark] = useState<boolean>(initialDark);
  // A question from the overview page; the counter remounts the chat so each one starts fresh.
  const [askSeed, setAskSeed] = useState<{ q: string; n: number } | null>(null);
  const [calcSeed, setCalcSeed] = useState<{ seed: CalcSeed; n: number } | null>(null);
  const [reportId, setReportId] = useState<number | null>(null);
  const current = NAV.find((n) => n.page === page) ?? NAV[0];

  useEffect(() => {
    const open = (e: Event) => {
      const seed = (e as CustomEvent<CalcSeed>).detail;
      setCalcSeed((s) => ({ seed, n: (s?.n ?? 0) + 1 }));
      setPage("calc");
    };
    const go = (e: Event) => {
      const target = (e as CustomEvent<string>).detail as Page;
      if (PAGES.includes(target)) setPage(target);
    };
    const report = (e: Event) => {
      setReportId((e as CustomEvent<number>).detail);
      setPage("report");
    };
    window.addEventListener(OPEN_CALC_EVENT, open);
    window.addEventListener(NAVIGATE_EVENT, go);
    window.addEventListener(OPEN_REPORT_EVENT, report);
    return () => {
      window.removeEventListener(OPEN_REPORT_EVENT, report);
      window.removeEventListener(OPEN_CALC_EVENT, open);
      window.removeEventListener(NAVIGATE_EVENT, go);
    };
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("tab", page);
    if (page !== "report") url.searchParams.delete("project");
    window.history.replaceState(null, "", url.toString());
    window.scrollTo({ top: 0 });
  }, [page]);

  const ask = (q: string) => {
    setAskSeed((s) => ({ q, n: (s?.n ?? 0) + 1 }));
    setPage("ask");
  };

  return (
    <div className="min-h-screen bg-page flex print:block print:bg-white">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 bg-card px-3 py-2 rounded z-50">
        Skip to content
      </a>

      {/* Sidebar (desktop) */}
      <aside className="print:!hidden hidden lg:flex w-64 shrink-0 flex-col border-r border-warm-border bg-card sticky top-0 h-screen">
        <button type="button" onClick={() => setPage("home")} className="h-16 px-5 flex items-center gap-3 border-b border-warm-border text-left">
          <BrandMark className="w-8 h-8" />
          <span className="flex flex-col leading-tight">
            <span className="font-heading font-bold text-body text-[15px]">GujRERA Saathi</span>
            <span className="text-[11px] text-muted">{tr("brand", "gu")}</span>
          </span>
        </button>
        <nav aria-label="Main" className="flex-1 overflow-y-auto px-3 py-4 flex flex-col gap-0.5">
          {NAV.map((n) => {
            const active = page === n.page;
            return (
              <button
                key={n.page}
                type="button"
                onClick={() => setPage(n.page)}
                aria-current={active ? "page" : undefined}
                className={`relative flex items-start gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors ${
                  active ? "bg-subtle text-body font-semibold" : "text-muted hover:text-body hover:bg-subtle"
                }`}
              >
                {active && <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full bg-brand" aria-hidden="true" />}
                <span className={`mt-0.5 ${active ? "text-brand-strong" : ""}`}><Icon name={n.icon} className="w-[18px] h-[18px]" /></span>
                <span className="leading-tight">
                  {tr(n.key, lang)}
                  <En k={n.key} className="font-normal" />
                </span>
              </button>
            );
          })}
        </nav>
        <div className="px-5 py-4 border-t border-warm-border text-[11px] text-muted leading-relaxed">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-accent-border bg-accent-surface px-2 py-0.5 font-semibold text-accent-amber-strong mb-2">
            <span className="w-1.5 h-1.5 rounded-full bg-brand" /> {tr("demoData", "en")}
          </span>
          <p>{tr("footer", "en")}</p>
        </div>
      </aside>

      <div className="flex-1 min-w-0 flex flex-col">
        {/* Top bar */}
        <header className="print:hidden sticky top-0 z-40 bg-card/95 backdrop-blur border-b border-warm-border">
          <div className="h-16 px-4 sm:px-6 flex items-center gap-3">
            <button type="button" onClick={() => setPage("home")} className="lg:hidden shrink-0" aria-label="GujRERA Saathi">
              <BrandMark className="w-8 h-8" />
            </button>
            <div className="min-w-0 leading-tight">
              <h1 className="font-heading font-bold text-body text-base sm:text-lg truncate">{tr(current.key, lang)}</h1>
              <En k={current.key} className="text-[12px] text-muted opacity-100 truncate" />
            </div>
            <div className="ml-auto flex items-center gap-2 shrink-0">
              <div className="flex rounded-lg border border-warm-border p-0.5" role="group" aria-label="Language">
                {LANGS.map((l) => (
                  <button
                    key={l.id}
                    type="button"
                    onClick={() => setLang(l.id)}
                    aria-pressed={lang === l.id}
                    title={l.name}
                    className={`px-2 py-1 rounded-md text-xs font-semibold ${
                      lang === l.id ? "bg-subtle text-body ring-1 ring-warm-strong" : "text-muted hover:text-body"
                    }`}
                  >
                    {l.label}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setDark((d) => !d)}
                aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
                className="hidden sm:flex w-8 h-8 rounded-lg border border-warm-border items-center justify-center text-muted hover:text-body"
              >
                <Icon name={dark ? "sun" : "moon"} className="w-4 h-4" />
              </button>
              <AccountBar />
            </div>
          </div>
          {/* Tabs (phones and tablets) */}
          <nav aria-label="Main" className="lg:hidden border-t border-warm-border overflow-x-auto [scrollbar-width:none]">
            <div className="flex px-2 w-max">
              {NAV.map((n) => {
                const active = page === n.page;
                return (
                  <button
                    key={n.page}
                    type="button"
                    onClick={() => setPage(n.page)}
                    aria-current={active ? "page" : undefined}
                    className={`px-3 pt-2 pb-1.5 text-xs whitespace-nowrap leading-tight border-b-2 ${
                      active ? "border-brand text-body font-semibold" : "border-transparent text-muted"
                    }`}
                  >
                    {tr(n.key, lang)}
                    <En k={n.key} className="text-[9px] font-normal" />
                  </button>
                );
              })}
            </div>
          </nav>
        </header>

        <main id="main" className="flex-1">
          {page === "home" && <HomePage onAsk={ask} onNavigate={setPage} />}
          {/* Chat and ad check stay mounted so a conversation survives switching pages. */}
          <div hidden={page !== "ask"}>
            <AskPage key={askSeed?.n ?? 0} initialQuestion={askSeed?.q ?? null} />
          </div>
          <div hidden={page !== "check"}>
            <ReraCheckPage />
          </div>
          {page === "calc" && <CalculatorPage key={calcSeed?.n ?? 0} seed={calcSeed?.seed ?? null} onAsk={ask} />}
          {page === "promoter" && <PromoterPage onAsk={ask} />}
          {page === "officer" && <OfficerPage />}
          {page === "risk" && <RiskPage />}
          {page === "enforce" && <EnforcementPage />}
          {page === "report" && <ReportPage projectId={reportId} />}
        </main>

        <footer className="print:hidden lg:hidden border-t border-warm-border">
          <div className="px-4 sm:px-6 py-4 text-xs text-muted">{tr("footer", lang)}</div>
        </footer>
      </div>
    </div>
  );
};

export const SaathiApp: React.FC = () => (
  <SaathiProvider>
    <Shell />
  </SaathiProvider>
);
