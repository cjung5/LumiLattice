"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { relaxCandidate, type Candidate } from "@/lib/api";

const pct = (v: number) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;

type Props = {
  candidate: Candidate;
  showRelaxed: boolean;
  onShowRelaxed: (show: boolean) => void;
  onChange: (candidate: Candidate) => void;
};

// CHGNet runs only in a local install (it needs PyTorch); the live demo explains this.
export function RelaxationPanel({ candidate, showRelaxed, onShowRelaxed, onChange }: Props) {
  const t = useTranslations("Relax");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const r = candidate.relaxation;

  async function run() {
    setBusy(true);
    setError(null);
    try {
      onChange(await relaxCandidate(candidate.candidate_id));
      onShowRelaxed(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-md border border-line p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{t("title")}</span>
        {!r && (
          <button
            type="button"
            disabled={busy}
            onClick={() => void run()}
            className="rounded-md border border-accent px-3 py-1 text-xs font-medium text-accent disabled:opacity-50"
          >
            {busy ? t("running") : t("run")}
          </button>
        )}
        {r && (
          <div className="flex gap-1 text-xs" role="group">
            <button
              type="button"
              onClick={() => onShowRelaxed(false)}
              className={`rounded px-2 py-0.5 ${!showRelaxed ? "bg-accent text-white" : "border border-line"}`}
            >
              {t("unrelaxed")}
            </button>
            <button
              type="button"
              onClick={() => onShowRelaxed(true)}
              className={`rounded px-2 py-0.5 ${showRelaxed ? "bg-accent text-white" : "border border-line"}`}
            >
              {t("relaxed")}
            </button>
          </div>
        )}
      </div>
      <p className="mt-1 text-xs text-muted">{t("hint")}</p>
      {error && <p className="mt-1 text-xs text-warning">{error}</p>}
      {r && (
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
          <div>
            <dt className="text-muted">Δa, Δb, Δc</dt>
            <dd className="tabular-nums">{r.lattice_change.map(pct).join(", ")}</dd>
          </div>
          <div>
            <dt className="text-muted">ΔV</dt>
            <dd className="tabular-nums">{pct(r.volume_change)}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("maxShift")}</dt>
            <dd className="tabular-nums">{r.max_displacement} Å</dd>
          </div>
          <div>
            <dt className="text-muted">{t("status")}</dt>
            <dd>
              {r.converged ? t("converged", { steps: r.steps }) : t("notConverged", { steps: r.steps })}
            </dd>
          </div>
          <div className="col-span-2 sm:col-span-4">
            <dt className="text-muted">{t("energy")}</dt>
            <dd className="tabular-nums">
              {r.energy_per_atom} eV/atom <span className="text-muted">— {t("energyNote")}</span>
            </dd>
          </div>
          <div className="col-span-2 text-muted sm:col-span-4">{r.method}</div>
        </dl>
      )}
    </div>
  );
}
