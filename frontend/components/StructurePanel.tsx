"use client";

import { useTranslations } from "next-intl";
import { AssessmentPanel } from "@/components/AssessmentPanel";
import { CrystalViewer } from "@/components/CrystalViewer";
import { Advanced, useLevel } from "@/components/Level";
import { OpticalPanel } from "@/components/OpticalPanel";
import { HostScore } from "@/components/PlainResult";
import { Term } from "@/components/Term";
import type { Goal, MaterialRecord, StructuralAssessment, StructurePayload } from "@/lib/api";

type Props = {
  structure: StructurePayload | null;
  record: MaterialRecord | null;
  assessment: StructuralAssessment | null;
  loading: boolean;
  error: string | null;
  goal?: Goal;
};

export function StructurePanel({ structure, record, assessment, loading, error, goal }: Props) {
  const t = useTranslations("Structure");
  const guided = useLevel().level === "guided";

  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      <h2 className="mb-3 font-semibold">
        {guided ? t("titleGuided") : t("title")}
        {structure && `: ${structure.formula}`}
      </h2>

      {loading && <p className="text-muted">{t("loading")}</p>}
      {error && <p className="text-sm text-danger">{error}</p>}
      {!loading && !error && !structure && <p className="text-muted">{guided ? t("emptyGuided") : t("empty")}</p>}

      {structure && !loading && (
        <div className="grid gap-4 md:grid-cols-[2fr_1fr]">
          <CrystalViewer cif={structure.cif} />
          <div className="space-y-3">
            {guided && (
              <p className="text-sm">
                {t("howToRead.before")} <Term id="cell">{t("howToRead.term")}</Term> {t("howToRead.after")}
              </p>
            )}
            <Advanced label={t("details")}>
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
            </Advanced>
          </div>
        </div>
      )}

      {structure && !loading && guided && goal && (
        <div className="mt-4">
          <HostScore goal={goal} formula={structure.formula} />
        </div>
      )}

      {structure && !loading && (
        <div className="mt-4 space-y-4">
          <Advanced label={t("evidenceDetails")}>
            <div>
              <h3 className="mb-1 text-sm font-medium">{t("optical")}</h3>
              <OpticalPanel key={structure.formula} formula={structure.formula} />
            </div>
            {assessment && (
              <div>
                <h3 className="mb-1 text-sm font-medium">{t("baseline")}</h3>
                <AssessmentPanel assessment={assessment} />
              </div>
            )}
          </Advanced>
        </div>
      )}
    </section>
  );
}
