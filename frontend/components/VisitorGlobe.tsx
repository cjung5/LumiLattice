"use client";

import type { GeoPermissibleObjects, GeoProjection } from "d3-geo";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";
import { getVisitStats, type VisitStats } from "@/lib/api";
import { ALPHA2_BY_NUMERIC } from "@/lib/isoCountries";

const VISITED_KEY = "lumilattice.visited";

/** Counts this browser once. If storage is blocked it is not counted, not counted every visit. */
async function countThisBrowser() {
  try {
    if (window.localStorage.getItem(VISITED_KEY)) return;
    window.localStorage.setItem(VISITED_KEY, "1");
  } catch {
    return;
  }
  await fetch("/api/visit", { method: "POST" }).catch(() => undefined);
}

type Land = { code: string | null; shape: GeoPermissibleObjects };
type Hover = { x: number; y: number; code: string };
type Colors = Record<"sea" | "seaLit" | "land" | "border" | "few" | "many" | "air" | "rim", string>;

const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const readColors = (): Colors => ({
  sea: css("--globe-sea"),
  seaLit: css("--globe-sea-lit"),
  land: css("--globe-land"),
  border: css("--globe-border"),
  few: css("--globe-few"),
  many: css("--globe-many"),
  air: css("--globe-air"),
  rim: css("--globe-rim"),
});
const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const blend = (a: string, b: string, t: number) => {
  const [from, to] = [rgb(a), rgb(b)];
  return `rgb(${from.map((v, i) => Math.round(v + (to[i] - v) * t)).join(",")})`;
};

export function VisitorGlobe() {
  const t = useTranslations("Visitors");
  const locale = useLocale();
  const canvas = useRef<HTMLCanvasElement>(null);
  const [stats, setStats] = useState<VisitStats | null>(null);
  const [failed, setFailed] = useState(false);
  const [hover, setHover] = useState<Hover | null>(null);
  const counts = useRef(new Map<string, number>());
  const redraw = useRef<() => void>(() => undefined);
  const turnTo = useRef<(code: string) => void>(() => undefined);

  const names = useMemo(() => new Intl.DisplayNames([locale], { type: "region" }), [locale]);
  const nameOf = (code: string) => names.of(code) ?? code;

  useEffect(() => {
    let active = true;
    countThisBrowser()
      .then(() => getVisitStats())
      .then((result) => active && setStats(result))
      .catch(() => active && setFailed(true));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    counts.current = new Map(stats?.countries.map((c) => [c.code, c.count]));
    redraw.current();
  }, [stats]);

  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext("2d");
    if (!element || !context) return;

    let stopped = false;
    let cleanup = () => undefined as void;

    // The map data and geometry code load only when the globe comes near the screen.
    const start = async () => {
      const [geo, topo, world] = await Promise.all([
        import("d3-geo"),
        import("topojson-client"),
        import("world-atlas/countries-110m.json"),
      ]);
      if (stopped) return;
      /* eslint-disable @typescript-eslint/no-explicit-any */
      const topology = world.default as any;
      const collection = topo.feature(topology, topology.objects.countries) as any;
      const borders = topo.mesh(topology, topology.objects.countries, (a: unknown, b: unknown) => a !== b) as GeoPermissibleObjects;
      /* eslint-enable @typescript-eslint/no-explicit-any */
      const lands: Land[] = collection.features.map((f: { id?: string }) => ({
        code: (f.id && ALPHA2_BY_NUMERIC[String(f.id).padStart(3, "0")]) || null,
        shape: f as GeoPermissibleObjects,
      }));

      const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const projection: GeoProjection = geo.geoOrthographic().clipAngle(90).precision(0.4);
      const path = geo.geoPath(projection, context);
      const sphere = { type: "Sphere" } as GeoPermissibleObjects;
      let rotation: [number, number] = [-127, -24];
      let size = 0;
      let radius = 0;
      let colors = readColors();
      let dragging: { x: number; y: number; rotation: [number, number] } | null = null;
      let hoveredCode: string | null = null;
      let glide: { from: [number, number]; to: [number, number]; start: number } | null = null;
      let resumeAt = 0;
      let visible = true;
      let frame = 0;
      let previous = 0;

      const draw = () => {
        if (!size) return;
        const center = size / 2;
        context.clearRect(0, 0, size, size);
        projection.translate([center, center]).scale(radius).rotate(rotation);

        // Air around the globe: bright at the surface, fading fast.
        const air = context.createRadialGradient(center, center, radius * 0.96, center, center, radius * 1.13);
        air.addColorStop(0, colors.air);
        air.addColorStop(1, "transparent");
        context.fillStyle = air;
        context.fillRect(0, 0, size, size);

        // The light comes from the upper left, so the sea is brightest there.
        const sea = context.createRadialGradient(center - radius * 0.42, center - radius * 0.46, radius * 0.08, center, center, radius * 1.04);
        sea.addColorStop(0, colors.seaLit);
        sea.addColorStop(1, colors.sea);
        context.fillStyle = sea;
        context.beginPath();
        path(sphere);
        context.fill();

        const most = Math.max(1, ...counts.current.values());
        context.fillStyle = colors.land;
        context.beginPath();
        for (const land of lands) if (!land.code || !counts.current.has(land.code)) path(land.shape);
        context.fill();

        context.strokeStyle = colors.border;
        context.lineWidth = 0.6;
        context.beginPath();
        path(borders);
        context.stroke();

        // Countries with visitors give off their own light. Logarithmic: one country must not
        // leave all the others looking empty.
        for (const land of lands) {
          const count = land.code ? counts.current.get(land.code) : undefined;
          if (!count) continue;
          const share = most > 1 ? Math.log(1 + count) / Math.log(1 + most) : 1;
          const color = blend(colors.few, colors.many, share);
          context.save();
          context.shadowColor = color;
          context.shadowBlur = 4 + 16 * share;
          context.fillStyle = color;
          context.beginPath();
          path(land.shape);
          context.fill();
          context.restore();
        }

        if (hoveredCode) {
          const land = lands.find((l) => l.code === hoveredCode);
          if (land) {
            context.strokeStyle = css("--foreground");
            context.lineWidth = 1.5;
            context.beginPath();
            path(land.shape);
            context.stroke();
          }
        }

        // The far side of a lit ball falls into shadow.
        const rim = context.createRadialGradient(center - radius * 0.3, center - radius * 0.34, radius * 0.5, center, center, radius * 1.02);
        rim.addColorStop(0, "transparent");
        rim.addColorStop(1, colors.rim);
        context.fillStyle = rim;
        context.beginPath();
        path(sphere);
        context.fill();
      };
      redraw.current = draw;

      const tick = (now: number) => {
        const dt = Math.min(0.05, (now - previous) / 1000 || 0);
        previous = now;
        if (glide) {
          const progress = Math.min(1, (now - glide.start) / 700);
          const eased = 1 - (1 - progress) ** 3;
          const delta = ((glide.to[0] - glide.from[0] + 540) % 360) - 180;
          rotation = [glide.from[0] + delta * eased, glide.from[1] + (glide.to[1] - glide.from[1]) * eased];
          if (progress === 1) glide = null;
        } else if (!dragging && !hoveredCode && now > resumeAt) {
          rotation = [rotation[0] + dt * 5, rotation[1]];
        }
        draw();
        frame = requestAnimationFrame(tick);
      };
      const run = () => {
        cancelAnimationFrame(frame);
        if (still) draw();
        else if (visible && !document.hidden) {
          previous = performance.now();
          frame = requestAnimationFrame(tick);
        }
      };

      turnTo.current = (code) => {
        const land = lands.find((l) => l.code === code);
        if (!land) return;
        const [lon, lat] = geo.geoCentroid(land.shape);
        const target: [number, number] = [-lon, -Math.max(-60, Math.min(60, lat))];
        resumeAt = performance.now() + 6000;
        if (still) {
          rotation = target;
          draw();
        } else {
          glide = { from: rotation, to: target, start: performance.now() };
        }
      };

      const resize = () => {
        const box = element.getBoundingClientRect();
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        size = box.width;
        radius = (size / 2) * 0.86;
        element.width = element.height = Math.round(size * ratio);
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        draw();
      };
      const pick = (x: number, y: number) => {
        if (Math.hypot(x - size / 2, y - size / 2) > radius) return null;
        const point = projection.invert?.([x, y]);
        if (!point) return null;
        return lands.find((l) => l.code && geo.geoContains(l.shape, point))?.code ?? null;
      };
      const onDown = (e: PointerEvent) => {
        dragging = { x: e.clientX, y: e.clientY, rotation };
        glide = null;
        element.setPointerCapture(e.pointerId);
      };
      const onMove = (e: PointerEvent) => {
        const box = element.getBoundingClientRect();
        if (dragging) {
          const speed = 90 / radius;
          rotation = [
            dragging.rotation[0] + (e.clientX - dragging.x) * speed,
            Math.max(-70, Math.min(70, dragging.rotation[1] - (e.clientY - dragging.y) * speed)),
          ];
          if (still) draw();
          return;
        }
        if (e.pointerType !== "mouse") return;
        const x = e.clientX - box.left;
        const y = e.clientY - box.top;
        const code = pick(x, y);
        hoveredCode = code;
        setHover(code ? { x, y, code } : null);
        if (still) draw();
      };
      const onUp = () => {
        dragging = null;
        resumeAt = performance.now() + 3000;
      };
      const onLeave = () => {
        hoveredCode = null;
        setHover(null);
        if (still) draw();
      };

      element.addEventListener("pointerdown", onDown);
      element.addEventListener("pointermove", onMove);
      element.addEventListener("pointerup", onUp);
      element.addEventListener("pointercancel", onUp);
      element.addEventListener("pointerleave", onLeave);
      const sized = new ResizeObserver(resize);
      sized.observe(element);
      const seen = new IntersectionObserver(([entry]) => {
        visible = entry.isIntersecting;
        if (visible) run();
        else cancelAnimationFrame(frame);
      });
      seen.observe(element);
      const themed = new MutationObserver(() => {
        colors = readColors();
        draw();
      });
      themed.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
      document.addEventListener("visibilitychange", run);
      resize();
      run();

      cleanup = () => {
        cancelAnimationFrame(frame);
        sized.disconnect();
        seen.disconnect();
        themed.disconnect();
        document.removeEventListener("visibilitychange", run);
        element.removeEventListener("pointerdown", onDown);
        element.removeEventListener("pointermove", onMove);
        element.removeEventListener("pointerup", onUp);
        element.removeEventListener("pointercancel", onUp);
        element.removeEventListener("pointerleave", onLeave);
      };
    };

    const near = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        near.disconnect();
        void start();
      },
      { rootMargin: "600px" },
    );
    near.observe(element);

    return () => {
      stopped = true;
      near.disconnect();
      cleanup();
    };
  }, []);

  const number = (n: number) => n.toLocaleString(locale);
  const hovered = hover ? (stats?.countries.find((c) => c.code === hover.code)?.count ?? 0) : 0;

  return (
    <section className="card" aria-labelledby="visitors-title">
      <div className="grid items-center gap-6 md:grid-cols-[1fr_minmax(0,26rem)]">
        <div className="min-w-0">
          <h2 id="visitors-title" className="text-lg font-semibold tracking-tight">{t("title")}</h2>
          <p className="mt-1 text-sm text-muted">{t("hint")}</p>
          {failed && <p className="mt-4 text-sm text-muted">{t("unavailable")}</p>}
          {stats && (
            <>
              <div className="mt-4 flex flex-wrap items-baseline gap-x-8 gap-y-2">
                <p>
                  <span className="prism-text text-5xl font-semibold tracking-tight tabular-nums">{number(stats.total)}</span>{" "}
                  <span className="text-sm text-muted">{t("total")}</span>
                </p>
                <p>
                  <span className="text-2xl font-semibold tabular-nums">{number(stats.countries.length)}</span>{" "}
                  <span className="text-sm text-muted">{t("countries")}</span>
                </p>
              </div>
              {stats.total === 0 ? (
                <p className="mt-4 text-sm text-muted">{t("empty")}</p>
              ) : (
                <div className="mt-4 max-h-64 overflow-auto pr-3">
                  <table className="w-full text-left text-sm tabular-nums">
                    <thead>
                      <tr>
                        <th className="py-1 pr-2">{t("colCountry")}</th>
                        <th className="py-1 text-right">{t("colVisitors")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.countries.map((c) => (
                        <tr key={c.code} className="border-t border-line">
                          <td className="py-1 pr-2">
                            <button
                              type="button"
                              aria-label={t("turnTo", { country: nameOf(c.code) })}
                              onClick={() => turnTo.current(c.code)}
                              className="text-left hover:text-accent-text"
                            >
                              {nameOf(c.code)}
                            </button>
                          </td>
                          <td className="py-1 text-right">{number(c.count)}</td>
                        </tr>
                      ))}
                      {stats.unknown > 0 && (
                        <tr className="border-t border-line text-muted">
                          <td className="py-1 pr-2">{t("unknown")}</td>
                          <td className="py-1 text-right">{number(stats.unknown)}</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
              {!stats.persistent && <p className="mt-3 text-xs text-muted">{t("memoryNote")}</p>}
            </>
          )}
        </div>
        <div>
          <div className="relative mx-auto aspect-square w-full max-w-[26rem]">
            <canvas
              ref={canvas}
              role="img"
              aria-label={t("globeLabel", { total: stats?.total ?? 0, countries: stats?.countries.length ?? 0 })}
              className="absolute inset-0 h-full w-full cursor-grab touch-pan-y active:cursor-grabbing"
            />
            {hover && (
              <div
                className="pointer-events-none absolute z-10 whitespace-nowrap rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-xs shadow-lg"
                style={{ left: hover.x, top: hover.y, transform: "translate(-50%, calc(-100% - 10px))" }}
              >
                <div className="font-semibold">{nameOf(hover.code)}</div>
                <div className="text-muted tabular-nums">{hovered ? t("visitors", { count: number(hovered) }) : t("noVisitors")}</div>
              </div>
            )}
          </div>
          <div className="mt-2 flex items-center justify-center gap-2 text-xs text-muted">
            <span>{t("few")}</span>
            <span aria-hidden className="h-2 w-24 rounded-full" style={{ background: "linear-gradient(90deg, var(--globe-few), var(--globe-many))" }} />
            <span>{t("many")}</span>
          </div>
          <p className="mx-auto mt-1 max-w-sm text-center text-xs text-muted">{t("drag")}</p>
        </div>
      </div>
    </section>
  );
}
