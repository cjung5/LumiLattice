import { useId } from "react";

// A 3 x 3 x 3 cubic lattice in isometric view. It is decoration, so screen readers skip it.
const SIZE = 3;
const ISO_X = 62;
const ISO_Y = 36;
const RISE = 72;
const place = (a: number, b: number, c: number): [number, number] => [
  210 + (a - b) * ISO_X,
  112 + (a + b) * ISO_Y - c * RISE + RISE,
];
const RANGE = [...Array(SIZE).keys()];
const NODES = RANGE.flatMap((a) => RANGE.flatMap((b) => RANGE.map((c) => [a, b, c] as const)));
const EDGES = NODES.flatMap(([a, b, c]) =>
  [
    [a + 1, b, c],
    [a, b + 1, c],
    [a, b, c + 1],
  ]
    .filter((end) => end.every((v) => v < SIZE))
    .map((end) => ({ key: `${a}${b}${c}-${end.join("")}`, from: place(a, b, c), to: place(end[0], end[1], end[2]) })),
);

export function LatticeArt({ className }: { className?: string }) {
  const id = useId();
  return (
    <svg viewBox="0 0 420 340" aria-hidden className={className}>
      <defs>
        <linearGradient id={`${id}-prism`} x1="0" y1="0" x2="1" y2="1" gradientUnits="userSpaceOnUse" gradientTransform="scale(420 340)">
          <stop offset="0" style={{ stopColor: "var(--prism-1)" }} />
          <stop offset="0.55" style={{ stopColor: "var(--prism-2)" }} />
          <stop offset="1" style={{ stopColor: "var(--prism-3)" }} />
        </linearGradient>
        <filter id={`${id}-glow`} x="-150%" y="-150%" width="400%" height="400%">
          <feGaussianBlur stdDeviation="7" />
        </filter>
      </defs>
      <g stroke={`url(#${id}-prism)`} strokeWidth="1.1" opacity="0.45">
        {EDGES.map(({ key, from, to }) => (
          <line key={key} x1={from[0]} y1={from[1]} x2={to[0]} y2={to[1]} />
        ))}
      </g>
      {NODES.map(([a, b, c]) => {
        const [x, y] = place(a, b, c);
        const center = a === 1 && b === 1 && c === 1;
        const lit = center || (a + b * 2 + c * 3) % 5 === 0;
        return (
          <g key={`${a}${b}${c}`}>
            {lit && (
              <circle
                className="lattice-node"
                style={{ animationDelay: `${((a * 7 + b * 5 + c * 3) % 12) * 0.4}s` }}
                cx={x}
                cy={y}
                r={center ? 14 : 9}
                fill={`url(#${id}-prism)`}
                filter={`url(#${id}-glow)`}
              />
            )}
            <circle cx={x} cy={y} r={center ? 6.5 : lit ? 4.5 : 3} fill={`url(#${id}-prism)`} opacity={lit ? 1 : 0.7} />
          </g>
        );
      })}
    </svg>
  );
}
