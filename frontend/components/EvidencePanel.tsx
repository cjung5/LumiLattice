"use client";

import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import { DispersionChart } from "@/components/charts/DispersionChart";
import { LandscapeChart, type MarkedPoint, type RangeBox } from "@/components/charts/LandscapeChart";
import { SiteMetricsChart } from "@/components/charts/SiteMetricsChart";
import { ScoreCard } from "@/components/ScoreCard";
import { useLevel } from "@/components/Level";
import { SpatialPanel } from "@/components/SpatialPanel";
import {
  getDispersion,
  getLandscape,
  scoreGoal,
  type Candidate,
  type DispersionData,
  type Goal,
  type GoalScore,
  type HostRef,
  type Landscape,
  type StructuralAssessment,
} from "@/lib/api";

type Tab = "score" | "landscape" | "dispersion" | "sites" | "spatial";

type Props = {
  goal: Goal;
  host: HostRef | null;
  hostFormula: string | null;
  hostAssessment: StructuralAssessment | null;
  candidate: Candidate | null;
};

let landscapeCache: Promise<Landscape> | null = null;

/** One shared request per page. A failure is not cached, and it gets one retry. */
function loadLandscape(): Promise<Landscape> {
  landscapeCache ??= getLandscape()
    .catch(() => new Promise((wait) => setTimeout(wait, 1000)).then(getLandscape))
    .catch((err) => {
      landscapeCache = null;
      throw err;
    });
  return landscapeCache;
}

/** Debounced async load that ignores stale responses. */
function useLoad<T>(key: string | null, load: () => Promise<T>, delay = 300): T | null {
  const [value, setValue] = useState<{ key: string; data: T } | null>(null);
  useEffect(() => {
    if (!key) return;
    let active = true;
    const timer = setTimeout(() => {
      load()
        .then((data) => active && setValue({ key, data }))
        .catch(() => undefined);
    }, delay);
    return () => {
      active = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return value && value.key === key ? value.data : null;
}

export function EvidencePanel({ goal, host, hostFormula, hostAssessment, candidate }: Props) {
  const t = useTranslations("Evidence");
  const guided = useLevel().level === "guided";
  const [selectedTab, setTab] = useState<Tab>("landscape");
  // Guided mode keeps the two views that need no background; Expert mode has the others.
  const tab: Tab = guided && (selectedTab === "dispersion" || selectedTab === "sites" || selectedTab === "spatial") ? "landscape" : selectedTab;
  const [relaxedView, setRelaxedView] = useState(false);
  const goalKey = JSON.stringify(goal);

  const landscape = useLoad("landscape", loadLandscape, 0);
  const hostScore = useLoad<GoalScore>(hostFormula ? `${hostFormula}|${goalKey}` : null, () => scoreGoal(goal, { formula: hostFormula! }));
  const candidateScore = useLoad<GoalScore>(
    candidate ? `${candidate.candidate_id}|${goalKey}` : null,
    () => scoreGoal(goal, { candidate_id: candidate!.candidate_id }),
  );

  const endMembers = useMemo(
    () => candidate?.optical_estimate?.end_members.map((m) => m.formula) ?? [],
    [candidate],
  );
  const formulas = [...new Set([hostFormula, ...endMembers].filter((f): f is string => !!f))].slice(0, 4);
  const dispersion = useLoad<DispersionData[]>(formulas.length ? formulas.join(",") : null, () => getDispersion(formulas));

  const points: MarkedPoint[] = [];
  const hostN = hostScore?.criteria.find((c) => c.id === "n")?.evidence;
  const hostGap = hostScore?.criteria.find((c) => c.id === "band_gap")?.evidence;
  if (hostFormula && hostN?.value != null && hostGap?.value != null) {
    points.push({ label: hostFormula, n: hostN.value, gap: hostGap.value, nStatus: hostN.status, gapStatus: hostGap.status, role: "host" });
  }
  for (const m of candidate?.optical_estimate?.end_members ?? []) {
    if (m.formula !== hostFormula && m.n.value != null && m.band_gap?.value != null) {
      points.push({ label: m.formula, n: m.n.value, gap: m.band_gap.value, nStatus: m.n.status, gapStatus: m.band_gap.status, role: "end" });
    }
  }
  const est = candidate?.optical_estimate;
  const box: RangeBox | null =
    candidate && est?.estimate.value_range && est.band_gap?.value_range
      ? { label: candidate.candidate_id, n: est.estimate.value_range, gap: est.band_gap.value_range }
      : null;

  const relaxation = candidate?.relaxation ?? null;
  const siteAssessment = candidate
    ? relaxedView && relaxation
      ? relaxation.assessment
      : candidate.assessment
    : hostAssessment;
  const siteSubject = candidate
    ? `${candidate.candidate_id}${relaxedView && relaxation ? ` (${t("relaxed")})` : ""}`
    : (hostFormula ?? "");

  const tabs: { id: Tab; label: string }[] = [
    { id: "landscape", label: t("tabLandscape") },
    ...(guided
      ? []
      : ([
          { id: "dispersion", label: t("tabDispersion") },
          { id: "sites", label: t("tabSites") },
          { id: "spatial", label: t("tabSpatial") },
        ] as const)),
    { id: "score", label: t("tabScore") },
  ];

  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      <h2 className="font-semibold">{guided ? t("titleGuided") : t("title")}</h2>
      <p className="mb-3 text-sm text-muted">{guided ? t("hintGuided") : t("hint")}</p>
      <div className="mb-3 flex flex-wrap gap-2" role="tablist">
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
            className={`rounded-md px-3 py-1 text-sm ${tab === item.id ? "bg-accent text-white" : "border border-line"}`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {guided && <p className="mb-2 text-sm">{t(tab === "score" ? "readScore" : "readLandscape")}</p>}
      {tab === "score" && (
        <div className="grid gap-3 md:grid-cols-2">
          {hostScore && <ScoreCard score={hostScore} title={t("hostScore", { formula: hostFormula ?? "" })} />}
          {candidateScore && <ScoreCard score={candidateScore} title={t("candidateScore", { id: candidate?.candidate_id ?? "" })} />}
          {!hostScore && !candidateScore && <p className="text-sm text-muted">{t("needSubject")}</p>}
        </div>
      )}
      {tab === "landscape" && (landscape ? <LandscapeChart data={landscape} goal={goal} points={points} box={box} /> : <p className="text-sm text-muted">{t("loading")}</p>)}
      {tab === "dispersion" &&
        (dispersion ? (
          <DispersionChart
            data={dispersion}
            primary={hostFormula}
            bandLabel={candidate && est?.estimate.status === "Heuristic" ? candidate.candidate_id : null}
            bandFormulas={endMembers}
          />
        ) : (
          <p className="text-sm text-muted">{formulas.length ? t("loading") : t("needSubject")}</p>
        ))}
      {tab === "spatial" && <SpatialPanel candidate={candidate} host={host} hostFormula={hostFormula} />}
      {tab === "sites" && (
        <div className="space-y-2">
          {relaxation && (
            <div className="flex gap-1 text-xs">
              <button type="button" onClick={() => setRelaxedView(false)} className={`rounded px-2 py-0.5 ${!relaxedView ? "bg-accent text-white" : "border border-line"}`}>{t("unrelaxed")}</button>
              <button type="button" onClick={() => setRelaxedView(true)} className={`rounded px-2 py-0.5 ${relaxedView ? "bg-accent text-white" : "border border-line"}`}>{t("relaxed")}</button>
            </div>
          )}
          {siteAssessment && siteAssessment.site_metrics?.length ? (
            <SiteMetricsChart metrics={siteAssessment.site_metrics} thresholds={siteAssessment.thresholds} subject={siteSubject} />
          ) : (
            <p className="text-sm text-muted">{t("needSubject")}</p>
          )}
        </div>
      )}
    </section>
  );
}
