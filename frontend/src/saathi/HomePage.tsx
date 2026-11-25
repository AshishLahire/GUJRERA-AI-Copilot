import React, { useEffect, useState } from "react";
import { Overview, fetchChatStarters, fetchOverview } from "../api/gujrera";
import { Icon } from "./Brand";
import { useSaathi } from "./context";
import { En } from "./En";
import { Journey } from "./Journey";
import { RegistryCharts } from "./RegistryCharts";
import { StringKey, tr } from "./strings";

export type Page = "home" | "ask" | "check" | "calc" | "promoter" | "officer" | "risk" | "enforce" | "report" | "desk" | "orders" | "qpr" | "watch" | "agreement" | "today" | "data";

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
    <section className={`warm-card ${className}`}>
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
    <div className="warm-card p-4 flex flex-col gap-3">
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

  // Examples name a project from the loaded database (demo or imported public records).
  const [names, setNames] = useState<{ en: string; gu: string } | null>(null);

  useEffect(() => {
    fetchOverview().then(setData).catch(() => setFailed(true));
    fetchChatStarters()
      .then((s) => s.project && !s.is_mock && setNames({ en: s.project, gu: s.project_gu || s.project }))
      .catch(() => setNames(null));
  }, []);

  const withName = (text: string): string =>
    names
      ? text.replace("Mangal Square", names.en).replace("મંગલ સ્ક્વેર", names.gu).replace("मंगल स्क्वेयर", names.en)
      : text;

  const ongoing = data?.projects_by_status.ongoing ?? null;

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      {/* Hero: what this is, which data, and the question box */}
      <section className="hero-band p-6 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <p className="text-xs font-semibold uppercase tracking-wider text-accent-amber-strong">
              {{ en: "Gujarat Real Estate Regulatory Authority", gu: "ગુજરાત રિયલ એસ્ટેટ નિયમનકારી સત્તામંડળ", hi: "गुजरात रियल एस्टेट विनियामक प्राधिकरण" }[lang]}
            </p>
            <h2 className="mt-2 font-heading text-2xl sm:text-3xl font-bold text-body leading-tight">
              {{ en: "Every RERA answer, in your language", gu: "તમારા ઘરનો દરેક જવાબ, તમારી ભાષામાં", hi: "हर RERA जवाब, आपकी भाषा में" }[lang]}
            </h2>
            <p className="mt-2 text-sm text-muted leading-relaxed">{tr("overviewSub", lang)}</p>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-accent-border bg-card px-3 py-1 text-xs font-semibold text-accent-amber-strong shadow-sm">
            <span className="w-1.5 h-1.5 rounded-full bg-brand" />
            {data?.is_mock
              ? tr("demoData", lang)
              : `${tr("publicData", lang)}${data ? ` · ${data.projects.toLocaleString("en-IN")} ${{ en: "projects", gu: "પ્રોજેક્ટ", hi: "प्रोजेक्ट" }[lang]}` : ""}`}
          </span>
        </div>
        <form
          className="mt-5 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (q.trim()) onAsk(q.trim());
          }}
        >
          <label htmlFor="overview-ask" className="sr-only">{tr("askTitle", lang)}</label>
          <input
            id="overview-ask"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={withName(tr("heroPlaceholder", lang))}
            className="flex-1 min-w-0 rounded-xl border border-warm-strong bg-card text-body px-4 py-3 text-sm shadow-sm focus:outline-none focus:border-brand focus:ring-2 focus:ring-brand/40"
          />
          <button type="submit" className="px-6 rounded-xl bg-primary-bg text-primary-text text-sm font-semibold leading-tight hover:opacity-90 shadow-sm">
            {tr("ask", lang)}
            <En k="ask" className="font-normal" />
          </button>
        </form>
        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLES[lang].map(withName).map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => onAsk(ex)}
              className="text-xs px-3 py-1.5 rounded-full border border-warm-border bg-card/80 text-body hover:border-brand"
            >
              {ex}
            </button>
          ))}
        </div>
      </section>

      <Journey onAsk={onAsk} onNavigate={onNavigate} />

      {/* Registry at a glance */}
      {failed ? (
        <p className="text-sm text-muted">Registry figures are unavailable: is the API running?</p>
      ) : (
        <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
          <Kpi k="kpiProjects" icon="building" value={data?.projects ?? null} />
          <Kpi k="kpiOngoing" icon="clock" value={ongoing} />
          {data && !data.is_mock ? (
            <>
              <Kpi k="kpiPastCompletion" icon="alert" value={data.past_completion}
                note={ongoing !== null ? `${Math.round((100 * data.past_completion) / Math.max(1, data.projects))}% ${tr("ofTotal", "en")} ${data.projects.toLocaleString("en-IN")}` : undefined} />
              <Kpi k="kpiEnding90" icon="calendar" value={data.ending_90_days} />
            </>
          ) : (
            <>
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
            </>
          )}
        </div>
      )}

      {data && <RegistryCharts data={data} lang={lang} />}

      {/* Charts */}
      {data && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="byDistrict">
            <Bars rows={data.projects_by_district.map((d) => ({ label: d.district, value: d.count }))} />
          </Panel>
          {!data.is_mock ? (
            <Panel title="pastByDistrict">
              <Bars rows={data.past_completion_by_district.map((d) => ({ label: d.district, value: d.count }))} />
            </Panel>
          ) : (
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
          )}
        </div>
      )}

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
