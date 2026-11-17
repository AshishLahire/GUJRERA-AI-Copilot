import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { AuthUser, Lang, fetchMe } from "../api/gujrera";

const TOKEN_KEY = "gujrera.token";
const LANG_KEY = "gujrera.lang";

function read(key: string): string | null {
  try {
    return sessionStorage.getItem(key) ?? localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null, persistent = false): void {
  try {
    const store = persistent ? localStorage : sessionStorage;
    if (value) store.setItem(key, value);
    else store.removeItem(key);
  } catch {
    // storage unavailable: the setting lasts for this page view only
  }
}

interface SaathiState {
  lang: Lang;
  setLang: (lang: Lang) => void;
  token: string | null;
  user: AuthUser | null;
  login: (token: string, user: AuthUser) => void;
  logout: () => void;
}

const Ctx = createContext<SaathiState | null>(null);

export const SaathiProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [lang, setLangState] = useState<Lang>(() => {
    const saved = read(LANG_KEY);
    return saved === "en" || saved === "hi" || saved === "gu" ? saved : "gu";
  });
  const [token, setToken] = useState<string | null>(() => read(TOKEN_KEY));
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  useEffect(() => {
    if (!token || user) return;
    fetchMe(token)
      .then((r) => setUser(r.user))
      .catch(() => {
        setToken(null);
        write(TOKEN_KEY, null);
      });
  }, [token, user]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    write(LANG_KEY, l, true);
  }, []);
  const login = useCallback((t: string, u: AuthUser) => {
    setToken(t);
    setUser(u);
    write(TOKEN_KEY, t);
  }, []);
  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    write(TOKEN_KEY, null);
  }, []);

  const value = useMemo(() => ({ lang, setLang, token, user, login, logout }), [lang, setLang, token, user, login, logout]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
};

export function useSaathi(): SaathiState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useSaathi must be used inside SaathiProvider");
  return v;
}
