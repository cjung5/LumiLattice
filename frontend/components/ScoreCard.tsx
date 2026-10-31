"use client";

import { useTranslations } from "next-intl";
import { useBackendText } from "@/lib/backendText";
import { EvidenceTag } from "@/components/EvidenceTag";
import type { GoalScore, Verdict } from "@/lib/api";

// Status colors always come with an icon and a word, never color alone.
export const VERDICT: Record<Verdict, { icon: string; color: string; ink: string }> = {
  meets: { icon: "✓", color: "var(--status-good)", ink: "#0b0b0f" },
  uncertain: { icon: "?", color: "var(--status-warning)", ink: "#0b0b0f" },
  fails: { icon: "✗", color: "var(--status-critical)", ink: "#ffffff" },
  unknown: { icon: "–", color: "var(--chart-muted)", ink: "#0b0b0f" },
};

export function ScoreCard({ score, title }: { score: GoalScore; title: string }) {
  const t = useTranslations("Score");
  const tb = useBackendText();
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
              <span aria-hidden className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold" style={{ background: VERDICT[c.verdict].color, color: VERDICT[c.verdict].ink }}>
                {VERDICT[c.verdict].icon}
              </span>
              {t(`verdict.${c.verdict}`)}
            </span>
            <span className="text-xs">
              <span className="font-medium">{t(`criterion.${c.id}`)}</span>
              <span className="text-muted"> — {tb(c.detail)}</span>
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
