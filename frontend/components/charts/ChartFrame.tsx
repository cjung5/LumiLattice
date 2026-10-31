"use client";

import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";

export type LegendItem = {
  label: string;
  /** dot, ring (open dot), diamond, line, box (outlined range), wash (filled region) */
  kind: "dot" | "ring" | "diamond" | "line" | "box" | "wash";
  color: string;
};

export function LegendKey({ item }: { item: LegendItem }) {
  if (item.kind === "line") {
    return <svg width="18" height="10" aria-hidden><line x1="1" y1="5" x2="17" y2="5" stroke={item.color} strokeWidth="2" strokeLinecap="round" /></svg>;
  }
  if (item.kind === "box") {
    return <svg width="14" height="12" aria-hidden><rect x="1" y="1" width="12" height="10" rx="2" fill={item.color} fillOpacity="0.15" stroke={item.color} strokeWidth="2" /></svg>;
  }
  if (item.kind === "wash") {
    return <svg width="14" height="12" aria-hidden><rect x="1" y="1" width="12" height="10" rx="2" fill={item.color} fillOpacity="0.12" /></svg>;
  }
  if (item.kind === "diamond") {
    return <svg width="10" height="10" aria-hidden><path d="M5 0.5 9.5 5 5 9.5 0.5 5Z" fill="var(--chart-surface)" stroke={item.color} strokeWidth="1.5" /></svg>;
  }
  if (item.kind === "ring") {
    return <svg width="10" height="10" aria-hidden><circle cx="5" cy="5" r="3.5" fill="none" stroke={item.color} strokeWidth="2" /></svg>;
  }
  return <svg width="10" height="10" aria-hidden><circle cx="5" cy="5" r="4" fill={item.color} /></svg>;
}

type Props = {
  title: string;
  subtitle?: string;
  legend?: LegendItem[];
  notes?: string[];
  table: ReactNode;
  children: ReactNode;
};

// Every chart has a legend (>= 2 series), notes on what the data is, and a table view.
export function ChartFrame({ title, subtitle, legend = [], notes = [], table, children }: Props) {
  const t = useTranslations("Charts");
  const [showTable, setShowTable] = useState(false);
  return (
    <figure className="rounded-md border border-line bg-chart-surface p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <figcaption>
          <div className="text-sm font-medium" style={{ color: "var(--chart-ink)" }}>{title}</div>
          {subtitle && <div className="text-xs" style={{ color: "var(--chart-ink-2)" }}>{subtitle}</div>}
        </figcaption>
        <button
          type="button"
          onClick={() => setShowTable((v) => !v)}
          className="rounded border border-line px-2 py-0.5 text-xs"
          aria-pressed={showTable}
        >
          {showTable ? t("showChart") : t("showTable")}
        </button>
      </div>
      {legend.length > 1 && !showTable && (
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs" style={{ color: "var(--chart-ink-2)" }}>
          {legend.map((item) => (
            <li key={item.label} className="flex items-center gap-1.5">
              <LegendKey item={item} />
              {item.label}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-2">{showTable ? <div className="max-h-80 overflow-auto">{table}</div> : children}</div>
      {notes.length > 0 && (
        <ul className="mt-2 list-disc pl-4 text-xs" style={{ color: "var(--chart-ink-2)" }}>
          {notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </figure>
  );
}

/** A floating tooltip inside the chart box; values lead, labels follow. */
export function Tooltip({ x, y, width, children }: { x: number; y: number; width: number; children: ReactNode }) {
  const left = x > width * 0.6 ? undefined : x + 12;
  const right = x > width * 0.6 ? width - x + 12 : undefined;
  return (
    <div
      className="pointer-events-none absolute z-10 rounded-md border border-line px-2 py-1 text-xs shadow-sm"
      style={{ top: y + 12, left, right, background: "var(--chart-surface)", color: "var(--chart-ink)" }}
    >
      {children}
    </div>
  );
}

export function scale(domain: [number, number], range: [number, number]) {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const f = (v: number) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);
  f.invert = (p: number) => d0 + ((p - r0) / (r1 - r0)) * (d1 - d0);
  return f;
}

export function ticks(min: number, max: number, count = 5): number[] {
  const span = max - min;
  const raw = span / count;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * pow).find((s) => span / s <= count) ?? raw;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}

/** Map a pointer event to SVG viewBox coordinates. */
export function svgPoint(event: React.PointerEvent<SVGElement>, width: number, height: number) {
  const box = (event.currentTarget.ownerSVGElement ?? (event.currentTarget as SVGSVGElement)).getBoundingClientRect();
  return {
    x: ((event.clientX - box.left) / box.width) * width,
    y: ((event.clientY - box.top) / box.height) * height,
    scaleX: box.width / width,
    scaleY: box.height / height,
  };
}
