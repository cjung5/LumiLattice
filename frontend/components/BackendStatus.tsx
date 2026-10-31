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

  if (state.kind === "checking") return <p className="text-sm text-muted">{t("checking")}</p>;
  if (state.kind === "offline") return <p className="text-sm text-danger">{t("offline", { url: API_BASE_URL })}</p>;

  // A researcher needs this only when a key is missing; the agent and search stop without one.
  const ready = state.health.model_api_key_configured && state.health.materials_project_configured;

  return (
    <details open={!ready} className="text-sm">
      <summary className="cursor-pointer text-muted">{t(ready ? "ready" : "notReady")}</summary>
      <div className="mt-2 rounded-lg border border-line bg-surface p-4">
        <ul className="space-y-1 text-sm">
          <li>✓ {t("online")}</li>
          <li>
            {t("model")}: <code>{state.health.model}</code>
          </li>
          <li className={state.health.model_api_key_configured ? "" : "text-danger"}>
            {state.health.model_api_key_configured
              ? `✓ ${t("keyConfigured")}`
              : `✗ ${t("keyMissing")}`}
          </li>
          <li className={state.health.materials_project_configured ? "" : "text-danger"}>
            {state.health.materials_project_configured
              ? `✓ ${t("mpConfigured")}`
              : `✗ ${t("mpMissing")}`}
          </li>
          <li className={state.health.candidate_store === "postgres" ? "" : "text-warning"}>
            {state.health.candidate_store === "postgres" ? `✓ ${t("storePostgres")}` : `! ${t("storeMemory")}`}
          </li>
          <li className={state.health.openalex_api_key_configured ? "" : "text-warning"}>
            {state.health.openalex_api_key_configured
              ? `✓ ${t("openAlexConfigured")}`
              : `! ${t("openAlexMissing")}`}
          </li>
        </ul>
      </div>
    </details>
  );
}
