import React, { useCallback, useEffect, useState } from "react";
import { AuthExpiredError, EnfCase, EnfList, fetchCase, fetchCases, updateCase } from "../api/gujrera";
import { Icon } from "./Brand";
import { useSaathi } from "./context";
import { En } from "./En";
import { LoginPrompt } from "./RolePages";
import { StringKey, tr } from "./strings";

const KIND_KEY: Record<EnfCase["kind"], StringKey> = {
  unregistered: "enfUnregistered",
  lapsed: "enfLapsed",
  misleading: "enfMisleading",
};
const KIND_STYLE: Record<EnfCase["kind"], string> = {
  unregistered: "bg-red-50 text-red-800 border-red-200 dark:bg-red-950/50 dark:text-red-200 dark:border-red-900",
  lapsed: "bg-red-50 text-red-800 border-red-200 dark:bg-red-950/50 dark:text-red-200 dark:border-red-900",
  misleading: "bg-accent-surface text-accent-amber-strong border-accent-border",
};
const STATUS_LABEL: Record<EnfCase["status"], string> = {
  new: "New", reviewing: "Reviewing", notice_issued: "Notice issued", closed: "Closed",
};
const OUTCOMES = [["registered", "Registered / regularised"], ["penalty", "Penalty imposed"], ["false_alarm", "False alarm"], ["other", "Other"]];
const FILTERS: [string, string][] = [["open", "Open"], ["new", "New"], ["reviewing", "Reviewing"], ["notice_issued", "Notice issued"], ["closed", "Closed"], ["", "All"]];
const DISTRICTS = ["Ahmedabad", "Surat", "Vadodara", "Rajkot", "Gandhinagar", "Bhavnagar"];

const fmt = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

const KindChip: React.FC<{ kind: EnfCase["kind"] }> = ({ kind }) => {
  const { lang } = useSaathi();
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap ${KIND_STYLE[kind]}`}>
      {tr(KIND_KEY[kind], lang)}
    </span>
  );
};

const CaseDetail: React.FC<{ id: number; onChanged: () => void }> = ({ id, onChanged }) => {
  const { token, lang, logout } = useSaathi();
  const [c, setC] = useState<EnfCase | null>(null);
  const [status, setStatus] = useState("");
  const [outcome, setOutcome] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setC(null);
    fetchCase(token, id)
      .then((x) => { setC(x); setStatus(x.status); setOutcome(x.outcome ?? ""); setNote(""); })
      .catch((e) => { if (e instanceof AuthExpiredError) logout(); setError((e as Error).message); });
  }, [id, token, logout]);

  const save = async () => {
    if (!token || !c) return;
    setBusy(true);
    setError(null);
    try {
      const x = await updateCase(token, c.id, { status, outcome: outcome || undefined, note: note || undefined });
      setC(x);
      setNote("");
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!c) return <div className="p-6 text-sm text-muted">{error ?? "…"}</div>;
  return (
    <div className="flex flex-col gap-5 p-5">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs text-muted">{c.ref_no}</span>
          <KindChip kind={c.kind} />
          <span className="text-xs text-muted">· {STATUS_LABEL[c.status]}{c.outcome ? ` (${c.outcome.replace("_", " ")})` : ""}</span>
        </div>
        <h3 className="mt-1 font-heading text-lg font-bold text-body">{c.title}</h3>
        <p className="text-xs text-muted">{c.law}</p>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <div><dt className="text-xs text-muted">Advertised promoter</dt><dd className="text-body">{c.advertised_promoter ?? "—"}</dd></div>
        <div><dt className="text-xs text-muted">District</dt><dd className="text-body">{c.district ?? "—"}</dd></div>
        <div className="col-span-2"><dt className="text-xs text-muted">Registration number claimed</dt><dd className="text-body font-mono text-xs break-all">{c.claimed_rera ?? "None shown on the ad"}</dd></div>
        <div><dt className="text-xs text-muted">Phone numbers on ads</dt><dd className="text-body tabular-nums">{c.phones.join(", ") || "—"}</dd></div>
        <div><dt className="text-xs text-muted">Websites</dt><dd className="text-body break-all">{c.websites.join(", ") || "—"}</dd></div>
        <div><dt className="text-xs text-muted">Reports</dt><dd className="text-body">{c.reports} · first {fmt(c.opened_on)}, last {fmt(c.last_reported)}</dd></div>
        <div><dt className="text-xs text-muted">Asks payment to an account</dt><dd className={c.asks_payment_to_account ? "text-red-700 dark:text-red-300 font-semibold" : "text-body"}>{c.asks_payment_to_account ? "Yes" : "No"}</dd></div>
      </dl>

      <section className="rounded-lg border border-warm-border">
        <h4 className="px-4 py-2.5 border-b border-warm-border text-sm font-bold text-body">{tr("enfAction", lang)}<En k="enfAction" className="text-muted" /></h4>
        <div className="p-4 grid gap-3">
          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs text-muted">Status
              <select value={status} onChange={(e) => setStatus(e.target.value)} className="mt-1 w-full rounded-md border border-warm-border bg-card text-body text-sm px-2 py-1.5">
                {Object.entries(STATUS_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            <label className="text-xs text-muted">Outcome
              <select value={outcome} onChange={(e) => setOutcome(e.target.value)} className="mt-1 w-full rounded-md border border-warm-border bg-card text-body text-sm px-2 py-1.5">
                <option value="">—</option>
                {OUTCOMES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
          </div>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} placeholder="Note (e.g. notice no., inspection date)"
            className="rounded-md border border-warm-border bg-card text-body text-sm px-3 py-2 focus:outline-none focus:border-brand" />
          <div className="flex items-center gap-3">
            <button type="button" onClick={() => void save()} disabled={busy}
              className="px-4 py-2 rounded-lg bg-primary-bg text-primary-text text-sm font-semibold leading-tight disabled:opacity-40">
              {busy ? "…" : <>{tr("enfSave", lang)}<En k="enfSave" className="font-normal" /></>}
            </button>
            {error && <span role="alert" className="text-xs text-red-700 dark:text-red-300">{error}</span>}
          </div>
          {c.notes && <pre className="whitespace-pre-wrap text-xs text-muted font-sans border-t border-warm-border pt-3">{c.notes}</pre>}
        </div>
      </section>

      <section>
        <h4 className="text-sm font-bold text-body mb-2">{tr("enfEvidence", lang)}<En k="enfEvidence" className="text-muted" /></h4>
        <ul className="flex flex-col gap-3">
          {(c.evidence ?? []).map((r) => (
            <li key={r.id} className="rounded-lg border border-warm-border p-3">
              <div className="flex flex-wrap gap-x-3 text-[11px] text-muted mb-2">
                <span>{fmt(r.reported_on)}</span><span>via {r.channel}</span><span>check: {r.verdict.replace(/_/g, " ")}</span>
              </div>
              <pre className="whitespace-pre-wrap text-xs text-body font-sans bg-subtle rounded p-2 max-h-40 overflow-auto">{r.excerpt}</pre>
              {r.problems.length > 0 && (
                <ul className="mt-2 text-xs text-muted list-disc pl-4 space-y-0.5">
                  {r.problems.map((p, i) => <li key={i}>{p}</li>)}
                </ul>
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
};

export const EnforcementPage: React.FC = () => {
  const { user, token, lang, logout } = useSaathi();
  const allowed = user?.role === "officer";
  const [status, setStatus] = useState("open");
  const [kind, setKind] = useState("");
  const [district, setDistrict] = useState("");
  const [data, setData] = useState<EnfList | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!allowed || !token) return;
    fetchCases(token, { status, kind, district })
      .then((d) => { setData(d); setSelected((s) => s ?? d.items[0]?.id ?? null); })
      .catch((e) => { if (e instanceof AuthExpiredError) logout(); setError((e as Error).message); });
  }, [allowed, token, status, kind, district, logout]);

  useEffect(load, [load]);

  const k = data?.counts;
  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <div className="max-w-3xl">
        <p className="text-sm text-muted leading-relaxed">{tr("enfIntro", lang)}</p>
        {lang !== "en" && <p lang="en" className="text-xs text-muted opacity-80 mt-0.5">{tr("enfIntro", "en")}</p>}
      </div>
      {!allowed && <LoginPrompt k="loginNeededEnforce" />}
      {allowed && error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 p-4 text-sm">{error}</div>}
      {allowed && k && (
        <>
          <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
            {([["enfOpen", k.open, "flag"], ["enfNew", k.new, "clock"], ["enfUnregistered", k.by_kind.unregistered ?? 0, "alert"], ["enfReports", k.reports, "chat"]] as [StringKey, number, string][]).map(([key, v, icon]) => (
              <div key={key} className="rounded-xl border border-warm-border bg-card p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="text-xs font-medium text-muted">{tr(key, lang)}<En k={key} /></div>
                  <span className="w-8 h-8 rounded-lg bg-brand-soft text-brand-strong flex items-center justify-center"><Icon name={icon} className="w-4 h-4" /></span>
                </div>
                <div className="mt-3 font-heading text-2xl font-bold text-body tabular-nums">{v}</div>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex flex-wrap rounded-lg border border-warm-border p-0.5" role="group" aria-label="Status">
              {FILTERS.map(([v, l]) => (
                <button key={v || "all"} type="button" aria-pressed={status === v} onClick={() => { setStatus(v); setSelected(null); }}
                  className={`px-3 py-1.5 rounded-md text-xs font-semibold ${status === v ? "bg-subtle text-body ring-1 ring-warm-strong" : "text-muted hover:text-body"}`}>
                  {l}
                </button>
              ))}
            </div>
            <select aria-label="Kind" value={kind} onChange={(e) => { setKind(e.target.value); setSelected(null); }}
              className="rounded-lg border border-warm-border bg-card text-body text-sm px-3 py-2">
              <option value="">All kinds</option>
              <option value="unregistered">{tr("enfUnregistered", "en")}</option>
              <option value="lapsed">{tr("enfLapsed", "en")}</option>
              <option value="misleading">{tr("enfMisleading", "en")}</option>
            </select>
            {data?.district_scope ? (
              <span className="text-sm text-muted">{data.district_scope}</span>
            ) : (
              <select aria-label="District" value={district} onChange={(e) => { setDistrict(e.target.value); setSelected(null); }}
                className="rounded-lg border border-warm-border bg-card text-body text-sm px-3 py-2">
                <option value="">All districts</option>
                {DISTRICTS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            )}
          </div>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] items-start">
            <ul className="rounded-xl border border-warm-border bg-card divide-y divide-warm-border overflow-hidden">
              {data!.items.map((c) => (
                <li key={c.id}>
                  <button type="button" onClick={() => setSelected(c.id)} aria-current={selected === c.id ? "true" : undefined}
                    className={`relative w-full text-left px-4 py-3 hover:bg-subtle ${selected === c.id ? "bg-subtle" : ""}`}>
                    {selected === c.id && <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full bg-brand" />}
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-body truncate">{c.title}</div>
                        <div className="text-[11px] text-muted">{c.ref_no} · {c.district ?? "?"} · {STATUS_LABEL[c.status]}</div>
                      </div>
                      <div className="text-right shrink-0">
                        <div className="font-heading font-bold tabular-nums text-body">{c.reports}</div>
                        <div className="text-[10px] text-muted">reports</div>
                      </div>
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2">
                      <KindChip kind={c.kind} />
                      {c.asks_payment_to_account && <span className="text-[11px] text-red-700 dark:text-red-300 font-semibold">pay-to-account</span>}
                      <span className="text-[11px] text-muted">last {fmt(c.last_reported)}</span>
                    </div>
                  </button>
                </li>
              ))}
              {data!.items.length === 0 && <li className="px-4 py-6 text-sm text-muted text-center">No cases.</li>}
            </ul>
            <div className="rounded-xl border border-warm-border bg-card lg:sticky lg:top-20">
              {selected ? <CaseDetail id={selected} onChanged={load} /> : <div className="p-6 text-sm text-muted">Select a case.</div>}
            </div>
          </div>
        </>
      )}
    </div>
  );
};
