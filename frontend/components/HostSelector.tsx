"use client";

import { useTranslations } from "next-intl";
import { useState, type ChangeEvent, type FormEvent } from "react";
import { PropertyValueView } from "@/components/EvidenceTag";
import { useLevel } from "@/components/Level";
import { Term } from "@/components/Term";
import {
  getCodStructure,
  searchCod,
  searchMaterials,
  uploadCif,
  type CodEntry,
  type MaterialRecord,
  type StructurePayload,
} from "@/lib/api";

type Source = "mp" | "cod";

// Starting points for someone who does not know a formula yet. Their numbers load from the data.
const STARTERS = [
  { id: "mp-5229", formula: "SrTiO3", key: "srtio3" },
  { id: "mp-390", formula: "TiO2", key: "anatase" },
  { id: "mp-10695", formula: "ZnS", key: "zns" },
  { id: "mp-3731", formula: "LiNbO3", key: "linbo3" },
] as const;

type Props = {
  selectedId: string | null;
  onSelectMaterial: (record: MaterialRecord) => void;
  onUploadedStructure: (structure: StructurePayload) => void;
};

export function HostSelector({ selectedId, onSelectMaterial, onUploadedStructure }: Props) {
  const t = useTranslations("Host");
  const { level } = useLevel();
  const guided = level === "guided";
  const [source, setSource] = useState<Source>("mp");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MaterialRecord[] | null>(null);
  const [codResults, setCodResults] = useState<CodEntry[] | null>(null);
  const [selectedCod, setSelectedCod] = useState<string | null>(null);
  const [busy, setBusy] = useState<"search" | "upload" | "load" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(kind: "search" | "upload" | "load", action: () => Promise<void>) {
    setBusy(kind);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  function onSearch(event: FormEvent) {
    event.preventDefault();
    void run("search", async () => {
      if (source === "mp") setResults(await searchMaterials(query.trim()));
      else setCodResults(await searchCod(query.trim()));
    });
  }

  function onUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    void run("upload", async () => onUploadedStructure(await uploadCif(file.name, await file.text())));
  }

  function selectCod(entry: CodEntry) {
    setSelectedCod(entry.cod_id);
    void run("load", async () => onUploadedStructure(await getCodStructure(entry.cod_id)));
  }

  function selectStarter(id: string) {
    void run("load", async () => {
      const match = (await searchMaterials(id)).find((m) => m.material_id === id);
      if (!match) throw new Error(`${id} could not be loaded.`);
      onSelectMaterial(match);
    });
  }

  const tabClass = (active: boolean) =>
    `rounded-md px-3 py-1 text-sm ${active ? "bg-accent text-white" : "border border-line"}`;

  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      <h2 className="font-semibold">{guided ? <>{t("titleGuided.before")} <Term id="host">{t("titleGuided.term")}</Term></> : t("title")}</h2>
      {guided ? (
        <>
          <p className="mb-3 mt-1 text-sm text-muted">{t("hintGuided")}</p>
          <div className="mb-3 grid gap-2 sm:grid-cols-2">
            {STARTERS.map((s) => (
              <button
                key={s.id}
                type="button"
                disabled={busy !== null}
                onClick={() => selectStarter(s.id)}
                aria-pressed={selectedId === s.id}
                className={`rounded-md border p-3 text-left text-sm disabled:opacity-60 ${selectedId === s.id ? "border-accent" : "border-line"}`}
              >
                <span className="font-medium">{s.formula}</span>
                <span className="mt-0.5 block text-muted">{t(`starter.${s.key}`)}</span>
              </button>
            ))}
          </div>
          <p className="mb-2 text-sm">{t("searchInstead")}</p>
        </>
      ) : (
        <>
          <div className="mb-2 mt-2 flex flex-wrap gap-2" role="tablist">
            <button type="button" role="tab" aria-selected={source === "mp"} className={tabClass(source === "mp")} onClick={() => setSource("mp")}>
              {t("sourceMp")}
            </button>
            <button type="button" role="tab" aria-selected={source === "cod"} className={tabClass(source === "cod")} onClick={() => setSource("cod")}>
              {t("sourceCod")}
            </button>
          </div>
          <p className="mb-3 text-sm text-muted">{source === "mp" ? t("hint") : t("hintCod")}</p>
        </>
      )}

      <form onSubmit={onSearch} className="flex flex-col gap-2 sm:flex-row">
        <input
          className="flex-1 rounded-md border border-line bg-background px-3 py-2"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={source === "mp" ? t("placeholder") : t("placeholderCod")}
        />
        <button
          type="submit"
          disabled={busy !== null || !query.trim()}
          className="rounded-md bg-accent px-4 py-2 font-medium text-white disabled:opacity-50"
        >
          {busy === "search" ? t("searching") : t("search")}
        </button>
        {!guided && (
          <label className="cursor-pointer rounded-md border border-line px-4 py-2 text-center font-medium">
            {busy === "upload" ? t("uploading") : t("upload")}
            <input type="file" accept=".cif" className="sr-only" onChange={onUpload} disabled={busy !== null} />
          </label>
        )}
      </form>

      {error && <p className="mt-3 text-sm text-danger">{error}</p>}
      {busy === "load" && <p className="mt-3 text-sm text-muted">{guided ? t("loadingStarter") : t("loadingCod")}</p>}

      {source === "mp" && results && results.length === 0 && (
        <p className="mt-3 text-sm text-muted">{t("noResults")}</p>
      )}
      {source === "mp" && results && results.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-muted">
              <tr>
                <th className="py-1 pr-3 font-normal">{t("columns.formula")}</th>
                {!guided && <th className="py-1 pr-3 font-normal">{t("columns.spacegroup")}</th>}
                {!guided && <th className="py-1 pr-3 font-normal">{t("columns.eHull")}</th>}
                <th className="py-1 pr-3 font-normal"><Term id="band_gap">{t("columns.bandGap")}</Term></th>
                <th className="py-1 pr-3 font-normal"><Term id="n">{t("columns.n")}</Term></th>
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
                  {!guided && <td className="py-1.5 pr-3">{record.spacegroup ?? "—"}</td>}
                  {!guided && <td className="py-1.5 pr-3"><PropertyValueView pv={record.energy_above_hull} /></td>}
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

      {source === "cod" && codResults && codResults.length === 0 && (
        <p className="mt-3 text-sm text-muted">{t("noResults")}</p>
      )}
      {source === "cod" && codResults && codResults.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-muted">
              <tr>
                <th className="py-1 pr-3 font-normal">COD</th>
                <th className="py-1 pr-3 font-normal">{t("columns.spacegroup")}</th>
                <th className="py-1 pr-3 font-normal">a, b, c (Å)</th>
                <th className="py-1 font-normal">{t("columns.reference")}</th>
              </tr>
            </thead>
            <tbody>
              {codResults.map((entry) => (
                <tr
                  key={entry.cod_id}
                  onClick={() => selectCod(entry)}
                  className={`cursor-pointer border-t border-line hover:bg-background ${
                    entry.cod_id === selectedCod ? "bg-background font-medium" : ""
                  }`}
                >
                  <td className="py-1.5 pr-3">
                    <a href={entry.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="font-mono text-accent underline">
                      {entry.cod_id}
                    </a>
                    <div className="text-xs text-muted">{entry.formula}</div>
                  </td>
                  <td className="py-1.5 pr-3">{entry.spacegroup ?? "—"}</td>
                  <td className="py-1.5 pr-3 font-mono text-xs tabular-nums">
                    {entry.cell.map((v) => (v == null ? "—" : v.toFixed(3))).join(", ")}
                  </td>
                  <td className="py-1.5 text-xs">
                    {[entry.authors?.split(";")[0], entry.journal, entry.year].filter(Boolean).join(" · ")}
                    {entry.doi && <div className="font-mono text-muted">doi:{entry.doi}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-xs text-muted">{t("codCredit")}</p>
        </div>
      )}
    </section>
  );
}
