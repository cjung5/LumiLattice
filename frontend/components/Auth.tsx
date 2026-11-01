"use client";

import { useTranslations } from "next-intl";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { setTokenSource } from "@/lib/api";

// Public mode sends no token, so the backend treats the browser as anyone. Private mode sends one,
// and the backend then also shows that account's private candidates and makes new ones private.
type Mode = "public" | "private";
const MODE_KEY = "lumilattice.mode";

type Session = { enabled: boolean; login: string | null; token: string | null; expires_at: number };

const AuthContext = createContext<{
  enabled: boolean;
  login: string | null;
  mode: Mode;
  failed: boolean;
  choose: (mode: Mode) => void;
  signOut: () => Promise<void>;
}>({ enabled: false, login: null, mode: "public", failed: false, choose: () => undefined, signOut: async () => undefined });

export const useAuth = () => useContext(AuthContext);

async function readSession(): Promise<Session> {
  const response = await fetch("/api/auth/session", { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as Session;
}

let cached: Session | null = null;

/** Throws when the sign-in has ended, so private work is never saved as public by mistake. */
async function currentToken(): Promise<string> {
  if (!cached?.token || cached.expires_at - 60 < Date.now() / 1000) cached = await readSession();
  if (!cached.token) throw new Error("Your sign-in has ended. Sign in again.");
  return cached.token;
}

function saveMode(mode: Mode) {
  try {
    window.localStorage.setItem(MODE_KEY, mode);
  } catch {
    // Blocked storage: the mode lasts until the page closes.
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [enabled, setEnabled] = useState(false);
  const [login, setLogin] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("public");
  const [failed, setFailed] = useState(false);

  // Set the token before the state changes: the workspace reloads on the new mode at once.
  function apply(next: Mode) {
    setTokenSource(next === "private" ? currentToken : null);
    setMode(next);
  }

  useEffect(() => {
    setFailed(new URLSearchParams(window.location.search).get("signin") === "failed");
    readSession()
      .then((session) => {
        cached = session;
        setEnabled(session.enabled);
        setLogin(session.login);
        let saved: string | null = null;
        try {
          saved = window.localStorage.getItem(MODE_KEY);
        } catch {
          // Blocked storage: stay in public mode.
        }
        if (session.login && saved === "private") apply("private");
      })
      .catch(() => setEnabled(false));
  }, []);

  function choose(next: Mode) {
    saveMode(next);
    if (next === "private" && !login) {
      const here = `${window.location.pathname}${window.location.search}`;
      window.location.assign(`/api/auth/github?next=${encodeURIComponent(here)}`);
      return;
    }
    apply(next);
  }

  async function signOut() {
    await fetch("/api/auth/signout", { method: "POST" });
    cached = null;
    saveMode("public");
    setLogin(null);
    apply("public");
  }

  return (
    <AuthContext.Provider value={{ enabled, login, mode, failed, choose, signOut }}>{children}</AuthContext.Provider>
  );
}

export function ModeSwitch() {
  const t = useTranslations("Auth");
  const { enabled, login, mode, failed, choose, signOut } = useAuth();
  if (!enabled) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <div role="radiogroup" aria-label={t("modeLabel")} className="segmented text-sm">
        {(["public", "private"] as const).map((option) => (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={mode === option}
            title={t(`${option}Hint`)}
            onClick={() => choose(option)}
            className="segment"
          >
            {option === "private" ? `🔒 ${t("private")}` : t("public")}
          </button>
        ))}
      </div>
      {login && (
        <>
          <span className="text-muted">@{login}</span>
          <button type="button" className="text-xs underline" onClick={() => void signOut()}>
            {t("signOut")}
          </button>
        </>
      )}
      {failed && !login && <span className="text-xs text-danger">{t("signInFailed")}</span>}
    </div>
  );
}
