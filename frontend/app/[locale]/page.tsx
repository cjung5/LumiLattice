import { useTranslations } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import { use } from "react";
import { BackendStatus } from "@/components/BackendStatus";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { Workspace } from "@/components/Workspace";
import { MACHINE_TRANSLATED } from "@/i18n/routing";

export default function HomePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = use(params);
  setRequestLocale(locale);
  const t = useTranslations("Home");
  const tl = useTranslations("Language");

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">LumiLattice</h1>
          <p className="text-lg">{t("tagline")}</p>
          <p className="mt-2 text-muted">{t("intro")}</p>
          {MACHINE_TRANSLATED.has(locale) && (
            <p className="mt-1 text-xs text-warning">{tl("machineTranslated")}</p>
          )}
        </div>
        <LanguageSwitcher />
      </header>
      <BackendStatus />
      <Workspace />
    </main>
  );
}
