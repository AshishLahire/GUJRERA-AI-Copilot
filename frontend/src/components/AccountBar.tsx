import React, { useState } from "react";
import { AuthUser, login } from "../api/gujrera";

const ROLE_LABEL: Record<AuthUser["role"], string> = {
  citizen: "Home buyer",
  developer: "Promoter",
  agent: "Agent",
  officer: "GUJRERA officer",
};

// Seeded demo accounts. The password is GUJRERA_DEMO_PASSWORD (see .env.example); it is never stored here.
const DEMO_ACCOUNTS: { username: string; label: string }[] = [
  { username: "dev_001", label: "Promoter" },
  { username: "agent_001", label: "Agent" },
  { username: "citizen_01", label: "Home buyer" },
  { username: "officer_surat", label: "Officer (Surat)" },
];

export const AccountBar: React.FC<{
  user: AuthUser | null;
  onLogin: (token: string, user: AuthUser) => void;
  onLogout: () => void;
}> = ({ user, onLogin, onLogout }) => {
  const [open, setOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (user) {
    return (
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-warm-border bg-subtle px-3 py-2 text-xs">
        <span className="font-semibold text-body">{user.display_name ?? user.username}</span>
        <span className="px-2 py-0.5 rounded-full border border-warm-border text-muted">{ROLE_LABEL[user.role]}</span>
        {user.is_demo && <span className="text-muted">demo account</span>}
        <button type="button" onClick={onLogout} className="ml-auto font-semibold text-muted hover:text-body underline">
          Log out
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
      onLogin(res.token, res.user);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <span>Promoter, agent or officer?</span>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="px-3 py-1.5 rounded-lg border border-warm-border bg-card text-body font-semibold hover:bg-subtle"
        >
          Log in
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="rounded-lg border border-warm-border bg-subtle p-3 flex flex-col gap-2 text-xs">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-muted mr-1">Demo accounts:</span>
        {DEMO_ACCOUNTS.map((a) => (
          <button
            key={a.username}
            type="button"
            onClick={() => setUsername(a.username)}
            className={`px-2 py-0.5 rounded-full border ${username === a.username ? "border-accent-amber text-body" : "border-warm-border text-muted"}`}
          >
            {a.label}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="Username"
          aria-label="Username"
          autoComplete="username"
          className="flex-1 min-w-[120px] rounded-md border border-warm-border bg-page text-body px-2.5 py-1.5"
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          aria-label="Password"
          autoComplete="current-password"
          className="flex-1 min-w-[120px] rounded-md border border-warm-border bg-page text-body px-2.5 py-1.5"
        />
        <button
          type="submit"
          disabled={busy || !username || !password}
          className="px-3 py-1.5 rounded-md bg-primary-bg text-primary-text font-semibold disabled:opacity-50"
        >
          {busy ? "…" : "Log in"}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="px-2 text-muted hover:text-body">
          Close
        </button>
      </div>
      {error && <div role="alert" className="text-red-700 dark:text-red-300">{error}</div>}
      <p className="text-muted">Prototype sign-in for demo accounts. GUJRERA's own sign-in (portal SSO or OTP) would replace it.</p>
    </form>
  );
};
