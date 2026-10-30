"use client";

import { useTranslations } from "next-intl";
import { useMemo, useState, type FormEvent } from "react";
import { AssessmentPanel } from "@/components/AssessmentPanel";
import { CrystalViewer } from "@/components/CrystalViewer";
import { DecisionBar } from "@/components/DecisionBar";
import {
  createCandidate,
  type Candidate,
  type DecisionKind,
  type HostRef,
  type Substitution,
} from "@/lib/api";

const FRACTIONS: { label: string; value: number }[] = [
  { label: "100%", value: 1 },
  { label: "1/2", value: 1 / 2 },
  { label: "1/3", value: 1 / 3 },
  { label: "1/4", value: 1 / 4 },
  { label: "1/6", value: 1 / 6 },
  { label: "1/8", value: 1 / 8 },
];

type Props = {
  host: HostRef;
  hostLabel: string;
  hostElements: string[];
  history: Candidate[];
  current: Candidate | null;
  agentBusy: boolean;
  onCandidate: (candidate: Candidate) => void;
  onSelect: (candidate: Candidate) => void;
  onDecide: (kind: DecisionKind, reason: string) => Promise<void>;
};

export function CandidatePanel({
  host,
  hostLabel,
  hostElements,
  history,
  current,
  agentBusy,
  onCandidate,
  onSelect,
  onDecide,
}: Props) {
  const t = useTranslations("Candidate");
  const [rows, setRows] = useState<Substitution[]>([
    { element_from: hostElements[0] ?? "", element_to: "", fraction: 1 / 2 },
  ]);
  const [selectedCheck, setSelectedCheck] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const elementOptions = useMemo(
    () => (current ? [...new Set(current.structure.sites.map((s) => s.species))] : hostElements),
    [current, hostElements],
  );
  const species = useMemo(() => current?.structure.sites.map((s) => s.species) ?? [], [current]);
  const emphasis = useMemo(
    () => (current ? Object.values(current.transformation.substituted_sites).flat() : []),
    [current],
  );
  const highlight = useMemo(
    () => current?.assessment.checks.find((c) => c.id === selectedCheck)?.atom_indices ?? [],
    [current, selectedCheck],
  );

  function updateRow(index: number, patch: Partial<Substitution>) {
    setRows((old) => old.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  async function generate(from: HostRef) {
    setBusy(true);
    setError(null);
    try {
      const candidate = await createCandidate(
        from,
        rows.map((r) => ({ ...r, element_to: r.element_to.trim() })),
      );
      onCandidate(candidate);
      setSelectedCheck(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void generate(host);
  }

  const canSubmit = !busy && rows.every((r) => r.element_from && r.element_to.trim());

  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      <h2 className="font-semibold">{t("title")}</h2>
      <p className="mb-3 text-sm text-muted">{t("hint", { host: hostLabel })}</p>

      <form onSubmit={onSubmit} className="space-y-2">
        {rows.map((row, index) => (
          <div key={index} className="flex flex-wrap items-center gap-2 text-sm">
            <select
              aria-label={t("from")}
              className="rounded-md border border-line bg-background px-2 py-1.5"
              value={row.element_from}
              onChange={(e) => updateRow(index, { element_from: e.target.value })}
            >
              {elementOptions.map((el) => (
                <option key={el} value={el}>
                  {el}
                </option>
              ))}
            </select>
            <span aria-hidden>→</span>
            <input
              aria-label={t("to")}
              className="w-20 rounded-md border border-line bg-background px-2 py-1.5"
              placeholder={t("toPlaceholder")}
              value={row.element_to}
              maxLength={3}
              onChange={(e) => updateRow(index, { element_to: e.target.value })}
            />
            <select
              aria-label={t("fraction")}
              className="rounded-md border border-line bg-background px-2 py-1.5"
              value={row.fraction}
              onChange={(e) => updateRow(index, { fraction: Number(e.target.value) })}
            >
              {FRACTIONS.map((f) => (
                <option key={f.label} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
            <span className="text-muted">{t("ofSites", { element: row.element_from })}</span>
            {rows.length > 1 && (
              <button
                type="button"
                className="text-muted underline"
                onClick={() => setRows((old) => old.filter((_, i) => i !== index))}
              >
                {t("remove")}
              </button>
            )}
          </div>
        ))}
        <div className="flex flex-wrap gap-2">
          {rows.length < 3 && (
            <button
              type="button"
              className="rounded-md border border-line px-3 py-1.5 text-sm"
              onClick={() =>
                setRows((old) => [
                  ...old,
                  { element_from: elementOptions[0] ?? "", element_to: "", fraction: 1 / 2 },
                ])
              }
            >
              {t("addRow")}
            </button>
          )}
          <button
            type="submit"
            disabled={!canSubmit}
            className="rounded-md bg-accent px-4 py-1.5 font-medium text-white disabled:opacity-50"
          >
            {busy ? t("generating") : t("generateFromHost")}
          </button>
          {current && (
            <button
              type="button"
              disabled={!canSubmit}
              onClick={() => void generate({ candidate_id: current.candidate_id })}
              className="rounded-md border border-accent px-4 py-1.5 font-medium text-accent disabled:opacity-50"
            >
              {t("reviseCurrent", { id: current.candidate_id })}
            </button>
          )}
        </div>
      </form>

      {error && <p className="mt-3 text-sm text-danger">{error}</p>}

      {current && (
        <div className="mt-4 space-y-3">
          <h3 className="font-medium">
            {current.candidate_id}: {current.formula}
            <span className="ml-2 text-xs font-normal text-muted">
              {t("lineage", {
                parent: current.parent_id ?? current.transformation.host.reference ?? "",
                supercell: current.transformation.supercell.join("×"),
              })}
            </span>
          </h3>
          <div className="grid gap-4 md:grid-cols-[3fr_2fr]">
            <div>
              <CrystalViewer
                cif={current.structure.cif}
                emphasis={emphasis}
                highlight={highlight}
                species={species}
              />
              <p className="mt-1 text-xs text-muted">{t("viewerLegend")}</p>
            </div>
            <AssessmentPanel
              assessment={current.assessment}
              selectedCheck={selectedCheck}
              onSelectCheck={setSelectedCheck}
            />
          </div>
          <p className="text-xs text-muted">{current.transformation.site_selection}</p>
          <DecisionBar
            key={current.candidate_id}
            candidate={current}
            busy={agentBusy}
            onDecide={onDecide}
          />
        </div>
      )}

      {history.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium">{t("history")}</h3>
          <ol className="mt-1 space-y-1 text-sm">
            {history.map((c) => {
              const last = c.decisions.at(-1);
              return (
                <li key={c.candidate_id}>
                  <button
                    type="button"
                    onClick={() => {
                      onSelect(c);
                      setSelectedCheck(null);
                    }}
                    className={`underline-offset-2 hover:underline ${
                      c.candidate_id === current?.candidate_id ? "font-semibold" : ""
                    }`}
                  >
                    {c.candidate_id} {c.formula}
                  </button>
                  <span className="text-muted">
                    {" "}
                    ← {c.parent_id ?? c.transformation.host.reference} ·{" "}
                    {c.transformation.substitutions
                      .map((s) => `${s.element_from}→${s.element_to} ${+(s.fraction * 100).toFixed(1)}%`)
                      .join(", ")}{" "}
                    · {c.assessment.status}
                  </span>
                  {last && (
                    <span className="ml-1 rounded border border-line px-1 text-xs">{last.decision}</span>
                  )}
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </section>
  );
}
