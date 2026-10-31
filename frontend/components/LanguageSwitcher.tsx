"use client";

import { useLocale, useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";
import { LOCALE_NAMES, routing, type Locale } from "@/i18n/routing";

export function LanguageSwitcher() {
  const t = useTranslations("Language");
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();

  return (
    <select
      aria-label={t("label")}
      className="field min-h-[2.125rem] !py-1 text-sm"
      value={locale}
      onChange={(event) => router.replace(pathname, { locale: event.target.value as Locale })}
    >
      {routing.locales.map((code) => (
        <option key={code} value={code}>
          {LOCALE_NAMES[code]}
        </option>
      ))}
    </select>
  );
}
