import React, { useEffect, useRef, useState } from "react";
import { AuthUser, login } from "../api/gujrera";
import { useSaathi } from "../saathi/context";
import { tr } from "../saathi/strings";

const ROLE_LABEL: Record<AuthUser["role"], string> = {
  citizen: "Home buyer",
  developer: "Promoter",
  agent: "Agent",
  officer: "GUJRERA officer",
};

// Seeded demo accounts. The password is GUJRERA_DEMO_PASSWORD (see .env.example); it is never stored here.
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
  const panelRef = useRef<HTMLDivElement>(null);

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
          <span className="text-muted">{ROLE_LABEL[user.role]}{user.is_demo ? " · demo" : ""}</span>
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
            {DEMO_ACCOUNTS.map((a) => (
              <button
                key={a.username}
                type="button"
                onClick={() => setUsername(a.username)}
                className={`px-2 py-0.5 rounded-full border ${
                  username === a.username ? "border-brand text-brand-strong font-semibold" : "border-warm-border text-muted"
                }`}
              >
                {a.label}
              </button>
            ))}
          </div>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Username"
            aria-label="Username"
            autoComplete="username"
            className="rounded-md border border-warm-border bg-page text-body px-2.5 py-2"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            aria-label="Password"
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
            Demo accounts for the prototype. GUJRERA's own sign-in (portal SSO or OTP) would replace this.
          </p>
        </form>
      )}
    </div>
  );
};
