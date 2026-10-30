export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Health = {
  status: string;
  model: string;
  model_api_key_configured: boolean;
  materials_project_configured: boolean;
  openalex_api_key_configured: boolean;
  reference_db_available: boolean;
  candidate_store: "memory" | "postgres";
  relaxation_available: boolean;
};

export type EvidenceStatus = "Experimental" | "DFT-computed" | "Heuristic" | "Unknown";

export type Provenance = {
  source: string;
  method?: string | null;
  version?: string | null;
  reference?: string | null;
};

export type PropertyValue = {
  name: string;
  value?: number | null;
  value_range?: [number, number] | null;
  units?: string | null;
  status: EvidenceStatus;
  conditions?: string | null;
  provenance?: Provenance | null;
};

export type MaterialRecord = {
  material_id: string;
  formula: string;
  crystal_system: string | null;
  spacegroup: string | null;
  spacegroup_number: number | null;
  nsites: number | null;
  is_stable: boolean;
  theoretical: boolean;
  icsd_ids: string[];
  band_gap: PropertyValue;
  energy_above_hull: PropertyValue;
  refractive_index: PropertyValue;
  url: string;
};

export type StructurePayload = {
  formula: string;
  spacegroup: string | null;
  spacegroup_number: number | null;
  lattice: {
    a: number;
    b: number;
    c: number;
    alpha: number;
    beta: number;
    gamma: number;
    volume: number;
  };
  sites: { index: number; species: string; frac_coords: [number, number, number] }[];
  cif: string;
  provenance: Provenance;
  warnings: string[];
};

export type PaperEvidence = {
  title: string;
  authors: string[];
  year: number | null;
  venue: string | null;
  doi: string | null;
  url: string | null;
  cited_by_count: number | null;
  open_access: boolean | null;
  open_access_url: string | null;
  provenance: Provenance;
  sources: string[];
};

export type LiteratureResult = {
  papers: PaperEvidence[];
  source_status: Record<string, string>;
};

export type CodEntry = {
  cod_id: string;
  formula: string;
  spacegroup: string | null;
  spacegroup_number: number | null;
  cell: [number | null, number | null, number | null];
  year: number | null;
  authors: string | null;
  title: string | null;
  journal: string | null;
  doi: string | null;
  url: string;
};

export type MeasuredIndex = {
  title: string;
  category: string;
  direction: string | null;
  n_450: number | null;
  n_550: number | null;
  n_650: number | null;
  k_550: number | null;
  wavelength_range_um: [number, number];
  reference: string;
  doi: string | null;
  url: string;
};

export type ComputedOptics = {
  jid: string;
  mp_id: string | null;
  spacegroup: string | null;
  has_icsd: boolean;
  band_gap_optb88vdw: number | null;
  band_gap_mbj: number | null;
  n_optb88vdw: number | null;
  n_mbj: number | null;
  url: string;
};

export type OpticalReference = {
  formula: string;
  best_n: PropertyValue;
  measured: MeasuredIndex[];
  computed: ComputedOptics[];
  note: string;
};

export type OpticalEstimate = {
  estimate: PropertyValue;
  end_members: { formula: string; n: PropertyValue }[];
};

export type Substitution = { element_from: string; element_to: string; fraction: number };

export type CheckStatus = "pass" | "warn" | "fail" | "info" | "not_applicable";
export type AssessmentStatus =
  | "Structurally Plausible"
  | "Structural Concerns"
  | "Insufficient Evidence";

export type CheckResult = {
  id: string;
  name: string;
  status: CheckStatus;
  message: string;
  atom_indices: number[];
  values: Record<string, number | string>;
  method: string | null;
};

export type StructuralAssessment = {
  status: AssessmentStatus;
  checks: CheckResult[];
  oxidation_states: Record<string, number> | null;
  notes: string[];
};

export type Candidate = {
  candidate_id: string;
  parent_id: string | null;
  formula: string;
  structure: StructurePayload;
  transformation: {
    host: Provenance;
    supercell: [number, number, number];
    substitutions: Substitution[];
    substituted_sites: Record<string, number[]>;
    site_selection: string;
    root_formula: string;
    lineage: Substitution[];
  };
  assessment: StructuralAssessment;
  optical_estimate: OpticalEstimate | null;
  created_at: string;
  decisions: { decision: "accept" | "modify" | "reject" | "explore"; reason: string; created_at: string }[];
  visibility: "private" | "published";
  credit: { display: "name" | "anonymous"; name: string | null; published_at: string } | null;
  relaxation: Relaxation | null;
  experiments: ExperimentRecord[];
};

export type Relaxation = {
  method: string;
  converged: boolean;
  steps: number;
  energy_per_atom: number;
  lattice_change: [number, number, number];
  volume_change: number;
  max_displacement: number;
  structure: StructurePayload;
  assessment: StructuralAssessment;
};

export type ExperimentInput = {
  property: "refractive_index" | "band_gap";
  value: number;
  wavelength_nm?: number | null;
  sample: "bulk" | "thin film" | "powder" | "other";
  method: string;
  reference?: string | null;
  notes?: string;
};

export type ExperimentRecord = ExperimentInput & { created_at: string };

export type HostRef =
  | { material_id: string }
  | { candidate_id: string }
  | { cif: string; filename: string };

export type ToolCall = {
  name: string;
  arguments: string;
  output: Record<string, unknown>;
};

export type AgentResult = {
  model: string;
  candidate_ids: string[];
  output_text: string;
  response_id: string;
  tool_calls: ToolCall[];
  completed: boolean;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    throw new Error(
      typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : `HTTP ${response.status}`,
    );
  }
  return response.json() as Promise<T>;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function getHealth(): Promise<Health> {
  return request<Health>("/api/health");
}

export function searchMaterials(query: string): Promise<MaterialRecord[]> {
  return request<MaterialRecord[]>(`/api/materials/search?${new URLSearchParams({ q: query })}`);
}

export function getStructure(materialId: string): Promise<StructurePayload> {
  return request<StructurePayload>(`/api/materials/${encodeURIComponent(materialId)}/structure`);
}

export function uploadCif(filename: string, cif: string): Promise<StructurePayload> {
  return postJson<StructurePayload>("/api/structures/cif", { filename, cif });
}

export function getOpticalReference(formula: string): Promise<OpticalReference> {
  return request<OpticalReference>(`/api/reference/${encodeURIComponent(formula)}`);
}

export function searchLiterature(query: string): Promise<LiteratureResult> {
  return request<LiteratureResult>(`/api/literature/search?${new URLSearchParams({ q: query })}`);
}

export function searchCod(formula: string): Promise<CodEntry[]> {
  return request<CodEntry[]>(`/api/cod/search?${new URLSearchParams({ formula })}`);
}

export function getCodStructure(codId: string): Promise<StructurePayload> {
  return request<StructurePayload>(`/api/cod/${encodeURIComponent(codId)}/structure`);
}

export type Visibility = "private" | "published";

export function setVisibility(
  candidateId: string,
  body: {
    visibility: Visibility;
    credit_display?: "name" | "anonymous";
    display_name?: string;
    consent?: boolean;
  },
): Promise<Candidate> {
  return postJson<Candidate>(`/api/candidates/${encodeURIComponent(candidateId)}/visibility`, body);
}

export function createCandidate(host: HostRef, substitutions: Substitution[]): Promise<Candidate> {
  return postJson<Candidate>("/api/candidates", { host, substitutions });
}

export function assessHost(host: HostRef): Promise<StructuralAssessment> {
  return postJson<StructuralAssessment>("/api/structures/assess", host);
}

export type DecisionKind = "accept" | "modify" | "reject" | "explore";

export type AgentContext = {
  host_material_id?: string;
  host_label?: string;
  current_candidate_id?: string;
  decision?: DecisionKind;
  feedback?: string;
};

export function runAgent(
  message: string,
  locale: string,
  previousResponseId: string | null,
  context: AgentContext,
): Promise<AgentResult> {
  return postJson<AgentResult>("/api/agent/run", {
    message,
    locale,
    previous_response_id: previousResponseId,
    context,
  });
}

export function getCandidate(candidateId: string): Promise<Candidate> {
  return request<Candidate>(`/api/candidates/${encodeURIComponent(candidateId)}`);
}

export function listCandidates(): Promise<Candidate[]> {
  return request<Candidate[]>("/api/candidates");
}

export function relaxCandidate(candidateId: string): Promise<Candidate> {
  return postJson<Candidate>(`/api/candidates/${encodeURIComponent(candidateId)}/relax`, {});
}

export function addExperiment(candidateId: string, body: ExperimentInput): Promise<Candidate> {
  return postJson<Candidate>(`/api/candidates/${encodeURIComponent(candidateId)}/experiments`, body);
}

export function addDecision(
  candidateId: string,
  decision: DecisionKind,
  reason: string,
): Promise<Candidate> {
  return postJson<Candidate>(`/api/candidates/${encodeURIComponent(candidateId)}/decisions`, {
    decision,
    reason,
  });
}
