"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { AgentPanel, type AgentTurn } from "@/components/AgentPanel";
import { CandidatePanel } from "@/components/CandidatePanel";
import { EvidencePanel } from "@/components/EvidencePanel";
import { ExampleCallout, FlowGuide, type ExampleState, type StepId } from "@/components/FlowGuide";
import { AR_GOAL, GoalPanel } from "@/components/GoalPanel";
import { HostSelector } from "@/components/HostSelector";
import { Intro } from "@/components/Intro";
import { Advanced, useLevel } from "@/components/Level";
import { useAuth } from "@/components/Auth";
import { VisitorGlobe } from "@/components/VisitorGlobe";
import { LiteraturePanel } from "@/components/LiteraturePanel";
import { RegistryPanel } from "@/components/RegistryPanel";
import { StructurePanel } from "@/components/StructurePanel";
import {
  addDecision,
  assessHost,
  createCandidate,
  getCandidate,
  getStructure,
  runAgent,
  searchMaterials,
  type AgentContext,
  type Candidate,
  type DecisionKind,
  type Goal,
  type HostRef,
  type MaterialRecord,
  type StructuralAssessment,
  type StructurePayload,
  type Substitution,
} from "@/lib/api";

// Sent to the model; the agent replies in the UI language.
const DECISION_PROMPTS: Partial<Record<DecisionKind, (id: string) => string>> = {
  modify: (id) => `Revise ${id} following my feedback, then compare the checks with ${id}.`,
  explore: (id) =>
    `Suggest and test up to 2 alternative candidates to ${id} that follow my feedback. Compare them.`,
};

// "Try the AR example": SrTiO3 has a high n; LaAlO3 has a wider gap. Does a La+Al co-substitution keep both?
const EXAMPLE: { materialId: string; substitutions: Substitution[] } = {
  materialId: "mp-5229",
  substitutions: [
    { element_from: "Sr", element_to: "La", fraction: 1 / 4 },
    { element_from: "Ti", element_to: "Al", fraction: 1 / 4 },
  ],
};

const sameSubstitutions = (a: Substitution[], b: Substitution[]) =>
  a.length === b.length &&
  a.every((s, i) => s.element_from === b[i].element_from && s.element_to === b[i].element_to && Math.abs(s.fraction - b[i].fraction) < 1e-6);

export function Workspace() {
  const locale = useLocale();
  const t = useTranslations("Decision");
  const tw = useTranslations("Workspace");
  const { enabled: authEnabled, mode } = useAuth();
  const guided = useLevel().level === "guided";
  const [record, setRecord] = useState<MaterialRecord | null>(null);
  const [structure, setStructure] = useState<StructurePayload | null>(null);
  const [hostAssessment, setHostAssessment] = useState<StructuralAssessment | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [goal, setGoal] = useState<Goal>({ ...AR_GOAL, forbidden_elements: [] });
  const [goalTouched, setGoalTouched] = useState(false);
  const [example, setExample] = useState<ExampleState>({ stage: null, error: null });
  const [scrollTarget, setScrollTarget] = useState<StepId | "agent" | "structure" | "result" | null>(null);
  const alignTimer = useRef<number | undefined>(undefined);
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

  async function selectMaterial(selected: MaterialRecord): Promise<boolean> {
    setRecord(selected);
    setLoading(true);
    setError(null);
    try {
      setStructure(await getStructure(selected.material_id));
      void loadAssessment({ material_id: selected.material_id });
      return true;
    } catch (err) {
      setStructure(null);
      setError(err instanceof Error ? err.message : String(err));
      return false;
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

  // Share links: ?candidate=LL-0003 opens that candidate, if this viewer can read it.
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

  const hostReady = !!structure && !loading;
  const done: Record<StepId, boolean> = {
    goal: goalTouched || hostReady || !!current,
    host: hostReady || !!current,
    candidate: !!current,
    evidence: !!current?.decisions.length,
  };

  // Scroll once the target section has rendered (it may appear only after a host or candidate loads).
  useEffect(() => {
    if (!scrollTarget) return;
    const section = document.getElementById(`step-${scrollTarget}`);
    if (!section) return;
    const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
    section.scrollIntoView({ behavior, block: "start" });
    setScrollTarget(null);
    // Panels above may still grow while their data loads; align once more after they settle.
    window.clearTimeout(alignTimer.current);
    alignTimer.current = window.setTimeout(() => section.scrollIntoView({ behavior, block: "start" }), 900);
  }, [scrollTarget, structure, current, loading]);

  function jump(step: StepId) {
    setScrollTarget(document.getElementById(`step-${step}`) ? step : "host");
  }

  async function runExample() {
    setExample({ stage: "goal", error: null });
    setGoal((old) => ({ ...old, ...AR_GOAL }));
    setGoalTouched(true);
    try {
      setExample({ stage: "host", error: null });
      if (record?.material_id !== EXAMPLE.materialId || !structure) {
        const match = (await searchMaterials(EXAMPLE.materialId)).find((m) => m.material_id === EXAMPLE.materialId);
        if (!match || !(await selectMaterial(match))) throw new Error(`${EXAMPLE.materialId} could not be loaded.`);
      }
      setExample({ stage: "candidate", error: null });
      // Reuse the example candidate if this session already made it.
      const known = history.find(
        (c) =>
          c.parent_id === null &&
          c.transformation.host.reference === EXAMPLE.materialId &&
          sameSubstitutions(c.transformation.substitutions, EXAMPLE.substitutions),
      );
      showCandidate(known ?? (await createCandidate({ material_id: EXAMPLE.materialId }, EXAMPLE.substitutions)));
      setExample({ stage: "done", error: null });
      setScrollTarget(guided ? "result" : "evidence");
    } catch (err) {
      setExample({ stage: null, error: err instanceof Error ? err.message : String(err) });
    }
  }

  async function askAgent(message: string, shown: string, extra: Partial<AgentContext> = {}) {
    setTurns((old) => [...old, { role: "user", text: shown }]);
    setAgentBusy(true);
    setAgentError(null);
    const context: AgentContext = {
      host_material_id: record?.material_id,
      host_label: hostLabel || undefined,
      current_candidate_id: current?.candidate_id,
      goal,
      audience: guided ? "beginner" : "expert",
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

  const callout = example.stage === "done" && (
    <ExampleCallout onDismiss={() => setExample({ stage: null, error: null })} />
  );

  return (
    <>
      <Intro
        folded={!!current}
        exampleRunning={example.stage !== null && example.stage !== "done"}
        onExample={() => void runExample()}
        onStart={() => jump("goal")}
      />
      <p className="mb-4 rounded-lg bg-accent-soft p-3 text-xs">
        {tw(!authEnabled ? "noAccounts" : mode === "private" ? "privateNotice" : "publicNotice")}
      </p>
      <FlowGuide
        done={done}
        hostLabel={hostLabel}
        candidateId={current?.candidate_id ?? null}
        example={example}
        onJump={jump}
        onExample={() => void runExample()}
      />
      <div id="step-goal" className="scroll-mt-4 md:scroll-mt-28">
        <GoalPanel
          goal={goal}
          onChange={(next) => {
            setGoal(next);
            setGoalTouched(true);
          }}
        />
      </div>
      <div id="step-host" className="scroll-mt-4 md:scroll-mt-28">
        <HostSelector
          selectedId={record?.material_id ?? null}
          onSelectMaterial={async (selected) => {
            if ((await selectMaterial(selected)) && guided) setScrollTarget("structure");
          }}
          onUploadedStructure={showUploadedStructure}
        />
      </div>
      <div id="step-structure" className="scroll-mt-4 md:scroll-mt-28">
        <StructurePanel
          structure={structure}
          record={record}
          assessment={hostAssessment}
          loading={loading}
          error={error}
          goal={goal}
        />
      </div>
      {((host && structure && !loading) || current) && (
        <div id="step-candidate" className="scroll-mt-4 md:scroll-mt-28">
          <CandidatePanel
            key={record?.material_id ?? structure?.provenance.reference ?? "no-host"}
            host={structure && !loading ? host : null}
            hostLabel={hostLabel}
            hostElements={structure ? [...new Set(structure.sites.map((s) => s.species))] : []}
            history={history}
            current={current}
            goal={goal}
            agentBusy={agentBusy}
            onCandidate={showCandidate}
            onAskAgent={(message, shown) => {
              void askAgent(message, shown ?? message);
              setScrollTarget("agent");
            }}
            onSeeEvidence={() => jump("evidence")}
            hostFormula={structure?.formula ?? null}
            notice={guided ? callout : null}
            onSelect={setCurrent}
            onDecide={decide}
          />
        </div>
      )}
      {(structure || current) && (
        <div id="step-evidence" className="scroll-mt-4 md:scroll-mt-28">
          {!guided && callout}
          <EvidencePanel
            goal={goal}
            host={structure && !loading ? host : null}
            hostFormula={structure?.formula ?? null}
            hostAssessment={hostAssessment}
            candidate={current}
          />
        </div>
      )}
      <div id="step-agent" className="scroll-mt-4 md:scroll-mt-28">
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
      </div>
      <Advanced label={tw("sharedAndPapers")}>
        <RegistryPanel version={registryVersion} onOpen={showCandidate} />
        <LiteraturePanel key={formula ?? "none"} formula={formula} />
      </Advanced>
      <VisitorGlobe />
    </>
  );
}
