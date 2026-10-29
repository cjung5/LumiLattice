import { defineRouting } from "next-intl/routing";

// Stage 1: English and Korean. Stage 2 adds zh-Hans, ja, es, de (spec section 5).
export const routing = defineRouting({
  locales: ["en", "ko"],
  defaultLocale: "en",
});

export type Locale = (typeof routing.locales)[number];

export const LOCALE_NAMES: Record<Locale, string> = {
  en: "English",
  ko: "한국어",
};
