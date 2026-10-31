"use client";

import { useTranslations } from "next-intl";
import { LatticeArt } from "@/components/brand/LatticeArt";
import { useLevel } from "@/components/Level";

type Props = {
  /** After the first candidate the explanation folds away, but stays one click away. */
  folded: boolean;
  exampleRunning: boolean;
  onExample: () => void;
  onStart: () => void;
};

const CARDS = ["problem", "do", "get"] as const;

export function Intro({ folded, exampleRunning, onExample, onStart }: Props) {
  const t = useTranslations("Intro");
  const th = useTranslations("Home");
  const tl = useTranslations("Level");
  const { level } = useLevel();

  const hero = (
    <section className="relative overflow-hidden py-4 md:py-8">
      <LatticeArt className="pointer-events-none absolute -right-10 top-1/2 hidden w-[26rem] -translate-y-1/2 md:block lg:right-0" />
      <div className="relative max-w-2xl">
        <p className="text-3xl font-semibold leading-tight tracking-tight sm:text-4xl md:text-[2.75rem]">
          <span className="prism-text">{th("headline")}</span>
        </p>
        <p className="mt-4 max-w-xl text-lg text-muted">{th("lead")}</p>
        <div className="mt-6 flex flex-wrap gap-3">
          <button type="button" onClick={onExample} disabled={exampleRunning} className="btn btn-primary">
            {t("example")}
          </button>
          <button type="button" onClick={onStart} className="btn btn-secondary">
            {t("start")}
          </button>
        </div>
        <p className="mt-3 text-xs text-muted">{tl("guidedHint")}</p>
      </div>
    </section>
  );

  const explanation = (
    <>
      <div className="grid gap-3 md:grid-cols-3">
        {CARDS.map((card) => (
          <div key={card} className="card">
            <h2 className="text-lg font-semibold tracking-tight">{t(`${card}Title`)}</h2>
            <p className="mt-2 text-sm text-muted">{t(`${card}Text`)}</p>
          </div>
        ))}
      </div>
      <p className="text-sm text-muted">{t("limit")}</p>
    </>
  );

  if (level !== "guided") {
    return folded ? null : <p className="text-lg text-muted">{th("headline")}</p>;
  }
  if (folded) {
    return (
      <details className="subcard text-sm">
        <summary className="font-medium">{t("whatIsThis")}</summary>
        <div className="mt-3 flex flex-col gap-3">{explanation}</div>
      </details>
    );
  }
  return (
    <>
      {hero}
      {explanation}
    </>
  );
}
