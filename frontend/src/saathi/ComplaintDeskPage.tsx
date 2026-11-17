import React, { useCallback, useEffect, useState } from "react";
import { AuthExpiredError, ComplaintBrief, OrderStatus, TriageResponse, fetchBrief, fetchOrdersToEnforce, fetchTriage, updateComplaintStatus, updateCompliance } from "../api/gujrera";
import { OrderCard } from "./OrderTrackerPage";
import { Icon } from "./Brand";
import { useSaathi } from "./context";
import { En } from "./En";
import { LoginPrompt } from "./RolePages";
import { StringKey, tr } from "./strings";

const BAND_STYLE: Record<string, string> = {
  urgent: "bg-red-50 text-red-800 border-red-200 dark:bg-red-950/50 dark:text-red-200 dark:border-red-900",
  high: "bg-accent-surface text-accent-amber-strong border-accent-border",
  normal: "bg-subtle text-muted border-warm-border",
};
const TONE_DOT: Record<string, string> = { good: "bg-emerald-600", warn: "bg-brand", bad: "bg-red-600" };
const NEXT: Record<string, string[]> = {
  filed: ["under_scrutiny", "hearing_scheduled", "withdrawn"],
  under_scrutiny: ["hearing_scheduled", "order_reserved", "disposed", "withdrawn"],
  hearing_scheduled: ["hearing_scheduled", "order_reserved", "disposed", "withdrawn"],
  order_reserved: ["disposed"],
};
const LABEL: Record<string, string> = {
  filed: "Filed", under_scrutiny: "Under scrutiny", hearing_scheduled: "Hearing scheduled", order_reserved: "Order reserved",
  disposed: "Disposed", withdrawn: "Withdrawn",
};
const OUTCOMES = ["allowed", "partly_allowed", "dismissed", "settled"];
const nice = (s: string) => s.replace(/_/g, " ");
const fmt = (iso: string) => new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

const Clock: React.FC<{ left: number }> = ({ left }) => (
  <span className={`text-[11px] font-semibold whitespace-nowrap ${left < 0 ? "text-red-700 dark:text-red-300" : left <= 15 ? "text-accent-amber-strong" : "text-muted"}`}>
    {left < 0 ? `${-left} days over` : `${left} days left`}
  </span>
);

const Brief: React.FC<{ id: number; onChanged: () => void }> = ({ id, onChanged }) => {
  const { token, lang, logout } = useSaathi();
  const [b, setB] = useState<ComplaintBrief | null>(null);
  const [status, setStatus] = useState("");
  const [hearing, setHearing] = useState("");
  const [outcome, setOutcome] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    fetchBrief(token, id, lang).then((x) => { setB(x); setStatus(""); setMsg(null); })
      .catch((e) => { if (e instanceof AuthExpiredError) logout(); setMsg((e as Error).message); });
  }, [id, token, lang, logout]);
  useEffect(() => { setB(null); load(); }, [load]);

  const save = async () => {
    if (!token || !b || !status) return;
    setBusy(true);
    setMsg(null);
    try {
      await updateComplaintStatus(token, b.complaint.id, { status, note: note || undefined, hearing_on: hearing || undefined, outcome: outcome || undefined });
      setNote(""); setHearing(""); setOutcome("");
      load();
      onChanged();
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!b) return <div className="p-6 text-sm text-muted">{msg ?? "…"}</div>;
  const c = b.complaint;
  const outcomes = b.precedents.category_outcomes;
  const decided = b.precedents.category_decided || 1;
  return (
    <article className="report-sheet flex flex-col gap-5 p-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs text-muted">{tr("deskBrief", lang)}{lang !== "en" ? ` · ${tr("deskBrief", "en")}` : ""}</div>
          <h3 className="font-heading text-lg font-bold text-body">{c.ref_no}</h3>
          <div className="text-xs text-muted">Form {c.form} · {nice(c.category)} · filed {fmt(c.filed_on)} via {c.channel} · {LABEL[c.status] ?? c.status}</div>
        </div>
        <div className="text-right">
          <Clock left={c.days_left} />
          <div className="text-[11px] text-muted">60-day date: {fmt(c.due_by)}</div>
          <button type="button" onClick={() => window.print()} className="print:hidden mt-1 inline-flex items-center gap-1 text-xs font-semibold text-body hover:underline">
            <Icon name="printer" className="w-3.5 h-3.5" /> Print brief
          </button>
        </div>
      </header>

      <section>
        <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">Complaint</h4>
        <p className="text-sm text-body bg-subtle rounded-md p-3">{c.summary}</p>
        {c.relief && <p className="text-xs text-muted mt-1">Relief sought: {nice(c.relief)}</p>}
      </section>

      <section>
        <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">Law</h4>
        <ul className="text-sm text-body flex flex-col gap-0.5">
          {b.sections.map((s) => <li key={s.section}><b>Section {s.section}</b> · {s.title}</li>)}
        </ul>
        <p className="text-xs text-muted mt-1">{b.forum === "adjudicating_officer" ? "Adjudicating officer" : "Authority"}: {b.forum_law}</p>
      </section>

      {b.project && (
        <section>
          <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">Project record · {b.project.project.name}</h4>
          <ul className="text-sm flex flex-col gap-1">
            {b.project.glance.map((g, i) => (
              <li key={i} className="flex gap-2"><span className={`mt-1.5 w-2 h-2 shrink-0 rounded-full ${TONE_DOT[g.tone]}`} />{g.text}</li>
            ))}
          </ul>
          {b.risk && (
            <p className="text-xs text-muted mt-2">Risk watchlist: <b className="text-body">{b.risk.score} ({b.risk.band})</b> · {b.risk.signals.slice(0, 2).join(" ")}</p>
          )}
        </section>
      )}

      <section>
        <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">How similar complaints were decided</h4>
        <div className="flex h-2.5 rounded-full overflow-hidden bg-subtle" role="img" aria-label="Outcomes">
          {[["allowed", "bg-emerald-600"], ["partly_allowed", "bg-emerald-400"], ["settled", "bg-brand"], ["dismissed", "bg-warm-strong"]].map(([k, cls]) => (
            <span key={k} className={cls} style={{ width: `${(100 * (outcomes[k] ?? 0)) / decided}%` }} />
          ))}
        </div>
        <p className="text-xs text-muted mt-1">
          {nice(c.category)}, {b.precedents.category_decided} decided: {OUTCOMES.map((o) => `${nice(o)} ${outcomes[o] ?? 0}`).join(" · ")}
        </p>
        {b.precedents.related.length > 0 && (
          <ul className="mt-2 text-xs flex flex-col gap-1">
            {b.precedents.related.map((r) => (
              <li key={r.ref_no}><span className="font-mono">{r.ref_no}</span> · {nice(r.category)} · <b>{nice(r.outcome)}</b>{r.same_project ? " · same project" : " · same promoter"}</li>
            ))}
          </ul>
        )}
      </section>

      {b.other_open.length > 0 && (
        <section>
          <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">Other open complaints on this project ({b.other_open.length}): hear together?</h4>
          <p className="text-xs text-body">{b.other_open.map((o) => `${o.ref_no} (${nice(o.category)})`).join(", ")}</p>
        </section>
      )}

      <section>
        <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">Points to put to the promoter</h4>
        <ul className="text-sm flex flex-col gap-1">
          {b.points_to_put.map((p, i) => (
            <li key={i} className="flex gap-2"><span className="mt-0.5 w-3.5 h-3.5 shrink-0 rounded border border-warm-strong" />{p}</li>
          ))}
        </ul>
      </section>

      <section>
        <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">Timeline</h4>
        <ol className="text-xs flex flex-col gap-0.5">
          {b.timeline.map((e, i) => <li key={i}><span className="tabular-nums text-muted">{fmt(e.at)}</span> · {LABEL[e.status] ?? e.status}{e.note ? ` · ${e.note}` : ""}</li>)}
        </ol>
      </section>

      {NEXT[c.status] && (
        <section className="print:hidden rounded-lg border border-warm-border p-4 grid gap-3">
          <div className="grid sm:grid-cols-3 gap-3">
            <label className="text-xs text-muted">Next step
              <select value={status} onChange={(e) => setStatus(e.target.value)} className="mt-1 w-full rounded-md border border-warm-border bg-card text-body text-sm px-2 py-1.5">
                <option value="">—</option>
                {NEXT[c.status].map((s) => <option key={s} value={s}>{LABEL[s]}</option>)}
              </select>
            </label>
            {status === "hearing_scheduled" && (
              <label className="text-xs text-muted">Hearing date
                <input type="date" value={hearing} onChange={(e) => setHearing(e.target.value)} className="mt-1 w-full rounded-md border border-warm-border bg-card text-body text-sm px-2 py-1.5" />
              </label>
            )}
            {status === "disposed" && (
              <label className="text-xs text-muted">Outcome
                <select value={outcome} onChange={(e) => setOutcome(e.target.value)} className="mt-1 w-full rounded-md border border-warm-border bg-card text-body text-sm px-2 py-1.5">
                  <option value="">—</option>
                  {OUTCOMES.map((o) => <option key={o} value={o}>{nice(o)}</option>)}
                </select>
              </label>
            )}
          </div>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional, shown in the buyer's tracking)"
            className="rounded-md border border-warm-border bg-card text-body text-sm px-3 py-2" />
          <div className="flex items-center gap-3">
            <button type="button" disabled={!status || busy} onClick={() => void save()}
              className="px-4 py-2 rounded-lg bg-primary-bg text-primary-text text-sm font-semibold disabled:opacity-40">{busy ? "…" : "Update"}</button>
            {msg && <span role="alert" className="text-xs text-red-700 dark:text-red-300">{msg}</span>}
          </div>
        </section>
      )}
    </article>
  );
};

const ORDER_STATUSES: [string, string][] = [["complied", "Complied"], ["partly_complied", "Partly done"], ["not_complied", "Not complied"],
  ["recovery", "Recovery started (Section 40)"], ["pending", "Pending"]];

const OrderAction: React.FC<{ o: OrderStatus; onChanged: () => void }> = ({ o, onChanged }) => {
  const { token } = useSaathi();
  const [status, setStatus] = useState("");
  const [date, setDate] = useState("");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const save = async () => {
    if (!token || !status) return;
    setMsg(null);
    try {
      await updateCompliance(token, o.order_id, { status, complied_on: date || undefined, note: note || undefined });
      setStatus(""); setDate(""); setNote("");
      onChanged();
    } catch (e) {
      setMsg((e as Error).message);
    }
  };
  return (
    <div className="p-5 flex flex-col gap-4">
      <ul><OrderCard o={o} /></ul>
      <div className="rounded-lg border border-warm-border p-4 grid gap-3">
        <div className="grid sm:grid-cols-2 gap-3">
          <label className="text-xs text-muted">Compliance
            <select value={status} onChange={(e) => setStatus(e.target.value)} className="mt-1 w-full rounded-md border border-warm-border bg-card text-body text-sm px-2 py-1.5">
              <option value="">—</option>
              {ORDER_STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          {status === "complied" && (
            <label className="text-xs text-muted">Complied on
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="mt-1 w-full rounded-md border border-warm-border bg-card text-body text-sm px-2 py-1.5" />
            </label>
          )}
        </div>
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder={status === "partly_complied" ? "What is done and what is left (required)" : "Note (optional)"}
          className="rounded-md border border-warm-border bg-card text-body text-sm px-3 py-2" />
        <div className="flex items-center gap-3">
          <button type="button" disabled={!status} onClick={() => void save()} className="px-4 py-2 rounded-lg bg-primary-bg text-primary-text text-sm font-semibold disabled:opacity-40">Update</button>
          {msg && <span role="alert" className="text-xs text-red-700 dark:text-red-300">{msg}</span>}
        </div>
      </div>
    </div>
  );
};

export const ComplaintDeskPage: React.FC = () => {
  const { user, token, lang, logout } = useSaathi();
  const allowed = user?.role === "officer";
  const [data, setData] = useState<TriageResponse | null>(null);
  const [category, setCategory] = useState("");
  const [tab, setTab] = useState<"queue" | "groups" | "orders">("queue");
  const [orders, setOrders] = useState<{ counts: Record<string, number>; items: OrderStatus[] } | null>(null);
  const [orderSel, setOrderSel] = useState<number | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!allowed || !token) return;
    fetchTriage(token, lang, { category })
      .then((d) => { setData(d); setSelected((s) => s ?? d.items[0]?.id ?? null); })
      .catch((e) => { if (e instanceof AuthExpiredError) logout(); setError((e as Error).message); });
  }, [allowed, token, lang, category, logout]);
  useEffect(load, [load]);
  const loadOrders = useCallback(() => {
    if (!allowed || !token) return;
    fetchOrdersToEnforce(token, lang).then((d) => { setOrders(d); setOrderSel((s) => s ?? d.items[0]?.order_id ?? null); })
      .catch((e) => { if (e instanceof AuthExpiredError) logout(); setError((e as Error).message); });
  }, [allowed, token, lang, logout]);
  useEffect(() => { if (tab === "orders") loadOrders(); }, [tab, loadOrders]);

  const s = data?.summary;
  const byRef = new Map((data?.items ?? []).map((i) => [i.ref_no, i.id]));
  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6 print:p-0">
      <div className="max-w-3xl print:hidden">
        <p className="text-sm text-muted leading-relaxed">{tr("deskIntro", lang)}</p>
        {lang !== "en" && <p lang="en" className="text-xs text-muted opacity-80 mt-0.5">{tr("deskIntro", "en")}</p>}
      </div>
      {!allowed && <LoginPrompt k="loginNeededDesk" />}
      {allowed && error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 p-4 text-sm">{error}</div>}
      {allowed && s && (
        <>
          <div className="grid gap-4 grid-cols-2 lg:grid-cols-4 print:hidden">
            {([["deskOpen", s.open, "complaint"], ["deskOverdue", s.overdue, "alert"], ["deskDue", s.due_15, "clock"], ["deskGroups", s.groups, "user"]] as [StringKey, number, string][]).map(([k, v, icon]) => (
              <div key={k} className="rounded-xl border border-warm-border bg-card p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="text-xs font-medium text-muted">{tr(k, lang)}<En k={k} /></div>
                  <span className="w-8 h-8 rounded-lg bg-brand-soft text-brand-strong flex items-center justify-center"><Icon name={icon} className="w-4 h-4" /></span>
                </div>
                <div className="mt-3 font-heading text-2xl font-bold text-body tabular-nums">{v}</div>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-3 print:hidden">
            <div className="flex rounded-lg border border-warm-border p-0.5" role="tablist">
              {(["queue", "groups", "orders"] as const).map((t) => (
                <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                  className={`px-3 py-1.5 rounded-md text-xs font-semibold ${tab === t ? "bg-subtle text-body ring-1 ring-warm-strong" : "text-muted hover:text-body"}`}>
                  {t === "queue" ? `${tr("deskQueue", "en")} (${data!.items.length})` : t === "groups" ? `${tr("deskGroups", "en")} (${data!.groups.length})` : `${tr("ordEnforce", "en")}${orders ? ` (${orders.items.length})` : ""}`}
                </button>
              ))}
            </div>
            <select aria-label="Category" value={category} onChange={(e) => { setCategory(e.target.value); setSelected(null); }}
              className="rounded-lg border border-warm-border bg-card text-body text-sm px-3 py-2">
              <option value="">All categories</option>
              {Object.keys(s.by_category).map((c) => <option key={c} value={c}>{nice(c)} ({s.by_category[c]})</option>)}
            </select>
            {data!.district_scope && <span className="text-sm text-muted">{data!.district_scope}</span>}
          </div>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] items-start">
            <div className="rounded-xl border border-warm-border bg-card overflow-hidden print:hidden">
              {tab === "orders" ? (
                <ul className="divide-y divide-warm-border max-h-[70vh] overflow-auto">
                  {(orders?.items ?? []).map((o) => (
                    <li key={o.order_id}>
                      <button type="button" onClick={() => setOrderSel(o.order_id)}
                        className={`relative w-full text-left px-4 py-3 hover:bg-subtle ${orderSel === o.order_id ? "bg-subtle" : ""}`}>
                        {orderSel === o.order_id && <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full bg-brand" />}
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-semibold text-body font-mono">{o.order_no}</div>
                            <div className="text-[11px] text-muted truncate">{o.project ?? "—"} · {o.promoter} · due {o.due_on}</div>
                          </div>
                          <span className="text-[11px] font-semibold whitespace-nowrap">{o.state?.replace(/_/g, " ")}</span>
                        </div>
                      </button>
                    </li>
                  ))}
                  {orders && orders.items.length === 0 && <li className="px-4 py-6 text-sm text-muted text-center">No orders waiting for compliance.</li>}
                </ul>
              ) : tab === "queue" ? (
                <ul className="divide-y divide-warm-border max-h-[70vh] overflow-auto">
                  {data!.items.map((i) => (
                    <li key={i.id}>
                      <button type="button" onClick={() => setSelected(i.id)} aria-current={selected === i.id ? "true" : undefined}
                        className={`relative w-full text-left px-4 py-3 hover:bg-subtle ${selected === i.id ? "bg-subtle" : ""}`}>
                        {selected === i.id && <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full bg-brand" />}
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-semibold text-body"><span className="font-mono text-xs">{i.ref_no}</span> · {nice(i.category)}</div>
                            <div className="text-[11px] text-muted truncate">{i.project ?? "—"} · {i.district}{i.group_size > 1 ? ` · ${i.group_size} on project` : ""}</div>
                          </div>
                          <div className="text-right shrink-0">
                            <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold ${BAND_STYLE[i.band]}`}>{i.band} · {i.score}</span>
                            <div><Clock left={i.days_left} /></div>
                          </div>
                        </div>
                        {i.reasons[0] && <div className="mt-1 text-[11px] text-muted line-clamp-1">{i.reasons.map((r) => `+${r.points} ${r.code.replace(/_/g, " ")}`).join(" · ")}</div>}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <ul className="divide-y divide-warm-border max-h-[70vh] overflow-auto">
                  {data!.groups.map((g) => (
                    <li key={g.project_id} className="px-4 py-3">
                      <div className="text-sm font-semibold text-body">{g.project} <span className="text-muted font-normal">· {g.district}</span></div>
                      <div className="text-[11px] text-muted">{g.complaints.length} open · oldest {g.oldest_days} days · {Object.entries(g.categories).map(([k, n]) => `${nice(k)} ${n}`).join(", ")}</div>
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {g.complaints.map((ref) => (
                          <button key={ref} type="button" disabled={!byRef.has(ref)} onClick={() => { setSelected(byRef.get(ref)!); setTab("queue"); }}
                            className="font-mono text-[11px] rounded border border-warm-border px-1.5 py-0.5 hover:border-warm-strong disabled:opacity-50">{ref}</button>
                        ))}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="rounded-xl border border-warm-border bg-card lg:sticky lg:top-20 print:border-0">
              {tab === "orders"
                ? (orders?.items.find((o) => o.order_id === orderSel)
                  ? <OrderAction o={orders!.items.find((o) => o.order_id === orderSel)!} onChanged={loadOrders} />
                  : <div className="p-6 text-sm text-muted">Select an order.</div>)
                : selected ? <Brief id={selected} onChanged={load} /> : <div className="p-6 text-sm text-muted">Select a complaint.</div>}
            </div>
          </div>
        </>
      )}
    </div>
  );
};
