import React, { useEffect, useState } from "react";
import { CalcSeed, Lang, NAVIGATE_EVENT, OPEN_CALC_EVENT, OPEN_REPORT_EVENT, fetchHealth } from "../api/gujrera";
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
import { ComplaintDeskPage } from "./ComplaintDeskPage";
import { OrderTrackerPage } from "./OrderTrackerPage";
import { QprPage } from "./QprPage";
import { WatchBell, WatchPage } from "./WatchPage";
import { AgreementPage } from "./AgreementPage";
import { MyComplaintPage } from "./MyComplaintPage";
import { OfficerDeskPage } from "./OfficerDeskPage";
import { DataOnboardingPage } from "./DataOnboardingPage";
import { AuditPage, UsersPage } from "./AdminPages";
import { CircularsPage } from "./CircularsPage";
import { AccuracyPage } from "./AccuracyPage";
import { StringKey, tr } from "./strings";

const PAGES: Page[] = ["home", "ask", "check", "calc", "promoter", "officer", "risk", "enforce", "report", "desk", "orders", "qpr", "watch", "agreement", "today", "data", "users", "audit", "circulars", "accuracy", "complaints"];
type NavItem = { page: Page; key: StringKey; icon: string };
const ITEM: Record<Page, NavItem> = {
  home: { page: "home", key: "navOverview", icon: "grid" },
  today: { page: "today", key: "navToday", icon: "clock" },
  data: { page: "data", key: "navData", icon: "server" },
  users: { page: "users", key: "navUsers", icon: "user" },
  audit: { page: "audit", key: "navAudit", icon: "lock" },
  circulars: { page: "circulars", key: "navCirculars", icon: "law" },
  accuracy: { page: "accuracy", key: "navAccuracy", icon: "chart" },
  ask: { page: "ask", key: "navAsk", icon: "chat" },
  check: { page: "check", key: "navCheck", icon: "shield" },
  calc: { page: "calc", key: "navCalc", icon: "calc" },
  complaints: { page: "complaints", key: "navComplaint", icon: "complaint" },
  report: { page: "report", key: "navReport", icon: "doc" },
  agreement: { page: "agreement", key: "navAgreement", icon: "law" },
  orders: { page: "orders", key: "navOrders", icon: "law" },
  watch: { page: "watch", key: "navWatch", icon: "eye" },
  promoter: { page: "promoter", key: "navPromoter", icon: "briefcase" },
  qpr: { page: "qpr", key: "navQpr", icon: "calendar" },
  officer: { page: "officer", key: "navOfficer", icon: "chart" },
  desk: { page: "desk", key: "navDesk", icon: "complaint" },
  risk: { page: "risk", key: "navRisk", icon: "alert" },
  enforce: { page: "enforce", key: "navEnforce", icon: "flag" },
};
/** Each role sees the tools for its own job. Pages that only make sense on GUJRERA's internal data
 * (penalty orders, the risk score) are hidden when the app runs on public records. */
function navFor(role: string | undefined, demo: boolean, statewide = false): NavItem[] {
  const pages: Page[] =
    role === "officer"
      ? ["today", "ask", "officer", "enforce", "desk", "report", "check", ...(demo ? (["risk", "orders"] as Page[]) : []),
         ...(statewide ? (["data", "circulars", "accuracy", "users", "audit"] as Page[]) : [])]
      : role === "developer" || role === "promoter"  // promoter accounts have the role "developer"
        ? ["home", "ask", "promoter", "qpr", "check"]
        : role === "agent"
          ? ["home", "ask", "check", "report"]
          : ["home", "check", "ask", "complaints", "report", "agreement", "watch", "calc", ...(demo ? (["orders"] as Page[]) : [])];
  return pages.map((p) => ITEM[p]);
}
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

const THEME_KEY = "saathi-theme";

/** Light is the default; dark only when this browser chose it with the toggle (or ?theme=dark in a link). */
function initialDark(): boolean {
  const theme = new URLSearchParams(window.location.search).get("theme");
  if (theme) return theme === "dark";
  try {
    return window.localStorage.getItem(THEME_KEY) === "dark";
  } catch {
    return false;
  }
}

function saveTheme(dark: boolean): void {
  try {
    window.localStorage.setItem(THEME_KEY, dark ? "dark" : "light");
  } catch {
    /* private window or blocked storage: the choice lasts until the page is closed */
  }
}

const Shell: React.FC = () => {
  const { lang, setLang, user, restoring } = useSaathi();
  const [page, setPage] = useState<Page>(initialPage);
  const [dark, setDark] = useState<boolean>(initialDark);
  // A question from the overview page; the counter remounts the chat so each one starts fresh.
  const [askSeed, setAskSeed] = useState<{ q: string; n: number } | null>(null);
  const [calcSeed, setCalcSeed] = useState<{ seed: CalcSeed; n: number } | null>(null);
  const [reportId, setReportId] = useState<number | null>(null);
  // Label the data honestly: demo records, or records imported from the public GUJRERA portal.
  // null until the health check answers: show neither label nor demo-only pages before we know.
  const [demo, setDemo] = useState<boolean | null>(null);
  useEffect(() => {
    fetchHealth().then((h) => setDemo(h.mock_projects > 0 || h.projects === 0)).catch(() => setDemo(true));
  }, []);
  const NAV = restoring ? [] : navFor(user?.role, demo === true, user?.role === "officer" && !user.district_scope);
  const current = ITEM[page] ?? ITEM.home;
  // An officer lands on their own work queue; leaving a role returns to that role's first page.
  const role = user?.role;
  useEffect(() => {
    if (restoring) return; // wait until the saved session is checked
    if (role === "officer") setPage((p) => (p === "home" ? "today" : p));
    else setPage((p) => (p === "today" ? "home" : p));
  }, [role, restoring]);

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
      <aside className="print:!hidden hidden lg:flex w-64 shrink-0 flex-col border-r border-warm-border bg-sidebar sticky top-0 h-screen">
        <button type="button" onClick={() => setPage(role === "officer" ? "today" : "home")} className="h-16 px-5 flex items-center gap-3 border-b border-warm-border text-left">
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
                  active ? "bg-card text-body font-semibold shadow-sm ring-1 ring-warm-border" : "text-muted hover:text-body hover:bg-card/70"
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
          {demo !== null && (<>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-accent-border bg-accent-surface px-2 py-0.5 font-semibold text-accent-amber-strong mb-2">
            <span className="w-1.5 h-1.5 rounded-full bg-brand" /> {tr(demo ? "demoData" : "publicData", "en")}
          </span>
          <p>{tr(demo ? "footer" : "footerPublic", lang)}</p>
          </>)}
        </div>
      </aside>

      <div className="flex-1 min-w-0 flex flex-col">
        {/* Top bar */}
        <header className="print:hidden sticky top-0 z-40 bg-card/95 backdrop-blur border-b border-warm-border">
          <div className="h-16 px-4 sm:px-6 flex items-center gap-3">
            <button type="button" onClick={() => setPage(role === "officer" ? "today" : "home")} className="lg:hidden shrink-0" aria-label="GujRERA Saathi">
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
                onClick={() => setDark((d) => { saveTheme(!d); return !d; })}
                aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
                className="hidden sm:flex w-8 h-8 rounded-lg border border-warm-border items-center justify-center text-muted hover:text-body"
              >
                <Icon name={dark ? "sun" : "moon"} className="w-4 h-4" />
              </button>
              <WatchBell page={page} />
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
          {restoring && <div className="max-w-7xl mx-auto px-6 py-10 text-sm text-muted" role="status">Loading your account…</div>}
          {!restoring && (<>
          {page === "home" && <HomePage onAsk={ask} onNavigate={setPage} />}
          {page === "today" && <OfficerDeskPage />}
          {page === "data" && <DataOnboardingPage />}
          {page === "users" && <UsersPage />}
          {page === "audit" && <AuditPage />}
          {page === "circulars" && <CircularsPage />}
          {page === "accuracy" && <AccuracyPage />}
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
          {page === "desk" && <ComplaintDeskPage />}
          {page === "orders" && <OrderTrackerPage />}
          {page === "qpr" && <QprPage />}
          {page === "watch" && <WatchPage />}
          {page === "agreement" && <AgreementPage />}
          {page === "complaints" && <MyComplaintPage />}
          </>)}
        </main>

        <footer className="print:hidden lg:hidden border-t border-warm-border">
          <div className="px-4 sm:px-6 py-4 text-xs text-muted">{demo !== null && tr(demo ? "footer" : "footerPublic", lang)}</div>
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
