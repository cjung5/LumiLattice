"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { API_BASE_URL, getHealth, type Health } from "@/lib/api";

type State =
  | { kind: "checking" }
  | { kind: "online"; health: Health }
  | { kind: "offline" };

export function BackendStatus() {
  const t = useTranslations("Status");
  const [state, setState] = useState<State>({ kind: "checking" });

  useEffect(() => {
    getHealth()
      .then((health) => setState({ kind: "online", health }))
      .catch(() => setState({ kind: "offline" }));
  }, []);

  // A researcher needs this only when something is missing; the agent and search stop without a key.
  const ready = state.kind === "online" && state.health.model_api_key_configured && state.health.materials_project_configured;
  const label = state.kind === "checking" ? t("checking") : state.kind === "offline" ? t("offline", { url: API_BASE_URL }) : t(ready ? "ready" : "notReady");
  const dot = state.kind === "checking" ? "bg-muted" : ready ? "bg-tag-exp" : "bg-danger";

  return (
    <details open={state.kind === "offline" || (state.kind === "online" && !ready)} className="relative text-sm">
      <summary title={label} aria-label={label} className="no-chevron btn btn-ghost btn-sm !px-2.5">
        <span aria-hidden className={`h-2.5 w-2.5 rounded-full ${dot}`} />
      </summary>
      <div className="glass absolute left-0 top-full z-30 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-lg p-4 shadow-lg sm:left-auto sm:right-0">
        <p className={state.kind === "offline" ? "text-danger" : "font-medium"}>{label}</p>
        {state.kind === "online" && (
          <ul className="mt-2 space-y-1 text-xs">
            <li>✓ {t("online")}</li>
            <li>
              {t("model")}: <code>{state.health.model}</code>
            </li>
            <li className={state.health.model_api_key_configured ? "" : "text-danger"}>
              {state.health.model_api_key_configured ? `✓ ${t("keyConfigured")}` : `✗ ${t("keyMissing")}`}
            </li>
            <li className={state.health.materials_project_configured ? "" : "text-danger"}>
              {state.health.materials_project_configured ? `✓ ${t("mpConfigured")}` : `✗ ${t("mpMissing")}`}
            </li>
            <li className={state.health.candidate_store === "postgres" ? "" : "text-warning"}>
              {state.health.candidate_store === "postgres" ? `✓ ${t("storePostgres")}` : `! ${t("storeMemory")}`}
            </li>
            <li className={state.health.openalex_api_key_configured ? "" : "text-warning"}>
              {state.health.openalex_api_key_configured ? `✓ ${t("openAlexConfigured")}` : `! ${t("openAlexMissing")}`}
            </li>
          </ul>
        )}
      </div>
    </details>
  );
}
