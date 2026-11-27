import React, { useEffect, useMemo, useState } from "react";
import { AuthExpiredError, RiskItem, RiskResponse, fetchRisk } from "../api/gujrera";
import { Icon } from "./Brand";
import { say, useSaathi } from "./context";
import { En } from "./En";
import { LoginPrompt } from "./RolePages";
import { StringKey, tr } from "./strings";

type Band = "high" | "medium" | "low";
const DISTRICTS = ["Ahmedabad", "Surat", "Vadodara", "Rajkot", "Gandhinagar", "Bhavnagar"];

const SIGNAL: Record<string, { en: string; gu: string; hi: string }> = {
  pace: { en: "Behind schedule", gu: "સમયપત્રકથી પાછળ", hi: "समय से पीछे" },
  projection: { en: "Late at current pace / stalled", gu: "હાલની ગતિએ મોડું / અટકેલું", hi: "मौजूदा गति से देर / रुका" },
  past_due: { en: "Promised date passed", gu: "વચન આપેલી તારીખ વીતી", hi: "वादा की तारीख निकली" },
  extended: { en: "Completion extended", gu: "પૂર્ણતા તારીખ લંબાવાઈ", hi: "पूर्णता तारीख बढ़ी" },
  qpr: { en: "Quarterly reports overdue/late", gu: "ત્રિમાસિક અહેવાલ બાકી/મોડા", hi: "तिमाही रिपोर्ट बाकी/देर" },
  registration: { en: "Registration expiring", gu: "નોંધણી પૂરી થતી", hi: "पंजीकरण समाप्त होता" },
  approvals: { en: "Approvals pending", gu: "મંજૂરી બાકી", hi: "अनुमोदन लंबित" },
  complaints: { en: "Open complaints", gu: "ખુલ્લી ફરિયાદો", hi: "खुली शिकायतें" },
  complaints_spike: { en: "Complaints rising", gu: "ફરિયાદો વધી", hi: "शिकायतें बढ़ीं" },
  promoter_delays: { en: "Promoter's other projects late", gu: "પ્રમોટરના અન્ય પ્રોજેક્ટ મોડા", hi: "प्रमोटर के अन्य प्रोजेक्ट देर से" },
  promoter_orders: { en: "Adverse orders on promoter", gu: "પ્રમોટર સામે આદેશ", hi: "प्रमोटर पर प्रतिकूल आदेश" },
  promoter_dues: { en: "Promoter's unpaid penalties", gu: "પ્રમોટરના બાકી દંડ", hi: "प्रमोटर के बकाया जुर्माने" },
};

const BAND_STYLE: Record<Band, string> = {
  high: "bg-red-50 text-red-800 border-red-200 dark:bg-red-950/50 dark:text-red-200 dark:border-red-900",
  medium: "bg-accent-surface text-accent-amber-strong border-accent-border",
  low: "bg-subtle text-muted border-warm-border",
};
const BAND_BAR: Record<Band, string> = { high: "bg-red-600 dark:bg-red-400", medium: "bg-brand", low: "bg-warm-strong" };
const BAND_KEY: Record<Band, StringKey> = { high: "riskHigh", medium: "riskMedium", low: "riskLow" };

const fmtDate = (iso: string | null) =>
  iso ? new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { month: "short", year: "numeric" }) : "—";

const BandChip: React.FC<{ band: Band }> = ({ band }) => {
  const { lang } = useSaathi();
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap ${BAND_STYLE[band]}`}>
      {tr(BAND_KEY[band], lang)}
    </span>
  );
};

const Row: React.FC<{ r: RiskItem }> = ({ r }) => {
  const { lang } = useSaathi();
  const [open, setOpen] = useState(false);
  const name = lang === "gu" && r.name_gu ? r.name_gu : r.name;
  return (
    <>
      <tr className="border-t border-warm-border hover:bg-subtle/60 cursor-pointer align-top" onClick={() => setOpen((o) => !o)}>
        <td className="px-4 py-3">
          <div className="flex items-start gap-2">
            <Icon name="arrow" className={`w-3.5 h-3.5 mt-1 shrink-0 text-muted transition-transform ${open ? "rotate-90" : ""}`} />
            <div className="min-w-0">
              <div className="font-semibold text-body">{name}</div>
              <div className="text-[11px] text-muted font-mono break-all">{r.rera_no}</div>
            </div>
          </div>
        </td>
        <td className="px-3 py-3 text-muted whitespace-nowrap hidden md:table-cell">{r.district}</td>
        <td className="px-3 py-3 text-muted hidden lg:table-cell">{r.promoter.replace(" (Demo)", "")}</td>
        <td className="px-3 py-3 whitespace-nowrap hidden sm:table-cell tabular-nums">
          <span className="text-body">{r.percent_complete ?? "—"}%</span>
          {r.expected_percent != null && <span className="text-muted text-xs"> / {Math.round(r.expected_percent)}%</span>}
        </td>
        <td className="px-3 py-3 whitespace-nowrap hidden xl:table-cell tabular-nums text-muted">{fmtDate(r.projected_finish)}</td>
        <td className="px-4 py-3">
          <div className="flex items-center gap-2 justify-end">
            <span className="w-16 h-1.5 rounded-full bg-subtle overflow-hidden hidden sm:block">
              <span className={`block h-full ${BAND_BAR[r.band]}`} style={{ width: `${r.score}%` }} />
            </span>
            <span className="font-heading font-bold tabular-nums w-7 text-right">{r.score}</span>
            <BandChip band={r.band} />
          </div>
        </td>
      </tr>
      {open && (
        <tr className="bg-subtle/60">
          <td colSpan={6} className="px-4 pb-4 pt-1">
            <ul className="flex flex-col gap-2 text-sm">
              {r.signals.map((s, i) => (
                <li key={i} className="flex gap-3">
                  <span className="w-10 shrink-0 text-right font-semibold tabular-nums text-body">+{s.points}</span>
                  <span className="min-w-0">
                    <span className="text-body">{s.text}</span>
                    <span className="block text-[11px] text-muted break-all">
                      {SIGNAL[s.code] ? say(SIGNAL[s.code], lang) : s.code} · {s.citations.map((c) => `${c.type.replace(/_/g, " ")} ${c.id}`).join(", ")}
                    </span>
                  </span>
                </li>
              ))}
              {r.signals.length === 0 && <li className="text-muted">{say({ en: "No warning signals.", gu: "કોઈ ચેતવણી સંકેત નથી.", hi: "कोई चेतावनी संकेत नहीं।" }, lang)}</li>}
            </ul>
          </td>
        </tr>
      )}
    </>
  );
};

export const RiskPage: React.FC = () => {
  const { user, token, lang, logout } = useSaathi();
  const allowed = user?.role === "officer";
  const [district, setDistrict] = useState<string>("");
  const [band, setBand] = useState<Band | "all">("high");
  const [data, setData] = useState<RiskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!allowed || !token) return;
    setBusy(true);
    setError(null);
    fetchRisk(token, lang, district || null)
      .then(setData)
      .catch((e) => {
        if (e instanceof AuthExpiredError) logout();
        setError((e as Error).message);
      })
      .finally(() => setBusy(false));
  }, [allowed, token, lang, district, logout]);

  const items = useMemo(() => (data ? data.items.filter((r) => band === "all" || r.band === band) : []), [data, band]);
  const s = data?.summary;
  const maxSignal = s ? Math.max(1, ...Object.values(s.by_signal)) : 1;

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <div className="max-w-3xl">
        <p className="text-sm text-muted leading-relaxed">{tr("riskIntro", lang)}</p>
        {lang !== "en" && <p lang="en" className="text-xs text-muted opacity-80 mt-0.5">{tr("riskIntro", "en")}</p>}
      </div>
      {!allowed && <LoginPrompt k="loginNeededRisk" />}
      {allowed && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            {data?.district_scope ? (
              <span className="text-sm text-muted">{data.district_scope}</span>
            ) : (
              <select
                aria-label={say({ en: "District", gu: "જિલ્લો", hi: "जिला" }, lang)}
                value={district}
                onChange={(e) => setDistrict(e.target.value)}
                className="rounded-lg border border-warm-border bg-card text-body text-sm px-3 py-2"
              >
                <option value="">{tr("riskAllDistricts", lang)}</option>
                {DISTRICTS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            )}
            <div className="flex rounded-lg border border-warm-border p-0.5" role="group" aria-label={say({ en: "Risk level", gu: "જોખમનું સ્તર", hi: "जोखिम का स्तर" }, lang)}>
              {(["high", "medium", "low", "all"] as const).map((b) => (
                <button
                  key={b}
                  type="button"
                  aria-pressed={band === b}
                  onClick={() => setBand(b)}
                  className={`px-3 py-1.5 rounded-md text-xs font-semibold ${band === b ? "bg-subtle text-body ring-1 ring-warm-strong" : "text-muted hover:text-body"}`}
                >
                  {b === "all" ? tr("riskAll", lang) : tr(BAND_KEY[b], lang)}
                  {s && b !== "all" ? <span className="ml-1 text-muted tabular-nums">{s.by_band[b]}</span> : null}
                </button>
              ))}
            </div>
            {busy && <span className="text-xs text-muted">…</span>}
          </div>
          {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 p-4 text-sm">{error}</div>}

          {s && (
            <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
              {([["riskWatched", s.projects, "building"], ["riskHigh", s.by_band.high, "alert"], ["riskMedium", s.by_band.medium, "clock"], ["riskLow", s.by_band.low, "shield"]] as [StringKey, number, string][]).map(([k, v, icon]) => (
                <div key={k} className="rounded-xl border border-warm-border bg-card p-4">
                  <div className="flex items-start justify-between gap-2">
                    <div className="text-xs font-medium text-muted">{tr(k, lang)}<En k={k} /></div>
                    <span className="w-8 h-8 rounded-lg bg-brand-soft text-brand-strong flex items-center justify-center"><Icon name={icon} className="w-4 h-4" /></span>
                  </div>
                  <div className="mt-3 font-heading text-2xl font-bold text-body tabular-nums">{v}</div>
                </div>
              ))}
            </div>
          )}

          {s && (
            <div className="grid gap-4 lg:grid-cols-2">
              <section className="rounded-xl border border-warm-border bg-card">
                <h2 className="px-5 pt-4 pb-3 border-b border-warm-border text-sm font-bold text-body">{tr("riskDrivers", lang)}<En k="riskDrivers" className="text-muted" /></h2>
                <ul className="p-5 flex flex-col gap-2.5">
                  {Object.entries(s.by_signal).map(([code, n]) => (
                    <li key={code} className="grid grid-cols-[minmax(0,13rem)_1fr_2rem] items-center gap-3 text-sm">
                      <span className="text-body truncate">{SIGNAL[code]?.[lang] ?? code}</span>
                      <span className="h-2 rounded-full bg-subtle overflow-hidden"><span className="block h-full rounded-full bg-brand" style={{ width: `${(100 * n) / maxSignal}%` }} /></span>
                      <span className="text-right tabular-nums text-muted">{n}</span>
                    </li>
                  ))}
                </ul>
              </section>
              <section className="rounded-xl border border-warm-border bg-card">
                <h2 className="px-5 pt-4 pb-3 border-b border-warm-border text-sm font-bold text-body">{tr("riskByDistrict", lang)}<En k="riskByDistrict" className="text-muted" /></h2>
                <ul className="p-5 flex flex-col gap-2.5">
                  {s.by_district.map((d) => {
                    const total = d.high + d.medium + d.low || 1;
                    return (
                      <li key={d.district} className="grid grid-cols-[minmax(0,8rem)_1fr_4.5rem] items-center gap-3 text-sm">
                        <span className="text-body">{d.district}</span>
                        <span className="h-2 rounded-full bg-subtle overflow-hidden flex">
                          <span className="h-full bg-red-600 dark:bg-red-400" style={{ width: `${(100 * d.high) / total}%` }} />
                          <span className="h-full bg-brand" style={{ width: `${(100 * d.medium) / total}%` }} />
                        </span>
                        <span className="text-right tabular-nums text-muted text-xs">{d.high} / {total}</span>
                      </li>
                    );
                  })}
                </ul>
              </section>
            </div>
          )}

          {data && (
            <section className="rounded-xl border border-warm-border bg-card overflow-hidden">
              <h2 className="px-5 py-3 border-b border-warm-border text-sm font-bold text-body">
                {tr("riskList", lang)}<En k="riskList" className="text-muted" />
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-xs text-muted bg-subtle">
                    <tr>
                      <th className="text-left font-semibold px-4 py-2">{say({ en: "Project", gu: "પ્રોજેક્ટ", hi: "प्रोजेक्ट" }, lang)}</th>
                      <th className="text-left font-semibold px-3 py-2 hidden md:table-cell">{say({ en: "District", gu: "જિલ્લો", hi: "जिला" }, lang)}</th>
                      <th className="text-left font-semibold px-3 py-2 hidden lg:table-cell">{say({ en: "Promoter", gu: "પ્રમોટર", hi: "प्रमोटर" }, lang)}</th>
                      <th className="text-left font-semibold px-3 py-2 hidden sm:table-cell">{say({ en: "Built / expected", gu: "બંધાયેલ / અપેક્ષિત", hi: "निर्मित / अपेक्षित" }, lang)}</th>
                      <th className="text-left font-semibold px-3 py-2 hidden xl:table-cell">{say({ en: "Projected finish", gu: "અંદાજિત પૂર્ણતા", hi: "अनुमानित समापन" }, lang)}</th>
                      <th className="text-right font-semibold px-4 py-2">{say({ en: "Score", gu: "સ્કોર", hi: "स्कोर" }, lang)}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((r) => <Row key={r.project_id} r={r} />)}
                    {items.length === 0 && (
                      <tr><td colSpan={6} className="px-4 py-6 text-center text-muted">{say({ en: "No projects at this level.", gu: "આ સ્તરે કોઈ પ્રોજેક્ટ નથી.", hi: "इस स्तर पर कोई प्रोजेक्ट नहीं।" }, lang)}</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              <p className="px-5 py-3 border-t border-warm-border text-[11px] text-muted">
                {say({
                  en: "Click a project to see each signal, its points and its source. Score = sum of points (max 100): high ≥ 60, medium ≥ 30.",
                  gu: "દરેક સંકેત, તેના પોઇન્ટ અને સ્રોત જોવા પ્રોજેક્ટ પર ક્લિક કરો. સ્કોર = પોઇન્ટનો સરવાળો (મહત્તમ 100): ઊંચું ≥ 60, મધ્યમ ≥ 30.",
                  hi: "हर संकेत, उसके अंक और स्रोत देखने के लिए प्रोजेक्ट पर क्लिक करें। स्कोर = अंकों का योग (अधिकतम 100): उच्च ≥ 60, मध्यम ≥ 30।",
                }, lang)}
              </p>
            </section>
          )}
        </>
      )}
    </div>
  );
};
