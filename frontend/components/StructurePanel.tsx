"use client";

import { useTranslations } from "next-intl";
import { CrystalViewer } from "@/components/CrystalViewer";
import type { MaterialRecord, StructurePayload } from "@/lib/api";

type Props = {
  structure: StructurePayload | null;
  record: MaterialRecord | null;
  loading: boolean;
  error: string | null;
};

export function StructurePanel({ structure, record, loading, error }: Props) {
  const t = useTranslations("Structure");

  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      <h2 className="mb-3 font-semibold">
        {t("title")}
        {structure && `: ${structure.formula}`}
      </h2>

      {loading && <p className="text-muted">{t("loading")}</p>}
      {error && <p className="text-sm text-danger">{error}</p>}
      {!loading && !error && !structure && <p className="text-muted">{t("empty")}</p>}

      {structure && !loading && (
        <div className="grid gap-4 md:grid-cols-[2fr_1fr]">
          <CrystalViewer cif={structure.cif} />
          <dl className="space-y-2 text-sm">
            <div>
              <dt className="text-muted">{t("spacegroup")}</dt>
              <dd>
                {structure.spacegroup ?? "—"}
                {structure.spacegroup_number && ` (#${structure.spacegroup_number})`}
              </dd>
            </div>
            <div>
              <dt className="text-muted">{t("lattice")}</dt>
              <dd className="font-mono text-xs tabular-nums">
                a={structure.lattice.a} b={structure.lattice.b} c={structure.lattice.c} Å
                <br />
                α={structure.lattice.alpha} β={structure.lattice.beta} γ={structure.lattice.gamma}°
                <br />V={structure.lattice.volume} Å³
              </dd>
            </div>
            <div>
              <dt className="text-muted">{t("sites")}</dt>
              <dd>{structure.sites.length}</dd>
            </div>
            <div>
              <dt className="text-muted">{t("source")}</dt>
              <dd>
                {record ? (
                  <a href={record.url} target="_blank" rel="noreferrer" className="text-accent underline">
                    {structure.provenance.source} · {record.material_id}
                  </a>
                ) : (
                  `${structure.provenance.source} · ${structure.provenance.reference ?? ""}`
                )}
              </dd>
            </div>
            {structure.warnings.length > 0 && (
              <div>
                <dt className="text-warning">{t("warnings")}</dt>
                <dd>
                  <ul className="list-disc pl-4 text-xs">
                    {structure.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </dd>
              </div>
            )}
          </dl>
        </div>
      )}
    </section>
  );
}
