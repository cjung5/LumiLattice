import { useTranslations } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import { use } from "react";
import { BackendStatus } from "@/components/BackendStatus";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { Workspace } from "@/components/Workspace";

export default function HomePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = use(params);
  setRequestLocale(locale);
  const t = useTranslations("Home");

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">LumiLattice</h1>
          <p className="text-lg">{t("tagline")}</p>
          <p className="mt-2 text-muted">{t("intro")}</p>
        </div>
        <LanguageSwitcher />
      </header>
      <BackendStatus />
      <Workspace />
    </main>
  );
}
