"use client";

import { useState } from "react";
import { HostSelector } from "@/components/HostSelector";
import { LiteraturePanel } from "@/components/LiteraturePanel";
import { StructurePanel } from "@/components/StructurePanel";
import { getStructure, type MaterialRecord, type StructurePayload } from "@/lib/api";

export function Workspace() {
  const [record, setRecord] = useState<MaterialRecord | null>(null);
  const [structure, setStructure] = useState<StructurePayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function selectMaterial(selected: MaterialRecord) {
    setRecord(selected);
    setLoading(true);
    setError(null);
    try {
      setStructure(await getStructure(selected.material_id));
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
  }

  const formula = structure?.formula ?? record?.formula ?? null;

  return (
    <>
      <HostSelector
        selectedId={record?.material_id ?? null}
        onSelectMaterial={selectMaterial}
        onUploadedStructure={showUploadedStructure}
      />
      <StructurePanel structure={structure} record={record} loading={loading} error={error} />
      <LiteraturePanel key={formula ?? "none"} formula={formula} />
    </>
  );
}
