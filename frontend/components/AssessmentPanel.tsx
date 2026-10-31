"use client";

import { useTranslations } from "next-intl";
import { useBackendText } from "@/lib/backendText";
import type { AssessmentStatus, CheckStatus, StructuralAssessment } from "@/lib/api";

const STATUS_STYLE: Record<AssessmentStatus, string> = {
  "Structurally Plausible": "border-tag-exp text-tag-exp",
  "Structural Concerns": "border-tag-heur text-tag-heur",
  "Insufficient Evidence": "border-tag-unknown text-tag-unknown",
};

const CHECK_ICON: Record<CheckStatus, { icon: string; className: string }> = {
  pass: { icon: "✓", className: "text-tag-exp" },
  warn: { icon: "!", className: "text-tag-heur" },
  fail: { icon: "✗", className: "text-danger" },
  info: { icon: "i", className: "text-tag-dft" },
  not_applicable: { icon: "–", className: "text-tag-unknown" },
};

type Props = {
  assessment: StructuralAssessment;
  selectedCheck?: string | null;
  onSelectCheck?: (checkId: string | null) => void;
};

export function AssessmentPanel({ assessment, selectedCheck, onSelectCheck }: Props) {
  const t = useTranslations("Assessment");
  const tb = useBackendText();
  const checks = assessment.checks.filter((c) => c.status !== "not_applicable");

  return (
    <div className="space-y-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded border px-2 py-0.5 font-medium ${STATUS_STYLE[assessment.status]}`}>
          {tb(assessment.status)}
        </span>
        {onSelectCheck && <span className="text-xs text-muted">{t("clickHint")}</span>}
      </div>
      <ul className="space-y-1">
        {checks.map((check) => {
          const icon = CHECK_ICON[check.status];
          const clickable = Boolean(onSelectCheck && check.atom_indices.length);
          const selected = selectedCheck === check.id;
          return (
            <li key={check.id}>
              <button
                type="button"
                disabled={!clickable}
                onClick={() => onSelectCheck?.(selected ? null : check.id)}
                title={check.method ? tb(check.method) : undefined}
                className={`flex w-full gap-2 rounded px-2 py-1 text-left ${
                  clickable ? "hover:bg-background" : "cursor-default"
                } ${selected ? "bg-background ring-1 ring-accent" : ""}`}
              >
                <span className={`w-4 shrink-0 text-center font-bold ${icon.className}`} aria-label={check.status}>
                  {icon.icon}
                </span>
                <span>
                  <span className="font-medium">{tb(check.name)}</span>
                  <span className="text-muted"> — {tb(check.message)}</span>
                  {clickable && (
                    <span className="ml-1 text-xs text-accent">
                      {t("atoms", { count: check.atom_indices.length })}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {assessment.notes.map((note) => (
        <p key={tb(note)} className="text-xs text-muted">
          {tb(note)}
        </p>
      ))}
    </div>
  );
}
