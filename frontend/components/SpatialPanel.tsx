"use client";

import { useTranslations } from "next-intl";
import { useBackendText } from "@/lib/backendText";
import { useEffect, useState } from "react";
import { ChartFrame, scale, svgPoint, ticks, Tooltip } from "@/components/charts/ChartFrame";
import {
  getCandidateSpatial,
  getHostSpatial,
  type Candidate,
  type HostRef,
  type Linkages,
  type Polyhedron,
  type SpatialAnalysis,
  type SymmetryInfo,
} from "@/lib/api";

type Props = { candidate: Candidate | null; host: HostRef | null; hostFormula: string | null };
type State = "before" | "after" | "relaxed";

// A surface-colored outline keeps labels legible where they cross marks.
const HALO = { stroke: "var(--chart-surface)", strokeWidth: 3, paintOrder: "stroke" as const, strokeLinejoin: "round" as const };

// Three states of the same sites; told apart by shape and fill as well as color.
// Each state sits slightly above/below the row center so equal values stay visible.
const OFFSET: Record<State, number> = { before: -9, after: 0, relaxed: 9 };
const MARK: Record<State, { fill: string; stroke: string; shape: "circle" | "square" }> = {
  before: { fill: "none", stroke: "var(--chart-muted)", shape: "circle" },
  after: { fill: "var(--chart-ink-2)", stroke: "var(--chart-surface)", shape: "circle" },
  relaxed: { fill: "var(--accent)", stroke: "var(--chart-surface)", shape: "square" },
};

function Mark({ state, x, y }: { state: State; x: number; y: number }) {
  const m = MARK[state];
  return m.shape === "square" ? (
    <rect x={x - 5} y={y - 5} width="10" height="10" rx="2" fill={m.fill} stroke={m.stroke} strokeWidth="2" />
  ) : (
    <circle cx={x} cy={y} r="5" fill={m.fill} stroke={m.stroke} strokeWidth="2" />
  );
}

function SymmetryChip({ info, label }: { info: SymmetryInfo | null; label: string }) {
  const t = useTranslations("Spatial");
  if (!info) return null;
  return (
    <div className="rounded-lg border border-line px-3 py-2 text-xs">
      <div className="text-muted">{label}</div>
      <div className="text-sm font-semibold">{info.spacegroup ?? "—"}</div>
      <div>
        {info.crystal_system ? t(`system.${info.crystal_system}`) : "—"} · {info.optical_class ? t(`optical.${info.optical_class}`) : "—"}
      </div>
    </div>
  );
}

function useSpatial(candidate: Candidate | null, host: HostRef | null) {
  const [data, setData] = useState<Partial<Record<State, SpatialAnalysis>> & { key?: string }>({});
  const key = candidate ? `${candidate.candidate_id}|${!!candidate.relaxation}` : host ? JSON.stringify(host).slice(0, 200) : "";
  useEffect(() => {
    if (!key) return;
    let active = true;
    (async () => {
      if (candidate) {
        const after = await getCandidateSpatial(candidate.candidate_id);
        const relaxed = candidate.relaxation ? await getCandidateSpatial(candidate.candidate_id, true) : undefined;
        if (active) setData({ key, after, relaxed });
      } else if (host) {
        const before = await getHostSpatial(host);
        if (active) setData({ key, before });
      }
    })().catch(() => undefined);
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return data.key === key ? data : {};
}

export function SpatialPanel({ candidate, host, hostFormula }: Props) {
  const t = useTranslations("Spatial");
  const tb = useBackendText();
  const data = useSpatial(candidate, host);
  const main = data.after ?? data.before;
  if (!main) return <p className="text-sm text-muted">{t("loading")}</p>;

  // Rows of polyhedra: before (the same site before substitution), after, relaxed.
  const rows: { site: string; values: Partial<Record<State, Polyhedron>> }[] = [];
  const add = (state: State, list: Polyhedron[] | undefined) =>
    (list ?? []).forEach((p, i) => {
      const site = data.after ? `${data.after.polyhedra[i]?.element ?? p.element}${p.index}` : `${p.element}${p.index}`;
      const row = rows.find((r) => r.site === site) ?? rows[rows.push({ site, values: {} }) - 1];
      row.values[state] = p;
    });
  if (data.after) {
    add("before", data.after.parent_polyhedra);
    add("after", data.after.polyhedra);
    add("relaxed", data.relaxed?.polyhedra);
  } else {
    add("before", data.before?.polyhedra);
  }

  const linkRows: { state: State; links: Linkages }[] = [];
  if (data.after?.parent_linkages) linkRows.push({ state: "before", links: data.after.parent_linkages });
  if (data.after) linkRows.push({ state: "after", links: data.after.linkages });
  if (data.relaxed) linkRows.push({ state: "relaxed", links: data.relaxed.linkages });
  if (!data.after && data.before) linkRows.push({ state: "before", links: data.before.linkages });

  const states = (["before", "after", "relaxed"] as State[]).filter((s) => rows.some((r) => r.values[s]) || linkRows.some((r) => r.state === s));
  const legend = states.map((s) => ({ label: t(`state.${s}`), kind: "dot" as const, color: s === "before" ? "var(--chart-muted)" : MARK[s].fill }));
  // Relaxed findings compare the relaxed geometry with the unrelaxed candidate.
  const findings = [...(data.after?.findings ?? data.before?.findings ?? []).map(tb), ...(data.relaxed?.findings ?? []).map((f) => `${t("state.relaxed")}: ${tb(f)}`)];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <SymmetryChip info={data.after?.parent_symmetry ?? data.before?.symmetry ?? null} label={data.after ? t("state.before") : (hostFormula ?? t("state.before"))} />
        {data.after && <span aria-hidden>→</span>}
        {data.after && <SymmetryChip info={data.after.symmetry} label={t("state.after")} />}
        {data.relaxed && <span aria-hidden>→</span>}
        {data.relaxed && <SymmetryChip info={data.relaxed.symmetry} label={t("state.relaxed")} />}
      </div>
      {findings.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-5 text-sm">
          {findings.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        <DistortionChart rows={rows} states={states} legend={legend} />
        <AngleChart rows={linkRows} legend={legend} />
      </div>
      {data.after?.ordering && <OrderingChart ordering={data.after.ordering} label={candidate?.candidate_id ?? ""} />}
      {data.after && data.after.dopants.length > 0 && (
        <table className="w-full text-left text-xs tabular-nums">
          <thead className="text-muted">
            <tr>
              <th className="py-1 pr-2 font-normal">{t("dopant")}</th>
              <th className="py-1 pr-2 font-normal">{t("sites")}</th>
              <th className="py-1 pr-2 font-normal">{t("nearest")}</th>
              <th className="py-1 font-normal">{t("spacing")}</th>
            </tr>
          </thead>
          <tbody>
            {data.after.dopants.map((d) => (
              <tr key={d.element} className="border-t border-line">
                <td className="py-0.5 pr-2">{d.element}</td>
                <td className="py-0.5 pr-2">{d.sites.join(", ")}</td>
                <td className="py-0.5 pr-2">{d.nearest_distances.join(", ")} Å</td>
                <td className="py-0.5">{d.cation_spacing} Å</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <ul className="list-disc pl-5 text-xs text-muted">
        {main.notes.map((n) => (
          <li key={n}>{tb(n)}</li>
        ))}
      </ul>
    </div>
  );
}

const W = 320;
const ROW = 34;
const M = { l: 64, r: 16, t: 10, b: 30 };

function DistortionChart({ rows, states, legend }: { rows: { site: string; values: Partial<Record<State, Polyhedron>> }[]; states: State[]; legend: { label: string; kind: "dot"; color: string }[] }) {
  const t = useTranslations("Spatial");
  const tb = useBackendText();
  const H = M.t + M.b + Math.max(rows.length, 1) * ROW;
  const max = Math.max(0.02, ...rows.flatMap((r) => Object.values(r.values).map((p) => p!.distortion_index))) * 1.15;
  const x = scale([0, max], [M.l, W - M.r]);
  const table = (
    <table className="w-full text-left text-xs tabular-nums">
      <thead className="text-muted">
        <tr>
          <th className="py-1 pr-2 font-normal">{t("site")}</th>
          <th className="py-1 pr-2 font-normal">{t("stateCol")}</th>
          <th className="py-1 pr-2 font-normal">{t("shape")}</th>
          <th className="py-1 pr-2 font-normal">Δ</th>
          <th className="py-1 pr-2 font-normal">⟨λ⟩</th>
          <th className="py-1 pr-2 font-normal">σ² (°²)</th>
          <th className="py-1 font-normal">V (Å³)</th>
        </tr>
      </thead>
      <tbody>
        {rows.flatMap((r) =>
          states.filter((s) => r.values[s]).map((s) => {
            const p = r.values[s]!;
            return (
              <tr key={`${r.site}${s}`} className="border-t border-line">
                <td className="py-0.5 pr-2">{r.site}</td>
                <td className="py-0.5 pr-2">{t(`state.${s}`)}</td>
                <td className="py-0.5 pr-2">{p.element}, CN {p.coordination}, {tb(p.shape)}{p.shape_score != null ? ` (${p.shape_score})` : ""}</td>
                <td className="py-0.5 pr-2">{p.distortion_index}</td>
                <td className="py-0.5 pr-2">{p.quadratic_elongation ?? "—"}</td>
                <td className="py-0.5 pr-2">{p.bond_angle_variance ?? "—"}</td>
                <td className="py-0.5">{p.volume ?? "—"}</td>
              </tr>
            );
          }),
        )}
      </tbody>
    </table>
  );
  return (
    <ChartFrame title={t("distortionTitle")} subtitle={t("distortionSubtitle")} legend={legend} notes={[t("distortionNote")]} table={table}>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={t("distortionTitle")}>
        <rect x={x(0.02)} y={M.t} width={W - M.r - x(0.02)} height={H - M.t - M.b} fill="var(--status-warning)" fillOpacity="0.1" />
        {ticks(0, max, 4).map((v) => (
          <g key={v}>
            <line x1={x(v)} x2={x(v)} y1={M.t} y2={H - M.b} stroke="var(--chart-grid)" />
            <text x={x(v)} y={H - M.b + 14} textAnchor="middle" fontSize="10" fill="var(--chart-muted)">{v}</text>
          </g>
        ))}
        <text x={(M.l + W - M.r) / 2} y={H - 4} textAnchor="middle" fontSize="10" fill="var(--chart-ink-2)">{t("distortionAxis")}</text>
        {rows.map((r, i) => {
          const cy = M.t + i * ROW + ROW / 2;
          return (
            <g key={r.site}>
              <text x={M.l - 6} y={cy + 4} textAnchor="end" fontSize="11" fill="var(--chart-ink)">{r.site}</text>
              {states.map((s) => (r.values[s] ? <Mark key={s} state={s} x={x(r.values[s]!.distortion_index)} y={cy + OFFSET[s]} /> : null))}
            </g>
          );
        })}
      </svg>
    </ChartFrame>
  );
}

function AngleChart({ rows, legend }: { rows: { state: State; links: Linkages }[]; legend: { label: string; kind: "dot"; color: string }[] }) {
  const t = useTranslations("Spatial");
  const all = rows.flatMap((r) => r.links.bxb_angles);
  const H = M.t + M.b + Math.max(rows.length, 1) * ROW;
  if (!all.length) {
    return (
      <ChartFrame title={t("angleTitle")} subtitle={t("angleSubtitle")} table={<p className="text-xs text-muted">{t("noAngles")}</p>}>
        <p className="py-6 text-center text-sm text-muted">{t("noAngles")}</p>
      </ChartFrame>
    );
  }
  const lo = Math.min(...all);
  const x = scale([Math.min(lo - 2, 170), 180.5], [M.l, W - M.r]);
  const table = (
    <table className="w-full text-left text-xs tabular-nums">
      <thead className="text-muted">
        <tr>
          <th className="py-1 pr-2 font-normal">{t("stateCol")}</th>
          <th className="py-1 pr-2 font-normal">{t("links")}</th>
          <th className="py-1 pr-2 font-normal">{t("angles")}</th>
          <th className="py-1 font-normal">{t("tilt")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.state} className="border-t border-line">
            <td className="py-0.5 pr-2">{t(`state.${r.state}`)}</td>
            <td className="py-0.5 pr-2">{t("linkCounts", { corner: r.links.corner, edge: r.links.edge, face: r.links.face })}</td>
            <td className="py-0.5 pr-2">{[...new Set(r.links.bxb_angles)].join(", ")}°</td>
            <td className="py-0.5">{r.links.mean_tilt == null ? "—" : `${r.links.mean_tilt}°`}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
  return (
    <ChartFrame title={t("angleTitle")} subtitle={t("angleSubtitle")} legend={legend.filter((l) => rows.some((r) => t(`state.${r.state}`) === l.label))} notes={[t("angleNote")]} table={table}>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={t("angleTitle")}>
        {ticks(x.invert(M.l), 180, 4).map((v) => (
          <g key={v}>
            <line x1={x(v)} x2={x(v)} y1={M.t} y2={H - M.b} stroke="var(--chart-grid)" />
            <text x={x(v)} y={H - M.b + 14} textAnchor="middle" fontSize="10" fill="var(--chart-muted)">{v}°</text>
          </g>
        ))}
        <text x={(M.l + W - M.r) / 2} y={H - 4} textAnchor="middle" fontSize="10" fill="var(--chart-ink-2)">{t("angleAxis")}</text>
        {rows.map((r, i) => {
          const cy = M.t + i * ROW + ROW / 2;
          const unique = [...new Set(r.links.bxb_angles)];
          return (
            <g key={r.state}>
              <text x={M.l - 6} y={cy + 4} textAnchor="end" fontSize="11" fill="var(--chart-ink)">{t(`stateShort.${r.state}`)}</text>
              {unique.map((a) => <Mark key={a} state={r.state} x={x(a)} y={cy} />)}
            </g>
          );
        })}
      </svg>
    </ChartFrame>
  );
}

const BINS = 32;

function OrderingChart({ ordering, label }: { ordering: NonNullable<SpatialAnalysis["ordering"]>; label: string }) {
  const t = useTranslations("Spatial");
  const tb = useBackendText();
  const [hover, setHover] = useState<{ bin: number; px: number; py: number; width: number } | null>(null);
  const W2 = 640;
  const H = 170;
  const m = { l: 40, r: 16, t: 28, b: 36 };
  const counts = new Map<number, number>();
  ordering.energies.forEach((e) => counts.set(e, (counts.get(e) ?? 0) + 1));
  const levels = [...counts.entries()].sort((a, b) => a[0] - b[0]);
  // Fixed-width energy bins, so close energies never draw on top of each other.
  const hi = Math.max(1, ...ordering.energies) * 1.02;
  const step = hi / BINS;
  const binOf = (e: number) => Math.min(BINS - 1, Math.floor(e / step));
  const bins = Array.from({ length: BINS }, () => 0);
  ordering.energies.forEach((e) => bins[binOf(e)]++);
  const chosenBin = binOf(ordering.chosen);
  const maxCount = Math.max(...bins);
  const x = scale([0, hi], [m.l, W2 - m.r]);
  const y = scale([0, maxCount], [H - m.b, m.t]);
  const barW = x(step) - x(0) - 2;
  const cx = x(ordering.chosen);
  const anchor = cx > W2 * 0.8 ? "end" : cx < W2 * 0.2 ? "start" : "middle";

  function onMove(event: React.PointerEvent<SVGRectElement>) {
    const p = svgPoint(event, W2, H);
    const bin = Math.floor(x.invert(p.x) / step);
    setHover(bin >= 0 && bin < BINS && bins[bin] ? { bin, px: p.x * p.scaleX, py: p.y * p.scaleY, width: W2 * p.scaleX } : null);
  }

  const table = (
    <table className="w-full text-left text-xs tabular-nums">
      <thead className="text-muted">
        <tr>
          <th className="py-1 pr-2 font-normal">ΔE (meV/atom)</th>
          <th className="py-1 font-normal">{t("count")}</th>
        </tr>
      </thead>
      <tbody>
        {levels.map(([e, c]) => (
          <tr key={e} className="border-t border-line">
            <td className="py-0.5 pr-2">{e}{Math.abs(e - ordering.chosen) < 0.01 ? ` ← ${label}` : ""}</td>
            <td className="py-0.5">{c}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
  return (
    <ChartFrame
      title={t("orderingTitle")}
      subtitle={t("orderingSubtitle", { total: ordering.total, distinct: ordering.distinct, cell: ordering.analysis_cell.join("×") })}
      legend={[
        { label: t("otherOrderings"), kind: "box", color: "var(--chart-muted)" },
        { label: t("thisOrdering", { id: label }), kind: "box", color: "var(--accent)" },
      ]}
      notes={[tb(ordering.method), ...(ordering.truncated ? [t("sampled")] : [])]}
      table={table}
    >
      {ordering.distinct === 1 ? (
        <p className="py-4 text-center text-sm text-muted">{t("allEqual")}</p>
      ) : (
        <div className="relative max-sm:overflow-x-auto">
          <svg viewBox={`0 0 ${W2} ${H}`} className="w-full max-sm:min-w-[40rem]" role="img" aria-label={t("orderingTitle")}>
            {ticks(0, hi, 6).map((v) => (
              <g key={`x${v}`}>
                <line x1={x(v)} x2={x(v)} y1={m.t} y2={H - m.b} stroke="var(--chart-grid)" />
                <text x={x(v)} y={H - m.b + 14} textAnchor="middle" fontSize="11" fill="var(--chart-muted)">{v}</text>
              </g>
            ))}
            {ticks(0, maxCount, 3).filter((v) => Number.isInteger(v) && v > 0).map((v) => (
              <text key={`y${v}`} x={m.l - 6} y={y(v) + 4} textAnchor="end" fontSize="11" fill="var(--chart-muted)">{v}</text>
            ))}
            <line x1={m.l} x2={W2 - m.r} y1={H - m.b} y2={H - m.b} stroke="var(--chart-axis)" />
            <text x={(m.l + W2 - m.r) / 2} y={H - 6} textAnchor="middle" fontSize="11" fill="var(--chart-ink-2)">{t("orderingAxis")}</text>
            {bins.map((c, i) =>
              c ? (
                <path
                  key={i}
                  d={roundTop(x(i * step) + 1, y(c), Math.max(barW, 2), H - m.b - y(c), 3)}
                  fill={i === chosenBin ? "var(--accent)" : "var(--chart-muted)"}
                  fillOpacity={i === chosenBin ? 1 : hover?.bin === i ? 0.9 : 0.6}
                />
              ) : null,
            )}
            <line x1={cx} x2={cx} y1={m.t - 6} y2={H - m.b} stroke="var(--accent)" strokeWidth="2" strokeDasharray="3 3" />
            <text x={cx} y={m.t - 10} textAnchor={anchor} fontSize="11" fontWeight="600" fill="var(--chart-ink)" {...HALO}>
              {t("thisOrdering", { id: label })} · {ordering.chosen} meV/atom
            </text>
            <rect x={m.l} y={m.t} width={W2 - m.l - m.r} height={H - m.t - m.b} fill="transparent" onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
          </svg>
          {hover && (
            <Tooltip x={hover.px} y={hover.py} width={hover.width}>
              <div className="font-semibold tabular-nums">{t("count")}: {bins[hover.bin]}</div>
              <div className="tabular-nums" style={{ color: "var(--chart-ink-2)" }}>
                ΔE {(hover.bin * step).toFixed(1)}–{((hover.bin + 1) * step).toFixed(1)} meV/atom
              </div>
            </Tooltip>
          )}
        </div>
      )}
    </ChartFrame>
  );
}

/** Bar with rounded top corners only, anchored flat on the baseline. */
function roundTop(x: number, y: number, w: number, h: number, r: number) {
  const k = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + k}Q${x},${y} ${x + k},${y}H${x + w - k}Q${x + w},${y} ${x + w},${y + k}V${y + h}Z`;
}
