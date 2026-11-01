"use client";

import { useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";
import { getCloudModel, type CloudModel } from "@/lib/api";

type Vec3 = [number, number, number];
type Mat3 = [Vec3, Vec3, Vec3]; // rows

const VOXELS_PER_ANGSTROM = 8;
const MAX_AXIS = 128;
const MAX_VOXELS = 1_500_000;
const REACH = 3.2; // cloud extent in standard deviations
const AXIS_RGB: [string, string, string] = ["#ff5a5a", "#4fd66b", "#5a9bff"];
const AXIS_NAMES = ["a", "b", "c"] as const;

const VOLUME_VERTEX = `#version 300 es
in vec2 corner;
out vec2 screen;
void main() { screen = corner; gl_Position = vec4(corner, 0.0, 1.0); }`;

// Ray marching in fractional coordinates. The crystal continues past the cell and fades out, so
// clouds are not cut flat at the box. Three things make them read as volumes: a soft density curve
// gives each cloud an edge, the density gradient shades it like a surface, and a short shadow ray
// darkens what lies behind other clouds.
const VOLUME_FRAGMENT = `#version 300 es
precision highp float;
precision highp sampler3D;
in vec2 screen;
out vec4 color;
uniform sampler3D cloud;      // rgb: element color; a: density
uniform sampler3D direction;  // rgb: direction * 0.5 + 0.5; a: stretch
uniform sampler3D wisps;      // tiling noise, for the wispy edges
uniform mat3 toWorld;         // camera to world
uniform mat3 toFractional;    // world (Å) to fractional
uniform vec3 center;          // of the cell, in Å
uniform vec3 margin;          // how far past the cell to draw, in fractions of the cell
uniform vec2 halfSize;        // of the view, in Å
uniform float thickness;
uniform float flow;           // 0 or 1
uniform float time;
uniform float byDirection;    // 0: element colors; 1: direction colors
const int STEPS = 120;
const int SHADOW_STEPS = 4;
const vec3 LIGHT = normalize(vec3(-0.5, 0.75, 0.6));

float wave(vec3 world, vec4 d) {
  if (flow < 0.5 || d.a < 0.03) return 1.0;
  vec3 axis = d.rgb * 2.0 - 1.0;
  float s = sin(dot(world, axis) * 6.0 - time * 2.2);
  return mix(1.0, 0.35 + 1.2 * smoothstep(-1.0, 1.0, s), clamp(d.a * 2.2, 0.0, 1.0));
}

vec3 directionColor(vec4 d) {
  // How far the stretch runs along a, b, and c. A round cloud has no direction, so it stays pale.
  vec3 axis = d.rgb * 2.0 - 1.0;
  vec3 along = abs(toFractional * axis);
  along /= max(max(along.r, along.g), max(along.b, 1e-4));
  along *= along;
  vec3 tint = along.r * vec3(1.0, 0.27, 0.3) + along.g * vec3(0.25, 0.9, 0.42) + along.b * vec3(0.28, 0.55, 1.0);
  return mix(vec3(0.8, 0.82, 0.9), tint / max(1.0, max(tint.r, max(tint.g, tint.b))), clamp(d.a * 2.6, 0.0, 1.0));
}

// Fades to zero outside the cell, over the margin.
float window(vec3 p) {
  vec3 outside = max(max(-p, p - 1.0) / margin, vec3(0.0));
  return 1.0 - smoothstep(0.0, 1.0, length(outside));
}

// A soft shoulder: thin at the edge, then quickly solid, so each cloud has a shape.
float curve(float a, vec3 world) {
  float n = texture(wisps, world * 0.33 + vec3(0.0, time * 0.012, 0.0)).r;
  float eroded = a - (1.0 - smoothstep(0.1, 0.7, a)) * n * 0.22;
  return smoothstep(0.07, 0.62, eroded);
}

void main() {
  vec3 origin = center + toWorld * vec3(screen * halfSize, 1000.0);
  vec3 forward = toWorld * vec3(0.0, 0.0, -1.0);
  vec3 start = toFractional * origin;
  vec3 step3 = toFractional * forward;
  vec3 low = (-margin - start) / step3;
  vec3 high = (vec3(1.0) + margin - start) / step3;
  vec3 near3 = min(low, high);
  vec3 far3 = max(low, high);
  float near = max(max(near3.x, near3.y), near3.z);
  float far = min(min(far3.x, far3.y), far3.z);
  if (far <= near) { color = vec4(0.0); return; }

  float stepLength = (far - near) / float(STEPS);
  float jitter = fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453);
  vec3 light = toWorld * LIGHT;
  vec3 lightFractional = toFractional * light;
  // World-space offsets for the gradient, one per axis.
  float e = 0.14;
  vec3 ex = toFractional * vec3(e, 0.0, 0.0);
  vec3 ey = toFractional * vec3(0.0, e, 0.0);
  vec3 ez = toFractional * vec3(0.0, 0.0, e);

  vec4 total = vec4(0.0);
  for (int i = 0; i < STEPS && total.a < 0.97; i++) {
    float t = near + (float(i) + jitter) * stepLength;
    vec3 p = start + step3 * t;
    float fade = window(p);
    if (fade < 0.01) continue;
    vec4 sampled = texture(cloud, p);
    if (sampled.a < 0.05) continue;
    vec3 world = origin + forward * t;
    vec4 d = texture(direction, p);
    float density = curve(sampled.a, world) * wave(world, d) * fade * thickness * 2.6;
    if (density < 0.002) continue;

    vec3 gradient = vec3(
      texture(cloud, p + ex).a - texture(cloud, p - ex).a,
      texture(cloud, p + ey).a - texture(cloud, p - ey).a,
      texture(cloud, p + ez).a - texture(cloud, p - ez).a
    );
    vec3 normal = -gradient / max(length(gradient), 1e-3);

    float blocked = 0.0;
    for (int s = 1; s <= SHADOW_STEPS; s++) {
      blocked += texture(cloud, p + lightFractional * float(s) * 0.3).a;
    }
    float shadow = exp(-blocked * 0.9 * thickness);
    float facing = max(dot(normal, light), 0.0);
    float rim = pow(1.0 - max(dot(normal, -forward), 0.0), 2.5);
    float shade = 0.3 + (0.25 + 1.05 * facing) * (0.25 + 0.75 * shadow) + 0.35 * rim;

    vec3 base = byDirection > 0.5 ? directionColor(d) : sampled.rgb;
    // The dense heart of a cloud glows a little, so the atom's center can be seen.
    vec3 lit = base * shade + base * pow(sampled.a, 3.0) * 0.5;
    float alpha = 1.0 - exp(-density * stepLength);
    total += vec4(lit * alpha, alpha) * (1.0 - total.a);
  }
  color = vec4(total.rgb / (1.0 + 0.25 * total.rgb), total.a);
}`;

const LINE_VERTEX = `#version 300 es
in vec3 position;
uniform mat3 toCamera;
uniform vec3 center;
uniform vec2 halfSize;
uniform float pointSize;
void main() {
  vec3 p = toCamera * (position - center);
  gl_Position = vec4(p.xy / halfSize, 0.0, 1.0);
  gl_PointSize = pointSize;
}`;

const LINE_FRAGMENT = `#version 300 es
precision mediump float;
uniform vec4 tint;
uniform float round;
out vec4 color;
void main() {
  if (round > 0.5 && length(gl_PointCoord - 0.5) > 0.5) discard;
  color = tint;
}`;

function program(gl: WebGL2RenderingContext, vertex: string, fragment: string): WebGLProgram {
  const made = gl.createProgram()!;
  for (const [type, source] of [[gl.VERTEX_SHADER, vertex], [gl.FRAGMENT_SHADER, fragment]] as const) {
    const shader = gl.createShader(type)!;
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) ?? "shader");
    gl.attachShader(made, shader);
  }
  gl.linkProgram(made);
  if (!gl.getProgramParameter(made, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(made) ?? "program");
  return made;
}

const hexToRgb = (hex: string): Vec3 => {
  const value = parseInt(hex.replace("#", "").padStart(6, "0").slice(0, 6), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
};

const multiply = (m: Mat3, v: Vec3): Vec3 => [
  m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
  m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
  m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
];

const transpose = (m: Mat3): Mat3 => [
  [m[0][0], m[1][0], m[2][0]],
  [m[0][1], m[1][1], m[2][1]],
  [m[0][2], m[1][2], m[2][2]],
];

function invert(m: Mat3): Mat3 {
  const [[a, b, c], [d, e, f], [g, h, i]] = m;
  const A = e * i - f * h;
  const B = f * g - d * i;
  const C = d * h - e * g;
  const det = a * A + b * B + c * C;
  return [
    [A / det, (c * h - b * i) / det, (b * f - c * e) / det],
    [B / det, (a * i - c * g) / det, (c * d - a * f) / det],
    [C / det, (b * g - a * h) / det, (a * e - b * d) / det],
  ];
}

// WebGL reads mat3 by column.
const glMat3 = (m: Mat3) => new Float32Array(transpose(m).flat());

function rotation(yaw: number, pitch: number): Mat3 {
  const [cy, sy, cp, sp] = [Math.cos(yaw), Math.sin(yaw), Math.cos(pitch), Math.sin(pitch)];
  return [
    [cy, sy * sp, sy * cp],
    [0, cp, -sp],
    [-sy, cy * sp, cy * cp],
  ];
}

type Field = { size: Vec3; cloud: Uint8Array; direction: Uint8Array };

/** Adds up each atom's Gaussian on a grid in fractional coordinates. The grid wraps at the cell. */
function buildField(model: CloudModel, colors: Record<string, string>): Field {
  const lattice = model.lattice as Mat3; // rows: a, b, c
  const toCartesian = transpose(lattice); // cart = toCartesian * frac
  const lengths = lattice.map((row) => Math.hypot(...row)) as Vec3;
  let size = lengths.map((l) => Math.max(16, Math.min(MAX_AXIS, Math.round(l * VOXELS_PER_ANGSTROM)))) as Vec3;
  const total = size[0] * size[1] * size[2];
  if (total > MAX_VOXELS) {
    const shrink = Math.cbrt(MAX_VOXELS / total);
    size = size.map((n) => Math.max(16, Math.floor(n * shrink))) as Vec3;
  }
  const [nx, ny, nz] = size;
  const count = nx * ny * nz;
  const density = new Float32Array(count);
  const rgb = new Float32Array(count * 3);
  const axis = new Float32Array(count * 3);
  const stretch = new Float32Array(count);

  // Cell heights, so a skewed cell still gets a wide enough box around each atom.
  const inverse = invert(toCartesian);
  const heights = inverse.map((row) => 1 / Math.hypot(...row)) as Vec3;

  for (const site of model.sites) {
    const [xx, yy, zz, xy, xz, yz] = site.covariance;
    const covariance: Mat3 = [[xx, xy, xz], [xy, yy, yz], [xz, yz, zz]];
    const precision = invert(covariance);
    const reach = REACH * Math.sqrt(Math.max(xx, yy, zz));
    const color = hexToRgb(colors[site.element] ?? "#c8c8d0");
    // A cation's cloud is tight, so without this it would nearly vanish beside the anions.
    const peak = Math.min(1.4, 0.5 / Math.max(0.2, site.radius * 0.42));
    const spans = size.map((n, i) => Math.ceil((reach / heights[i]) * n)) as Vec3;
    const middle = site.frac.map((f, i) => f * size[i]) as Vec3;
    const from = middle.map((m, i) => Math.floor(m - spans[i])) as Vec3;
    const to = middle.map((m, i) => Math.ceil(m + spans[i])) as Vec3;
    for (let k = from[2]; k <= to[2]; k++) {
      const fz = (k + 0.5) / nz - site.frac[2];
      const wz = ((k % nz) + nz) % nz;
      for (let j = from[1]; j <= to[1]; j++) {
        const fy = (j + 0.5) / ny - site.frac[1];
        const wy = ((j % ny) + ny) % ny;
        for (let i = from[0]; i <= to[0]; i++) {
          const fx = (i + 0.5) / nx - site.frac[0];
          const dx = toCartesian[0][0] * fx + toCartesian[0][1] * fy + toCartesian[0][2] * fz;
          const dy = toCartesian[1][0] * fx + toCartesian[1][1] * fy + toCartesian[1][2] * fz;
          const dz = toCartesian[2][0] * fx + toCartesian[2][1] * fy + toCartesian[2][2] * fz;
          const q =
            precision[0][0] * dx * dx + precision[1][1] * dy * dy + precision[2][2] * dz * dz +
            2 * (precision[0][1] * dx * dy + precision[0][2] * dx * dz + precision[1][2] * dy * dz);
          if (q > REACH * REACH * 2) continue;
          const weight = peak * Math.exp(-0.5 * q);
          const index = (((i % nx) + nx) % nx) + nx * (wy + ny * wz);
          density[index] += weight;
          rgb[index * 3] += weight * color[0];
          rgb[index * 3 + 1] += weight * color[1];
          rgb[index * 3 + 2] += weight * color[2];
          axis[index * 3] += weight * site.direction[0];
          axis[index * 3 + 1] += weight * site.direction[1];
          axis[index * 3 + 2] += weight * site.direction[2];
          stretch[index] += weight * site.stretch;
        }
      }
    }
  }

  const cloud = new Uint8Array(count * 4);
  const direction = new Uint8Array(count * 4);
  for (let v = 0; v < count; v++) {
    const w = density[v];
    if (w < 1e-4) continue;
    cloud[v * 4] = rgb[v * 3] / w;
    cloud[v * 4 + 1] = rgb[v * 3 + 1] / w;
    cloud[v * 4 + 2] = rgb[v * 3 + 2] / w;
    cloud[v * 4 + 3] = Math.min(255, w * 215);
    const length = Math.hypot(axis[v * 3], axis[v * 3 + 1], axis[v * 3 + 2]) || 1;
    direction[v * 4] = ((axis[v * 3] / length) * 0.5 + 0.5) * 255;
    direction[v * 4 + 1] = ((axis[v * 3 + 1] / length) * 0.5 + 0.5) * 255;
    direction[v * 4 + 2] = ((axis[v * 3 + 2] / length) * 0.5 + 0.5) * 255;
    direction[v * 4 + 3] = (stretch[v] / w) * 255;
  }
  return { size, cloud, direction };
}

function texture3d(gl: WebGL2RenderingContext, unit: number, size: Vec3, data: Uint8Array) {
  const made = gl.createTexture();
  gl.activeTexture(gl.TEXTURE0 + unit);
  gl.bindTexture(gl.TEXTURE_3D, made);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  for (const wrap of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T, gl.TEXTURE_WRAP_R]) {
    gl.texParameteri(gl.TEXTURE_3D, wrap, gl.REPEAT);
  }
  gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
  gl.texImage3D(gl.TEXTURE_3D, 0, gl.RGBA8, size[0], size[1], size[2], 0, gl.RGBA, gl.UNSIGNED_BYTE, data);
}

/** Smooth tiling noise, for the wispy cloud edges. Fixed seed: every view looks the same. */
function wispTexture(): Uint8Array {
  const size = 32;
  let seed = 7;
  const random = () => {
    seed = (seed * 16807) % 2147483647;
    return seed / 2147483647;
  };
  const coarse = (period: number) => Float32Array.from({ length: period ** 3 }, random);
  const out = new Float32Array(size ** 3);
  for (const [period, weight] of [[4, 0.6], [8, 0.3], [16, 0.1]] as const) {
    const grid = coarse(period);
    const at = (x: number, y: number, z: number) => grid[(x % period) + period * ((y % period) + period * (z % period))];
    const smooth = (v: number) => v * v * (3 - 2 * v);
    for (let k = 0; k < size; k++) for (let j = 0; j < size; j++) for (let i = 0; i < size; i++) {
      const [fx, fy, fz] = [(i / size) * period, (j / size) * period, (k / size) * period];
      const [x, y, z] = [Math.floor(fx), Math.floor(fy), Math.floor(fz)];
      const [u, v, w] = [smooth(fx - x), smooth(fy - y), smooth(fz - z)];
      const value =
        (1 - w) * ((1 - v) * ((1 - u) * at(x, y, z) + u * at(x + 1, y, z)) + v * ((1 - u) * at(x, y + 1, z) + u * at(x + 1, y + 1, z))) +
        w * ((1 - v) * ((1 - u) * at(x, y, z + 1) + u * at(x + 1, y, z + 1)) + v * ((1 - u) * at(x, y + 1, z + 1) + u * at(x + 1, y + 1, z + 1)));
      out[i + size * (j + size * k)] += value * weight;
    }
  }
  const bytes = new Uint8Array(size ** 3 * 4);
  out.forEach((value, index) => {
    bytes[index * 4] = Math.min(255, value * 255);
    bytes[index * 4 + 3] = 255;
  });
  return bytes;
}

const models = new Map<string, Promise<CloudModel>>();

function loadModel(cif: string): Promise<CloudModel> {
  let request = models.get(cif);
  if (!request) {
    request = getCloudModel(cif).catch((err) => {
      models.delete(cif);
      throw err;
    });
    models.set(cif, request);
  }
  return request;
}

type Props = {
  cif: string;
  colors: Record<string, string>;
  /** Site indices to mark (e.g. substituted sites). */
  emphasis?: number[];
};

export function CloudView({ cif, colors, emphasis = [] }: Props) {
  const t = useTranslations("Viewer");
  const canvas = useRef<HTMLCanvasElement>(null);
  const axisLabels = useRef<(SVGTextElement | null)[]>([]);
  const axisLines = useRef<(SVGLineElement | null)[]>([]);
  const [model, setModel] = useState<{ cif: string; data: CloudModel } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [byDirection, setByDirection] = useState(false);
  const [flow, setFlow] = useState(false);
  const [spin, setSpin] = useState(true);
  const [thickness, setThickness] = useState(1);
  const settings = useRef({ byDirection, flow, spin, thickness });
  settings.current = { byDirection, flow, spin, thickness };
  const reduceMotion = useRef(false);
  const graphics = useRef<WebGL2RenderingContext | null>(null);
  const emphasisKey = emphasis.join();

  useEffect(() => {
    let active = true;
    setError(null);
    loadModel(cif)
      .then((data) => active && setModel({ cif, data }))
      .catch((err) => active && setError(err instanceof Error ? err.message : String(err)));
    reduceMotion.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion.current) setSpin(false);
    return () => {
      active = false;
    };
  }, [cif]);

  const data = model?.cif === cif ? model.data : null;

  useEffect(() => {
    const element = canvas.current;
    if (!element || !data) return;
    const gl = element.getContext("webgl2", { alpha: true, premultipliedAlpha: true, antialias: true });
    if (!gl) {
      setError(t("noWebgl"));
      return;
    }
    graphics.current = gl;

    const lattice = data.lattice as Mat3;
    const toCartesian = transpose(lattice);
    const toFractional = invert(toCartesian);
    const center = multiply(toCartesian, [0.5, 0.5, 0.5]);
    let radius = 0;
    for (const a of [0, 1]) for (const b of [0, 1]) for (const c of [0, 1]) {
      const corner = multiply(toCartesian, [a, b, c]);
      radius = Math.max(radius, Math.hypot(corner[0] - center[0], corner[1] - center[1], corner[2] - center[2]));
    }

    const field = buildField(data, colors);
    texture3d(gl, 0, field.size, field.cloud);
    texture3d(gl, 1, field.size, field.direction);
    texture3d(gl, 2, [32, 32, 32], wispTexture());
    const lengths = lattice.map((row) => Math.hypot(...row));
    // About 1.6 Å past each face, so atoms on the faces show whole clouds.
    const margin = lengths.map((l) => Math.min(0.5, 1.6 / l)) as Vec3;
    let frameScale = 1;
    let frameTime = 16;

    // A browser can drop the graphics context at any time. That must cost this picture, not the page.
    let volume: WebGLProgram;
    let lines: WebGLProgram;
    try {
      volume = program(gl, VOLUME_VERTEX, VOLUME_FRAGMENT);
      lines = program(gl, LINE_VERTEX, LINE_FRAGMENT);
    } catch {
      setError(t("noWebgl"));
      return;
    }
    const quad = gl.createVertexArray();
    gl.bindVertexArray(quad);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const cornerAt = gl.getAttribLocation(volume, "corner");
    gl.enableVertexAttribArray(cornerAt);
    gl.vertexAttribPointer(cornerAt, 2, gl.FLOAT, false, 0, 0);

    const edges: number[] = [];
    const corners = [0, 1];
    for (const a of corners) for (const b of corners) {
      for (const [p, q] of [[[0, a, b], [1, a, b]], [[a, 0, b], [a, 1, b]], [[a, b, 0], [a, b, 1]]] as Vec3[][]) {
        edges.push(...multiply(toCartesian, p), ...multiply(toCartesian, q));
      }
    }
    const marks = emphasis.flatMap((i) => multiply(toCartesian, (data.sites[i]?.frac ?? [0, 0, 0]) as Vec3));
    const geometry = gl.createVertexArray();
    gl.bindVertexArray(geometry);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([...edges, ...marks]), gl.STATIC_DRAW);
    const positionAt = gl.getAttribLocation(lines, "position");
    gl.enableVertexAttribArray(positionAt);
    gl.vertexAttribPointer(positionAt, 3, gl.FLOAT, false, 0, 0);

    const u = (p: WebGLProgram, name: string) => gl.getUniformLocation(p, name);
    const uniforms = {
      cloud: u(volume, "cloud"),
      direction: u(volume, "direction"),
      wisps: u(volume, "wisps"),
      margin: u(volume, "margin"),
      toWorld: u(volume, "toWorld"),
      toFractional: u(volume, "toFractional"),
      center: u(volume, "center"),
      halfSize: u(volume, "halfSize"),
      thickness: u(volume, "thickness"),
      flow: u(volume, "flow"),
      time: u(volume, "time"),
      byDirection: u(volume, "byDirection"),
    };
    const lineUniforms = {
      toCamera: u(lines, "toCamera"),
      center: u(lines, "center"),
      halfSize: u(lines, "halfSize"),
      tint: u(lines, "tint"),
      round: u(lines, "round"),
      pointSize: u(lines, "pointSize"),
    };

    let yaw = 0.55;
    let pitch = -0.38;
    let zoom = (radius + 1.5) / radius; // the whole cell, and the clouds past its faces
    let dragging: { x: number; y: number } | null = null;
    let dirty = true;
    let last = performance.now();
    let frame = 0;
    let visible = true;

    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 1.5) * frameScale;
      const width = Math.round(element.clientWidth * ratio);
      const height = Math.round(element.clientHeight * ratio);
      if (element.width !== width || element.height !== height) {
        element.width = width;
        element.height = height;
        dirty = true;
      }
    };

    const draw = (now: number) => {
      frame = requestAnimationFrame(draw);
      if (!visible) return;
      const { byDirection: direct, flow: moving, spin: spinning, thickness: thick } = settings.current;
      const elapsed = now - last;
      const dt = Math.min(0.05, elapsed / 1000);
      last = now;
      // A slow graphics chip draws fewer pixels rather than stuttering.
      frameTime = frameTime * 0.9 + elapsed * 0.1;
      if (frameTime > 45 && frameScale > 0.5) {
        frameScale = Math.max(0.5, frameScale * 0.85);
        frameTime = 30;
      }
      if (spinning && !dragging) {
        yaw += dt * 0.28;
        dirty = true;
      }
      resize();
      if (!dirty && !moving) return;
      dirty = false;

      const aspect = element.width / Math.max(1, element.height);
      const half: [number, number] = aspect >= 1 ? [radius * zoom * aspect, radius * zoom] : [radius * zoom, (radius * zoom) / aspect];
      const toWorld = rotation(yaw, pitch);
      const toCamera = transpose(toWorld);

      gl.viewport(0, 0, element.width, element.height);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);

      gl.useProgram(lines);
      gl.bindVertexArray(geometry);
      gl.uniformMatrix3fv(lineUniforms.toCamera, false, glMat3(toCamera));
      gl.uniform3fv(lineUniforms.center, center);
      gl.uniform2fv(lineUniforms.halfSize, half);
      gl.uniform1f(lineUniforms.round, 0);
      gl.uniform1f(lineUniforms.pointSize, 1);
      gl.uniform4f(lineUniforms.tint, 0.3, 0.32, 0.4, 0.5);
      gl.drawArrays(gl.LINES, 0, edges.length / 3);

      gl.useProgram(volume);
      gl.bindVertexArray(quad);
      gl.uniform1i(uniforms.cloud, 0);
      gl.uniform1i(uniforms.direction, 1);
      gl.uniform1i(uniforms.wisps, 2);
      gl.uniform3fv(uniforms.margin, margin);
      gl.uniformMatrix3fv(uniforms.toWorld, false, glMat3(toWorld));
      gl.uniformMatrix3fv(uniforms.toFractional, false, glMat3(toFractional));
      gl.uniform3fv(uniforms.center, center);
      gl.uniform2fv(uniforms.halfSize, half);
      gl.uniform1f(uniforms.thickness, thick);
      gl.uniform1f(uniforms.flow, moving && !reduceMotion.current ? 1 : 0);
      gl.uniform1f(uniforms.time, now / 1000);
      gl.uniform1f(uniforms.byDirection, direct ? 1 : 0);
      gl.drawArrays(gl.TRIANGLES, 0, 3);

      // Marks and box edges on top, so substituted atoms stay findable inside the cloud.
      gl.useProgram(lines);
      gl.bindVertexArray(geometry);
      gl.uniform4f(lineUniforms.tint, 0.55, 0.58, 0.68, 0.35);
      gl.drawArrays(gl.LINES, 0, edges.length / 3);
      if (marks.length) {
        const ratio = element.width / Math.max(1, element.clientWidth);
        gl.uniform1f(lineUniforms.round, 1);
        gl.uniform1f(lineUniforms.pointSize, 11 * ratio);
        gl.uniform4f(lineUniforms.tint, 0, 0, 0, 0.75);
        gl.drawArrays(gl.POINTS, edges.length / 3, marks.length / 3);
        gl.uniform1f(lineUniforms.pointSize, 7 * ratio);
        gl.uniform4f(lineUniforms.tint, 1, 1, 1, 1);
        gl.drawArrays(gl.POINTS, edges.length / 3, marks.length / 3);
      }

      for (let i = 0; i < 3; i++) {
        const unit = lattice[i].map((v) => v / Math.hypot(...lattice[i])) as Vec3;
        const p = multiply(toCamera, unit);
        axisLines.current[i]?.setAttribute("x2", String(32 + p[0] * 22));
        axisLines.current[i]?.setAttribute("y2", String(32 - p[1] * 22));
        axisLabels.current[i]?.setAttribute("x", String(32 + p[0] * 29));
        axisLabels.current[i]?.setAttribute("y", String(36 - p[1] * 29));
      }
    };

    const onDown = (e: PointerEvent) => {
      dragging = { x: e.clientX, y: e.clientY };
      element.setPointerCapture(e.pointerId);
    };
    const onMove = (e: PointerEvent) => {
      if (!dragging) return;
      yaw -= (e.clientX - dragging.x) * 0.01;
      pitch = Math.max(-1.5, Math.min(1.5, pitch - (e.clientY - dragging.y) * 0.01));
      dragging = { x: e.clientX, y: e.clientY };
      dirty = true;
    };
    const onUp = () => {
      dragging = null;
    };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      zoom = Math.max(0.35, Math.min(2.5, zoom * Math.exp(e.deltaY * 0.001)));
      dirty = true;
    };
    const onLost = () => {
      cancelAnimationFrame(frame);
      setError(t("noWebgl"));
    };
    element.addEventListener("webglcontextlost", onLost);
    element.addEventListener("pointerdown", onDown);
    element.addEventListener("pointermove", onMove);
    element.addEventListener("pointerup", onUp);
    element.addEventListener("pointercancel", onUp);
    element.addEventListener("wheel", onWheel, { passive: false });
    const seen = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      dirty = true;
    });
    seen.observe(element);
    frame = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(frame);
      seen.disconnect();
      element.removeEventListener("pointerdown", onDown);
      element.removeEventListener("pointermove", onMove);
      element.removeEventListener("pointerup", onUp);
      element.removeEventListener("pointercancel", onUp);
      element.removeEventListener("wheel", onWheel);
      element.removeEventListener("webglcontextlost", onLost);
      gl.deleteProgram(volume);
      gl.deleteProgram(lines);
    };
    // The site list by value: a new array with the same sites must not restart the picture.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, colors, emphasisKey]);

  // Only when the canvas goes away: this canvas cannot draw again after its context is released.
  useEffect(
    () => () => {
      graphics.current?.getExtension("WEBGL_lose_context")?.loseContext();
      graphics.current = null;
    },
    [],
  );

  // The sites that stretch most, in words: the colors alone do not work for everyone.
  const stretched = useMemo(() => {
    if (!data) return [];
    const lattice = data.lattice as Mat3;
    const inverse = invert(transpose(lattice));
    return [...data.sites]
      .sort((a, b) => b.stretch - a.stretch)
      .slice(0, 3)
      .filter((site) => site.stretch > 0.05)
      .map((site) => {
        const along = multiply(inverse, site.direction as Vec3).map((v, i) => Math.abs(v) * Math.hypot(...lattice[i]));
        const peak = Math.max(...along);
        const axes = AXIS_NAMES.filter((_, i) => along[i] > peak * 0.6).join("+");
        return { label: `${site.element}${site.index}`, axes, stretch: site.stretch };
      });
  }, [data]);

  return (
    <div>
      <div className="relative h-96 w-full overflow-hidden rounded-lg border border-line" style={{ background: "radial-gradient(circle at 50% 40%, #0f2a1f, #061610 75%)" }}>
        <canvas ref={canvas} className="absolute inset-0 h-full w-full cursor-grab touch-none active:cursor-grabbing" aria-label={t("cloudLabel")} role="img" />
        {!data && !error && <p className="absolute inset-0 flex items-center justify-center text-sm text-white/70">{t("cloudLoading")}</p>}
        {error && <p className="absolute inset-0 flex items-center justify-center p-4 text-center text-sm text-white">{error}</p>}
        <svg viewBox="0 0 64 64" className="pointer-events-none absolute bottom-1 left-1 h-16 w-16" aria-hidden>
          {[0, 1, 2].map((i) => (
            <g key={i}>
              <line ref={(el) => { axisLines.current[i] = el; }} x1="32" y1="32" x2="32" y2="32" stroke={AXIS_RGB[i]} strokeWidth="2" strokeLinecap="round" />
              <text ref={(el) => { axisLabels.current[i] = el; }} fontSize="10" fontWeight="700" fill={AXIS_RGB[i]} textAnchor="middle">{AXIS_NAMES[i]}</text>
            </g>
          ))}
        </svg>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
        <div role="radiogroup" aria-label={t("colorLabel")} className="segmented">
          {([false, true] as const).map((option) => (
            <button
              key={String(option)}
              type="button"
              role="radio"
              aria-checked={byDirection === option}
              onClick={() => {
                setByDirection(option);
                if (option && !reduceMotion.current) setFlow(true);
                if (!option) setFlow(false);
              }}
              className="segment"
            >
              {t(option ? "colorDirection" : "colorElement")}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={flow} onChange={(e) => setFlow(e.target.checked)} />
          {t("flow")}
        </label>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={spin} onChange={(e) => setSpin(e.target.checked)} />
          {t("spin")}
        </label>
        <label className="flex items-center gap-1">
          {t("thickness")}
          <input type="range" min={0.3} max={2.5} step={0.1} value={thickness} onChange={(e) => setThickness(e.target.valueAsNumber)} className="w-24" />
        </label>
      </div>

      {byDirection && (
        <p className="mt-1 text-xs">
          {AXIS_NAMES.map((name, i) => (
            <span key={name} className="mr-2 whitespace-nowrap">
              <span aria-hidden style={{ color: AXIS_RGB[i] }}>■ </span>
              {t("along", { axis: name })}
            </span>
          ))}
          <span className="whitespace-nowrap"><span aria-hidden className="text-muted">■ </span>{t("round")}</span>
        </p>
      )}
      {stretched.length > 0 && (
        <p className="mt-1 text-xs">
          <span className="font-medium">{t("mostStretched")}</span>{" "}
          {stretched.map((s) => t("stretchItem", { site: s.label, axes: s.axes, stretch: s.stretch.toFixed(2) })).join(", ")}
        </p>
      )}
      <p className="mt-1 text-xs text-muted">{t("cloudNote")}{flow ? ` ${t("flowNote")}` : ""}</p>
    </div>
  );
}
