"use client";

import { useEffect, useRef } from "react";

// Light moving through a cubic lattice, drawn the way light behaves: a white-hot core, brightness
// that falls with the square of the distance, and additive blending at night. Each strut and node
// is lit only by how near it is to a light. It is decoration, so screen readers skip it.
const SIZE = 4;
const SEGMENTS = 5;
const LEVELS = 8;
type Vec3 = [number, number, number];

const offset = (SIZE - 1) / 2;
const NODES: Vec3[] = [];
for (let a = 0; a < SIZE; a++) for (let b = 0; b < SIZE; b++) for (let c = 0; c < SIZE; c++) NODES.push([a - offset, b - offset, c - offset]);
const at = (a: number, b: number, c: number) => a * SIZE * SIZE + b * SIZE + c;
const EDGES: [number, number][] = [];
const NEIGHBORS: number[][] = NODES.map(() => []);
for (let a = 0; a < SIZE; a++) for (let b = 0; b < SIZE; b++) for (let c = 0; c < SIZE; c++) {
  for (const [da, db, dc] of [[1, 0, 0], [0, 1, 0], [0, 0, 1]]) {
    if (a + da < SIZE && b + db < SIZE && c + dc < SIZE) {
      const from = at(a, b, c);
      const to = at(a + da, b + db, c + dc);
      EDGES.push([from, to]);
      NEIGHBORS[from].push(to);
      NEIGHBORS[to].push(from);
    }
  }
}

type Photon = { from: number; to: number; t: number; speed: number; power: number; last: number };

/** Mostly straight on, with a turn now and then: a ray bending at the planes of a crystal. */
function nextNode(photon: Photon): number {
  const here = NODES[photon.to];
  const before = NODES[photon.from];
  const ahead = NEIGHBORS[photon.to].find((n) => NODES[n].every((v, i) => Math.abs(v - (2 * here[i] - before[i])) < 1e-6));
  if (ahead !== undefined && Math.random() < 0.72) return ahead;
  const options = NEIGHBORS[photon.to].filter((n) => n !== photon.from);
  return options[Math.floor(Math.random() * options.length)];
}

function makeSprite(stops: [number, string][]) {
  const sprite = document.createElement("canvas");
  sprite.width = sprite.height = 128;
  const context = sprite.getContext("2d")!;
  const gradient = context.createRadialGradient(64, 64, 0, 64, 64, 64);
  stops.forEach(([position, color]) => gradient.addColorStop(position, color));
  context.fillStyle = gradient;
  context.fillRect(0, 0, 128, 128);
  return sprite;
}

// Stops follow the fall-off of a point light: steep near the core, a long dim tail.
const NIGHT = {
  blend: "lighter" as GlobalCompositeOperation,
  sprite: [[0, "rgba(255,255,245,1)"], [0.06, "rgba(253,247,190,.85)"], [0.16, "rgba(205,240,150,.38)"], [0.34, "rgba(120,220,150,.13)"], [0.62, "rgba(70,190,130,.04)"], [1, "rgba(40,160,110,0)"]] as [number, string][],
  strut: (level: number) => `rgba(${130 + 125 * level}, ${215 + 40 * level}, ${160 + 40 * level}, ${0.13 + 0.87 * level ** 1.4})`,
  node: (level: number) => `rgba(${150 + 105 * level}, ${225 + 30 * level}, ${170 + 40 * level}, ${0.32 + 0.68 * level})`,
  core: "rgba(255,255,248,1)",
};
const DAY = {
  blend: "source-over" as GlobalCompositeOperation,
  sprite: [[0, "rgba(255,252,225,1)"], [0.08, "rgba(255,236,140,.9)"], [0.2, "rgba(255,221,90,.45)"], [0.42, "rgba(245,214,90,.16)"], [0.7, "rgba(225,214,100,.05)"], [1, "rgba(210,210,110,0)"]] as [number, string][],
  strut: (level: number) => `rgba(${20 + 175 * level}, ${107 + 33 * level}, ${58 - 40 * level}, ${0.2 + 0.75 * level ** 1.4})`,
  node: (level: number) => `rgba(${16 + 190 * level}, ${95 + 55 * level}, ${52 - 40 * level}, ${0.5 + 0.5 * level})`,
  core: "rgba(255,250,215,1)",
};

export function LatticeLight({ className }: { className?: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext("2d");
    if (!element || !context) return;

    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const photons: Photon[] = [
      { from: at(0, 1, 1), to: at(1, 1, 1), t: 0.4, speed: 0.95, power: 1, last: 0 },
      { from: at(3, 2, 2), to: at(2, 2, 2), t: 0.1, speed: 0.7, power: 0.7, last: 0 },
    ];
    const size = { width: 0, height: 0, ratio: 1 };
    const pointer = { x: -9999, y: -9999, power: 0, target: 0 };
    let dark = document.documentElement.dataset.theme === "dark";
    let theme = dark ? NIGHT : DAY;
    let sprite = makeSprite(theme.sprite);
    let yaw = 0.62;
    let frame = 0;
    let previous = 0;
    let visible = true;

    const resize = () => {
      const box = element.getBoundingClientRect();
      size.width = box.width;
      size.height = box.height;
      size.ratio = Math.min(window.devicePixelRatio || 1, 2);
      element.width = Math.round(box.width * size.ratio);
      element.height = Math.round(box.height * size.ratio);
    };

    const draw = () => {
      const { width, height, ratio } = size;
      if (!width || !height) return;
      const isDark = document.documentElement.dataset.theme === "dark";
      if (isDark !== dark) {
        dark = isDark;
        theme = dark ? NIGHT : DAY;
        sprite = makeSprite(theme.sprite);
      }
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      context.globalCompositeOperation = theme.blend;
      context.lineCap = "round";

      const unit = Math.min(width, height) / 7;
      const cosYaw = Math.cos(yaw);
      const sinYaw = Math.sin(yaw);
      const cosPitch = Math.cos(0.52);
      const sinPitch = Math.sin(0.52);
      const placed = NODES.map(([x, y, z]) => {
        const x1 = x * cosYaw - z * sinYaw;
        const z1 = x * sinYaw + z * cosYaw;
        const y1 = y * cosPitch - z1 * sinPitch;
        const z2 = y * sinPitch + z1 * cosPitch;
        const scale = 7 / (7 + z2);
        return { x: width / 2 + x1 * unit * scale, y: height / 2 - y1 * unit * scale, near: scale };
      });

      const lights = photons.map((p) => {
        const a = placed[p.from];
        const b = placed[p.to];
        return { x: a.x + (b.x - a.x) * p.t, y: a.y + (b.y - a.y) * p.t, power: p.power };
      });
      if (pointer.power > 0.01) lights.push({ x: pointer.x, y: pointer.y, power: pointer.power * 0.8 });
      const reach = unit * 0.62;
      const lightAt = (x: number, y: number) => {
        let total = 0;
        for (const light of lights) {
          const distance = Math.hypot(x - light.x, y - light.y) / reach;
          total += light.power / (1 + distance * distance);
        }
        return Math.min(1, total);
      };

      const paths = Array.from({ length: LEVELS }, () => new Path2D());
      for (const [from, to] of EDGES) {
        const a = placed[from];
        const b = placed[to];
        for (let s = 0; s < SEGMENTS; s++) {
          const t0 = s / SEGMENTS;
          const t1 = (s + 1) / SEGMENTS;
          const x0 = a.x + (b.x - a.x) * t0;
          const y0 = a.y + (b.y - a.y) * t0;
          const x1 = a.x + (b.x - a.x) * t1;
          const y1 = a.y + (b.y - a.y) * t1;
          const lit = lightAt((x0 + x1) / 2, (y0 + y1) / 2);
          const level = Math.min(LEVELS - 1, Math.floor(lit * LEVELS));
          paths[level].moveTo(x0, y0);
          paths[level].lineTo(x1, y1);
        }
      }
      paths.forEach((path, index) => {
        const level = index / (LEVELS - 1);
        context.strokeStyle = theme.strut(level);
        context.lineWidth = 0.7 + level * 1.3;
        context.stroke(path);
      });

      for (const node of placed) {
        const lit = lightAt(node.x, node.y);
        if (lit > 0.1) {
          const glow = (6 + 34 * lit) * node.near;
          context.globalAlpha = Math.min(1, lit * 0.8);
          context.drawImage(sprite, node.x - glow, node.y - glow, glow * 2, glow * 2);
          context.globalAlpha = 1;
        }
        context.fillStyle = theme.node(lit);
        context.beginPath();
        context.arc(node.x, node.y, (1.5 + 2.4 * lit) * node.near, 0, Math.PI * 2);
        context.fill();
      }

      for (const light of lights) {
        const bloom = unit * 1.5 * light.power;
        context.drawImage(sprite, light.x - bloom, light.y - bloom, bloom * 2, bloom * 2);
        context.fillStyle = theme.core;
        context.beginPath();
        context.arc(light.x, light.y, 2.6 * light.power, 0, Math.PI * 2);
        context.fill();
      }
      context.globalCompositeOperation = "source-over";
    };

    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - previous) / 1000 || 0);
      previous = now;
      yaw += dt * 0.07;
      pointer.power += (pointer.target - pointer.power) * Math.min(1, dt * 6);
      for (const photon of photons) {
        photon.t += dt * photon.speed;
        if (photon.t >= 1) {
          const next = nextNode(photon);
          photon.from = photon.to;
          photon.to = next;
          photon.t = 0;
        }
      }
      draw();
      frame = requestAnimationFrame(tick);
    };

    const start = () => {
      cancelAnimationFrame(frame);
      if (still) {
        draw();
      } else if (visible && !document.hidden) {
        previous = performance.now();
        frame = requestAnimationFrame(tick);
      }
    };

    const sized = new ResizeObserver(() => {
      resize();
      draw();
    });
    sized.observe(element);
    const seen = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible) start();
      else cancelAnimationFrame(frame);
    });
    seen.observe(element);
    // A new theme needs a new picture even when nothing is moving.
    const themed = new MutationObserver(draw);
    themed.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const onMove = (event: PointerEvent) => {
      if (event.pointerType !== "mouse") return;
      const box = element.getBoundingClientRect();
      pointer.x = event.clientX - box.left;
      pointer.y = event.clientY - box.top;
      pointer.target = pointer.x > -60 && pointer.y > -60 && pointer.x < box.width + 60 && pointer.y < box.height + 60 ? 1 : 0;
    };
    if (!still) window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("visibilitychange", start);
    resize();
    start();

    return () => {
      cancelAnimationFrame(frame);
      sized.disconnect();
      seen.disconnect();
      themed.disconnect();
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("visibilitychange", start);
    };
  }, []);

  return <canvas ref={canvas} aria-hidden className={className} />;
}

/** Tells the page where the pointer is, so card edges can catch the light as it passes. */
export function PointerLight() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let frame = 0;
    const root = document.documentElement;
    const onMove = (event: PointerEvent) => {
      if (event.pointerType !== "mouse") return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        root.style.setProperty("--lx", `${event.clientX}px`);
        root.style.setProperty("--ly", `${event.clientY}px`);
        root.style.setProperty("--lit", "1");
      });
    };
    // No pointer on the page: no light on it.
    const onLeave = () => {
      cancelAnimationFrame(frame);
      root.style.setProperty("--lit", "0");
      root.style.setProperty("--lx", "-999px");
      root.style.setProperty("--ly", "-999px");
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    root.addEventListener("pointerleave", onLeave);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
      root.removeEventListener("pointerleave", onLeave);
    };
  }, []);
  return <div aria-hidden className="pointer-light" />;
}
