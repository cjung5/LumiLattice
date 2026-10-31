"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

const STORAGE_KEY = "lumilattice.theme";
type Theme = "light" | "dark";

/** Runs before the first paint (see the layout), so a page never flashes the wrong theme. */
export const THEME_SCRIPT = `(function(){var s;try{s=localStorage.getItem("${STORAGE_KEY}")}catch(e){}document.documentElement.dataset.theme=s||"dark"})()`;

export function ThemeSwitch() {
  const t = useTranslations("Theme");
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  }, []);

  function apply(next: Theme) {
    // All at once: with each control on its own short transition, the page passes through a
    // mix of both themes, and a busy page can stay in that mix for a moment.
    const root = document.documentElement;
    root.dataset.themeSwitching = "";
    root.dataset.theme = next;
    setTheme(next);
    requestAnimationFrame(() => requestAnimationFrame(() => delete root.dataset.themeSwitching));
  }

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    apply(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // The choice lasts for this page only.
    }
  }

  const label = t(theme === "dark" ? "toLight" : "toDark");
  return (
    <button type="button" onClick={toggle} aria-label={label} title={label} className="btn btn-ghost btn-sm !px-2" disabled={theme === null}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        {theme === "dark" ? (
          <>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.900 4.900l1.400 1.400M17.700 17.700l1.400 1.400M2 12h2M20 12h2M4.900 19.100l1.400-1.400M17.700 6.300l1.400-1.400" />
          </>
        ) : (
          <path d="M20 14.500A8.500 8.500 0 0 1 9.500 4a8.500 8.500 0 1 0 10.500 10.500Z" />
        )}
      </svg>
    </button>
  );
}
