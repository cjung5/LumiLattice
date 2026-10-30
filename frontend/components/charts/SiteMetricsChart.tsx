"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { ChartFrame, scale, Tooltip } from "@/components/charts/ChartFrame";
import type { SiteMetric } from "@/lib/api";

type Props = {
  metrics: SiteMetric[];
  thresholds: Record<string, number>;
  /** Shown in the title, e.g. "LL-0002 (relaxed)". */
  subject: string;
};

const W = 300;
const ROW = 26;
const M = { l: 70, r: 44, t: 22, b: 26 };

type Panel = { key: "size_mismatch" | "bvs_bond_change"; warn: number; fail: number; title: string };

// Two small multiples (never one dual-axis chart): ionic size fit and bond-valence misfit.
export function SiteMetricsChart({ metrics, thresholds, subject }: Props) {
  const t = useTranslations("Charts");
  const [hover, setHover] = useState<{ x: number; y: number; text: string; value: string } | null>(null);
  const panels: Panel[] = [
    { key: "size_mismatch", warn: thresholds.size_warn ?? 0.1, fail: thresholds.size_fail ?? 0.2, title: t("sizePanel") },
    { key: "bvs_bond_change", warn: thresholds.bvs_warn ?? 0.04, fail: thresholds.bvs_fail ?? 0.1, title: t("bvsPanel") },
  ];
  const H = M.t + M.b + Math.max(metrics.length, 1) * ROW;

  const table = (
    <table className="w-full text-left text-xs tabular-nums">
      <thead style={{ color: "var(--chart-ink-2)" }}>
        <tr>
          <th className="py-1 pr-2 font-normal">{t("site")}</th>
          <th className="py-1 pr-2 font-normal">CN</th>
          <th className="py-1 pr-2 font-normal">{t("meanBond")}</th>
          <th className="py-1 pr-2 font-normal">{t("expectedBond")}</th>
          <th className="py-1 pr-2 font-normal">{t("sizePanel")}</th>
          <th className="py-1 pr-2 font-normal">BVS</th>
          <th className="py-1 font-normal">{t("bvsPanel")}</th>
        </tr>
      </thead>
      <tbody>
        {metrics.map((m) => (
          <tr key={m.index} className="border-t border-line">
            <td className="py-0.5 pr-2">{m.element}{m.index}</td>
            <td className="py-0.5 pr-2">{m.coordination}</td>
            <td className="py-0.5 pr-2">{m.mean_bond}</td>
            <td className="py-0.5 pr-2">{m.expected_bond ?? "—"}</td>
            <td className="py-0.5 pr-2">{m.size_mismatch == null ? "—" : `${(m.size_mismatch * 100).toFixed(1)}%`}</td>
            <td className="py-0.5 pr-2">{m.bvs ?? "—"} / {m.oxidation_state}</td>
            <td className="py-0.5">{m.bvs_bond_change == null ? "—" : `${(m.bvs_bond_change * 100).toFixed(1)}%`}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  return (
    <ChartFrame
      title={t("sitesTitle", { subject })}
      subtitle={t("sitesSubtitle")}
      legend={[
        { label: t("legendTooSmall"), kind: "box", color: "var(--div-pos)" },
        { label: t("legendTooLarge"), kind: "box", color: "var(--div-neg)" },
      ]}
      notes={[t("sitesNote")]}
      table={table}
    >
      <div className="relative grid gap-3 sm:grid-cols-2">
        {panels.map((panel) => {
          const extent = Math.max(
            panel.fail * 1.4,
            ...metrics.map((m) => Math.abs((m[panel.key] as number | null) ?? 0) * 1.1),
          );
          const x = scale([-extent, extent], [M.l, W - M.r]);
          return (
            <svg key={panel.key} viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={panel.title}>
              <text x={M.l} y={12} fontSize="11" fontWeight="600" fill="var(--chart-ink)">{panel.title}</text>
              {/* status zones: warn and fail, both sides */}
              {[-1, 1].map((sign) => (
                <g key={sign}>
                  <rect x={Math.min(x(sign * panel.warn), x(sign * panel.fail))} y={M.t} width={Math.abs(x(panel.fail) - x(panel.warn))} height={H - M.t - M.b} fill="var(--status-warning)" fillOpacity="0.12" />
                  <rect x={sign > 0 ? x(panel.fail) : M.l} y={M.t} width={sign > 0 ? W - M.r - x(panel.fail) : x(-panel.fail) - M.l} height={H - M.t - M.b} fill="var(--status-critical)" fillOpacity="0.1" />
                </g>
              ))}
              <text x={x(panel.warn) + 2} y={H - M.b + 22} fontSize="10" fill="var(--chart-muted)">! {Math.round(panel.warn * 100)}%</text>
              <text x={x(panel.fail) + 2} y={H - M.b + 22} fontSize="10" fill="var(--chart-muted)">✗ {Math.round(panel.fail * 100)}%</text>
              <line x1={x(0)} x2={x(0)} y1={M.t} y2={H - M.b} stroke="var(--chart-axis)" />
              <text x={x(0)} y={H - M.b + 12} textAnchor="middle" fontSize="10" fill="var(--chart-muted)">0</text>
              {metrics.map((m, row) => {
                const v = m[panel.key] as number | null;
                const cy = M.t + row * ROW + ROW / 2;
                const label = `${m.element}${m.index}`;
                return (
                  <g key={m.index}>
                    <text x={M.l - 6} y={cy + 4} textAnchor="end" fontSize="11" fill="var(--chart-ink)">{label}</text>
                    {v != null && (
                      <>
                        <rect
                          x={Math.min(x(0), x(v))}
                          y={cy - 7}
                          width={Math.max(Math.abs(x(v) - x(0)), 2)}
                          height="14"
                          rx="4"
                          fill={v >= 0 ? "var(--div-pos)" : "var(--div-neg)"}
                          onPointerEnter={(e) => {
                            const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                            const parent = (e.currentTarget.ownerSVGElement!.parentElement as HTMLElement).getBoundingClientRect();
                            setHover({ x: box.left - parent.left + (x(v) / W) * box.width, y: box.top - parent.top + (cy / H) * box.height, text: `${label} · ${panel.title}`, value: `${(v * 100).toFixed(1)}%` });
                          }}
                          onPointerLeave={() => setHover(null)}
                        />
                        <text x={v >= 0 ? x(v) + 4 : x(v) - 4} y={cy + 4} textAnchor={v >= 0 ? "start" : "end"} fontSize="10" fill="var(--chart-ink-2)">{`${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`}</text>
                      </>
                    )}
                  </g>
                );
              })}
            </svg>
          );
        })}
        {hover && (
          <Tooltip x={hover.x} y={hover.y} width={9999}>
            <div className="font-semibold tabular-nums">{hover.value}</div>
            <div style={{ color: "var(--chart-ink-2)" }}>{hover.text}</div>
          </Tooltip>
        )}
      </div>
    </ChartFrame>
  );
}
