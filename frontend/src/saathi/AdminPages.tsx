import React, { useCallback, useEffect, useState } from "react";
import {
  AdminUser,
  AdminUsers,
  AuditFilters,
  AuditLogResponse,
  AuthExpiredError,
  createAdminUser,
  downloadAuditCsv,
  fetchAdminUsers,
  fetchAuditLog,
  resetAdminPassword,
  updateAdminUser,
} from "../api/gujrera";
import { useSaathi } from "./context";

const n = (v: number) => v.toLocaleString("en-IN");
const when = (iso: string | null) => (iso ? iso.replace("T", " ") : "—");

const useAdmin = () => {
  const { user, token, logout } = useSaathi();
  const allowed = user?.role === "officer" && !user.district_scope;
  const [error, setError] = useState<string | null>(null);
  const fail = useCallback((e: unknown) => {
    if (e instanceof AuthExpiredError) logout();
    setError((e as Error).message);
  }, [logout]);
  return { user, token, allowed, error, setError, fail };
};

const Hero: React.FC<{ eyebrow: string; title: string; lead: string }> = ({ eyebrow, title, lead }) => (
  <section className="hero-band p-6">
    <p className="text-xs font-semibold uppercase tracking-wider text-accent-amber-strong">{eyebrow}</p>
    <h2 className="mt-1 font-heading text-2xl font-bold text-body">{title}</h2>
    <p className="mt-1 text-sm text-muted max-w-3xl">{lead}</p>
  </section>
);

const NotAllowed: React.FC = () => (
  <div className="max-w-3xl mx-auto px-4 py-8 text-sm text-muted">Administration is for state-level GUJRERA officers.</div>
);

const Tile: React.FC<{ label: string; value: number; tone?: "bad" | "plain" }> = ({ label, value, tone = "plain" }) => (
  <div className={`warm-card p-3 border-l-4 ${tone === "bad" && value > 0 ? "border-l-red-600" : "border-l-warm-strong"}`}>
    <div className="font-heading text-2xl font-bold text-body tabular-nums">{n(value)}</div>
    <div className="text-xs text-muted leading-snug">{label}</div>
  </div>
);

/** A one-time password, shown once with a copy button. */
const OneTime: React.FC<{ who: string; password: string; onClose: () => void }> = ({ who, password, onClose }) => {
  const [copied, setCopied] = useState(false);
  return (
    <div role="status" className="warm-card p-4 border-l-4 border-l-emerald-600 flex flex-wrap items-center gap-3">
      <div className="text-sm text-body flex-1 min-w-[240px]">
        One-time password for <b>{who}</b>. It is shown only now and is not stored in clear: hand it over in person or by phone.
      </div>
      <code className="px-3 py-1.5 rounded-lg bg-subtle border border-warm-border font-mono text-sm text-body select-all">{password}</code>
      <button type="button" onClick={() => { void navigator.clipboard?.writeText(password).then(() => setCopied(true)); }}
        className="text-xs px-3 py-1.5 rounded-lg border border-warm-border text-body hover:border-brand">{copied ? "Copied" : "Copy"}</button>
      <button type="button" onClick={onClose} className="text-xs px-3 py-1.5 rounded-lg bg-primary-bg text-primary-text font-semibold">Done</button>
    </div>
  );
};

// ------------------------------------------------------------------ Users and roles
export const UsersPage: React.FC = () => {
  const { user, token, allowed, error, setError, fail } = useAdmin();
  const [data, setData] = useState<AdminUsers | null>(null);
  const [role, setRole] = useState("");
  const [q, setQ] = useState("");
  const [form, setForm] = useState({ username: "", display_name: "", role: "officer", district_scope: "" });
  const [busy, setBusy] = useState(false);
  const [secret, setSecret] = useState<{ who: string; password: string } | null>(null);

  const load = useCallback(() => {
    if (token && allowed) fetchAdminUsers(token, role || undefined, q || undefined).then(setData).catch(fail);
  }, [token, allowed, role, q, fail]);
  useEffect(load, [load]);

  if (!allowed) return <NotAllowed />;

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const r = await createAdminUser(token, { ...form, district_scope: form.role === "officer" ? form.district_scope || null : null });
      setSecret({ who: r.user.username, password: r.temporary_password });
      setForm({ username: "", display_name: "", role: form.role, district_scope: form.district_scope });
      load();
    } catch (err) { fail(err); } finally { setBusy(false); }
  };
  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try { await fn(); load(); } catch (err) { fail(err); }
  };
  const reset = async (u: AdminUser) => {
    if (!token || !window.confirm(`Reset the password of ${u.username}? Their open sessions end now.`)) return;
    await act(async () => { const r = await resetAdminPassword(token, u.id); setSecret({ who: u.username, password: r.temporary_password }); });
  };
  const toggle = (u: AdminUser) => {
    if (!token) return;
    if (u.is_active && !window.confirm(`Disable ${u.username}? They are logged out at once and cannot log in.`)) return;
    void act(() => updateAdminUser(token, u.id, { is_active: !u.is_active }));
  };
  const rescope = (u: AdminUser, scope: string) => {
    if (token) void act(() => updateAdminUser(token, u.id, { set_scope: true, district_scope: scope || null }));
  };

  const counts = data?.counts ?? {};
  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <Hero eyebrow="Administration" title="Users and roles"
        lead="Create accounts for the POC's test users, set each officer's district, disable an account or reset a password. Disabling or resetting logs the person out at once. Every change is in the audit log." />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Tile label="Officers" value={counts.officer ?? 0} />
        <Tile label="Home buyers" value={counts.citizen ?? 0} />
        <Tile label="Promoters" value={counts.developer ?? 0} />
        <Tile label="Agents" value={counts.agent ?? 0} />
      </div>
      {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 dark:bg-red-950/40 dark:text-red-200 dark:border-red-900 p-3 text-sm">{error}</div>}
      {secret && <OneTime who={secret.who} password={secret.password} onClose={() => setSecret(null)} />}

      <form onSubmit={create} className="warm-card p-5 flex flex-col gap-3">
        <h3 className="font-heading text-sm font-bold text-body">New account</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="text-xs text-muted flex flex-col gap-1">Username
            <input required value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value.toLowerCase() })}
              placeholder="e.g. officer_bharuch" className="rounded-lg border border-warm-border bg-card text-body text-sm px-3 py-2" />
          </label>
          <label className="text-xs text-muted flex flex-col gap-1">Name shown in the app
            <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })}
              placeholder="e.g. Deputy Secretary, Bharuch" className="rounded-lg border border-warm-border bg-card text-body text-sm px-3 py-2" />
          </label>
          <label className="text-xs text-muted flex flex-col gap-1">Role
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}
              className="rounded-lg border border-warm-border bg-card text-body text-sm px-3 py-2">
              <option value="officer">GUJRERA officer</option>
              <option value="citizen">Home buyer (test user)</option>
            </select>
          </label>
          {form.role === "officer" && (
            <label className="text-xs text-muted flex flex-col gap-1">District
              <select value={form.district_scope} onChange={(e) => setForm({ ...form, district_scope: e.target.value })}
                className="rounded-lg border border-warm-border bg-card text-body text-sm px-3 py-2">
                <option value="">Statewide (also an administrator)</option>
                {data?.districts.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </label>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" disabled={busy || !form.username.trim()}
            className="px-5 py-2 rounded-xl bg-brand text-on-brand text-sm font-bold disabled:opacity-50">{busy ? "Creating…" : "Create account"}</button>
          <span className="text-xs text-muted">A one-time password is generated and shown once. Promoter and agent accounts are linked to registry records and are not created here.</span>
        </div>
      </form>

      <section className="warm-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="font-heading text-sm font-bold text-body">Accounts{data ? ` (${n(data.users.length)})` : ""}</h3>
          <div className="flex flex-wrap gap-2">
            <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Filter by role"
              className="rounded-lg border border-warm-border bg-card text-body text-xs px-2 py-1.5">
              <option value="">All roles</option>
              <option value="officer">Officers</option>
              <option value="citizen">Home buyers</option>
              <option value="developer">Promoters</option>
              <option value="agent">Agents</option>
            </select>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or username" aria-label="Search accounts"
              className="rounded-lg border border-warm-border bg-card text-body text-xs px-2.5 py-1.5" />
          </div>
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-xs min-w-[860px]">
            <thead>
              <tr className="text-muted text-left border-b border-warm-border">
                <th className="py-2 font-medium">Account</th><th className="py-2 font-medium">Role</th>
                <th className="py-2 font-medium">District</th><th className="py-2 font-medium">Last login</th>
                <th className="py-2 font-medium">Status</th><th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {data?.users.map((u) => {
                const self = u.username === user?.username;
                return (
                  <tr key={u.id} className={`border-b border-warm-border last:border-0 align-top ${u.is_active ? "" : "opacity-60"}`}>
                    <td className="py-2 pr-2">
                      <div className="font-semibold text-body">{u.username}{self && <span className="ml-1 text-muted font-normal">(you)</span>}</div>
                      <div className="text-muted">{u.display_name}{u.organisation ? ` · ${u.organisation}` : ""}{u.is_demo ? " · demo" : ""}</div>
                    </td>
                    <td className="py-2 pr-2 text-body">{u.role_label}</td>
                    <td className="py-2 pr-2">
                      {u.role === "officer" ? (
                        <select value={u.district_scope ?? ""} disabled={self} aria-label={`District of ${u.username}`}
                          onChange={(e) => rescope(u, e.target.value)}
                          className="rounded-md border border-warm-border bg-card text-body px-1.5 py-1 disabled:opacity-60">
                          <option value="">Statewide</option>
                          {data.districts.map((d) => <option key={d} value={d}>{d}</option>)}
                        </select>
                      ) : <span className="text-muted">—</span>}
                    </td>
                    <td className="py-2 pr-2 text-muted whitespace-nowrap">{when(u.last_login_at)}</td>
                    <td className="py-2 pr-2">
                      <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold ${u.is_active ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-900" : "border-red-300 bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-200 dark:border-red-900"}`}>
                        {u.is_active ? "Active" : "Disabled"}
                      </span>
                    </td>
                    <td className="py-2 text-right whitespace-nowrap">
                      <button type="button" onClick={() => void reset(u)} className="text-[11px] font-semibold text-brand-strong mr-3">Reset password</button>
                      {!self && (
                        <button type="button" onClick={() => toggle(u)} className={`text-[11px] font-semibold ${u.is_active ? "text-red-700 dark:text-red-300" : "text-emerald-700 dark:text-emerald-300"}`}>
                          {u.is_active ? "Disable" : "Enable"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};

// ------------------------------------------------------------------ Audit log
const CAT_STYLE: Record<string, string> = {
  refusal: "border-red-300 bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-200 dark:border-red-900",
  admin: "border-accent-border bg-accent-surface text-accent-amber-strong",
  data: "border-accent-border bg-accent-surface text-accent-amber-strong",
};

const detailText = (d: Record<string, unknown>): string => {
  const keys = ["question", "username", "file", "rows", "asked", "scope", "reason", "what", "role", "district_scope",
                "is_active", "status", "inserted", "updated", "rejected", "ref_no", "project_id"];
  const parts = keys.filter((k) => d[k] !== undefined && d[k] !== null && d[k] !== "").map((k) => `${k.replace(/_/g, " ")}: ${String(d[k])}`);
  return parts.length ? parts.join(" · ") : JSON.stringify(d);
};

export const AuditPage: React.FC = () => {
  const { token, allowed, error, fail } = useAdmin();
  const [f, setF] = useState<AuditFilters>({ category: "" });
  const [data, setData] = useState<AuditLogResponse | null>(null);
  const [open, setOpen] = useState<number | null>(null);

  const load = useCallback((filters: AuditFilters) => {
    if (token && allowed) fetchAuditLog(token, filters).then(setData).catch(fail);
  }, [token, allowed, fail]);
  useEffect(() => { load(f); }, [load, f]);

  if (!allowed) return <NotAllowed />;
  const s = data?.summary;
  const set = (patch: Partial<AuditFilters>) => setF((x) => ({ ...x, ...patch, offset: 0 }));

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <Hero eyebrow="Administration" title="Audit log"
        lead="Who did what, and when: every report, export, data load and account change, and every refusal (another district, an attempt to change data, an unsafe query, a failed login, a page the role may not open). Passwords are never logged." />
      {s && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <Tile label="Entries in this view" value={data!.total} />
          <Tile label="People" value={s.distinct_users} />
          <Tile label="Failed logins" value={s.failed_logins} tone="bad" />
          <Tile label="Asked about another district" value={s.out_of_scope} tone="bad" />
          <Tile label="Tried to change data" value={s.write_attempts} tone="bad" />
          <Tile label="Pages a role may not open" value={s.access_denied + s.blocked_queries} tone="bad" />
        </div>
      )}
      {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 p-3 text-sm">{error}</div>}

      <section className="warm-card p-5 flex flex-col gap-3">
        <div className="flex flex-wrap gap-2 items-end">
          <div className="flex rounded-lg border border-warm-border p-0.5" role="group" aria-label="Category">
            {[["", "All"], ["refusal", "Refusals"], ["report", "Reports"], ["data", "Data loads"], ["admin", "Accounts"], ["login", "Logins"], ["work", "Officer work"]].map(([k, label]) => (
              <button key={k} type="button" onClick={() => set({ category: k })} aria-pressed={(f.category ?? "") === k}
                className={`px-2.5 py-1 rounded-md text-xs font-semibold ${(f.category ?? "") === k ? "bg-brand-soft text-body ring-1 ring-brand" : "text-muted hover:text-body"}`}>
                {label}{data && k ? ` ${n(data.summary.by_category[k] ?? 0)}` : ""}
              </button>
            ))}
          </div>
          <input placeholder="Username" value={f.username ?? ""} onChange={(e) => set({ username: e.target.value })} aria-label="Username"
            className="rounded-lg border border-warm-border bg-card text-body text-xs px-2.5 py-1.5 w-36" />
          <select value={f.role ?? ""} onChange={(e) => set({ role: e.target.value })} aria-label="Role"
            className="rounded-lg border border-warm-border bg-card text-body text-xs px-2 py-1.5">
            <option value="">All roles</option><option value="officer">Officers</option><option value="citizen">Citizens</option>
            <option value="developer">Promoters</option><option value="agent">Agents</option>
          </select>
          <label className="text-[11px] text-muted flex items-center gap-1">From
            <input type="date" value={f.since ?? ""} onChange={(e) => set({ since: e.target.value })}
              className="rounded-lg border border-warm-border bg-card text-body text-xs px-2 py-1" /></label>
          <label className="text-[11px] text-muted flex items-center gap-1">To
            <input type="date" value={f.until ?? ""} onChange={(e) => set({ until: e.target.value })}
              className="rounded-lg border border-warm-border bg-card text-body text-xs px-2 py-1" /></label>
          <input placeholder="Search details (e.g. Bopal)" value={f.q ?? ""} onChange={(e) => set({ q: e.target.value })} aria-label="Search details"
            className="rounded-lg border border-warm-border bg-card text-body text-xs px-2.5 py-1.5 w-48" />
          <button type="button" onClick={() => token && void downloadAuditCsv(token, f).catch(fail)}
            className="ml-auto text-xs px-3 py-1.5 rounded-lg bg-primary-bg text-primary-text font-semibold">Download CSV</button>
        </div>
        {data && <p className="text-[11px] text-muted">From {data.since}{data.until ? ` to ${data.until}` : " to today"} · newest first · {n(data.total)} entries</p>}
        <div className="overflow-x-auto">
          <table className="w-full text-xs min-w-[820px]">
            <thead>
              <tr className="text-muted text-left border-b border-warm-border">
                <th className="py-2 font-medium w-36">Time</th><th className="py-2 font-medium w-36">Who</th>
                <th className="py-2 font-medium">What happened</th><th className="py-2 font-medium">Details</th>
              </tr>
            </thead>
            <tbody>
              {data?.entries.map((e) => (
                <tr key={e.id} className="border-b border-warm-border last:border-0 align-top cursor-pointer hover:bg-subtle/60"
                  onClick={() => setOpen(open === e.id ? null : e.id)}>
                  <td className="py-1.5 pr-2 text-muted whitespace-nowrap tabular-nums">{e.at.replace("T", " ")}</td>
                  <td className="py-1.5 pr-2"><span className="text-body font-semibold">{e.user ?? "—"}</span><span className="block text-muted">{e.role}</span></td>
                  <td className="py-1.5 pr-2">
                    <span className={`inline-block px-2 py-0.5 rounded-full border text-[10px] font-semibold mr-1 ${CAT_STYLE[e.category] ?? "border-warm-border text-muted"}`}>{e.category}</span>
                    <span className="text-body">{e.label}</span>
                  </td>
                  <td className="py-1.5 text-muted break-words">
                    {open === e.id ? <pre className="whitespace-pre-wrap font-mono text-[11px] text-body">{JSON.stringify(e.detail, null, 2)}</pre> : detailText(e.detail)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data && data.entries.length === 0 && <p className="py-4 text-sm text-muted">Nothing matches these filters.</p>}
        </div>
        {data && data.total > (f.offset ?? 0) + data.entries.length && (
          <button type="button" onClick={() => setF((x) => ({ ...x, offset: (x.offset ?? 0) + 100 }))}
            className="self-start text-xs font-semibold text-brand-strong">Older entries →</button>
        )}
        {(f.offset ?? 0) > 0 && (
          <button type="button" onClick={() => setF((x) => ({ ...x, offset: Math.max(0, (x.offset ?? 0) - 100) }))}
            className="self-start text-xs font-semibold text-brand-strong">← Newer entries</button>
        )}
      </section>
    </div>
  );
};
