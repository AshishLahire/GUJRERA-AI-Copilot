import React, { useEffect, useState } from "react";
import { Lang } from "../api/gujrera";
import { AccountBar } from "../components/AccountBar";
import { AskPage } from "../components/AskPage";
import { ReraCheckPage } from "../components/ReraCheckPage";
import { BrandMark, Icon } from "./Brand";
import { SaathiProvider, useSaathi } from "./context";
import { HomePage, Page } from "./HomePage";
import { OfficerPage, PromoterPage } from "./RolePages";
import { tr } from "./strings";

const PAGES: Page[] = ["home", "ask", "check", "promoter", "officer"];
const NAV: { page: Page; key: "navHome" | "navAsk" | "navCheck" | "navPromoter" | "navOfficer" }[] = [
  { page: "home", key: "navHome" },
  { page: "ask", key: "navAsk" },
  { page: "check", key: "navCheck" },
  { page: "promoter", key: "navPromoter" },
  { page: "officer", key: "navOfficer" },
];
const LANGS: { id: Lang; label: string }[] = [
  { id: "gu", label: "ગુ" },
  { id: "hi", label: "हि" },
  { id: "en", label: "EN" },
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
  // A question from the home page; the counter remounts the chat so each one starts fresh.
  const [askSeed, setAskSeed] = useState<{ q: string; n: number } | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("tab", page);
    window.history.replaceState(null, "", url.toString());
    window.scrollTo({ top: 0 });
  }, [page]);

  const ask = (q: string) => {
    setAskSeed((s) => ({ q, n: (s?.n ?? 0) + 1 }));
    setPage("ask");
  };

  return (
    <div className="min-h-screen flex flex-col bg-page">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 bg-card px-3 py-2 rounded z-50">
        Skip to content
      </a>
      <header className="sticky top-0 z-40 bg-card/95 backdrop-blur border-b border-warm-border">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center gap-3">
          <button type="button" onClick={() => setPage("home")} className="flex items-center gap-2.5 shrink-0" aria-label={tr("brand", "en")}>
            <BrandMark />
            <span className="flex flex-col items-start leading-tight">
              <span className="font-heading font-bold text-body text-[15px]">GujRERA Saathi</span>
              <span className="text-[11px] text-muted hidden sm:block">{lang === "en" ? tr("tagline", "en") : tr("brand", lang)}</span>
            </span>
          </button>
          <nav aria-label="Main" className="hidden xl:flex items-center gap-1 ml-4">
            {NAV.map((n) => (
              <button
                key={n.page}
                type="button"
                onClick={() => setPage(n.page)}
                aria-current={page === n.page ? "page" : undefined}
                className={`px-3 py-2 rounded-lg text-sm font-semibold whitespace-nowrap ${
                  page === n.page ? "bg-brand-soft text-brand" : "text-muted hover:text-body hover:bg-subtle"
                }`}
              >
                {tr(n.key, lang)}
              </button>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2 min-w-0">
            <div className="flex rounded-lg border border-warm-border p-0.5 bg-subtle" role="group" aria-label="Language">
              {LANGS.map((l) => (
                <button
                  key={l.id}
                  type="button"
                  onClick={() => setLang(l.id)}
                  aria-pressed={lang === l.id}
                  className={`px-2 py-1 rounded-md text-xs font-semibold ${lang === l.id ? "bg-card text-brand shadow-sm" : "text-muted"}`}
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
        <nav aria-label="Main" className="xl:hidden border-t border-warm-border overflow-x-auto [scrollbar-width:none]">
          <div className="flex gap-1 px-3 py-1.5 w-max">
            {NAV.map((n) => (
              <button
                key={n.page}
                type="button"
                onClick={() => setPage(n.page)}
                aria-current={page === n.page ? "page" : undefined}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap ${
                  page === n.page ? "bg-brand-soft text-brand" : "text-muted"
                }`}
              >
                {tr(n.key, lang)}
              </button>
            ))}
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
        {page === "promoter" && <PromoterPage onAsk={ask} />}
        {page === "officer" && <OfficerPage />}
      </main>

      <footer className="border-t border-warm-border bg-card">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-5 flex flex-col sm:flex-row gap-2 sm:items-center justify-between text-xs text-muted">
          <span className="flex items-center gap-2">
            <BrandMark className="w-5 h-5" /> GujRERA Saathi · {tr("brand", "gu")}
          </span>
          <span className="max-w-2xl">{tr("footer", lang)}</span>
        </div>
      </footer>
    </div>
  );
};

export const SaathiApp: React.FC = () => (
  <SaathiProvider>
    <Shell />
  </SaathiProvider>
);
