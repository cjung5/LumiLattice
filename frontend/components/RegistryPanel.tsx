"use client";

import { useTranslations } from "next-intl";
import { useAuth } from "@/components/Auth";
import { useBackendText } from "@/lib/backendText";
import { useEffect, useState } from "react";
import { formatValue } from "@/components/EvidenceTag";
import { listCandidates, type Candidate } from "@/lib/api";

const MAX_COMPARE = 3;
const CHECK_ICON: Record<string, string> = { pass: "✓", warn: "!", fail: "✗", info: "i", not_applicable: "–" };

type Props = {
  /** Changes when candidates are created or updated elsewhere, so the list reloads. */
  version: number;
  onOpen: (candidate: Candidate) => void;
};

// P1 stage 2: every candidate in one table, with filters and a side-by-side comparison.
export function RegistryPanel({ version, onOpen }: Props) {
  const t = useTranslations("Registry");
  const { mode } = useAuth();
  const tb = useBackendText();
  const [items, setItems] = useState<Candidate[]>([]);
  const [filter, setFilter] = useState<"all" | "plausible" | "published" | "decided" | "mine">("all");
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    listCandidates()
      .then((list) => active && setItems(list))
      .catch((err) => active && setError(err instanceof Error ? err.message : String(err)));
    return () => {
      active = false;
    };
  }, [version]);

  const shown = items.filter((c) =>
    filter === "plausible"
      ? c.assessment.status === "Structurally Plausible"
      : filter === "published"
        ? c.visibility === "published"
        : filter === "decided"
          ? c.decisions.length > 0
          : filter === "mine"
            ? c.mine
            : true,
  );
  const compared = items.filter((c) => selected.includes(c.candidate_id));
  const checkIds = [...new Set(compared.flatMap((c) => c.assessment.checks.map((k) => k.id)))];

  function toggle(id: string) {
    setSelected((old) =>
      old.includes(id) ? old.filter((x) => x !== id) : old.length < MAX_COMPARE ? [...old, id] : old,
    );
  }

  return (
    <section className="card">
      <h2 className="text-lg font-semibold tracking-tight">{t("title")}</h2>
      <p className="mb-2 text-sm text-muted">{t(mode === "private" ? "hintPrivate" : "hint", { max: MAX_COMPARE })}</p>
      <div className="segmented mb-3 text-xs">
        {(["all", "plausible", "published", "decided", ...(mode === "private" ? (["mine"] as const) : [])] as const).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className="segment" aria-pressed={filter === f}
          >
            {t(`filter.${f}`)}
          </button>
        ))}
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
      {shown.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-muted">
              <tr>
                <th className="py-1 pr-2 font-normal">{t("compare")}</th>
                <th className="py-1 pr-2 font-normal">ID</th>
                <th className="py-1 pr-2 font-normal">{t("formula")}</th>
                <th className="py-1 pr-2 font-normal">{t("origin")}</th>
                <th className="py-1 pr-2 font-normal">{t("status")}</th>
                <th className="py-1 pr-2 font-normal">n</th>
                <th className="py-1 font-normal">{t("decision")}</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((c) => (
                <tr key={c.candidate_id} className="border-t border-line">
                  <td className="py-1 pr-2">
                    <input
                      type="checkbox"
                      aria-label={t("compare")}
                      checked={selected.includes(c.candidate_id)}
                      onChange={() => toggle(c.candidate_id)}
                    />
                  </td>
                  <td className="py-1 pr-2">
                    <button type="button" className="font-mono text-accent-text underline" onClick={() => onOpen(c)}>
                      {c.candidate_id}
                    </button>
                    {c.visibility === "published" && <span className="ml-1">🌐</span>}
                    {c.mine && c.visibility === "private" && <span className="ml-1">🔒</span>}
                  </td>
                  <td className="py-1 pr-2">{c.formula}</td>
                  <td className="py-1 pr-2 text-muted">{c.parent_id ?? c.transformation.host.reference}</td>
                  <td className="py-1 pr-2">{tb(c.assessment.status)}</td>
                  <td className="py-1 pr-2 tabular-nums">
                    {c.optical_estimate ? formatValue(c.optical_estimate.estimate) : "—"}
                  </td>
                  <td className="py-1">{c.decisions.at(-1)?.decision ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {compared.length > 1 && (
        <div className="mt-4 overflow-x-auto">
          <h3 className="mb-1 text-sm font-medium">{t("comparison")}</h3>
          <table className="w-full text-left text-xs">
            <thead>
              <tr>
                <th className="py-1 pr-2 font-normal text-muted" />
                {compared.map((c) => (
                  <th key={c.candidate_id} className="py-1 pr-2 font-medium">
                    {c.candidate_id} {c.formula}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-line">
                <td className="py-1 pr-2 text-muted">{t("substitutions")}</td>
                {compared.map((c) => (
                  <td key={c.candidate_id} className="py-1 pr-2">
                    {c.transformation.lineage
                      .map((s) => `${s.element_from}→${s.element_to} ${+(s.fraction * 100).toFixed(1)}%`)
                      .join(", ")}
                  </td>
                ))}
              </tr>
              <tr className="border-t border-line">
                <td className="py-1 pr-2 text-muted">{t("status")}</td>
                {compared.map((c) => (
                  <td key={c.candidate_id} className="py-1 pr-2">
                    {tb(c.assessment.status)}
                  </td>
                ))}
              </tr>
              {checkIds.map((id) => (
                <tr key={id} className="border-t border-line">
                  <td className="py-1 pr-2 text-muted">
                    {compared.flatMap((c) => c.assessment.checks).find((k) => k.id === id)?.name}
                  </td>
                  {compared.map((c) => {
                    const check = c.assessment.checks.find((k) => k.id === id);
                    return (
                      <td key={c.candidate_id} className="py-1 pr-2" title={check?.message ? tb(check.message) : undefined}>
                        {check ? CHECK_ICON[check.status] : "—"}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr className="border-t border-line">
                <td className="py-1 pr-2 text-muted">{t("nRange")}</td>
                {compared.map((c) => (
                  <td key={c.candidate_id} className="py-1 pr-2 tabular-nums">
                    {c.optical_estimate ? formatValue(c.optical_estimate.estimate) : "—"}
                  </td>
                ))}
              </tr>
              <tr className="border-t border-line">
                <td className="py-1 pr-2 text-muted">{t("relaxedVolume")}</td>
                {compared.map((c) => (
                  <td key={c.candidate_id} className="py-1 pr-2 tabular-nums">
                    {c.relaxation ? `${(c.relaxation.volume_change * 100).toFixed(1)}%` : "—"}
                  </td>
                ))}
              </tr>
              <tr className="border-t border-line">
                <td className="py-1 pr-2 text-muted">{t("experiments")}</td>
                {compared.map((c) => (
                  <td key={c.candidate_id} className="py-1 pr-2">
                    {c.experiments.length || "—"}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
