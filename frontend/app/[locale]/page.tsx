import { useTranslations } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import { use } from "react";
import { AuthProvider, ModeSwitch } from "@/components/Auth";
import { BackendStatus } from "@/components/BackendStatus";
import { PointerLight } from "@/components/brand/LatticeLight";
import { Logo } from "@/components/brand/Logo";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { LevelProvider, LevelSwitch } from "@/components/Level";
import { ThemeSwitch } from "@/components/ThemeSwitch";
import { ModeWorkspace } from "@/components/ModeWorkspace";
import { MACHINE_TRANSLATED } from "@/i18n/routing";

export default function HomePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = use(params);
  setRequestLocale(locale);
  const tl = useTranslations("Language");

  return (
    <LevelProvider>
      <AuthProvider>
      <PointerLight />
      {/* The lattice's canvas runs past the column. Clip, not hidden: the step bar must stay sticky. */}
      <div className="overflow-x-clip">
      <main className="mx-auto flex max-w-6xl flex-col gap-5 px-4 pb-16 pt-4 sm:px-6">
        <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div className="flex items-center gap-2.5">
            <Logo />
            <h1 className="text-xl font-semibold tracking-tight">LumiLattice</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <ModeSwitch />
            <LevelSwitch />
            <BackendStatus />
            <ThemeSwitch />
            <LanguageSwitcher />
          </div>
        </header>
        {MACHINE_TRANSLATED.has(locale) && <p className="text-xs text-warning">{tl("machineTranslated")}</p>}
        <ModeWorkspace />
      </main>
      </div>
      </AuthProvider>
    </LevelProvider>
  );
}
