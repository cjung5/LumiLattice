"use client";

import { useTranslations } from "next-intl";
import { useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { AssessmentPanel } from "@/components/AssessmentPanel";
import { CritiquePanel } from "@/components/CritiquePanel";
import { CrystalViewer, type ViewerHandle } from "@/components/CrystalViewer";
import { DecisionBar } from "@/components/DecisionBar";
import { PropertyValueView } from "@/components/EvidenceTag";
import { ExperimentPanel } from "@/components/ExperimentPanel";
import { Advanced, useLevel } from "@/components/Level";
import { PlainResult } from "@/components/PlainResult";
import { NoveltyPanel } from "@/components/NoveltyPanel";
import { PublishControl } from "@/components/PublishControl";
import { RelaxationPanel } from "@/components/RelaxationPanel";
import { Leaderboard, ScorePanel } from "@/components/ScorePanel";
import { Term } from "@/components/Term";
import {
  createCandidate,
  downloadExport,
  type Arrangement,
  type Candidate,
  type DecisionKind,
  type ExportKind,
  type Goal,
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

// Sent to the research agent in English; it replies in the UI language.
const suggestPrompt = (host: string) =>
  `Suggest one atom swap for ${host} that moves it toward my goal. Make the candidate, score it, and say why you chose that element.`;

type Props = {
  /** Null when a candidate is opened from a link or the registry without a host. */
  host: HostRef | null;
  hostLabel: string;
  hostElements: string[];
  history: Candidate[];
  current: Candidate | null;
  /** Scored in the exported JSON record. */
  goal: Goal;
  agentBusy: boolean;
  onCandidate: (candidate: Candidate) => void;
  /** Sends a message to the research agent (e.g. a change the critique suggests). */
  onAskAgent?: (message: string, shown?: string) => void;
  onSeeEvidence?: () => void;
  hostFormula?: string | null;
  /** Shown above the result (the question the example asks). */
  notice?: ReactNode;
  onSelect: (candidate: Candidate) => void;
  onDecide: (kind: DecisionKind, reason: string) => Promise<void>;
};

export function CandidatePanel({
  host,
  hostLabel,
  hostElements,
  history,
  current,
  goal,
  agentBusy,
  onCandidate,
  onAskAgent,
  onSeeEvidence,
  hostFormula = null,
  notice,
  onSelect,
  onDecide,
}: Props) {
  const t = useTranslations("Candidate");
  const guided = useLevel().level === "guided";
  const [rows, setRows] = useState<Substitution[]>([
    { element_from: hostElements[0] ?? "", element_to: "", fraction: 1 / 2 },
  ]);
  const [arrangement, setArrangement] = useState<Arrangement>("spread");
  const [selectedCheck, setSelectedCheck] = useState<string | null>(null);
  const [showRelaxed, setShowRelaxed] = useState(false);
  const [copied, setCopied] = useState(false);
  const [exporting, setExporting] = useState<ExportKind | null>(null);
  const viewer = useRef<ViewerHandle>(null);
  const [exportError, setExportError] = useState<string | null>(null);
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
  // CHGNet keeps the site order, so indices and highlights apply to both geometries.
  const relaxed = showRelaxed && current?.relaxation ? current.relaxation : null;
  const assessment = relaxed?.assessment ?? current?.assessment ?? null;
  const highlight = useMemo(
    () => assessment?.checks.find((c) => c.id === selectedCheck)?.atom_indices ?? [],
    [assessment, selectedCheck],
  );

  async function copyLink() {
    if (!current) return;
    const url = new URL(window.location.href);
    url.search = new URLSearchParams({ candidate: current.candidate_id }).toString();
    await navigator.clipboard.writeText(url.toString());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function exportFile(kind: ExportKind) {
    if (!current) return;
    setExporting(kind);
    setExportError(null);
    try {
      await downloadExport(current.candidate_id, kind, goal);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : String(err));
    } finally {
      setExporting(null);
    }
  }

  function updateRow(index: number, patch: Partial<Substitution>) {
    setRows((old) => old.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  async function generate(from: HostRef) {
    setBusy(true);
    setError(null);
    try {
      const candidate = await createCandidate(
        from,
        rows.map((r) => ({
          ...r,
          element_from: r.element_from || elementOptions[0] || "",
          element_to: r.element_to.trim(),
        })),
        arrangement,
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
    if (host) void generate(host);
  }

  const canSubmit =
    !busy && rows.every((r) => (r.element_from || elementOptions[0]) && r.element_to.trim());

  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      <h2 className="font-semibold">
        {guided ? (
          <>{t("titleGuided.before")} <Term id="swap">{t("titleGuided.term")}</Term> {t("titleGuided.after")}</>
        ) : (
          t("title")
        )}
      </h2>
      <p className="mb-3 text-sm text-muted">{host ? (guided ? t("hintGuided", { host: hostLabel }) : t("hint", { host: hostLabel })) : t("noHost")}</p>

      <form onSubmit={onSubmit} className="space-y-2">
        {rows.map((row, index) => (
          <div key={index} className="flex flex-wrap items-center gap-2 text-sm">
            <select
              aria-label={t("from")}
              className="rounded-md border border-line bg-background px-2 py-1.5"
              value={row.element_from || elementOptions[0] || ""}
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
            <span className="text-muted">
              {t("ofSites", { element: row.element_from || elementOptions[0] || "" })}
            </span>
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
        {!guided && <div className="flex flex-wrap items-center gap-2 text-sm">
          <label className="flex items-center gap-2">
            <span>{t("arrangement")}</span>
            <select
              className="rounded-md border border-line bg-background px-2 py-1.5"
              value={arrangement}
              onChange={(e) => setArrangement(e.target.value as Arrangement)}
            >
              {(["spread", "lowest_ewald"] as const).map((a) => (
                <option key={a} value={a}>
                  {t(`arrangementOption.${a}`)}
                </option>
              ))}
            </select>
          </label>
          {arrangement === "lowest_ewald" && <span className="text-xs text-muted">{t("arrangementHint")}</span>}
        </div>}
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
            disabled={!canSubmit || !host}
            className="rounded-md bg-accent px-4 py-1.5 font-medium text-white disabled:opacity-50"
          >
            {busy ? t("generating") : guided ? t("generateGuided") : t("generateFromHost")}
          </button>
          {guided && host && onAskAgent && (
            <button
              type="button"
              disabled={agentBusy}
              onClick={() => onAskAgent(suggestPrompt(hostLabel), t("suggest"))}
              className="rounded-md border border-accent px-4 py-1.5 font-medium text-accent disabled:opacity-50"
            >
              {t("suggest")}
            </button>
          )}
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
          <div id="step-result" className="scroll-mt-4 space-y-3 md:scroll-mt-28">
            {notice}
            {guided && (
              <PlainResult candidate={current} goal={goal} hostFormula={hostFormula} onAskAgent={onAskAgent} onSeeEvidence={onSeeEvidence} />
            )}
          </div>
          <ScorePanel candidate={current} goal={goal} onAskAgent={onAskAgent} />
          <NoveltyPanel key={`novelty-${current.candidate_id}`} candidate={current} />
          {history.length > 1 && <Leaderboard candidates={history} current={current.candidate_id} goal={goal} onSelect={onSelect} />}
          <h3 className="font-medium">
            {current.candidate_id}: {current.formula}
            <span className="ml-2 text-xs font-normal text-muted">
              {t("lineage", {
                parent: current.parent_id ?? current.transformation.host.reference ?? "",
                supercell: current.transformation.supercell.join("×"),
              })}
            </span>
            <button type="button" onClick={() => void copyLink()} className="ml-2 text-xs font-normal text-accent underline">
              {copied ? t("linkCopied") : t("copyLink")}
            </button>
          </h3>
          <Advanced label={t("moreTools")}>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-muted">{t("export")}</span>
            {(["cif", ...(current.relaxation ? ["cif-relaxed" as const] : []), "record"] as ExportKind[]).map((kind) => (
              <button
                key={kind}
                type="button"
                disabled={exporting !== null}
                onClick={() => void exportFile(kind)}
                className="rounded-md border border-line px-2 py-1 disabled:opacity-50"
              >
                {exporting === kind ? t("exporting") : t(`exportKind.${kind}`)}
              </button>
            ))}
            <span className="text-muted">{t("exportNote")}</span>
            {exportError && <span className="text-danger">{exportError}</span>}
          </div>
          <RelaxationPanel
            key={`relax-${current.candidate_id}`}
            candidate={current}
            showRelaxed={showRelaxed}
            onShowRelaxed={setShowRelaxed}
            onChange={onCandidate}
          />
          <PublishControl key={`pub-${current.candidate_id}`} candidate={current} onChange={onCandidate} />
          <ExperimentPanel key={`exp-${current.candidate_id}`} candidate={current} onChange={onCandidate} />
          </Advanced>
          <div className={guided ? "" : "grid gap-4 md:grid-cols-[3fr_2fr]"}>
            <div>
              <CrystalViewer
                ref={viewer}
                cif={(relaxed?.structure ?? current.structure).cif}
                emphasis={emphasis}
                highlight={highlight}
                species={species}
              />
              <p className="mt-1 text-xs text-muted">{t("viewerLegend")}</p>
            </div>
            {!guided && (
              <AssessmentPanel
                assessment={assessment ?? current.assessment}
                selectedCheck={selectedCheck}
                onSelectCheck={setSelectedCheck}
              />
            )}
          </div>
          {guided && (
            <Advanced label={t("checkDetails")}>
              <AssessmentPanel
                assessment={assessment ?? current.assessment}
                selectedCheck={selectedCheck}
                onSelectCheck={setSelectedCheck}
              />
            </Advanced>
          )}
          {!guided && current.optical_estimate && (
            <div className="rounded-md border border-line p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{t("nEstimate")}</span>
                <PropertyValueView pv={current.optical_estimate.estimate} />
              </div>
              <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs">
                {current.optical_estimate.end_members.map((m) => (
                  <li key={m.formula} className="flex items-center gap-1">
                    <span>{m.formula}:</span>
                    <PropertyValueView pv={m.n} />
                  </li>
                ))}
              </ul>
              {current.optical_estimate.estimate.conditions && (
                <p className="mt-1 text-xs text-muted">{current.optical_estimate.estimate.conditions}</p>
              )}
            </div>
          )}
          {!guided && <p className="text-xs text-muted">{current.transformation.site_selection}</p>}
          <CritiquePanel
            key={`critique-${current.candidate_id}`}
            candidate={current}
            goal={goal}
            geometry={relaxed ? "relaxed" : "unrelaxed"}
            capture={() => viewer.current?.capture() ?? Promise.resolve({ views: [], legend: {} })}
            onChange={onCandidate}
            onAskAgent={onAskAgent}
          />
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
                      setShowRelaxed(false);
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
