"use client";

import { useTranslations } from "next-intl";

const percent = (x: number, lo: number, hi: number) => Math.max(0, Math.min(100, ((x - lo) / (hi - lo)) * 100));

type Range = [number, number];

const N_MIN = 1.3;
const N_MAX = 3;
// Textbook values for scale only (near 550 nm). They are not scored.
const N_REFERENCES = [
  { key: "glass", n: 1.5 },
  { key: "sapphire", n: 1.77 },
  { key: "diamond", n: 2.42 },
] as const;

/** Where a material's n sits between everyday materials. */
export function NScale({ goal, range, host }: { goal: number; range?: Range | null; host?: number | null }) {
  const t = useTranslations("Plain");
  const at = (x: number) => percent(x, N_MIN, N_MAX);
  return (
    <div className="pt-7 pb-5" role="img" aria-label={t("nScale", { goal })}>
      <div className="relative h-2 rounded-full bg-line">
        {range && (
          <div
            className="absolute inset-y-0 min-w-2 rounded-full bg-accent"
            style={{ left: `${at(range[0])}%`, width: `${at(range[1]) - at(range[0])}%` }}
          />
        )}
        {host != null && (
          <div
            className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-foreground bg-surface"
            style={{ left: `${at(host)}%` }}
          />
        )}
        <div className="absolute -top-1 h-4 w-0.5 -translate-x-1/2 bg-foreground" style={{ left: `${at(goal)}%` }} />
        <div className="absolute -top-6 -translate-x-1/2 whitespace-nowrap text-xs font-medium" style={{ left: `${at(goal)}%` }}>
          {t("goalAtLeast", { value: goal })}
        </div>
        {N_REFERENCES.map((r) => (
          <div key={r.key} className="absolute top-3 -translate-x-1/2 whitespace-nowrap text-xs text-muted" style={{ left: `${at(r.n)}%` }}>
            {t(r.key)}
          </div>
        ))}
      </div>
    </div>
  );
}

const NM_MIN = 380;
const NM_MAX = 700;
const SPECTRUM =
  "linear-gradient(to right, #7a00c8 0%, #3a3aff 19%, #00b7d8 34%, #2fc22f 47%, #e6e200 62%, #ff8a00 75%, #d40000 100%)";
const COLORS = [
  { key: "blue", nm: 460 },
  { key: "green", nm: 530 },
  { key: "yellow", nm: 580 },
  { key: "red", nm: 650 },
] as const;

/** Light with a shorter wavelength than this (nm) has enough energy to be absorbed. */
export const edgeNm = (gap: number) => Math.round(1240 / gap);

/** The visible spectrum, with the part the material absorbs darkened. */
export function GapScale({ goal, range }: { goal: number; range?: Range | null }) {
  const t = useTranslations("Plain");
  const at = (nm: number) => percent(nm, NM_MIN, NM_MAX);
  const sure = range ? at(1240 / range[1]) : 0; // absorbed even at the widest gap in the range
  const maybe = range ? at(1240 / range[0]) : 0; // absorbed at the narrowest gap
  return (
    <div className="pt-7 pb-5" role="img" aria-label={t("gapScale", { goal, nm: edgeNm(goal) })}>
      <div className="relative h-3 rounded" style={{ background: SPECTRUM }}>
        {sure > 0 && <div className="absolute inset-y-0 left-0 rounded-l bg-black/85" style={{ width: `${sure}%` }} />}
        {maybe > sure && (
          <div
            className="absolute inset-y-0"
            style={{
              left: `${sure}%`,
              width: `${maybe - sure}%`,
              background: "repeating-linear-gradient(135deg, rgba(0,0,0,.8) 0 3px, transparent 3px 7px)",
            }}
          />
        )}
        <div className="absolute -top-1 h-5 w-0.5 -translate-x-1/2 bg-foreground" style={{ left: `${at(1240 / goal)}%` }} />
        <div
          className="absolute -top-6 whitespace-nowrap text-xs font-medium"
          style={at(1240 / goal) < 50 ? { left: `${at(1240 / goal)}%` } : { right: `${100 - at(1240 / goal)}%` }}
        >
          {t("goalClearFrom", { nm: edgeNm(goal) })}
        </div>
        {COLORS.map((c) => (
          <div key={c.key} className="absolute top-4 -translate-x-1/2 whitespace-nowrap text-xs text-muted" style={{ left: `${at(c.nm)}%` }}>
            {t(c.key)}
          </div>
        ))}
      </div>
    </div>
  );
}
