"use client";

import { useState } from "react";
import { CandidatePanel } from "@/components/CandidatePanel";
import { HostSelector } from "@/components/HostSelector";
import { LiteraturePanel } from "@/components/LiteraturePanel";
import { StructurePanel } from "@/components/StructurePanel";
import {
  assessHost,
  getStructure,
  type HostRef,
  type MaterialRecord,
  type StructuralAssessment,
  type StructurePayload,
} from "@/lib/api";

export function Workspace() {
  const [record, setRecord] = useState<MaterialRecord | null>(null);
  const [structure, setStructure] = useState<StructurePayload | null>(null);
  const [hostAssessment, setHostAssessment] = useState<StructuralAssessment | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const formula = structure?.formula ?? record?.formula ?? null;
  const host: HostRef | null = record
    ? { material_id: record.material_id }
    : structure
      ? { cif: structure.cif, filename: structure.provenance.reference ?? "upload.cif" }
      : null;
  const hostLabel = record ? `${record.formula} (${record.material_id})` : (formula ?? "");
  const hostKey = record?.material_id ?? structure?.provenance.reference ?? "none";

  return (
    <>
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
      {host && structure && !loading && (
        <CandidatePanel
          key={hostKey}
          host={host}
          hostLabel={hostLabel}
          hostElements={[...new Set(structure.sites.map((s) => s.species))]}
        />
      )}
      <LiteraturePanel key={formula ?? "none"} formula={formula} />
    </>
  );
}
