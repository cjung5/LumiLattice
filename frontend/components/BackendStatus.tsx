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

  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      <h2 className="mb-2 font-semibold">{t("title")}</h2>
      {state.kind === "checking" && <p className="text-muted">{t("checking")}</p>}
      {state.kind === "offline" && (
        <p className="text-danger">{t("offline", { url: API_BASE_URL })}</p>
      )}
      {state.kind === "online" && (
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
          <li className={state.health.openalex_api_key_configured ? "" : "text-warning"}>
            {state.health.openalex_api_key_configured
              ? `✓ ${t("openAlexConfigured")}`
              : `! ${t("openAlexMissing")}`}
          </li>
        </ul>
      )}
    </section>
  );
}
