"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { AgentPanel, type AgentTurn } from "@/components/AgentPanel";
import { CandidatePanel } from "@/components/CandidatePanel";
import { EvidencePanel } from "@/components/EvidencePanel";
import { GoalPanel } from "@/components/GoalPanel";
import { HostSelector } from "@/components/HostSelector";
import { LiteraturePanel } from "@/components/LiteraturePanel";
import { RegistryPanel } from "@/components/RegistryPanel";
import { StructurePanel } from "@/components/StructurePanel";
import {
  addDecision,
  assessHost,
  getCandidate,
  getStructure,
  runAgent,
  type AgentContext,
  type Candidate,
  type DecisionKind,
  type Goal,
  type HostRef,
  type MaterialRecord,
  type StructuralAssessment,
  type StructurePayload,
} from "@/lib/api";

// Sent to the model; the agent replies in the UI language.
const DECISION_PROMPTS: Partial<Record<DecisionKind, (id: string) => string>> = {
  modify: (id) => `Revise ${id} following my feedback, then compare the checks with ${id}.`,
  explore: (id) =>
    `Suggest and test up to 2 alternative candidates to ${id} that follow my feedback. Compare them.`,
};

export function Workspace() {
  const locale = useLocale();
  const t = useTranslations("Decision");
  const [record, setRecord] = useState<MaterialRecord | null>(null);
  const [structure, setStructure] = useState<StructurePayload | null>(null);
  const [hostAssessment, setHostAssessment] = useState<StructuralAssessment | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [goal, setGoal] = useState<Goal>({ target_n: 2.2, min_band_gap: 3.0, forbidden_elements: [] });
  const [history, setHistory] = useState<Candidate[]>([]);
  const [current, setCurrent] = useState<Candidate | null>(null);
  const [registryVersion, setRegistryVersion] = useState(0);

  const [turns, setTurns] = useState<AgentTurn[]>([]);
  const [responseId, setResponseId] = useState<string | null>(null);
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);

  async function loadAssessment(host: HostRef) {
    setHostAssessment(null);
    try {
      setHostAssessment(await assessHost(host));
    } catch {
      // The baseline assessment is optional; the structure stays usable without it.
    }
  }

  async function selectMaterial(selected: MaterialRecord) {
    setRecord(selected);
    setLoading(true);
    setError(null);
    try {
      setStructure(await getStructure(selected.material_id));
      void loadAssessment({ material_id: selected.material_id });
    } catch (err) {
      setStructure(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  function showUploadedStructure(uploaded: StructurePayload) {
    setRecord(null);
    setError(null);
    setStructure(uploaded);
    void loadAssessment({ cif: uploaded.cif, filename: uploaded.provenance.reference ?? "upload.cif" });
  }

  function upsertCandidate(candidate: Candidate) {
    setRegistryVersion((v) => v + 1);
    setHistory((old) =>
      old.some((c) => c.candidate_id === candidate.candidate_id)
        ? old.map((c) => (c.candidate_id === candidate.candidate_id ? candidate : c))
        : [...old, candidate],
    );
  }

  function showCandidate(candidate: Candidate) {
    upsertCandidate(candidate);
    setCurrent(candidate);
  }

  async function openCandidate(candidateId: string) {
    const known = history.find((c) => c.candidate_id === candidateId);
    showCandidate(known ?? (await getCandidate(candidateId)));
  }

  // Share links: ?candidate=LL-0003 opens that candidate (it stays private to this backend).
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("candidate");
    if (!id) return;
    getCandidate(id)
      .then((candidate) => {
        setHistory((old) => (old.some((c) => c.candidate_id === id) ? old : [...old, candidate]));
        setCurrent(candidate);
      })
      .catch(() => setError(`Candidate ${id} was not found on this server.`));
  }, []);

  const formula = structure?.formula ?? record?.formula ?? null;
  const host: HostRef | null = record
    ? { material_id: record.material_id }
    : structure
      ? { cif: structure.cif, filename: structure.provenance.reference ?? "upload.cif" }
      : null;
  const hostLabel = record
    ? `${record.formula} (${record.material_id})`
    : structure
      ? `${structure.formula} (${structure.provenance.reference ?? structure.provenance.source})`
      : "";

  async function askAgent(message: string, shown: string, extra: Partial<AgentContext> = {}) {
    setTurns((old) => [...old, { role: "user", text: shown }]);
    setAgentBusy(true);
    setAgentError(null);
    const context: AgentContext = {
      host_material_id: record?.material_id,
      host_label: hostLabel || undefined,
      current_candidate_id: current?.candidate_id,
      goal,
      ...extra,
    };
    try {
      const result = await runAgent(message, locale, responseId, context);
      setResponseId(result.response_id);
      setTurns((old) => [
        ...old,
        {
          role: "assistant",
          text: result.output_text,
          toolCalls: result.tool_calls,
          candidateIds: result.candidate_ids,
        },
      ]);
      // Agent-made candidates join the same history as hand-made ones.
      const created = await Promise.all(result.candidate_ids.map((id) => getCandidate(id)));
      created.forEach(upsertCandidate);
      if (created.length) setCurrent(created[created.length - 1]);
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : String(err));
    } finally {
      setAgentBusy(false);
    }
  }

  async function decide(kind: DecisionKind, reason: string) {
    if (!current) return;
    const id = current.candidate_id;
    try {
      const updated = await addDecision(id, kind, reason);
      showCandidate(updated);
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : String(err));
      return;
    }
    const prompt = DECISION_PROMPTS[kind];
    if (prompt) {
      const shown = `${t(kind)} ${id}: ${reason}`;
      await askAgent(prompt(id), shown, { current_candidate_id: id, decision: kind, feedback: reason });
    }
  }

  return (
    <>
      <GoalPanel goal={goal} onChange={setGoal} />
      <HostSelector
        selectedId={record?.material_id ?? null}
        onSelectMaterial={selectMaterial}
        onUploadedStructure={showUploadedStructure}
      />
      <StructurePanel
        structure={structure}
        record={record}
        assessment={hostAssessment}
        loading={loading}
        error={error}
      />
      {((host && structure && !loading) || current) && (
        <CandidatePanel
          key={record?.material_id ?? structure?.provenance.reference ?? "no-host"}
          host={structure && !loading ? host : null}
          hostLabel={hostLabel}
          hostElements={structure ? [...new Set(structure.sites.map((s) => s.species))] : []}
          history={history}
          current={current}
          agentBusy={agentBusy}
          onCandidate={showCandidate}
          onSelect={setCurrent}
          onDecide={decide}
        />
      )}
      {(structure || current) && (
        <EvidencePanel
          goal={goal}
          host={structure && !loading ? host : null}
          hostFormula={structure?.formula ?? null}
          hostAssessment={hostAssessment}
          candidate={current}
        />
      )}
      <AgentPanel
        turns={turns}
        busy={agentBusy}
        error={agentError}
        onSend={(message) => void askAgent(message, message)}
        onReset={() => {
          setTurns([]);
          setResponseId(null);
          setAgentError(null);
        }}
        onOpenCandidate={(id) => void openCandidate(id)}
      />
      <RegistryPanel version={registryVersion} onOpen={showCandidate} />
      <LiteraturePanel key={formula ?? "none"} formula={formula} />
    </>
  );
}
