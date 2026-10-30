"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { EvidenceTag } from "@/components/EvidenceTag";
import { addExperiment, type Candidate, type ExperimentInput } from "@/lib/api";

type Props = {
  candidate: Candidate;
  onChange: (candidate: Candidate) => void;
};

// Prediction vs. experiment (spec 3.5): the researcher adds a measurement, and the app
// shows whether it falls inside the candidate's Heuristic n range.
export function ExperimentPanel({ candidate, onChange }: Props) {
  const t = useTranslations("Experiment");
  const [form, setForm] = useState<ExperimentInput>({
    property: "refractive_index",
    value: NaN,
    wavelength_nm: 550,
    sample: "bulk",
    method: "",
    reference: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const range = candidate.optical_estimate?.estimate.value_range ?? null;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onChange(
        await addExperiment(candidate.candidate_id, {
          ...form,
          wavelength_nm: form.property === "refractive_index" ? form.wavelength_nm : null,
          reference: form.reference?.trim() || null,
        }),
      );
      setForm((f) => ({ ...f, value: NaN, method: "", reference: "" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function comparison(value: number, property: string) {
    if (property !== "refractive_index" || !range) return null;
    const inside = value >= range[0] && value <= range[1];
    return (
      <span className={inside ? "text-tag-exp" : "text-tag-heur"}>
        {inside ? t("inside", { lo: range[0], hi: range[1] }) : t("outside", { lo: range[0], hi: range[1] })}
      </span>
    );
  }

  return (
    <div className="rounded-md border border-line p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{t("title")}</span>
        <span className="text-xs text-muted">
          {candidate.experiments.length ? t("measured", { count: candidate.experiments.length }) : t("notTested")}
        </span>
      </div>

      {candidate.experiments.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs">
          {candidate.experiments.map((e) => (
            <li key={e.created_at} className="flex flex-wrap items-center gap-2">
              <EvidenceTag status="Experimental" />
              <span className="tabular-nums">
                {e.property === "refractive_index"
                  ? `n(${e.wavelength_nm} nm) = ${e.value}`
                  : `${t("bandGap")} = ${e.value} eV`}
              </span>
              <span className="text-muted">
                {[e.sample, e.method, e.reference].filter(Boolean).join(" · ")}
              </span>
              {comparison(e.value, e.property)}
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={onSubmit} className="mt-2 flex flex-wrap items-end gap-2 text-xs">
        <label className="flex flex-col">
          {t("property")}
          <select
            className="rounded border border-line bg-background px-2 py-1"
            value={form.property}
            onChange={(e) => setForm({ ...form, property: e.target.value as ExperimentInput["property"] })}
          >
            <option value="refractive_index">n</option>
            <option value="band_gap">{t("bandGap")} (eV)</option>
          </select>
        </label>
        <label className="flex flex-col">
          {t("value")}
          <input
            type="number"
            step="any"
            min={0}
            required
            className="w-20 rounded border border-line bg-background px-2 py-1"
            value={Number.isNaN(form.value) ? "" : form.value}
            onChange={(e) => setForm({ ...form, value: e.target.valueAsNumber })}
          />
        </label>
        {form.property === "refractive_index" && (
          <label className="flex flex-col">
            {t("wavelength")}
            <input
              type="number"
              min={1}
              required
              className="w-20 rounded border border-line bg-background px-2 py-1"
              value={form.wavelength_nm ?? ""}
              onChange={(e) => setForm({ ...form, wavelength_nm: e.target.valueAsNumber })}
            />
          </label>
        )}
        <label className="flex flex-col">
          {t("sample")}
          <select
            className="rounded border border-line bg-background px-2 py-1"
            value={form.sample}
            onChange={(e) => setForm({ ...form, sample: e.target.value as ExperimentInput["sample"] })}
          >
            <option value="bulk">{t("bulk")}</option>
            <option value="thin film">{t("thinFilm")}</option>
            <option value="powder">{t("powder")}</option>
            <option value="other">{t("other")}</option>
          </select>
        </label>
        <label className="flex flex-col">
          {t("method")}
          <input
            className="w-32 rounded border border-line bg-background px-2 py-1"
            placeholder={t("methodPlaceholder")}
            value={form.method}
            maxLength={200}
            onChange={(e) => setForm({ ...form, method: e.target.value })}
          />
        </label>
        <label className="flex flex-col">
          {t("reference")}
          <input
            className="w-36 rounded border border-line bg-background px-2 py-1"
            placeholder="DOI / URL"
            value={form.reference ?? ""}
            maxLength={300}
            onChange={(e) => setForm({ ...form, reference: e.target.value })}
          />
        </label>
        <button
          type="submit"
          disabled={busy || Number.isNaN(form.value)}
          className="rounded-md bg-accent px-3 py-1 font-medium text-white disabled:opacity-50"
        >
          {t("add")}
        </button>
      </form>
      <p className="mt-1 text-xs text-muted">{t("hint")}</p>
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </div>
  );
}
