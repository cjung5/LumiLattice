import { useId } from "react";

/** The mark: one lit unit cell, seen along its body diagonal. */
export function Logo({ size = 28 }: { size?: number }) {
  const id = useId();
  const nodes = [[16, 3], [27, 9.5], [27, 22.5], [16, 29], [5, 22.5], [5, 9.5]];
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden className="shrink-0">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" style={{ stopColor: "var(--leaf-1)" }} />
          <stop offset="0.55" style={{ stopColor: "var(--leaf-2)" }} />
          <stop offset="1" style={{ stopColor: "var(--leaf-3)" }} />
        </linearGradient>
      </defs>
      <g fill="none" stroke={`url(#${id})`} strokeWidth="1.6" strokeLinejoin="round">
        <path d="M16 3 27 9.500V22.500L16 29 5 22.500V9.500Z" />
        <path d="M16 16 5 9.500M16 16 27 9.500M16 16V29" />
      </g>
      {nodes.map(([cx, cy]) => (
        <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="2" fill={`url(#${id})`} />
      ))}
      <circle cx="16" cy="16" r="3.2" fill={`url(#${id})`} />
    </svg>
  );
}
