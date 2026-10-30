"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { EvidenceTag, PropertyValueView } from "@/components/EvidenceTag";
import { getOpticalReference, type OpticalReference } from "@/lib/api";

const fmt = (v: number | null) => (v == null ? "—" : v.toFixed(3));

// The parent gives this panel a `key` per formula, so it loads once per host formula.
export function OpticalPanel({ formula }: { formula: string }) {
  const t = useTranslations("Optical");
  const [data, setData] = useState<OpticalReference | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getOpticalReference(formula)
      .then((ref) => active && setData(ref))
      .catch((err) => active && setError(err instanceof Error ? err.message : String(err)));
    return () => {
      active = false;
    };
  }, [formula]);

  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!data) return <p className="text-sm text-muted">{t("loading")}</p>;

  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{t("bestN", { formula: data.formula })}</span>
        <PropertyValueView pv={data.best_n} />
      </div>
      {data.best_n.conditions && <p className="text-xs text-muted">{data.best_n.conditions}</p>}

      {data.measured.length > 0 && (
        <details open>
          <summary className="cursor-pointer font-medium">
            {t("measured", { count: data.measured.length })} <EvidenceTag status="Experimental" />
          </summary>
          <div className="mt-1 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-muted">
                <tr>
                  <th className="py-1 pr-2 font-normal">{t("source")}</th>
                  <th className="py-1 pr-2 font-normal">{t("form")}</th>
                  <th className="py-1 pr-2 font-normal">n(450)</th>
                  <th className="py-1 pr-2 font-normal">n(550)</th>
                  <th className="py-1 pr-2 font-normal">n(650)</th>
                  <th className="py-1 font-normal">k(550)</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {data.measured.map((m) => (
                  <tr key={m.url} className="border-t border-line">
                    <td className="py-1 pr-2">
                      <a href={m.url} target="_blank" rel="noreferrer" className="text-accent underline">
                        {m.title}
                      </a>
                      {m.doi && <div className="font-mono text-muted">doi:{m.doi}</div>}
                    </td>
                    <td className="py-1 pr-2">
                      {m.category || "—"}
                      {m.direction && ` (${m.direction})`}
                    </td>
                    <td className="py-1 pr-2">{fmt(m.n_450)}</td>
                    <td className="py-1 pr-2 font-medium">{fmt(m.n_550)}</td>
                    <td className="py-1 pr-2">{fmt(m.n_650)}</td>
                    <td className="py-1">{m.k_550 == null ? "—" : m.k_550}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      {data.computed.length > 0 && (
        <details>
          <summary className="cursor-pointer font-medium">
            {t("computed", { count: data.computed.length })} <EvidenceTag status="DFT-computed" />
          </summary>
          <p className="mt-1 text-xs text-muted">{t("computedNote")}</p>
          <div className="mt-1 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-muted">
                <tr>
                  <th className="py-1 pr-2 font-normal">JARVIS</th>
                  <th className="py-1 pr-2 font-normal">{t("spacegroup")}</th>
                  <th className="py-1 pr-2 font-normal">{t("gapOpt")}</th>
                  <th className="py-1 pr-2 font-normal">{t("gapMbj")}</th>
                  <th className="py-1 pr-2 font-normal">n (OptB88vdW)</th>
                  <th className="py-1 font-normal">n (TBmBJ)</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {data.computed.map((c) => (
                  <tr key={c.jid} className="border-t border-line">
                    <td className="py-1 pr-2">
                      <a href={c.url} target="_blank" rel="noreferrer" className="text-accent underline">
                        {c.jid}
                      </a>
                      {c.mp_id && <div className="font-mono text-muted">{c.mp_id}</div>}
                    </td>
                    <td className="py-1 pr-2">
                      {c.spacegroup ?? "—"}
                      {c.has_icsd && <span className="ml-1 text-muted">ICSD</span>}
                    </td>
                    <td className="py-1 pr-2">{fmt(c.band_gap_optb88vdw)}</td>
                    <td className="py-1 pr-2">{fmt(c.band_gap_mbj)}</td>
                    <td className="py-1 pr-2">{fmt(c.n_optb88vdw)}</td>
                    <td className="py-1">{fmt(c.n_mbj)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      <p className="text-xs text-muted">{data.note}</p>
    </div>
  );
}
