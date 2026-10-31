"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { useLevel } from "@/components/Level";
import type { Candidate, DecisionKind } from "@/lib/api";

const BUTTONS: { kind: DecisionKind; icon: string; className: string }[] = [
  { kind: "accept", icon: "✓", className: "border-tag-exp text-tag-exp" },
  { kind: "modify", icon: "✎", className: "border-accent text-accent-text" },
  { kind: "explore", icon: "⇄", className: "border-accent text-accent-text" },
  { kind: "reject", icon: "✗", className: "border-danger text-danger" },
];

type Props = {
  candidate: Candidate;
  busy: boolean;
  onDecide: (kind: DecisionKind, reason: string) => Promise<void>;
};

// Accept and reject are recorded. Modify and explore are recorded and sent to the agent.
export function DecisionBar({ candidate, busy, onDecide }: Props) {
  const t = useTranslations("Decision");
  const guided = useLevel().level === "guided";
  const [reason, setReason] = useState("");
  const last = candidate.decisions.at(-1);

  async function decide(kind: DecisionKind) {
    await onDecide(kind, reason.trim());
    setReason("");
  }

  return (
    <div className="rounded-md border border-line bg-background p-3">
      <label className="text-sm font-medium" htmlFor={`reason-${candidate.candidate_id}`}>
        {t("title", { id: candidate.candidate_id })}
      </label>
      <textarea
        id={`reason-${candidate.candidate_id}`}
        className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
        rows={2}
        maxLength={2000}
        placeholder={guided ? t("placeholderGuided") : t("placeholder")}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      <div className="mt-2 flex flex-wrap gap-2">
        {BUTTONS.map((b) => (
          <button
            key={b.kind}
            type="button"
            disabled={busy || ((b.kind === "modify" || b.kind === "explore") && !reason.trim())}
            onClick={() => void decide(b.kind)}
            title={t(`${b.kind}Hint`)}
            className={`rounded-md border px-3 py-1 text-sm font-medium disabled:opacity-40 ${b.className}`}
          >
            {b.icon} {t(b.kind)}
          </button>
        ))}
      </div>
      <p className="mt-1 text-xs text-muted">{guided ? t("hintGuided") : t("hint")}</p>
      {last && (
        <p className="mt-1 text-xs">
          {t("last", { decision: t(last.decision) })}
          {last.reason && <span className="text-muted"> — “{last.reason}”</span>}
        </p>
      )}
    </div>
  );
}
