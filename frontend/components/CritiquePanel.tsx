"use client";

import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import type { CapturedViews } from "@/components/CrystalViewer";
import { useLevel } from "@/components/Level";
import { critiqueCandidate, type Candidate, type Critique, type Goal } from "@/lib/api";

type Props = {
  candidate: Candidate;
  goal: Goal;
  /** The geometry the viewer shows now; the captured views are of this cell. */
  geometry: "unrelaxed" | "relaxed";
  capture: () => Promise<CapturedViews>;
  onChange: (candidate: Candidate) => void;
  onAskAgent?: (message: string) => void;
};

// Verdicts and point kinds carry an icon and a label as well as a color.
const VERDICT: Record<Critique["verdict"], { icon: string; color: string }> = {
  promising: { icon: "✓", color: "var(--tag-exp)" },
  mixed: { icon: "~", color: "var(--warning)" },
  weak: { icon: "✕", color: "var(--danger)" },
  insufficient_evidence: { icon: "?", color: "var(--muted)" },
};
const KIND: Record<Critique["points"][number]["kind"], { icon: string; color: string }> = {
  strength: { icon: "✓", color: "var(--tag-exp)" },
  concern: { icon: "!", color: "var(--warning)" },
  open_question: { icon: "?", color: "var(--muted)" },
};

// Sent to the research agent in English; it replies in the UI language.
const testPrompt = (id: string, change: string, rationale: string) =>
  `Test this change suggested by the Muse Spark critique of ${id}: ${change} Reason: ${rationale} ` +
  `Make the candidate, then compare its checks and goal score with ${id}.`;

export function CritiquePanel({ candidate, goal, geometry, capture, onChange, onAskAgent }: Props) {
  const t = useTranslations("Critique");
  const locale = useLocale();
  const guided = useLevel().level === "guided";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const critiques = candidate.critiques ?? [];
  const latest = critiques.at(-1) ?? null;
  const older = critiques.slice(0, -1).reverse();

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const { views, legend } = await capture().catch(() => ({ views: [], legend: {} }));
      onChange(await critiqueCandidate(candidate.candidate_id, { goal, locale, geometry, views, legend, audience: guided ? "beginner" : "expert" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="subcard text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h4 className="font-medium">
            {t("title")}
            <span className="ml-2 rounded-full border border-line px-2 py-0.5 text-xs font-normal text-muted">{t("aiTag")}</span>
          </h4>
          <p className="mt-1 text-xs text-muted">{guided ? t("hintGuided") : t("hint")}</p>
        </div>
        <button
          type="button"
          onClick={() => void run()}
          disabled={busy}
          className="btn btn-primary btn-sm"
        >
          {busy ? t("running") : latest ? t("rerun") : t("run")}
        </button>
      </div>
      {busy && <p className="mt-2 text-xs text-muted" aria-live="polite">{t("runningLong", { id: candidate.candidate_id })}</p>}
      {error && <p className="mt-2 text-danger">{error}</p>}
      {latest && <CritiqueView critique={latest} candidateId={candidate.candidate_id} onAskAgent={onAskAgent} />}
      {older.length > 0 && (
        <details className="mt-3">
          <summary className="text-xs text-muted">{t("older", { count: older.length })}</summary>
          <div className="mt-2 space-y-4">
            {older.map((c) => (
              <CritiqueView key={c.created_at} critique={c} candidateId={candidate.candidate_id} />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function CritiqueView({
  critique,
  candidateId,
  onAskAgent,
}: {
  critique: Critique;
  candidateId: string;
  onAskAgent?: (message: string) => void;
}) {
  const t = useTranslations("Critique");
  const locale = useLocale();
  const guided = useLevel().level === "guided";
  const [sent, setSent] = useState<number | null>(null);
  const evidence = new Map(critique.evidence.map((e) => [e.id, e.text]));
  const verdict = VERDICT[critique.verdict];

  // The IDs let an expert trace each claim; the evidence list below stays open to everyone.
  const chips = (ids: string[]) =>
    guided ? null : ids.map((id) => (
      <span
        key={id}
        title={evidence.get(id)}
        className="ml-1 inline-block rounded border border-line px-1 font-mono text-xs text-muted"
      >
        {id}
      </span>
    ));

  return (
    <div className="mt-3 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-medium" style={{ borderColor: verdict.color }}>
          <span aria-hidden style={{ color: verdict.color }}>{verdict.icon}</span>
          {t(`verdict.${critique.verdict}`)}
        </span>
        <span className="text-xs text-muted">
          {t("meta", {
            model: critique.model,
            views: critique.views,
            geometry: t(`geometry.${critique.geometry}`),
            time: new Date(critique.created_at).toLocaleString(locale),
          })}
        </span>
      </div>
      {critique.views === 0 && <p className="text-xs text-muted">{t("noViews")}</p>}
      <p>{critique.summary}</p>

      <ul className="space-y-1.5">
        {critique.points.map((p, i) => (
          <li key={i} className="flex gap-2">
            <span aria-hidden className="w-4 shrink-0 text-center font-semibold" style={{ color: KIND[p.kind].color }}>
              {KIND[p.kind].icon}
            </span>
            <span>
              <span className="sr-only">{t(`kind.${p.kind}`)}: </span>
              {p.text}
              {p.basis !== "evidence" && (
                <span className="ml-1 rounded bg-foreground/5 px-1 text-xs text-muted">{t(`basis.${p.basis}`)}</span>
              )}
              {chips(p.evidence)}
            </span>
          </li>
        ))}
      </ul>

      {critique.suggestions.length > 0 && (
        <div>
          <h5 className="text-xs font-medium text-muted">{t("suggestions")}</h5>
          <ol className="mt-1 space-y-2">
            {critique.suggestions.map((s, i) => (
              <li key={i} className="rounded-lg border border-line p-3">
                <div className="font-medium">{s.change}</div>
                <div className="text-xs">
                  {s.rationale}
                  {chips(s.evidence)}
                </div>
                {onAskAgent && (
                  <button
                    type="button"
                    disabled={sent === i}
                    onClick={() => {
                      onAskAgent(testPrompt(candidateId, s.change, s.rationale));
                      setSent(i);
                    }}
                    className="mt-1 text-xs text-accent-text underline disabled:no-underline disabled:opacity-60"
                  >
                    {sent === i ? t("sent") : t("testThis")}
                  </button>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}

      {critique.questions.length > 0 && (
        <div>
          <h5 className="text-xs font-medium text-muted">{t("questions")}</h5>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {critique.questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ul>
        </div>
      )}

      {critique.warnings.length > 0 && (
        <div className="rounded-lg border border-warning p-3 text-xs">
          <div className="font-medium text-warning">{t("warnings")}</div>
          <ul className="mt-1 list-disc pl-5">
            {critique.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <details>
        <summary className="text-xs text-muted">{t("evidence", { count: critique.evidence.length })}</summary>
        <ul className="mt-1 space-y-0.5 text-xs">
          {critique.evidence.map((e) => (
            <li key={e.id}>
              <span className="font-mono text-muted">{e.id}</span> {e.text}
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
