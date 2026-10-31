"use client";

import { useTranslations } from "next-intl";
import { LevelSwitch, useLevel } from "@/components/Level";

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
  const { level } = useLevel();

  const body = (
    <>
      <div className="grid gap-4 md:grid-cols-3">
        {CARDS.map((card) => (
          <div key={card}>
            <h2 className="font-semibold">{t(`${card}Title`)}</h2>
            <p className="mt-1 text-sm">{t(`${card}Text`)}</p>
          </div>
        ))}
      </div>
      <p className="mt-3 text-sm text-muted">{t("limit")}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" onClick={onExample} disabled={exampleRunning} className="rounded-md bg-accent px-4 py-2 font-medium text-white disabled:opacity-50">
          {t("example")}
        </button>
        <button type="button" onClick={onStart} className="rounded-md border border-line px-4 py-2">
          {t("start")}
        </button>
      </div>
    </>
  );

  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      {level === "guided" &&
        (folded ? (
          <details className="mb-3">
            <summary className="cursor-pointer text-sm font-medium">{t("whatIsThis")}</summary>
            <div className="mt-3">{body}</div>
          </details>
        ) : (
          <div className="mb-4">{body}</div>
        ))}
      <LevelSwitch />
    </section>
  );
}
