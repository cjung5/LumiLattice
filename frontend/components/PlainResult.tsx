"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { formatValue, EvidenceTag } from "@/components/EvidenceTag";
import { GapScale, NScale } from "@/components/LightScales";
import { VERDICT } from "@/components/ScoreCard";
import { Term } from "@/components/Term";
import { scoreGoal, type Candidate, type Goal, type GoalScore, type LinearMix, type PropertyValue, type Verdict } from "@/lib/api";

const rangeOf = (pv?: PropertyValue | null): [number, number] | null =>
  pv?.value_range ?? (pv?.value != null ? [pv.value, pv.value] : null);

/** The goal score in everyday words, with the same verdicts and evidence as the Goal score tab. */
export function PlainScore({ score, hostN, mix }: { score: GoalScore; hostN?: number | null; mix?: LinearMix | null }) {
  const t = useTranslations("Plain");
  // "No forbidden elements" adds nothing unless the researcher ruled some out.
  const rows = score.criteria.filter((c) => c.id !== "elements" || score.goal.forbidden_elements.length > 0);
  return (
    <ul className="space-y-3">
      {rows.map((c) => (
        <li key={c.id}>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span
              aria-hidden
              className="inline-flex h-5 w-5 items-center justify-center rounded-full text-xs font-bold"
              style={{ background: VERDICT[c.verdict].color, color: VERDICT[c.verdict].ink }}
            >
              {VERDICT[c.verdict].icon}
            </span>
            <span className="font-medium">
              {c.id === "n" ? <Term id="n">{t("criterion.n")}</Term> : c.id === "band_gap" ? <Term id="band_gap">{t("criterion.band_gap")}</Term> : t(`criterion.${c.id}`)}
            </span>
            {c.evidence && c.evidence.status !== "Unknown" && (
              <>
                <span className="tabular-nums">{formatValue(c.evidence)}</span>
                <EvidenceTag status={c.evidence.status} />
              </>
            )}
          </div>
          <p className="mt-0.5 pl-7">
            {t(`sentence.${c.id}.${c.verdict}`)}
            {c.id === "band_gap" && c.verdict !== "meets" && c.evidence?.status === "DFT-computed" && ` ${t("dftGapNote")}`}
          </p>
          {c.id === "n" && (
            <div className="pl-7">
              <NScale goal={score.goal.target_n} range={rangeOf(c.evidence)} host={hostN} mix={mix?.n} />
              {mix?.n != null && (
                <p className="text-xs">
                  <span aria-hidden>◆ </span>
                  <Term id="mix">{t("mixName")}</Term>: {t("mixN", { value: mix.n.toFixed(2), error: mix.typical_n_error })}
                </p>
              )}
            </div>
          )}
          {c.id === "band_gap" && (
            <div className="pl-7">
              <GapScale goal={score.goal.min_band_gap} range={rangeOf(c.evidence)} mix={mix?.band_gap} />
              {mix?.band_gap != null && (
                <p className="text-xs">
                  <span aria-hidden>◆ </span>
                  <Term id="mix">{t("mixName")}</Term>: {t("mixGap", { value: mix.band_gap.toFixed(2), error: mix.typical_gap_error_ev })}
                </p>
              )}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function useScore(goal: Goal, subject: { candidate_id: string } | { formula: string } | null) {
  const [score, setScore] = useState<{ key: string; data: GoalScore } | null>(null);
  const key = subject ? JSON.stringify([goal, subject]) : null;
  useEffect(() => {
    if (!key || !subject) return;
    let active = true;
    scoreGoal(goal, subject)
      .then((data) => active && setScore({ key, data }))
      .catch(() => undefined);
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return score?.key === key ? score.data : null;
}

export function HostScore({ goal, formula }: { goal: Goal; formula: string }) {
  const t = useTranslations("Plain");
  const score = useScore(goal, { formula });
  if (!score) return null;
  return (
    <div className="subcard text-sm">
      <h3 className="mb-2 font-medium">{t("hostTitle", { formula })}</h3>
      <PlainScore score={score} />
    </div>
  );
}

const headlineOf = (verdicts: Verdict[]) =>
  verdicts.includes("fails") ? "fails" : verdicts.every((v) => v === "meets") ? "meets" : "uncertain";

type Props = {
  candidate: Candidate;
  goal: Goal;
  hostFormula: string | null;
  onAskAgent?: (message: string, shown: string) => void;
  onSeeEvidence?: () => void;
};

// Sent to the research agent in English; it replies in the UI language.
const explainPrompt = (id: string) =>
  `Explain the result for ${id}: what each score means for AR glasses, why it came out this way, and what is still unknown.`;
const improvePrompt = (id: string) =>
  `Suggest and test one change to ${id} that moves it closer to my goal. Say why you chose it, then compare the two.`;

/** The first thing a beginner reads about a candidate: does it work, how sure are we, what next. */
export function PlainResult({ candidate, goal, hostFormula, onAskAgent, onSeeEvidence }: Props) {
  const t = useTranslations("Plain");
  const id = candidate.candidate_id;
  const score = useScore(goal, { candidate_id: id });
  const host = useScore(goal, hostFormula ? { formula: hostFormula } : null);
  const hostN = host?.criteria.find((c) => c.id === "n")?.evidence?.value;
  const swaps = candidate.transformation.substitutions
    .map((s) => t("swap", { from: s.element_from, to: s.element_to, percent: +(s.fraction * 100).toFixed(1) }))
    .join(", ");

  return (
    <div className="space-y-3 rounded-xl border border-accent bg-surface p-5 text-sm shadow-[0_0_32px_-14px_var(--accent)]">
      <div>
        <p className="text-xs text-muted">
          {t("subject", { id, formula: candidate.formula })}
          {swaps && ` · ${swaps}`}
        </p>
        {score ? (
          <h3 className="mt-1 text-lg font-semibold">{t(`headline.${headlineOf(score.criteria.map((c) => c.verdict))}`)}</h3>
        ) : (
          <p className="mt-1 text-muted">{t("loading")}</p>
        )}
      </div>
      {score && <PlainScore score={score} hostN={hostN} mix={candidate.optical_estimate?.linear_mix} />}
      {hostN != null && hostFormula && <p className="text-xs text-muted">{t("hostMark", { formula: hostFormula })}</p>}
      <p className="text-xs text-muted">{t("caveat")}</p>
      <div className="flex flex-wrap gap-2">
        {onAskAgent && (
          <>
            <button type="button" onClick={() => onAskAgent(explainPrompt(id), t("explain"))} className="btn btn-primary btn-sm">
              {t("explain")}
            </button>
            <button type="button" onClick={() => onAskAgent(improvePrompt(id), t("improve"))} className="btn btn-outline btn-sm">
              {t("improve")}
            </button>
          </>
        )}
        {onSeeEvidence && (
          <button type="button" onClick={onSeeEvidence} className="btn btn-ghost btn-sm">
            {t("seeEvidence")}
          </button>
        )}
      </div>
    </div>
  );
}
