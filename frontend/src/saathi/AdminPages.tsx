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
import { Said, say, useSaathi } from "./context";

const n = (v: number) => v.toLocaleString("en-IN");
const when = (iso: string | null) => (iso ? iso.replace("T", " ") : "—");

const ADMIN: Said = { en: "Administration", gu: "વહીવટ", hi: "प्रशासन" };

const ROLE_FILTER: Record<string, Said> = {
  "": { en: "All roles", gu: "બધી ભૂમિકાઓ", hi: "सभी भूमिकाएँ" },
  officer: { en: "Officers", gu: "અધિકારીઓ", hi: "अधिकारी" },
  citizen: { en: "Home buyers", gu: "ઘર ખરીદનારા", hi: "घर खरीदार" },
  developer: { en: "Promoters", gu: "પ્રમોટરો", hi: "प्रमोटर" },
  agent: { en: "Agents", gu: "એજન્ટો", hi: "एजेंट" },
};
const CITIZENS: Said = { en: "Citizens", gu: "નાગરિકો", hi: "नागरिक" };

const CATEGORIES: [string, Said][] = [
  ["", { en: "All", gu: "બધું", hi: "सभी" }],
  ["refusal", { en: "Refusals", gu: "ઇનકાર", hi: "इनकार" }],
  ["report", { en: "Reports", gu: "રિપોર્ટ", hi: "रिपोर्ट" }],
  ["data", { en: "Data loads", gu: "ડેટા લોડ", hi: "डेटा लोड" }],
  ["admin", { en: "Accounts", gu: "ખાતાં", hi: "खाते" }],
  ["login", { en: "Logins", gu: "લૉગિન", hi: "लॉगिन" }],
  ["work", { en: "Officer work", gu: "અધિકારીનું કામ", hi: "अधिकारी का कार्य" }],
  ["public", { en: "Citizen and public use", gu: "નાગરિક અને જાહેર ઉપયોગ", hi: "नागरिक और सार्वजनिक उपयोग" }],
];

const useAdmin = () => {
  const { user, token, logout, lang } = useSaathi();
  const allowed = user?.role === "officer" && !user.district_scope;
  const [error, setError] = useState<string | null>(null);
  const fail = useCallback((e: unknown) => {
    if (e instanceof AuthExpiredError) logout();
    setError((e as Error).message);
  }, [logout]);
  return { user, token, allowed, error, setError, fail, lang };
};

const Hero: React.FC<{ eyebrow: string; title: string; lead: string }> = ({ eyebrow, title, lead }) => (
  <section className="hero-band p-6">
    <p className="text-xs font-semibold uppercase tracking-wider text-accent-amber-strong">{eyebrow}</p>
    <h2 className="mt-1 font-heading text-2xl font-bold text-body">{title}</h2>
    <p className="mt-1 text-sm text-muted max-w-3xl">{lead}</p>
  </section>
);

const NotAllowed: React.FC = () => {
  const { lang } = useSaathi();
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 text-sm text-muted">
      {say({ en: "Administration is for state-level GUJRERA officers.", gu: "વહીવટ ફક્ત રાજ્ય સ્તરના GUJRERA અધિકારીઓ માટે છે.", hi: "प्रशासन केवल राज्य स्तर के GUJRERA अधिकारियों के लिए है।" }, lang)}
    </div>
  );
};

const Tile: React.FC<{ label: string; value: number; tone?: "bad" | "plain" }> = ({ label, value, tone = "plain" }) => (
  <div className={`warm-card p-3 border-l-4 ${tone === "bad" && value > 0 ? "border-l-red-600" : "border-l-warm-strong"}`}>
    <div className="font-heading text-2xl font-bold text-body tabular-nums">{n(value)}</div>
    <div className="text-xs text-muted leading-snug">{label}</div>
  </div>
);

/** A one-time password, shown once with a copy button. */
const OneTime: React.FC<{ who: string; password: string; onClose: () => void }> = ({ who, password, onClose }) => {
  const { lang } = useSaathi();
  const [copied, setCopied] = useState(false);
  return (
    <div role="status" className="warm-card p-4 border-l-4 border-l-emerald-600 flex flex-wrap items-center gap-3">
      <div className="text-sm text-body flex-1 min-w-[240px]">
        {lang === "gu" ? (
          <><b>{who}</b> માટે એક વખતનો પાસવર્ડ. તે ફક્ત અત્યારે જ દેખાય છે અને ખુલ્લા સ્વરૂપે સંગ્રહિત નથી: રૂબરૂ અથવા ફોન પર આપો.</>
        ) : lang === "hi" ? (
          <><b>{who}</b> के लिए एक बार का पासवर्ड. यह केवल अभी दिखाया जा रहा है और खुले रूप में संग्रहीत नहीं है: इसे व्यक्तिगत रूप से या फ़ोन पर दें।</>
        ) : (
          <>One-time password for <b>{who}</b>. It is shown only now and is not stored in clear: hand it over in person or by phone.</>
        )}
      </div>
      <code className="px-3 py-1.5 rounded-lg bg-subtle border border-warm-border font-mono text-sm text-body select-all">{password}</code>
      <button type="button" onClick={() => { void navigator.clipboard?.writeText(password).then(() => setCopied(true)); }}
        className="text-xs px-3 py-1.5 rounded-lg border border-warm-border text-body hover:border-brand">
        {copied ? say({ en: "Copied", gu: "કૉપિ થયું", hi: "कॉपी हो गया" }, lang) : say({ en: "Copy", gu: "કૉપિ કરો", hi: "कॉपी करें" }, lang)}
      </button>
      <button type="button" onClick={onClose} className="text-xs px-3 py-1.5 rounded-lg bg-primary-bg text-primary-text font-semibold">
        {say({ en: "Done", gu: "થઈ ગયું", hi: "हो गया" }, lang)}
      </button>
    </div>
  );
};

// ------------------------------------------------------------------ Users and roles
export const UsersPage: React.FC = () => {
  const { user, token, allowed, error, setError, fail, lang } = useAdmin();
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
    const msg = say({
      en: `Reset the password of ${u.username}? Their open sessions end now.`,
      gu: `${u.username} નો પાસવર્ડ ફરી સેટ કરવો છે? તેમના ખુલ્લા સત્રો હમણાં જ બંધ થશે.`,
      hi: `${u.username} का पासवर्ड रीसेट करें? उनके खुले सत्र अभी समाप्त हो जाएँगे।`,
    }, lang);
    if (!token || !window.confirm(msg)) return;
    await act(async () => { const r = await resetAdminPassword(token, u.id); setSecret({ who: u.username, password: r.temporary_password }); });
  };
  const toggle = (u: AdminUser) => {
    if (!token) return;
    const msg = say({
      en: `Disable ${u.username}? They are logged out at once and cannot log in.`,
      gu: `${u.username} ને નિષ્ક્રિય કરવા છે? તેઓ તરત જ લૉગ આઉટ થશે અને લૉગિન કરી શકશે નહીં.`,
      hi: `${u.username} को निष्क्रिय करें? वे तुरंत लॉग आउट हो जाएँगे और लॉगिन नहीं कर सकेंगे।`,
    }, lang);
    if (u.is_active && !window.confirm(msg)) return;
    void act(() => updateAdminUser(token, u.id, { is_active: !u.is_active }));
  };
  const rescope = (u: AdminUser, scope: string) => {
    if (token) void act(() => updateAdminUser(token, u.id, { set_scope: true, district_scope: scope || null }));
  };

  const counts = data?.counts ?? {};
  const statewide = say({ en: "Statewide", gu: "આખા રાજ્ય માટે", hi: "पूरे राज्य के लिए" }, lang);
  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <Hero eyebrow={say(ADMIN, lang)} title={say({ en: "Users and roles", gu: "વપરાશકર્તાઓ અને ભૂમિકાઓ", hi: "उपयोगकर्ता और भूमिकाएँ" }, lang)}
        lead={say({
          en: "Create accounts for the POC's test users, set each officer's district, disable an account or reset a password. Disabling or resetting logs the person out at once. Every change is in the audit log.",
          gu: "POC ના પરીક્ષણ વપરાશકર્તાઓ માટે ખાતાં બનાવો, દરેક અધિકારીનો જિલ્લો નક્કી કરો, ખાતું નિષ્ક્રિય કરો અથવા પાસવર્ડ ફરી સેટ કરો. નિષ્ક્રિય કરવાથી કે પાસવર્ડ ફરી સેટ કરવાથી વ્યક્તિ તરત જ લૉગ આઉટ થાય છે. દરેક ફેરફાર ઓડિટ લોગમાં નોંધાય છે.",
          hi: "POC के परीक्षण उपयोगकर्ताओं के लिए खाते बनाएँ, हर अधिकारी का जिला तय करें, खाता निष्क्रिय करें या पासवर्ड रीसेट करें। निष्क्रिय या रीसेट करने पर व्यक्ति तुरंत लॉग आउट हो जाता है। हर बदलाव ऑडिट लॉग में दर्ज होता है।",
        }, lang)} />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Tile label={say(ROLE_FILTER.officer, lang)} value={counts.officer ?? 0} />
        <Tile label={say(ROLE_FILTER.citizen, lang)} value={counts.citizen ?? 0} />
        <Tile label={say(ROLE_FILTER.developer, lang)} value={counts.developer ?? 0} />
        <Tile label={say(ROLE_FILTER.agent, lang)} value={counts.agent ?? 0} />
      </div>
      {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 dark:bg-red-950/40 dark:text-red-200 dark:border-red-900 p-3 text-sm">{error}</div>}
      {secret && <OneTime who={secret.who} password={secret.password} onClose={() => setSecret(null)} />}

      <form onSubmit={create} className="warm-card p-5 flex flex-col gap-3">
        <h3 className="font-heading text-sm font-bold text-body">{say({ en: "New account", gu: "નવું ખાતું", hi: "नया खाता" }, lang)}</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="text-xs text-muted flex flex-col gap-1">{say({ en: "Username", gu: "યુઝરનેમ", hi: "यूज़रनेम" }, lang)}
            <input required value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value.toLowerCase() })}
              placeholder={say({ en: "e.g. officer_bharuch", gu: "દા.ત. officer_bharuch", hi: "उदा. officer_bharuch" }, lang)} className="rounded-lg border border-warm-border bg-card text-body text-sm px-3 py-2" />
          </label>
          <label className="text-xs text-muted flex flex-col gap-1">{say({ en: "Name shown in the app", gu: "એપમાં દેખાતું નામ", hi: "ऐप में दिखने वाला नाम" }, lang)}
            <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })}
              placeholder={say({ en: "e.g. Deputy Secretary, Bharuch", gu: "દા.ત. નાયબ સચિવ, ભરૂચ", hi: "उदा. उप सचिव, भरूच" }, lang)} className="rounded-lg border border-warm-border bg-card text-body text-sm px-3 py-2" />
          </label>
          <label className="text-xs text-muted flex flex-col gap-1">{say({ en: "Role", gu: "ભૂમિકા", hi: "भूमिका" }, lang)}
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}
              className="rounded-lg border border-warm-border bg-card text-body text-sm px-3 py-2">
              <option value="officer">{say({ en: "GUJRERA officer", gu: "GUJRERA અધિકારી", hi: "GUJRERA अधिकारी" }, lang)}</option>
              <option value="citizen">{say({ en: "Home buyer (test user)", gu: "ઘર ખરીદનાર (પરીક્ષણ વપરાશકર્તા)", hi: "घर खरीदार (परीक्षण उपयोगकर्ता)" }, lang)}</option>
            </select>
          </label>
          {form.role === "officer" && (
            <label className="text-xs text-muted flex flex-col gap-1">{say({ en: "District", gu: "જિલ્લો", hi: "जिला" }, lang)}
              <select value={form.district_scope} onChange={(e) => setForm({ ...form, district_scope: e.target.value })}
                className="rounded-lg border border-warm-border bg-card text-body text-sm px-3 py-2">
                <option value="">{say({ en: "Statewide (also an administrator)", gu: "આખા રાજ્ય માટે (વહીવટકર્તા પણ)", hi: "पूरे राज्य के लिए (प्रशासक भी)" }, lang)}</option>
                {data?.districts.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </label>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" disabled={busy || !form.username.trim()}
            className="px-5 py-2 rounded-xl bg-brand text-on-brand text-sm font-bold disabled:opacity-50">
            {busy ? say({ en: "Creating…", gu: "બનાવી રહ્યા છીએ…", hi: "बनाया जा रहा है…" }, lang) : say({ en: "Create account", gu: "ખાતું બનાવો", hi: "खाता बनाएँ" }, lang)}
          </button>
          <span className="text-xs text-muted">{say({
            en: "A one-time password is generated and shown once. Promoter and agent accounts are linked to registry records and are not created here.",
            gu: "એક વખતનો પાસવર્ડ બને છે અને એક જ વાર દેખાય છે. પ્રમોટર અને એજન્ટ ખાતાં રજિસ્ટ્રીના રેકોર્ડ સાથે જોડાયેલાં છે અને અહીં બનાવાતાં નથી.",
            hi: "एक बार का पासवर्ड बनता है और एक ही बार दिखाया जाता है। प्रमोटर और एजेंट खाते रजिस्ट्री रिकॉर्ड से जुड़े हैं और यहाँ नहीं बनाए जाते।",
          }, lang)}</span>
        </div>
      </form>

      <section className="warm-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="font-heading text-sm font-bold text-body">{say({ en: "Accounts", gu: "ખાતાં", hi: "खाते" }, lang)}{data ? ` (${n(data.users.length)})` : ""}</h3>
          <div className="flex flex-wrap gap-2">
            <select value={role} onChange={(e) => setRole(e.target.value)} aria-label={say({ en: "Filter by role", gu: "ભૂમિકા પ્રમાણે ફિલ્ટર", hi: "भूमिका के अनुसार फ़िल्टर" }, lang)}
              className="rounded-lg border border-warm-border bg-card text-body text-xs px-2 py-1.5">
              <option value="">{say(ROLE_FILTER[""], lang)}</option>
              <option value="officer">{say(ROLE_FILTER.officer, lang)}</option>
              <option value="citizen">{say(ROLE_FILTER.citizen, lang)}</option>
              <option value="developer">{say(ROLE_FILTER.developer, lang)}</option>
              <option value="agent">{say(ROLE_FILTER.agent, lang)}</option>
            </select>
            <input value={q} onChange={(e) => setQ(e.target.value)}
              placeholder={say({ en: "Search name or username", gu: "નામ અથવા યુઝરનેમ શોધો", hi: "नाम या यूज़रनेम खोजें" }, lang)}
              aria-label={say({ en: "Search accounts", gu: "ખાતાં શોધો", hi: "खाते खोजें" }, lang)}
              className="rounded-lg border border-warm-border bg-card text-body text-xs px-2.5 py-1.5" />
          </div>
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-xs min-w-[860px]">
            <thead>
              <tr className="text-muted text-left border-b border-warm-border">
                <th className="py-2 font-medium">{say({ en: "Account", gu: "ખાતું", hi: "खाता" }, lang)}</th><th className="py-2 font-medium">{say({ en: "Role", gu: "ભૂમિકા", hi: "भूमिका" }, lang)}</th>
                <th className="py-2 font-medium">{say({ en: "District", gu: "જિલ્લો", hi: "जिला" }, lang)}</th><th className="py-2 font-medium">{say({ en: "Last login", gu: "છેલ્લું લૉગિન", hi: "अंतिम लॉगिन" }, lang)}</th>
                <th className="py-2 font-medium">{say({ en: "Status", gu: "સ્થિતિ", hi: "स्थिति" }, lang)}</th><th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {data?.users.map((u) => {
                const self = u.username === user?.username;
                return (
                  <tr key={u.id} className={`border-b border-warm-border last:border-0 align-top ${u.is_active ? "" : "opacity-60"}`}>
                    <td className="py-2 pr-2">
                      <div className="font-semibold text-body">{u.username}{self && <span className="ml-1 text-muted font-normal">{say({ en: "(you)", gu: "(તમે)", hi: "(आप)" }, lang)}</span>}</div>
                      <div className="text-muted">{u.display_name}{u.organisation ? ` · ${u.organisation}` : ""}{u.is_demo ? ` · ${say({ en: "demo", gu: "ડેમો", hi: "डेमो" }, lang)}` : ""}</div>
                    </td>
                    <td className="py-2 pr-2 text-body">{u.role_label_i18n?.[lang] ?? u.role_label}</td>
                    <td className="py-2 pr-2">
                      {u.role === "officer" ? (
                        <select value={u.district_scope ?? ""} disabled={self}
                          aria-label={say({ en: `District of ${u.username}`, gu: `${u.username} નો જિલ્લો`, hi: `${u.username} का जिला` }, lang)}
                          onChange={(e) => rescope(u, e.target.value)}
                          className="rounded-md border border-warm-border bg-card text-body px-1.5 py-1 disabled:opacity-60">
                          <option value="">{statewide}</option>
                          {data.districts.map((d) => <option key={d} value={d}>{d}</option>)}
                        </select>
                      ) : <span className="text-muted">—</span>}
                    </td>
                    <td className="py-2 pr-2 text-muted whitespace-nowrap">{when(u.last_login_at)}</td>
                    <td className="py-2 pr-2">
                      <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold ${u.is_active ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-900" : "border-red-300 bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-200 dark:border-red-900"}`}>
                        {u.is_active ? say({ en: "Active", gu: "સક્રિય", hi: "सक्रिय" }, lang) : say({ en: "Disabled", gu: "નિષ્ક્રિય", hi: "निष्क्रिय" }, lang)}
                      </span>
                    </td>
                    <td className="py-2 text-right whitespace-nowrap">
                      <button type="button" onClick={() => void reset(u)} className="text-[11px] font-semibold text-brand-strong mr-3">
                        {say({ en: "Reset password", gu: "પાસવર્ડ ફરી સેટ કરો", hi: "पासवर्ड रीसेट करें" }, lang)}
                      </button>
                      {!self && (
                        <button type="button" onClick={() => toggle(u)} className={`text-[11px] font-semibold ${u.is_active ? "text-red-700 dark:text-red-300" : "text-emerald-700 dark:text-emerald-300"}`}>
                          {u.is_active ? say({ en: "Disable", gu: "નિષ્ક્રિય કરો", hi: "निष्क्रिय करें" }, lang) : say({ en: "Enable", gu: "સક્રિય કરો", hi: "सक्रिय करें" }, lang)}
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
  const { token, allowed, error, fail, lang } = useAdmin();
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

  const range = (d: AuditLogResponse): string => {
    if (lang === "gu") return `${d.since}${d.until ? ` થી ${d.until}` : " થી આજ સુધી"} · નવી પહેલાં · ${n(d.total)} નોંધો`;
    if (lang === "hi") return `${d.since}${d.until ? ` से ${d.until}` : " से आज तक"} · नई पहले · ${n(d.total)} प्रविष्टियाँ`;
    return `From ${d.since}${d.until ? ` to ${d.until}` : " to today"} · newest first · ${n(d.total)} entries`;
  };

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <Hero eyebrow={say(ADMIN, lang)} title={say({ en: "Audit log", gu: "ઓડિટ લોગ", hi: "ऑडिट लॉग" }, lang)}
        lead={say({
          en: "Who did what, and when: every report, export, data load and account change, and every refusal (another district, an attempt to change data, an unsafe query, a failed login, a page the role may not open). Passwords are never logged.",
          gu: "કોણે શું કર્યું અને ક્યારે: દરેક રિપોર્ટ, નિકાસ, ડેટા લોડ અને ખાતામાં ફેરફાર, તથા દરેક ઇનકાર (બીજો જિલ્લો, ડેટા બદલવાનો પ્રયાસ, અસુરક્ષિત ક્વેરી, નિષ્ફળ લૉગિન, ભૂમિકા ન ખોલી શકે તેવું પેજ). પાસવર્ડ ક્યારેય નોંધાતા નથી.",
          hi: "किसने क्या किया और कब: हर रिपोर्ट, निर्यात, डेटा लोड और खाते में बदलाव, और हर इनकार (दूसरा जिला, डेटा बदलने का प्रयास, असुरक्षित क्वेरी, विफल लॉगिन, ऐसा पेज जिसे भूमिका नहीं खोल सकती)। पासवर्ड कभी दर्ज नहीं किए जाते।",
        }, lang)} />
      {s && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <Tile label={say({ en: "Entries in this view", gu: "આ દૃશ્યમાં નોંધો", hi: "इस दृश्य में प्रविष्टियाँ" }, lang)} value={data!.total} />
          <Tile label={say({ en: "People", gu: "વ્યક્તિઓ", hi: "व्यक्ति" }, lang)} value={s.distinct_users} />
          <Tile label={say({ en: "Failed logins", gu: "નિષ્ફળ લૉગિન", hi: "विफल लॉगिन" }, lang)} value={s.failed_logins} tone="bad" />
          <Tile label={say({ en: "Asked about another district", gu: "બીજા જિલ્લા વિશે પૂછ્યું", hi: "दूसरे जिले के बारे में पूछा" }, lang)} value={s.out_of_scope} tone="bad" />
          <Tile label={say({ en: "Tried to change data", gu: "ડેટા બદલવાનો પ્રયાસ", hi: "डेटा बदलने का प्रयास" }, lang)} value={s.write_attempts} tone="bad" />
          <Tile label={say({ en: "Pages a role may not open", gu: "ભૂમિકા ન ખોલી શકે તેવાં પેજ", hi: "ऐसे पेज जिन्हें भूमिका नहीं खोल सकती" }, lang)} value={s.access_denied + s.blocked_queries} tone="bad" />
        </div>
      )}
      {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 p-3 text-sm">{error}</div>}

      <section className="warm-card p-5 flex flex-col gap-3">
        <div className="flex flex-wrap gap-2 items-end">
          <div className="flex rounded-lg border border-warm-border p-0.5" role="group" aria-label={say({ en: "Category", gu: "શ્રેણી", hi: "श्रेणी" }, lang)}>
            {CATEGORIES.map(([k, label]) => (
              <button key={k} type="button" onClick={() => set({ category: k })} aria-pressed={(f.category ?? "") === k}
                className={`px-2.5 py-1 rounded-md text-xs font-semibold ${(f.category ?? "") === k ? "bg-brand-soft text-body ring-1 ring-brand" : "text-muted hover:text-body"}`}>
                {say(label, lang)}{data && k ? ` ${n(data.summary.by_category[k] ?? 0)}` : ""}
              </button>
            ))}
          </div>
          <input placeholder={say({ en: "Username", gu: "યુઝરનેમ", hi: "यूज़रनेम" }, lang)} value={f.username ?? ""} onChange={(e) => set({ username: e.target.value })}
            aria-label={say({ en: "Username", gu: "યુઝરનેમ", hi: "यूज़रनेम" }, lang)}
            className="rounded-lg border border-warm-border bg-card text-body text-xs px-2.5 py-1.5 w-36" />
          <select value={f.role ?? ""} onChange={(e) => set({ role: e.target.value })} aria-label={say({ en: "Role", gu: "ભૂમિકા", hi: "भूमिका" }, lang)}
            className="rounded-lg border border-warm-border bg-card text-body text-xs px-2 py-1.5">
            <option value="">{say(ROLE_FILTER[""], lang)}</option><option value="officer">{say(ROLE_FILTER.officer, lang)}</option><option value="citizen">{say(CITIZENS, lang)}</option>
            <option value="developer">{say(ROLE_FILTER.developer, lang)}</option><option value="agent">{say(ROLE_FILTER.agent, lang)}</option>
          </select>
          <label className="text-[11px] text-muted flex items-center gap-1">{say({ en: "From", gu: "થી", hi: "से" }, lang)}
            <input type="date" value={f.since ?? ""} onChange={(e) => set({ since: e.target.value })}
              className="rounded-lg border border-warm-border bg-card text-body text-xs px-2 py-1" /></label>
          <label className="text-[11px] text-muted flex items-center gap-1">{say({ en: "To", gu: "સુધી", hi: "तक" }, lang)}
            <input type="date" value={f.until ?? ""} onChange={(e) => set({ until: e.target.value })}
              className="rounded-lg border border-warm-border bg-card text-body text-xs px-2 py-1" /></label>
          <input placeholder={say({ en: "Search details (e.g. Bopal)", gu: "વિગતો શોધો (દા.ત. Bopal)", hi: "विवरण खोजें (उदा. Bopal)" }, lang)} value={f.q ?? ""} onChange={(e) => set({ q: e.target.value })}
            aria-label={say({ en: "Search details", gu: "વિગતો શોધો", hi: "विवरण खोजें" }, lang)}
            className="rounded-lg border border-warm-border bg-card text-body text-xs px-2.5 py-1.5 w-48" />
          <button type="button" onClick={() => token && void downloadAuditCsv(token, f).catch(fail)}
            className="ml-auto text-xs px-3 py-1.5 rounded-lg bg-primary-bg text-primary-text font-semibold">
            {say({ en: "Download CSV", gu: "CSV ડાઉનલોડ", hi: "CSV डाउनलोड" }, lang)}
          </button>
        </div>
        {data && <p className="text-[11px] text-muted">{range(data)}</p>}
        <div className="overflow-x-auto">
          <table className="w-full text-xs min-w-[820px]">
            <thead>
              <tr className="text-muted text-left border-b border-warm-border">
                <th className="py-2 font-medium w-36">{say({ en: "Time", gu: "સમય", hi: "समय" }, lang)}</th><th className="py-2 font-medium w-36">{say({ en: "Who", gu: "કોણ", hi: "कौन" }, lang)}</th>
                <th className="py-2 font-medium">{say({ en: "What happened", gu: "શું થયું", hi: "क्या हुआ" }, lang)}</th><th className="py-2 font-medium">{say({ en: "Details", gu: "વિગતો", hi: "विवरण" }, lang)}</th>
              </tr>
            </thead>
            <tbody>
              {data?.entries.map((e) => (
                <tr key={e.id} className="border-b border-warm-border last:border-0 align-top cursor-pointer hover:bg-subtle/60"
                  onClick={() => setOpen(open === e.id ? null : e.id)}>
                  <td className="py-1.5 pr-2 text-muted whitespace-nowrap tabular-nums">{e.at.replace("T", " ")}</td>
                  <td className="py-1.5 pr-2"><span className="text-body font-semibold">{e.user ?? "—"}</span><span className="block text-muted">{e.role_i18n?.[lang] ?? e.role}</span></td>
                  <td className="py-1.5 pr-2">
                    <span className={`inline-block px-2 py-0.5 rounded-full border text-[10px] font-semibold mr-1 ${CAT_STYLE[e.category] ?? "border-warm-border text-muted"}`}>{(() => { const c = CATEGORIES.find(([k]) => k === e.category); return c ? say(c[1], lang) : e.category; })()}</span>
                    <span className="text-body">{e.label_i18n?.[lang] ?? e.label}</span>
                  </td>
                  <td className="py-1.5 text-muted break-words">
                    {open === e.id ? <pre className="whitespace-pre-wrap font-mono text-[11px] text-body">{JSON.stringify(e.detail, null, 2)}</pre> : detailText(e.detail)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data && data.entries.length === 0 && <p className="py-4 text-sm text-muted">{say({ en: "Nothing matches these filters.", gu: "આ ફિલ્ટર સાથે કંઈ મળતું નથી.", hi: "इन फ़िल्टर से कुछ मेल नहीं खाता।" }, lang)}</p>}
        </div>
        {data && data.total > (f.offset ?? 0) + data.entries.length && (
          <button type="button" onClick={() => setF((x) => ({ ...x, offset: (x.offset ?? 0) + 100 }))}
            className="self-start text-xs font-semibold text-brand-strong">{say({ en: "Older entries →", gu: "જૂની નોંધો →", hi: "पुरानी प्रविष्टियाँ →" }, lang)}</button>
        )}
        {(f.offset ?? 0) > 0 && (
          <button type="button" onClick={() => setF((x) => ({ ...x, offset: Math.max(0, (x.offset ?? 0) - 100) }))}
            className="self-start text-xs font-semibold text-brand-strong">{say({ en: "← Newer entries", gu: "← નવી નોંધો", hi: "← नई प्रविष्टियाँ" }, lang)}</button>
        )}
      </section>
    </div>
  );
};
