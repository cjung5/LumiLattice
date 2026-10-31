"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { useLevel } from "@/components/Level";
import { edgeNm, GapScale, NScale } from "@/components/LightScales";
import { Term } from "@/components/Term";
import type { Goal } from "@/lib/api";

const TOXIC = ["Pb", "Cd", "Hg", "Tl", "As"];
/** AR waveguide preset: high index, transparent across the visible range (gap above ~3.1 eV). */
export const AR_GOAL = { target_n: 2.2, min_band_gap: 3.0 };

type Props = { goal: Goal; onChange: (goal: Goal) => void };

// Spec 3.1 / P0 #1: the research goal comes first; every host and candidate is scored against it.
export function GoalPanel({ goal, onChange }: Props) {
  const t = useTranslations("Goal");
  const { level } = useLevel();
  const [elementText, setElementText] = useState(goal.forbidden_elements.join(", "));

  function setElements(text: string) {
    setElementText(text);
    const list = text
      .split(/[\s,]+/)
      .map((e) => e.trim())
      .filter((e) => /^[A-Za-z]{1,2}$/.test(e))
      .map((e) => e[0].toUpperCase() + e.slice(1).toLowerCase());
    onChange({ ...goal, forbidden_elements: [...new Set(list)] });
  }

  if (level === "guided") {
    const avoidToxic = TOXIC.every((e) => goal.forbidden_elements.includes(e));
    return (
      <section className="rounded-lg border border-line bg-surface p-4 text-sm">
        <h2 className="text-base font-semibold">{t("titleGuided")}</h2>
        <p className="mb-3 text-muted">{t("hintGuided")}</p>
        <div className="grid gap-6 md:grid-cols-2">
          <div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label htmlFor="goal-n" className="font-medium"><Term id="n">{t("nGuided")}</Term></label>
              <input
                id="goal-n"
                type="number"
                step="0.05"
                min={1}
                max={5}
                className="w-20 rounded-md border border-line bg-background px-2 py-1"
                value={goal.target_n}
                onChange={(e) => onChange({ ...goal, target_n: e.target.valueAsNumber || goal.target_n })}
              />
            </div>
            <NScale goal={goal.target_n} />
          </div>
          <div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label htmlFor="goal-gap" className="font-medium"><Term id="band_gap">{t("gapGuided")}</Term></label>
              <input
                id="goal-gap"
                type="number"
                step="0.1"
                min={0.5}
                max={15}
                className="w-20 rounded-md border border-line bg-background px-2 py-1"
                value={goal.min_band_gap}
                onChange={(e) => onChange({ ...goal, min_band_gap: e.target.valueAsNumber || goal.min_band_gap })}
              />
            </div>
            <GapScale goal={goal.min_band_gap} />
          </div>
        </div>
        <p className="mt-1">{t("sentence", { n: goal.target_n, nm: edgeNm(goal.min_band_gap) })}</p>
        <label className="mt-2 flex items-center gap-2">
          <input
            type="checkbox"
            checked={avoidToxic}
            onChange={(e) => {
              const others = goal.forbidden_elements.filter((el) => !TOXIC.includes(el));
              setElementText("");
              onChange({ ...goal, forbidden_elements: e.target.checked ? [...others, ...TOXIC] : others });
            }}
          />
          {t("avoidToxic", { elements: TOXIC.join(", ") })}
        </label>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      <h2 className="font-semibold">{t("title")}</h2>
      <p className="mb-3 text-sm text-muted">{t("hint")}</p>
      <div className="flex flex-wrap items-end gap-4 text-sm">
        <label className="flex flex-col gap-1">
          <span>{t("targetN")}</span>
          <input
            type="number"
            step="0.05"
            min={1}
            max={5}
            className="w-24 rounded-md border border-line bg-background px-2 py-1.5"
            value={goal.target_n}
            onChange={(e) => onChange({ ...goal, target_n: e.target.valueAsNumber || goal.target_n })}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span>{t("minGap")}</span>
          <input
            type="number"
            step="0.1"
            min={0}
            max={15}
            className="w-24 rounded-md border border-line bg-background px-2 py-1.5"
            value={goal.min_band_gap}
            onChange={(e) => onChange({ ...goal, min_band_gap: e.target.valueAsNumber || goal.min_band_gap })}
          />
        </label>
        <label className="flex min-w-48 flex-1 flex-col gap-1">
          <span>{t("forbidden")}</span>
          <input
            className="rounded-md border border-line bg-background px-2 py-1.5"
            placeholder={t("forbiddenPlaceholder")}
            value={elementText}
            onChange={(e) => setElements(e.target.value)}
          />
        </label>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-md border border-line px-3 py-1.5 text-xs"
            onClick={() => {
              setElementText(goal.forbidden_elements.join(", "));
              onChange({ ...goal, ...AR_GOAL });
            }}
          >
            {t("presetAr")}
          </button>
          <button
            type="button"
            className="rounded-md border border-line px-3 py-1.5 text-xs"
            onClick={() => setElements([...new Set([...goal.forbidden_elements, ...TOXIC])].join(", "))}
          >
            {t("presetToxic")}
          </button>
        </div>
      </div>
      <p className="mt-2 text-xs text-muted">{t("note")}</p>
    </section>
  );
}
