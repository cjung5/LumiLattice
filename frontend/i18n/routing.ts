import { defineRouting } from "next-intl/routing";

// en and ko are written by hand. The others come from backend/scripts/translate_ui.py
// (Muse Spark), and the UI marks them as machine-translated.
export const routing = defineRouting({
  locales: ["en", "ko", "zh-Hans", "ja", "es", "de"],
  defaultLocale: "en",
});

export type Locale = (typeof routing.locales)[number];

export const LOCALE_NAMES: Record<Locale, string> = {
  en: "English",
  ko: "한국어",
  "zh-Hans": "简体中文",
  ja: "日本語",
  es: "Español",
  de: "Deutsch",
};

export const MACHINE_TRANSLATED: ReadonlySet<string> = new Set(["zh-Hans", "ja", "es", "de"]);
