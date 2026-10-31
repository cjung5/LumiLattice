"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { getNovelty, type Candidate, type Novelty, type NoveltyLevel } from "@/lib/api";

const LEVELS: NoveltyLevel[] = ["known", "computed", "related", "unreported"];
const CHECK_ICON = { found: "✓", not_found: "–", unavailable: "!" } as const;

export function NoveltyPanel({ candidate }: { candidate: Candidate }) {
  const t = useTranslations("NoveltyCheck");
  const [result, setResult] = useState<Novelty | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);

  const run = useCallback(() => {
    setBusy(true);
    setError(null);
    return getNovelty(candidate.candidate_id)
      .then(setResult)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setBusy(false));
  }, [candidate.candidate_id]);

  useEffect(() => {
    void run();
  }, [run]);

  return (
    <section className="space-y-3 rounded-md border border-line p-4 text-sm" aria-label={t("title")}>
      <div>
        <h3 className="font-semibold">{t("title")}</h3>
        <p className="mt-1 text-xs text-muted">{t("hint")}</p>
      </div>
      {busy && <p className="text-muted" aria-live="polite">{t("checking")}</p>}
      {error && <p className="text-danger">{error}</p>}
      {result && !busy && (
        <>
          <ol className="grid gap-1 sm:grid-cols-4">
            {LEVELS.map((level) => {
              const active = level === result.level;
              return (
                <li
                  key={level}
                  aria-current={active ? "step" : undefined}
                  className={`rounded border px-2 py-1 text-xs ${active ? "border-accent font-semibold" : "border-line text-muted"}`}
                >
                  {active && <span aria-hidden>● </span>}
                  {t(`level.${level}.name`)}
                </li>
              );
            })}
          </ol>
          <p>{t(`level.${result.level}.meaning`)}</p>
          <p>
            <span className="font-medium">{t("next")}</span> {t(`level.${result.level}.next`)}
          </p>

          {!result.complete && (
            <p className="rounded border border-warning p-2 text-xs">
              <span aria-hidden>! </span>
              {t("incomplete")}{" "}
              <button type="button" onClick={() => void run()} className="text-accent underline">
                {t("retry")}
              </button>
            </p>
          )}

          {result.nearest.length > 0 && (
            <div>
              <h4 className="font-medium">{t("nearestTitle")}</h4>
              <ul className="mt-1 text-xs">
                {result.nearest.map((n) => (
                  <li key={n.formula}>
                    {n.formula}: {t("atomsDiffer", { percent: Math.round(n.atoms_differ * 100) })}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <ul className="space-y-2 text-xs">
            {result.checks.map((check) => (
              <li key={check.id}>
                <div className="flex gap-2">
                  <span aria-hidden className="w-3 shrink-0 text-center font-semibold">{CHECK_ICON[check.status]}</span>
                  <span>
                    <span className="font-medium">{t(`check.${check.id}`)}</span>: {t(`status.${check.status}`)}
                  </span>
                </div>
                {check.items.length > 0 && (
                  <ul className="ml-5 mt-0.5 list-disc pl-3">
                    {check.items.map((item) => (
                      <li key={item.label}>
                        {item.url ? (
                          <a href={item.url} target="_blank" rel="noreferrer" className="text-accent underline">
                            {item.label}
                          </a>
                        ) : (
                          item.label
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted">{result.caveat}</p>
        </>
      )}
    </section>
  );
}
