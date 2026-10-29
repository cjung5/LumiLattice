"use client";

import { useTranslations } from "next-intl";
import { useState, type ChangeEvent, type FormEvent } from "react";
import { PropertyValueView } from "@/components/EvidenceTag";
import { searchMaterials, uploadCif, type MaterialRecord, type StructurePayload } from "@/lib/api";

type Props = {
  selectedId: string | null;
  onSelectMaterial: (record: MaterialRecord) => void;
  onUploadedStructure: (structure: StructurePayload) => void;
};

export function HostSelector({ selectedId, onSelectMaterial, onUploadedStructure }: Props) {
  const t = useTranslations("Host");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MaterialRecord[] | null>(null);
  const [busy, setBusy] = useState<"search" | "upload" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    setBusy("search");
    setError(null);
    try {
      setResults(await searchMaterials(query.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  async function onUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy("upload");
    setError(null);
    try {
      onUploadedStructure(await uploadCif(file.name, await file.text()));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      <h2 className="font-semibold">{t("title")}</h2>
      <p className="mb-3 text-sm text-muted">{t("hint")}</p>

      <form onSubmit={onSearch} className="flex flex-col gap-2 sm:flex-row">
        <input
          className="flex-1 rounded-md border border-line bg-background px-3 py-2"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t("placeholder")}
        />
        <button
          type="submit"
          disabled={busy !== null || !query.trim()}
          className="rounded-md bg-accent px-4 py-2 font-medium text-white disabled:opacity-50"
        >
          {busy === "search" ? t("searching") : t("search")}
        </button>
        <label className="cursor-pointer rounded-md border border-line px-4 py-2 text-center font-medium">
          {busy === "upload" ? t("uploading") : t("upload")}
          <input type="file" accept=".cif" className="sr-only" onChange={onUpload} disabled={busy !== null} />
        </label>
      </form>

      {error && <p className="mt-3 text-sm text-danger">{error}</p>}

      {results && results.length === 0 && <p className="mt-3 text-sm text-muted">{t("noResults")}</p>}

      {results && results.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-muted">
              <tr>
                <th className="py-1 pr-3 font-normal">{t("columns.formula")}</th>
                <th className="py-1 pr-3 font-normal">{t("columns.spacegroup")}</th>
                <th className="py-1 pr-3 font-normal">{t("columns.eHull")}</th>
                <th className="py-1 pr-3 font-normal">{t("columns.bandGap")}</th>
                <th className="py-1 pr-3 font-normal">{t("columns.n")}</th>
                <th className="py-1 font-normal">{t("columns.status")}</th>
              </tr>
            </thead>
            <tbody>
              {results.map((record) => (
                <tr
                  key={record.material_id}
                  onClick={() => onSelectMaterial(record)}
                  className={`cursor-pointer border-t border-line hover:bg-background ${
                    record.material_id === selectedId ? "bg-background font-medium" : ""
                  }`}
                >
                  <td className="py-1.5 pr-3">
                    {record.formula}
                    <div className="font-mono text-xs text-muted">{record.material_id}</div>
                  </td>
                  <td className="py-1.5 pr-3">{record.spacegroup ?? "—"}</td>
                  <td className="py-1.5 pr-3"><PropertyValueView pv={record.energy_above_hull} /></td>
                  <td className="py-1.5 pr-3"><PropertyValueView pv={record.band_gap} /></td>
                  <td className="py-1.5 pr-3"><PropertyValueView pv={record.refractive_index} /></td>
                  <td className="py-1.5 text-xs">
                    {record.is_stable && <div>{t("stable")}</div>}
                    <div>{record.theoretical ? t("theoretical") : t("experimental")}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
