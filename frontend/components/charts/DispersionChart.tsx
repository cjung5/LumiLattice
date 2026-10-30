"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { ChartFrame, scale, svgPoint, ticks, Tooltip } from "@/components/charts/ChartFrame";
import type { DispersionData } from "@/lib/api";

type Props = {
  data: DispersionData[];
  /** Formula drawn at full strength (the host); the others are end members. */
  primary: string | null;
  /** Candidate label; when set, the band between end-member curves is shaded (Heuristic). */
  bandLabel: string | null;
  bandFormulas: string[];
};

const W = 640;
const H = 300;
const M = { l: 48, r: 92, t: 12, b: 52 };
// Approximate colors of the visible spectrum, for the wavelength strip only.
const SPECTRUM: [number, string][] = [
  [380, "#7a00a8"], [440, "#2a3cff"], [490, "#00b6ff"], [520, "#00d400"],
  [570, "#e8e000"], [600, "#ff8a00"], [650, "#ff1a00"], [780, "#8f0000"],
];

export function DispersionChart({ data, primary, bandLabel, bandFormulas }: Props) {
  const t = useTranslations("Charts");
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [pointer, setPointer] = useState<{ px: number; py: number } | null>(null);
  const wl = data[0]?.wavelengths_nm ?? [];
  const lines = data.filter((d) => d.bulk_median && d.bulk_median.some((v) => v != null));
  const missing = data.filter((d) => !lines.includes(d)).map((d) => d.formula);

  const values = lines.flatMap((d) => d.bulk_median!.filter((v): v is number => v != null));
  const lo = values.length ? Math.min(...values) : 1.5;
  const hi = values.length ? Math.max(...values) : 2.5;
  const pad = Math.max((hi - lo) * 0.1, 0.05);
  const Y: [number, number] = [lo - pad, hi + pad];
  const x = scale([380, 780], [M.l, W - M.r]);
  const y = scale(Y, [H - M.b, M.t]);

  const path = (series: (number | null)[]) =>
    series
      .map((v, i) => (v == null ? null : `${x(wl[i]).toFixed(1)},${y(v).toFixed(1)}`))
      .reduce<string>((acc, pt, i) => (pt == null ? acc : acc + (i && series[i - 1] != null ? "L" : "M") + pt), "");

  const bandSeries = lines.filter((d) => bandFormulas.includes(d.formula)).map((d) => d.bulk_median!);
  const band = bandLabel && bandSeries.length >= 2
    ? wl.map((_, i) => {
        const v = bandSeries.map((s) => s[i]).filter((u): u is number => u != null);
        return v.length >= 2 ? [Math.min(...v), Math.max(...v)] : null;
      })
    : null;
  const bandPath = band
    ? (() => {
        const idx = band.map((b, i) => (b ? i : -1)).filter((i) => i >= 0);
        if (idx.length < 2) return "";
        const top = idx.map((i) => `${x(wl[i])},${y(band[i]![1])}`);
        const bottom = [...idx].reverse().map((i) => `${x(wl[i])},${y(band[i]![0])}`);
        return `M${top.join("L")}L${bottom.join("L")}Z`;
      })()
    : "";

  // End labels: nudge apart by at least 13 px, with a leader line back to the curve.
  const ends: { formula: string; i: number; y0: number; y1: number }[] = lines
    .map((d) => {
      const last = d.bulk_median!.reduce<number>((acc, v, i) => (v != null ? i : acc), -1);
      const y0 = y(d.bulk_median![last]!);
      return { formula: d.formula, i: last, y0, y1: y0 };
    })
    .sort((a, b) => a.y0 - b.y0);
  ends.forEach((e, k) => {
    if (k > 0) e.y1 = Math.max(e.y0, ends[k - 1].y1 + 13);
  });

  function onMove(event: React.PointerEvent<SVGRectElement>) {
    const p = svgPoint(event, W, H);
    const nm = x.invert(p.x);
    const i = Math.round((nm - 380) / 10);
    setHoverIndex(i >= 0 && i < wl.length ? i : null);
    setPointer({ px: p.x * p.scaleX, py: p.y * p.scaleY });
  }

  const table = (
    <table className="w-full text-left text-xs tabular-nums">
      <thead style={{ color: "var(--chart-ink-2)" }}>
        <tr>
          <th className="py-1 pr-2 font-normal">λ (nm)</th>
          {lines.map((d) => <th key={d.formula} className="py-1 pr-2 font-normal">{d.formula}</th>)}
          {band && <th className="py-1 font-normal">{bandLabel}</th>}
        </tr>
      </thead>
      <tbody>
        {wl.map((nm, i) => (
          <tr key={nm} className="border-t border-line">
            <td className="py-0.5 pr-2">{nm}</td>
            {lines.map((d) => <td key={d.formula} className="py-0.5 pr-2">{d.bulk_median![i] ?? "—"}</td>)}
            {band && <td className="py-0.5">{band[i] ? `${band[i]![0]}–${band[i]![1]}` : "—"}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );

  return (
    <ChartFrame
      title={t("dispersionTitle")}
      subtitle={t("dispersionSubtitle")}
      legend={[
        { label: t("legendMeasuredCurve"), kind: "line", color: "var(--series-exp)" },
        ...(band ? [{ label: t("legendBand", { id: bandLabel ?? "" }), kind: "wash" as const, color: "var(--series-heur)" }] : []),
      ]}
      notes={[t("dispersionNote"), ...(missing.length ? [t("noCurve", { formulas: missing.join(", ") })] : [])]}
      table={table}
    >
      {lines.length === 0 ? (
        <p className="py-6 text-center text-sm" style={{ color: "var(--chart-ink-2)" }}>{t("noCurveAtAll")}</p>
      ) : (
        <div className="relative">
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={t("dispersionTitle")}>
            <defs>
              <linearGradient id="spectrum" x1="0" x2="1" y1="0" y2="0">
                {SPECTRUM.map(([nm, c]) => <stop key={nm} offset={`${((nm - 380) / 400) * 100}%`} stopColor={c} />)}
              </linearGradient>
            </defs>
            {ticks(380, 780, 8).map((v) => (
              <g key={`x${v}`}>
                <line x1={x(v)} x2={x(v)} y1={M.t} y2={H - M.b} stroke="var(--chart-grid)" />
                <text x={x(v)} y={H - M.b + 24} textAnchor="middle" fontSize="11" fill="var(--chart-muted)">{v}</text>
              </g>
            ))}
            {ticks(Y[0], Y[1], 5).map((v) => (
              <g key={`y${v}`}>
                <line x1={M.l} x2={W - M.r} y1={y(v)} y2={y(v)} stroke="var(--chart-grid)" />
                <text x={M.l - 6} y={y(v) + 4} textAnchor="end" fontSize="11" fill="var(--chart-muted)">{v.toFixed(2)}</text>
              </g>
            ))}
            <rect x={M.l} y={H - M.b + 4} width={W - M.l - M.r} height="6" rx="3" fill="url(#spectrum)" opacity="0.8" />
            <text x={(M.l + W - M.r) / 2} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--chart-ink-2)">{t("axisWavelength")}</text>
            <text transform={`translate(12,${(M.t + H - M.b) / 2}) rotate(-90)`} textAnchor="middle" fontSize="11" fill="var(--chart-ink-2)">n</text>
            {bandPath && <path d={bandPath} fill="var(--series-heur)" fillOpacity="0.16" />}
            {lines.map((d) => (
              <path
                key={d.formula}
                d={path(d.bulk_median!)}
                fill="none"
                stroke="var(--series-exp)"
                strokeOpacity={d.formula === primary ? 1 : 0.55}
                strokeWidth="2"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            ))}
            {ends.map((e) => {
              const ex = x(wl[e.i]);
              const y1 = e.y1;
              return (
                <g key={e.formula}>
                  {Math.abs(y1 - e.y0) > 1 && <line x1={ex + 2} y1={e.y0} x2={ex + 8} y2={y1} stroke="var(--chart-muted)" />}
                  <text x={ex + 10} y={y1 + 4} fontSize="11" fontWeight={e.formula === primary ? 600 : 400} fill="var(--chart-ink)">{e.formula}</text>
                </g>
              );
            })}
            {hoverIndex != null && <line x1={x(wl[hoverIndex])} x2={x(wl[hoverIndex])} y1={M.t} y2={H - M.b} stroke="var(--chart-ink-2)" strokeWidth="1" />}
            <rect x={M.l} y={M.t} width={W - M.l - M.r} height={H - M.t - M.b} fill="transparent" onPointerMove={onMove} onPointerLeave={() => { setHoverIndex(null); setPointer(null); }} />
          </svg>
          {hoverIndex != null && pointer && (
            <Tooltip x={pointer.px} y={pointer.py} width={9999}>
              <div className="mb-0.5" style={{ color: "var(--chart-ink-2)" }}>{wl[hoverIndex]} nm</div>
              {lines.map((d) => (
                <div key={d.formula} className="flex items-center gap-1.5 tabular-nums">
                  <svg width="12" height="4" aria-hidden><line x1="0" y1="2" x2="12" y2="2" stroke="var(--series-exp)" strokeWidth="2" /></svg>
                  <span className="font-semibold">{d.bulk_median![hoverIndex] ?? "—"}</span>
                  <span style={{ color: "var(--chart-ink-2)" }}>{d.formula}</span>
                </div>
              ))}
              {band?.[hoverIndex] && (
                <div className="flex items-center gap-1.5 tabular-nums">
                  <svg width="12" height="4" aria-hidden><line x1="0" y1="2" x2="12" y2="2" stroke="var(--series-heur)" strokeWidth="2" /></svg>
                  <span className="font-semibold">≈ {band[hoverIndex]![0]}–{band[hoverIndex]![1]}</span>
                  <span style={{ color: "var(--chart-ink-2)" }}>{bandLabel}</span>
                </div>
              )}
            </Tooltip>
          )}
        </div>
      )}
    </ChartFrame>
  );
}
