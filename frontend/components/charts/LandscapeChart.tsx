"use client";

import { useTranslations } from "next-intl";
import { useBackendText } from "@/lib/backendText";
import { useMemo, useState } from "react";
import { ChartFrame, scale, svgPoint, ticks, Tooltip } from "@/components/charts/ChartFrame";
import type { EvidenceStatus, Goal, Landscape } from "@/lib/api";

export type MarkedPoint = {
  label: string;
  n: number;
  gap: number;
  nStatus: EvidenceStatus;
  gapStatus: EvidenceStatus;
  role: "host" | "end";
};

export type RangeBox = {
  label: string;
  n: [number, number];
  gap: [number, number];
  /** The linear-mix guess, inside the box. */
  mix?: { n: number; gap: number } | null;
};

type Props = {
  data: Landscape;
  goal: Goal;
  points: MarkedPoint[];
  box: RangeBox | null;
};

const W = 640;
const H = 400;
const M = { l: 48, r: 14, t: 12, b: 40 };
const X: [number, number] = [0, 9];
const Y: [number, number] = [1.2, 3.6];
// A surface-colored outline keeps labels legible where they cross points.
const HALO = { stroke: "var(--chart-surface)", strokeWidth: 3, paintOrder: "stroke" as const, strokeLinejoin: "round" as const };
const statusColor = (s: EvidenceStatus) =>
  s === "Experimental" ? "var(--series-exp)" : s === "DFT-computed" ? "var(--series-dft)" : "var(--chart-muted)";

type Hover = { px: number; py: number; label: string; n: number; gap: number; source: string };

export function LandscapeChart({ data, goal, points, box }: Props) {
  const t = useTranslations("Charts");
  const tb = useBackendText();
  const x = scale(X, [M.l, W - M.r]);
  const y = scale(Y, [H - M.b, M.t]);
  const [hover, setHover] = useState<Hover | null>(null);

  const inside = (g: number, n: number) => g >= X[0] && g <= X[1] && n >= Y[0] && n <= Y[1];
  const computed = useMemo(() => data.computed.filter(([g, n]) => inside(g, n)), [data.computed]);
  const measured = data.measured.filter((p) => inside(p.band_gap, p.n));
  const hidden = data.measured.length - measured.length;
  const mossPath = data.moss
    .filter(([g, n]) => inside(g, n))
    .map(([g, n], i) => `${i ? "L" : "M"}${x(g).toFixed(1)},${y(n).toFixed(1)}`)
    .join("");

  // Nearest labeled point (measured materials, host, end members) within 24 px.
  const targets = useMemo(
    () => [
      ...measured.map((p) => ({ label: p.formula, n: p.n, gap: p.band_gap, source: t(p.gap_measured ? "srcMeasuredBoth" : "srcMeasured") })),
      ...points.map((p) => ({ label: p.label, n: p.n, gap: p.gap, source: `n: ${p.nStatus} · gap: ${p.gapStatus}` })),
      ...(box?.mix ? [{ label: box.label, n: box.mix.n, gap: box.mix.gap, source: t("srcMix") }] : []),
    ],
    [measured, points, box, t],
  );

  function onMove(event: React.PointerEvent<SVGRectElement>) {
    const p = svgPoint(event, W, H);
    let best: (typeof targets)[number] | null = null;
    let bestD = 24 / p.scaleX;
    for (const target of targets) {
      const d = Math.hypot(x(target.gap) - p.x, y(target.n) - p.y);
      if (d < bestD) {
        bestD = d;
        best = target;
      }
    }
    setHover(best ? { px: x(best.gap) * p.scaleX, py: y(best.n) * p.scaleY, ...best } : null);
  }

  const goalX = x(Math.min(Math.max(goal.min_band_gap, X[0]), X[1]));
  const goalY = y(Math.min(Math.max(goal.target_n, Y[0]), Y[1]));

  const table = (
    <table className="w-full text-left text-xs tabular-nums">
      <thead style={{ color: "var(--chart-ink-2)" }}>
        <tr>
          <th className="py-1 pr-2 font-normal">{t("material")}</th>
          <th className="py-1 pr-2 font-normal">n (550 nm)</th>
          <th className="py-1 pr-2 font-normal">{t("gapColumn")}</th>
          <th className="py-1 pr-2 font-normal">{t("gapSource")}</th>
          <th className="py-1 font-normal">{t("inGoal")}</th>
        </tr>
      </thead>
      <tbody>
        {[...data.measured]
          .sort((a, b) => b.n - a.n)
          .map((p) => (
            <tr key={p.formula} className="border-t border-line">
              <td className="py-0.5 pr-2">{p.formula}</td>
              <td className="py-0.5 pr-2">{p.n}</td>
              <td className="py-0.5 pr-2">{p.band_gap}</td>
              <td className="py-0.5 pr-2">{p.gap_measured ? t("gapSourceMeasured") : "TBmBJ"}</td>
              <td className="py-0.5">{p.n >= goal.target_n && p.band_gap >= goal.min_band_gap ? "✓" : ""}</td>
            </tr>
          ))}
      </tbody>
    </table>
  );

  return (
    <ChartFrame
      title={t("landscapeTitle")}
      subtitle={t("landscapeSubtitle", { measured: data.measured.length, computed: data.computed_total })}
      legend={[
        { label: t("legendMeasuredBoth"), kind: "dot", color: "var(--series-exp)" },
        { label: t("legendMeasured"), kind: "ring", color: "var(--series-exp)" },
        { label: t("legendComputed"), kind: "dot", color: "var(--series-dft)" },
        ...(box ? [{ label: t("legendRange"), kind: "box" as const, color: "var(--series-heur)" }] : []),
        ...(box?.mix ? [{ label: t("legendMix"), kind: "diamond" as const, color: "var(--chart-ink)" }] : []),
        { label: t("legendGoal"), kind: "wash", color: "var(--chart-ink)" },
        { label: t("legendMoss"), kind: "line", color: "var(--chart-muted)" },
      ]}
      notes={[...data.notes.map(tb), ...(hidden ? [t("hiddenPoints", { count: hidden })] : [])]}
      table={table}
    >
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={t("landscapeTitle")}>
          {/* goal region */}
          <rect x={goalX} y={M.t} width={W - M.r - goalX} height={goalY - M.t} fill="var(--chart-ink)" fillOpacity="0.05" />
          <text x={W - M.r - 4} y={M.t + 12} textAnchor="end" fontSize="11" fill="var(--chart-ink-2)" {...HALO}>
            {t("goalRegion", { n: goal.target_n, gap: goal.min_band_gap })}
          </text>
          {/* grid and axes */}
          {ticks(X[0], X[1], 9).map((v) => (
            <g key={`x${v}`}>
              <line x1={x(v)} x2={x(v)} y1={M.t} y2={H - M.b} stroke="var(--chart-grid)" strokeWidth="1" />
              <text x={x(v)} y={H - M.b + 14} textAnchor="middle" fontSize="11" fill="var(--chart-muted)">{v}</text>
            </g>
          ))}
          {ticks(Y[0], Y[1], 6).map((v) => (
            <g key={`y${v}`}>
              <line x1={M.l} x2={W - M.r} y1={y(v)} y2={y(v)} stroke="var(--chart-grid)" strokeWidth="1" />
              <text x={M.l - 6} y={y(v) + 4} textAnchor="end" fontSize="11" fill="var(--chart-muted)">{v.toFixed(1)}</text>
            </g>
          ))}
          <line x1={M.l} x2={W - M.r} y1={H - M.b} y2={H - M.b} stroke="var(--chart-axis)" />
          <text x={(M.l + W - M.r) / 2} y={H - 6} textAnchor="middle" fontSize="11" fill="var(--chart-ink-2)">{t("axisGap")}</text>
          <text transform={`translate(12,${(M.t + H - M.b) / 2}) rotate(-90)`} textAnchor="middle" fontSize="11" fill="var(--chart-ink-2)">{t("axisN")}</text>
          {/* Moss relation */}
          <path d={mossPath} fill="none" stroke="var(--chart-muted)" strokeWidth="1.5" />
          {/* DFT cloud (context) */}
          {computed.map(([g, n], i) => (
            <circle key={i} cx={x(g)} cy={y(n)} r="1.8" fill="var(--series-dft)" fillOpacity="0.28" />
          ))}
          {/* measured materials */}
          {measured.map((p) =>
            p.gap_measured ? (
              <circle key={p.formula} cx={x(p.band_gap)} cy={y(p.n)} r="4" fill="var(--series-exp)" stroke="var(--chart-surface)" strokeWidth="2" />
            ) : (
              <circle key={p.formula} cx={x(p.band_gap)} cy={y(p.n)} r="3.5" fill="var(--chart-surface)" stroke="var(--series-exp)" strokeWidth="2" />
            ),
          )}
          {/* candidate range */}
          {box && (
            <g>
              <rect
                x={x(box.gap[0])}
                y={y(box.n[1])}
                width={Math.max(x(box.gap[1]) - x(box.gap[0]), 3)}
                height={Math.max(y(box.n[0]) - y(box.n[1]), 3)}
                rx="3"
                fill="var(--series-heur)"
                fillOpacity="0.14"
                stroke="var(--series-heur)"
                strokeWidth="2"
              />
              {/* Above the box: the host and end members are labeled inside and around it. */}
              <text
                x={x(box.gap[1])}
                y={Math.max(y(box.n[1]) - 6, M.t + 12)}
                textAnchor="end"
                fontSize="11"
                fontWeight="600"
                fill="var(--chart-ink)"
                {...HALO}
              >
                {box.label}
              </text>
            </g>
          )}
          {box?.mix && inside(box.mix.gap, box.mix.n) && (
            <path
              d={`M${x(box.mix.gap)} ${y(box.mix.n) - 6} l6 6 l-6 6 l-6 -6Z`}
              fill="var(--chart-surface)"
              stroke="var(--chart-ink)"
              strokeWidth="1.5"
            />
          )}
          {/* host and end members, labeled */}
          {points.filter((p) => inside(p.gap, p.n)).map((p) => (
            <g key={`${p.role}-${p.label}`}>
              <circle cx={x(p.gap)} cy={y(p.n)} r={p.role === "host" ? 7 : 5.5} fill={statusColor(p.nStatus)} stroke="var(--chart-ink)" strokeWidth={p.role === "host" ? 2 : 1.5} />
              <text x={x(p.gap) + 9} y={y(p.n) - 7} fontSize="11" fontWeight={p.role === "host" ? 600 : 400} fill="var(--chart-ink)" {...HALO}>{p.label}</text>
            </g>
          ))}
          <rect x={M.l} y={M.t} width={W - M.l - M.r} height={H - M.t - M.b} fill="transparent" onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
        </svg>
        {hover && (
          <Tooltip x={hover.px} y={hover.py} width={9999}>
            <div className="font-semibold tabular-nums">n {hover.n} · {hover.gap} eV</div>
            <div style={{ color: "var(--chart-ink-2)" }}>{hover.label} — {hover.source}</div>
          </Tooltip>
        )}
      </div>
    </ChartFrame>
  );
}
