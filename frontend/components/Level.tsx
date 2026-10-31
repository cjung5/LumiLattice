"use client";

import { useTranslations } from "next-intl";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

// Guided: plain words and the main path. Expert: every tool on screen. Nothing is removed in
// Guided mode; the technical parts move behind <Advanced>.
export type Level = "guided" | "expert";

const STORAGE_KEY = "lumilattice.level";
const LevelContext = createContext<{ level: Level; setLevel: (level: Level) => void }>({
  level: "guided",
  setLevel: () => undefined,
});

export function LevelProvider({ children }: { children: ReactNode }) {
  const [level, setLevelState] = useState<Level>("guided");

  useEffect(() => {
    try {
      if (window.localStorage.getItem(STORAGE_KEY) === "expert") setLevelState("expert");
    } catch {
      // Blocked storage: stay in Guided mode.
    }
  }, []);

  function setLevel(next: Level) {
    setLevelState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // The choice lasts for this page only.
    }
  }

  return <LevelContext.Provider value={{ level, setLevel }}>{children}</LevelContext.Provider>;
}

export const useLevel = () => useContext(LevelContext);

export function LevelSwitch() {
  const t = useTranslations("Level");
  const { level, setLevel } = useLevel();
  return (
    <div role="radiogroup" aria-label={t("label")} title={t(`${level}Hint`)} className="segmented text-sm">
      {(["guided", "expert"] as const).map((option) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={level === option}
          onClick={() => setLevel(option)}
          className="segment"
        >
          {t(option)}
        </button>
      ))}
    </div>
  );
}

/** Technical content: on screen in Expert mode, one click away in Guided mode. */
export function Advanced({ label, children }: { label: string; children: ReactNode }) {
  const { level } = useLevel();
  if (level === "expert") return <>{children}</>;
  return (
    <details className="subcard text-sm">
      <summary className="font-medium">{label}</summary>
      <div className="mt-3 space-y-3">{children}</div>
    </details>
  );
}
