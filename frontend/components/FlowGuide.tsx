"use client";

import { useTranslations } from "next-intl";
import { useLevel } from "@/components/Level";

export type StepId = "goal" | "host" | "candidate" | "evidence";
export const STEPS: StepId[] = ["goal", "host", "candidate", "evidence"];
export type ExampleStage = "goal" | "host" | "candidate" | "done";
export type ExampleState = { stage: ExampleStage | null; error: string | null };

type Props = {
  done: Record<StepId, boolean>;
  hostLabel: string;
  candidateId: string | null;
  example: ExampleState;
  onJump: (step: StepId) => void;
  onExample: () => void;
};

// The four steps of the spec's workflow, with what to do next. Steps stay clickable in any order.
export function FlowGuide({ done, hostLabel, candidateId, example, onJump, onExample }: Props) {
  const t = useTranslations("Guide");
  const guided = useLevel().level === "guided";
  const next = STEPS.find((s) => !done[s]) ?? null;
  const running = example.stage !== null && example.stage !== "done";

  let message;
  if (example.error) {
    message = <span className="text-danger">{t("exampleError", { error: example.error })}</span>;
  } else if (running) {
    message = <span>{t(`exampleStage.${example.stage}`)}</span>;
  } else if (next) {
    message = (
      <span>
        <span className="font-medium text-foreground">{t("next")}</span> {t(guided ? `hintGuided.${next}` : `hint.${next}`, { host: hostLabel, id: candidateId ?? "" })}
      </span>
    );
  } else {
    message = <span>{t("allDone")}</span>;
  }

  return (
    <nav aria-label={t("label")} className="glass z-20 rounded-lg px-3 py-2.5 shadow-sm md:sticky md:top-0">
      <div className="flex flex-wrap items-center gap-2">
        <ol className="flex flex-1 flex-wrap items-center gap-1 text-sm">
          {STEPS.map((step, i) => {
            const state = done[step] ? "done" : step === next ? "current" : "todo";
            return (
              <li key={step} className="flex items-center gap-1">
                {i > 0 && <span aria-hidden className={`hidden h-px w-5 sm:block ${state === "todo" ? "bg-line-strong" : "bg-accent"}`} />}
                <button
                  type="button"
                  onClick={() => onJump(step)}
                  aria-current={state === "current" ? "step" : undefined}
                  className={`flex items-center gap-1.5 rounded-full py-1 pl-1 pr-3 ${state === "current" ? "bg-accent text-on-accent" : "hover:bg-surface-2"}`}
                >
                  <span
                    aria-hidden
                    className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${
                      state === "current" ? "bg-on-accent text-accent" : state === "done" ? "bg-accent-soft text-accent-text" : "border border-line-strong text-muted"
                    }`}
                  >
                    {state === "done" ? "✓" : i + 1}
                  </span>
                  <span className={state === "todo" ? "text-muted" : state === "current" ? "font-medium" : undefined}>{t(guided ? `stepGuided.${step}` : `step.${step}`)}</span>
                  <span className="sr-only">{t(`state.${state}`)}</span>
                </button>
              </li>
            );
          })}
        </ol>
        {!guided && (
          <button type="button" onClick={onExample} disabled={running} className="btn btn-outline btn-sm w-full sm:w-auto">
            {running ? t("exampleRunning") : t("example")}
          </button>
        )}
      </div>
      <p className="mt-1.5 px-1 text-sm text-muted" aria-live="polite">{message}</p>
    </nav>
  );
}

/** The question the AR example asks, shown above the evidence it points to. */
export function ExampleCallout({ onDismiss }: { onDismiss: () => void }) {
  const t = useTranslations("Guide");
  const te = useTranslations("Evidence");
  const guided = useLevel().level === "guided";
  return (
    <div className="lit mb-4 flex items-start gap-3 rounded-lg border border-accent bg-accent-soft p-4 text-sm">
      <p className="flex-1">
        <span className="font-semibold">{t("exampleTitle")}</span>{" "}
        {guided
          ? t("exampleStoryGuided")
          : t("exampleStory", { landscape: te("tabLandscape"), score: te("tabScore"), spatial: te("tabSpatial") })}
      </p>
      <button type="button" onClick={onDismiss} className="btn btn-ghost btn-sm">
        {t("dismiss")}
      </button>
    </div>
  );
}
