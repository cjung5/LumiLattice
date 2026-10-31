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
  best_gap: PropertyValue;
  measured_gaps: number[];
  measured: MeasuredIndex[];
  computed: ComputedOptics[];
  note: string;
};

export type OpticalEstimate = {
  estimate: PropertyValue;
  band_gap: PropertyValue | null;
  end_members: { formula: string; n: PropertyValue; band_gap: PropertyValue | null }[];
};

export type DispersionData = {
  formula: string;
  wavelengths_nm: number[];
  curves: { title: string; category: string; direction: string | null; n: (number | null)[] }[];
  bulk_median: (number | null)[] | null;
};

export type Landscape = {
  measured: { formula: string; n: number; band_gap: number; gap_measured: boolean }[];
  computed: [number, number][];
  computed_total: number;
  moss: [number, number][];
  notes: string[];
};

export type SymmetryInfo = {
  spacegroup: string | null;
  number: number | null;
  crystal_system: string | null;
  optical_class: "isotropic" | "uniaxial" | "biaxial" | null;
};

export type Polyhedron = {
  index: number;
  element: string;
  coordination: number;
  shape: string;
  shape_score: number | null;
  distortion_index: number;
  quadratic_elongation: number | null;
  bond_angle_variance: number | null;
  volume: number | null;
};

export type Linkages = {
  corner: number;
  edge: number;
  face: number;
  bxb_angles: number[];
  mean_tilt: number | null;
};

export type SpatialAnalysis = {
  symmetry: SymmetryInfo;
  parent_symmetry: SymmetryInfo | null;
  polyhedra: Polyhedron[];
  linkages: Linkages;
  parent_polyhedra: Polyhedron[];
  parent_linkages: Linkages | null;
  dopants: {
    element: string;
    sites: number[];
    nearest_distances: number[];
    shortest: number | null;
    cation_spacing: number;
  }[];
  ordering: {
    energies: number[];
    chosen: number;
    chosen_rank: number;
    distinct: number;
    total: number;
    truncated: boolean;
    analysis_cell: [number, number, number];
    method: string;
  } | null;
  findings: string[];
  notes: string[];
};

export type Goal = { target_n: number; min_band_gap: number; forbidden_elements: string[] };

export type Verdict = "meets" | "uncertain" | "fails" | "unknown";

export type GoalScore = {
  subject: string;
  goal: Goal;
  criteria: {
    id: "n" | "band_gap" | "elements" | "structure";
    verdict: Verdict;
    detail: string;
    evidence?: PropertyValue | null;
  }[];
  meets: number;
  total: number;
};

export type SiteMetric = {
  index: number;
  element: string;
  oxidation_state: number;
  coordination: number;
  bond_lengths: number[];
  mean_bond: number;
  expected_bond: number | null;
  size_mismatch: number | null;
  bvs: number | null;
  bvs_bond_change: number | null;
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
  site_metrics: SiteMetric[];
  thresholds: Record<string, number>;
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
    arrangement: Arrangement;
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
  critiques: Critique[];
};

export type CritiqueEvidence = { id: string; group: string; text: string };

/** Muse Spark's review: an opinion that cites evidence IDs, never evidence itself. */
export type Critique = {
  created_at: string;
  model: string;
  locale: string;
  geometry: "unrelaxed" | "relaxed";
  views: number;
  verdict: "promising" | "mixed" | "weak" | "insufficient_evidence";
  summary: string;
  points: { kind: "strength" | "concern" | "open_question"; text: string; evidence: string[]; basis: "evidence" | "image" | "both" }[];
  suggestions: { change: string; rationale: string; evidence: string[] }[];
  questions: string[];
  evidence: CritiqueEvidence[];
  warnings: string[];
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

async function errorFrom(response: Response): Promise<Error> {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  return new Error(
    typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : `HTTP ${response.status}`,
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) throw await errorFrom(response);
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

export function getLandscape(): Promise<Landscape> {
  return request<Landscape>("/api/landscape");
}

export function getDispersion(formulas: string[]): Promise<DispersionData[]> {
  return request<DispersionData[]>(`/api/dispersion?${new URLSearchParams({ formulas: formulas.join(",") })}`);
}

export function getCandidateSpatial(candidateId: string, relaxed = false): Promise<SpatialAnalysis> {
  return request<SpatialAnalysis>(
    `/api/candidates/${encodeURIComponent(candidateId)}/spatial?relaxed=${relaxed}`,
  );
}

export function getHostSpatial(host: HostRef): Promise<SpatialAnalysis> {
  return postJson<SpatialAnalysis>("/api/structures/spatial", host);
}

export function scoreGoal(goal: Goal, subject: { candidate_id?: string; formula?: string }): Promise<GoalScore> {
  return postJson<GoalScore>("/api/score", { goal, ...subject });
}

export type MetricId = "n" | "band_gap" | "trade_off" | "isotropy" | "fit" | "supply";

export type ScoreMetric = {
  id: MetricId;
  weight: number;
  low: number;
  high: number;
  value: string | null;
  evidence: EvidenceStatus | "Model";
  detail: string;
};

export type BenchmarkEntry = { formula: string; score: number; n: number; band_gap: number };

export type Scorecard = {
  subject: string;
  low: number;
  high: number;
  optical_low: number;
  optical_high: number;
  metrics: ScoreMetric[];
  evidence_mix: Partial<Record<EvidenceStatus | "Model", number>>;
  biggest_gain: MetricId;
  disqualified: string[];
  benchmark: {
    size: number;
    beats_low: number;
    beats_high: number;
    host: BenchmarkEntry | null;
    landmarks: BenchmarkEntry[];
    note: string;
  };
  method: string;
  validation: {
    gap_cases: number;
    gap_inside: number;
    oxide_cases: number;
    oxide_inside: number;
    oxide_systems: number;
    oxide_other_cases: number;
    oxide_other_inside: number;
    oxide_other_rank: number;
    n_cases: number;
    n_inside: number;
    swaps: number;
    swaps_kept: number;
    implausible: number;
    implausible_caught: number;
  } | null;
};

export type NoveltyLevel = "known" | "computed" | "related" | "unreported";

export type Novelty = {
  subject: string;
  formula: string;
  level: NoveltyLevel;
  complete: boolean;
  checks: {
    id: "mp_exact" | "cod_exact" | "reference" | "mp_system" | "papers";
    status: "found" | "not_found" | "unavailable";
    detail: string;
    items: { label: string; url?: string | null }[];
  }[];
  nearest: { formula: string; atoms_differ: number }[];
  caveat: string;
};

export function getScorecard(id: string, goal: Goal): Promise<Scorecard> {
  return postJson<Scorecard>(`/api/candidates/${encodeURIComponent(id)}/scorecard`, goal);
}

export function getNovelty(id: string): Promise<Novelty> {
  return request<Novelty>(`/api/candidates/${encodeURIComponent(id)}/novelty`);
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

export function critiqueCandidate(
  id: string,
  body: {
    goal: Goal;
    locale: string;
    geometry: "unrelaxed" | "relaxed";
    views: { label: string; image: string }[];
    legend: Record<string, string>;
    audience?: "beginner" | "expert";
  },
): Promise<Candidate> {
  return postJson<Candidate>(`/api/candidates/${encodeURIComponent(id)}/critique`, body);
}

export type ExportKind = "cif" | "cif-relaxed" | "record";

/** The JSON record includes the goal score when a goal is given. */
export function exportUrl(id: string, kind: ExportKind, goal?: Goal): string {
  const base = `${API_BASE_URL}/api/candidates/${encodeURIComponent(id)}`;
  if (kind !== "record") return `${base}/export.cif${kind === "cif-relaxed" ? "?relaxed=true" : ""}`;
  const params = goal
    ? `?${new URLSearchParams({
        target_n: String(goal.target_n),
        min_band_gap: String(goal.min_band_gap),
        forbidden: goal.forbidden_elements.join(","),
      })}`
    : "";
  return `${base}/export.json${params}`;
}

/** Fetch an export and save it under its file name (<a download> ignores cross-origin URLs). */
export async function downloadExport(id: string, kind: ExportKind, goal?: Goal): Promise<void> {
  const response = await fetch(exportUrl(id, kind, goal));
  if (!response.ok) throw await errorFrom(response);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = kind === "record" ? `${id}-record.json` : `${id}${kind === "cif-relaxed" ? "-relaxed" : ""}.cif`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** "spread": new atoms as far apart as possible; "lowest_ewald": lowest point-charge energy. */
export type Arrangement = "spread" | "lowest_ewald";

export function createCandidate(
  host: HostRef,
  substitutions: Substitution[],
  arrangement: Arrangement = "spread",
): Promise<Candidate> {
  return postJson<Candidate>("/api/candidates", { host, substitutions, arrangement });
}

export function assessHost(host: HostRef): Promise<StructuralAssessment> {
  return postJson<StructuralAssessment>("/api/structures/assess", host);
}

export type DecisionKind = "accept" | "modify" | "reject" | "explore";

export type Audience = "beginner" | "expert";

export type AgentContext = {
  audience?: Audience;
  host_material_id?: string;
  host_label?: string;
  current_candidate_id?: string;
  decision?: DecisionKind;
  feedback?: string;
  goal?: Goal;
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
