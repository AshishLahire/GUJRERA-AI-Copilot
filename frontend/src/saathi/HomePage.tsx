import React, { useEffect, useState } from "react";
import { Overview, fetchOverview } from "../api/gujrera";
import { Icon } from "./Brand";
import { useSaathi } from "./context";
import { En } from "./En";
import { StringKey, tr } from "./strings";

export type Page = "home" | "ask" | "check" | "calc" | "promoter" | "officer" | "risk" | "enforce" | "report" | "desk";

const EXAMPLES: Record<"en" | "gu" | "hi", string[]> = {
  gu: ["મંગલ સ્ક્વેર નું પઝેશન ક્યારે મળશે?", "પઝેશનમાં વિલંબ થાય તો શું મને વ્યાજ મળે?", "મારે ફરિયાદ નોંધાવવી છે"],
  hi: ["कब्जे में देरी होने पर क्या मुझे ब्याज मिलेगा?", "शिकायत कैसे दर्ज करें?", "मेरी शिकायत की स्थिति"],
  en: ["When will I get possession of Mangal Square?", "Can a builder take 20% before the agreement?", "I want to file a complaint"],
};

const COMPLAINT_STATUS: [string, StringKey][] = [
  ["filed", "stFiled"],
  ["under_scrutiny", "stUnderScrutiny"],
  ["hearing_scheduled", "stHearing"],
  ["order_reserved", "stReserved"],
  ["disposed", "stDisposed"],
  ["withdrawn", "stWithdrawn"],
];

const Panel: React.FC<{ title: StringKey; children: React.ReactNode; className?: string }> = ({ title, children, className = "" }) => {
  const { lang } = useSaathi();
  return (
    <section className={`rounded-xl border border-warm-border bg-card ${className}`}>
      <h2 className="px-5 pt-4 pb-3 border-b border-warm-border font-heading text-sm font-bold text-body">
        {tr(title, lang)}
        <En k={title} className="text-muted" />
      </h2>
      <div className="p-5">{children}</div>
    </section>
  );
};

const Kpi: React.FC<{ k: StringKey; icon: string; value: number | null; note?: string }> = ({ k, icon, value, note }) => {
  const { lang } = useSaathi();
  return (
    <div className="rounded-xl border border-warm-border bg-card p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="text-xs font-medium text-muted leading-snug">
          {tr(k, lang)}
          <En k={k} />
        </div>
        <span className="w-8 h-8 shrink-0 rounded-lg bg-brand-soft text-brand-strong flex items-center justify-center">
          <Icon name={icon} className="w-4 h-4" />
        </span>
      </div>
      <div className="font-heading text-2xl font-bold text-body tabular-nums">
        {value === null ? <span className="inline-block w-12 h-7 rounded bg-skeleton animate-pulse" /> : value.toLocaleString("en-IN")}
      </div>
      {note && <div className="text-xs text-muted -mt-2">{note}</div>}
    </div>
  );
};

/** Horizontal bars: label, a thin yellow bar, and the count. */
const Bars: React.FC<{ rows: { label: React.ReactNode; value: number }[] }> = ({ rows }) => {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="flex flex-col gap-3">
      {rows.map((r, i) => (
        <li key={i} className="grid grid-cols-[minmax(0,9rem)_1fr_2.5rem] items-center gap-3 text-sm">
          <span className="text-body truncate">{r.label}</span>
          <span className="h-2 rounded-full bg-subtle overflow-hidden">
            <span className="block h-full rounded-full bg-brand" style={{ width: `${(100 * r.value) / max}%` }} />
          </span>
          <span className="text-right tabular-nums text-muted">{r.value}</span>
        </li>
      ))}
    </ul>
  );
};

export const HomePage: React.FC<{ onAsk: (q: string) => void; onNavigate: (p: Page) => void }> = ({ onAsk, onNavigate }) => {
  const { lang } = useSaathi();
  const [q, setQ] = useState("");
  const [data, setData] = useState<Overview | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetchOverview().then(setData).catch(() => setFailed(true));
  }, []);

  const actions: { icon: string; key: StringKey; body: StringKey; page: Page; prompt?: string }[] = [
    { icon: "building", key: "tileProjectTitle", body: "tileProjectBody", page: "ask" },
    { icon: "shield", key: "tileCheckTitle", body: "tileCheckBody", page: "check" },
    {
      icon: "complaint", key: "tileComplaintTitle", body: "tileComplaintBody", page: "ask",
      prompt: { en: "I want to file a complaint", gu: "મારે ફરિયાદ નોંધાવવી છે", hi: "मुझे शिकायत दर्ज करनी है" }[lang],
    },
    { icon: "law", key: "tileRightsTitle", body: "tileRightsBody", page: "ask" },
    { icon: "calc", key: "navCalc", body: "calcIntro", page: "calc" },
  ];
  const ongoing = data?.projects_by_status.ongoing ?? null;

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      {/* Intro */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-2xl">
          <p className="text-sm text-muted leading-relaxed">{tr("overviewSub", lang)}</p>
          {lang !== "en" && <p lang="en" className="text-xs text-muted opacity-80 mt-0.5">{tr("overviewSub", "en")}</p>}
        </div>
        {data?.is_mock && (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-accent-border bg-accent-surface px-2.5 py-1 text-xs font-semibold text-accent-amber-strong">
            <span className="w-1.5 h-1.5 rounded-full bg-brand" />
            {tr("demoData", lang)}{lang !== "en" && ` · ${tr("demoData", "en")}`}
          </span>
        )}
      </div>

      {/* Ask */}
      <section className="rounded-xl border border-warm-border bg-card p-5">
        <label htmlFor="overview-ask" className="block font-heading text-sm font-bold text-body">
          {tr("askTitle", lang)}
          <En k="askTitle" className="text-muted" />
        </label>
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (q.trim()) onAsk(q.trim());
          }}
        >
          <input
            id="overview-ask"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={tr("heroPlaceholder", lang)}
            className="flex-1 min-w-0 rounded-lg border border-warm-border bg-card text-body px-3.5 py-2.5 text-sm focus:outline-none focus:border-brand focus:ring-2 focus:ring-brand/30"
          />
          <button type="submit" className="px-5 rounded-lg bg-primary-bg text-primary-text text-sm font-semibold leading-tight hover:opacity-90">
            {tr("ask", lang)}
            <En k="ask" className="font-normal" />
          </button>
        </form>
        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLES[lang].map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => onAsk(ex)}
              className="text-xs px-3 py-1.5 rounded-full border border-warm-border text-muted hover:text-body hover:border-warm-strong"
            >
              {ex}
            </button>
          ))}
        </div>
      </section>

      {/* KPIs */}
      {failed ? (
        <p className="text-sm text-muted">Registry figures are unavailable: is the API running?</p>
      ) : (
        <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
          <Kpi k="kpiProjects" icon="building" value={data?.projects ?? null} />
          <Kpi k="kpiOngoing" icon="clock" value={ongoing} />
          <Kpi
            k="kpiDelayed"
            icon="alert"
            value={data?.ongoing_delayed ?? null}
            note={data && ongoing ? `${Math.round((100 * data.ongoing_delayed) / ongoing)}% ${tr("ofTotal", "en")} ${ongoing}` : undefined}
          />
          <Kpi
            k="kpiComplaintsOpen"
            icon="complaint"
            value={data?.complaints_open ?? null}
            note={data ? `${tr("ofTotal", "en")} ${data.complaints}` : undefined}
          />
        </div>
      )}

      {/* Charts */}
      {data && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="byDistrict">
            <Bars rows={data.projects_by_district.map((d) => ({ label: d.district, value: d.count }))} />
          </Panel>
          <Panel title="complaintsByStatus">
            <Bars
              rows={COMPLAINT_STATUS.filter(([st]) => data.complaints_by_status[st]).map(([st, k]) => ({
                label: (
                  <>
                    {tr(k, lang)}
                    {lang !== "en" && <span lang="en" className="text-muted text-xs"> · {tr(k, "en")}</span>}
                  </>
                ),
                value: data.complaints_by_status[st],
              }))}
            />
          </Panel>
        </div>
      )}

      {/* Quick actions */}
      <section>
        <h2 className="font-heading text-sm font-bold text-body mb-3">
          {tr("quickActions", lang)}
          <En k="quickActions" className="text-muted" />
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          {actions.map((a) => (
            <button
              key={a.key}
              type="button"
              onClick={() => (a.prompt ? onAsk(a.prompt) : onNavigate(a.page))}
              className="group text-left rounded-xl border border-warm-border bg-card p-4 hover:border-warm-strong hover:shadow-sm transition"
            >
              <div className="flex items-center justify-between">
                <span className="w-8 h-8 rounded-lg bg-brand-soft text-brand-strong flex items-center justify-center">
                  <Icon name={a.icon} className="w-4 h-4" />
                </span>
                <Icon name="arrow" className="w-4 h-4 text-muted group-hover:text-body" />
              </div>
              <span className="block mt-3 text-sm font-semibold text-body">
                {tr(a.key, lang)}
                <En k={a.key} className="font-normal text-muted" />
              </span>
              <span className="block mt-1 text-xs text-muted leading-relaxed line-clamp-3">{tr(a.body, lang)}</span>
            </button>
          ))}
        </div>
      </section>

      {/* Trust */}
      <Panel title="trustTitle">
        <ul className="grid gap-4 md:grid-cols-3">
          {(["trust1", "trust2", "trust3"] as const).map((k, i) => (
            <li key={k} className="flex gap-3 text-sm text-body leading-relaxed">
              <span className="w-7 h-7 shrink-0 rounded-md bg-subtle text-muted flex items-center justify-center">
                <Icon name={["shield", "server", "lock"][i]} className="w-4 h-4" />
              </span>
              <span>
                {tr(k, lang)}
                {lang !== "en" && <span lang="en" className="block text-xs text-muted mt-0.5">{tr(k, "en")}</span>}
              </span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
};
