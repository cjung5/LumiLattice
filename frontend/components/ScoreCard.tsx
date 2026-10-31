"use client";

import { useTranslations } from "next-intl";
import { EvidenceTag } from "@/components/EvidenceTag";
import type { GoalScore, Verdict } from "@/lib/api";

// Status colors always come with an icon and a word, never color alone.
export const VERDICT: Record<Verdict, { icon: string; color: string }> = {
  meets: { icon: "✓", color: "var(--status-good)" },
  uncertain: { icon: "?", color: "var(--status-warning)" },
  fails: { icon: "✗", color: "var(--status-critical)" },
  unknown: { icon: "–", color: "var(--chart-muted)" },
};

export function ScoreCard({ score, title }: { score: GoalScore; title: string }) {
  const t = useTranslations("Score");
  return (
    <div className="rounded-md border border-line p-3 text-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-medium">{title}</span>
        <span className="text-xs text-muted">{t("summary", { meets: score.meets, total: score.total })}</span>
      </div>
      <ul className="mt-2 space-y-1">
        {score.criteria.map((c) => (
          <li key={c.id} className="flex gap-2">
            <span className="flex w-24 shrink-0 items-center gap-1 text-xs font-medium">
              <span aria-hidden className="inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold text-white" style={{ background: VERDICT[c.verdict].color }}>
                {VERDICT[c.verdict].icon}
              </span>
              {t(`verdict.${c.verdict}`)}
            </span>
            <span className="text-xs">
              <span className="font-medium">{t(`criterion.${c.id}`)}</span>
              <span className="text-muted"> — {c.detail}</span>
              {c.evidence && c.evidence.status !== "Unknown" && (
                <span className="ml-1 align-middle"><EvidenceTag status={c.evidence.status} /></span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
