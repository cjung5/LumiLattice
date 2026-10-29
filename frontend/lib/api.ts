export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Health = {
  status: string;
  model: string;
  model_api_key_configured: boolean;
  materials_project_configured: boolean;
  openalex_api_key_configured: boolean;
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
  open_access: boolean;
  open_access_url: string | null;
  provenance: Provenance;
};

export type ToolCall = {
  name: string;
  arguments: string;
  output: Record<string, unknown>;
};

export type AgentResult = {
  model: string;
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

export function searchLiterature(query: string): Promise<PaperEvidence[]> {
  return request<PaperEvidence[]>(`/api/literature/search?${new URLSearchParams({ q: query })}`);
}

export function runAgent(message: string, locale: string): Promise<AgentResult> {
  return postJson<AgentResult>("/api/agent/run", { message, locale });
}
