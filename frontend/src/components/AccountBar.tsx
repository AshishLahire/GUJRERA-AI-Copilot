import React, { useEffect, useRef, useState } from "react";
import { AuthUser, fetchDemoAccounts, login } from "../api/gujrera";
import { Said, say, useSaathi } from "../saathi/context";
import { tr } from "../saathi/strings";

const ROLE_LABEL: Record<AuthUser["role"], Said> = {
  citizen: { en: "Home buyer", gu: "ઘર ખરીદનાર", hi: "घर खरीदार" },
  developer: { en: "Promoter", gu: "પ્રમોટર", hi: "प्रमोटर" },
  agent: { en: "Agent", gu: "એજન્ટ", hi: "एजेंट" },
  officer: { en: "GUJRERA officer", gu: "GUJRERA અધિકારી", hi: "GUJRERA अधिकारी" },
};

/** The server's quick-pick labels ("Officer (Surat)", "Home buyer 01") in the interface language. */
function pickLabel(label: string, lang: "en" | "gu" | "hi"): string {
  if (lang === "en") return label;
  const officer = label.match(/^Officer \((.+)\)$/);
  if (officer) {
    const where = officer[1] === "statewide" ? { gu: "આખું રાજ્ય", hi: "पूरा राज्य" }[lang] : officer[1];
    return `${{ gu: "અધિકારી", hi: "अधिकारी" }[lang]} (${where})`;
  }
  const buyer = label.match(/^Home buyer(.*)$/);
  if (buyer) return `${{ gu: "ઘર ખરીદનાર", hi: "घर खरीदार" }[lang]}${buyer[1]}`;
  if (label === "Promoter") return say(ROLE_LABEL.developer, lang);
  if (label === "Agent") return say(ROLE_LABEL.agent, lang);
  return label;
}

// Fallback quick picks if the server list cannot be loaded. The server lists the demo accounts that exist in
// the loaded database (demo data or imported public records). The password is never stored here.
const DEMO_ACCOUNTS: { username: string; label: string }[] = [
  { username: "dev_002", label: "Promoter" },
  { username: "agent_001", label: "Agent" },
  { username: "citizen_01", label: "Home buyer" },
  { username: "officer_surat", label: "Officer (Surat)" },
];

/** Header login: a button that opens a small panel; shows the account when logged in. */
export const AccountBar: React.FC = () => {
  const { user, login: setLogin, logout, lang } = useSaathi();
  const [open, setOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accounts, setAccounts] = useState(DEMO_ACCOUNTS);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    fetchDemoAccounts()
      .then((r) => setAccounts(r.accounts))
      .catch(() => setAccounts(DEMO_ACCOUNTS));
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  if (user) {
    return (
      <div className="flex items-center gap-2 text-xs min-w-0">
        <div className="hidden xl:flex flex-col items-end leading-tight min-w-0">
          <span className="font-semibold text-body truncate max-w-[180px]">{user.display_name ?? user.username}</span>
          <span className="text-muted">{say(ROLE_LABEL[user.role], lang)}{user.is_demo ? ` · ${say({ en: "demo", gu: "ડેમો", hi: "डेमो" }, lang)}` : ""}</span>
        </div>
        <button
          type="button"
          onClick={logout}
          className="px-3 py-1.5 rounded-lg border border-warm-border bg-card text-body font-semibold hover:bg-subtle"
        >
          {tr("logout", lang)}
        </button>
      </div>
    );
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await login(username, password);
      setPassword("");
      setOpen(false);
      setLogin(res.token, res.user);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="px-3.5 py-1.5 rounded-lg bg-primary-bg text-primary-text text-xs font-semibold hover:opacity-90"
      >
        {tr("login", lang)}
      </button>
      {open && (
        <form
          onSubmit={submit}
          className="absolute right-0 top-full mt-2 w-[min(320px,calc(100vw-32px))] rounded-xl border border-warm-border bg-card shadow-lg p-4 flex flex-col gap-2.5 text-xs z-50"
        >
          <div className="font-heading text-sm font-bold text-body">{tr("login", lang)}</div>
          <div className="flex flex-wrap gap-1.5">
            {accounts.map((a) => (
              <button
                key={a.username}
                type="button"
                onClick={() => setUsername(a.username)}
                className={`px-2 py-0.5 rounded-full border ${
                  username === a.username ? "border-brand text-brand-strong font-semibold" : "border-warm-border text-muted"
                }`}
              >
                {pickLabel(a.label, lang)}
              </button>
            ))}
          </div>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder={say({ en: "Username", gu: "યુઝરનેમ", hi: "यूज़रनेम" }, lang)}
            aria-label={say({ en: "Username", gu: "યુઝરનેમ", hi: "यूज़रनेम" }, lang)}
            autoComplete="username"
            className="rounded-md border border-warm-border bg-page text-body px-2.5 py-2"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={say({ en: "Password", gu: "પાસવર્ડ", hi: "पासवर्ड" }, lang)}
            aria-label={say({ en: "Password", gu: "પાસવર્ડ", hi: "पासवर्ड" }, lang)}
            autoComplete="current-password"
            className="rounded-md border border-warm-border bg-page text-body px-2.5 py-2"
          />
          {error && <div role="alert" className="text-red-700 dark:text-red-300">{error}</div>}
          <button
            type="submit"
            disabled={busy || !username || !password}
            className="py-2 rounded-md bg-primary-bg text-primary-text font-semibold disabled:opacity-50"
          >
            {busy ? "…" : tr("login", lang)}
          </button>
          <p className="text-muted leading-snug">
            {say({ en: "Demo accounts for the prototype. GUJRERA's own sign-in (portal SSO or OTP) would replace this.", gu: "પ્રોટોટાઇપ માટેનાં ડેમો ખાતાં. GUJRERA નું પોતાનું સાઇન-ઇન (પોર્ટલ SSO કે OTP) તેની જગ્યા લેશે.", hi: "प्रोटोटाइप के लिए डेमो खाते। GUJRERA का अपना साइन-इन (पोर्टल SSO या OTP) इनकी जगह लेगा।" }, lang)}
          </p>
        </form>
      )}
    </div>
  );
};
