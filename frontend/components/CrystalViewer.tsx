"use client";

import type { GLViewer } from "3dmol";
import { useEffect, useImperativeHandle, useRef, type Ref } from "react";

// Jmol colors cover every element; 3Dmol's default scheme paints many cations the same pink.
const STICK = { radius: 0.12, colorscheme: "Jmol" };
const BASE_STYLE = { sphere: { scale: 0.3, colorscheme: "Jmol" }, stick: STICK };
const EMPHASIS_STYLE = { sphere: { scale: 0.42, colorscheme: "Jmol" }, stick: STICK };
const HIGHLIGHT_STYLE = { sphere: { scale: 0.48, color: "#e11d8f" }, stick: STICK };
const LABEL = { fontSize: 11, backgroundOpacity: 0.7, inFront: true };

export type CapturedViews = { views: { label: string; image: string }[]; legend: Record<string, string> };
export type ViewerHandle = { capture: () => Promise<CapturedViews> };

type Props = {
  cif: string;
  /** Site indices to draw larger (e.g. substituted sites). */
  emphasis?: number[];
  /** Site indices to color and label (e.g. atoms in a selected check). */
  highlight?: number[];
  /** Element symbol per site index, for labels. */
  species?: string[];
  ref?: Ref<ViewerHandle>;
};

function label(viewer: GLViewer, indices: number[], species: string[]) {
  for (const atom of viewer.selectedAtoms({ index: indices })) {
    viewer.addLabel(`${species[atom.index ?? 0] ?? ""}${atom.index}`, {
      ...LABEL,
      position: { x: atom.x ?? 0, y: atom.y ?? 0, z: atom.z ?? 0 },
    });
  }
}

/** Smaller JPEG copy of a rendered frame, so three views stay well under 1 MB. */
async function shrink(dataUrl: string, maxWidth = 640): Promise<string> {
  const img = new Image();
  img.src = dataUrl;
  await img.decode();
  const scale = Math.min(1, maxWidth / img.width);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(img.width * scale);
  canvas.height = Math.round(img.height * scale);
  const context = canvas.getContext("2d");
  if (!context) return dataUrl;
  context.fillStyle = "white";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(img, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.85);
}

// 3Dmol.js touches `window`, so it is loaded only in the browser.
// The CIF is P1, so atom index i in the viewer is site i in the backend.
export function CrystalViewer({ cif, emphasis = [], highlight = [], species = [], ref }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<GLViewer | null>(null);
  const loadedCif = useRef<string | null>(null);
  // Camera straight down the c axis (before the display tilt), for axis-aligned captures.
  const axisView = useRef<number[] | null>(null);

  function decorate(viewer: GLViewer) {
    viewer.removeAllLabels();
    viewer.setStyle({}, BASE_STYLE);
    if (emphasis.length) viewer.setStyle({ index: emphasis }, EMPHASIS_STYLE);
    if (highlight.length) {
      viewer.setStyle({ index: highlight }, HIGHLIGHT_STYLE);
      label(viewer, highlight, species);
    }
    viewer.render();
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const $3Dmol = await import("3dmol");
      if (cancelled || !containerRef.current) return;
      viewerRef.current ??= $3Dmol.createViewer(containerRef.current, {
        backgroundColor: "white",
      });
      const viewer = viewerRef.current;

      if (loadedCif.current !== cif) {
        viewer.clear();
        const model = viewer.addModel(cif, "cif");
        viewer.addUnitCell(model);
        viewer.zoomTo();
        axisView.current = viewer.getView();
        // A small tilt shows depth instead of looking straight down an axis.
        viewer.rotate(-20, "x");
        viewer.rotate(25, "y");
        loadedCif.current = cif;
      }
      decorate(viewer);
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cif, emphasis, highlight, species]);

  useImperativeHandle(
    ref,
    () => ({
      // Three axis views with the substituted atoms labeled by site ID (e.g. La0), then the
      // researcher's own view is restored.
      async capture() {
        const viewer = viewerRef.current;
        if (!viewer || !axisView.current) return { views: [], legend: {} };
        const $3Dmol = await import("3dmol");
        const saved = viewer.getView();
        viewer.removeAllLabels();
        label(viewer, emphasis, species);
        const shots: [string, (() => void) | null][] = [
          ["down the c axis", null],
          ["down the a axis", () => viewer.rotate(90, "y")],
          ["down the b axis", () => viewer.rotate(90, "x")],
        ];
        const views: CapturedViews["views"] = [];
        try {
          for (const [name, turn] of shots) {
            viewer.setView(axisView.current);
            turn?.();
            viewer.render();
            views.push({ label: name, image: await shrink(viewer.pngURI()) });
          }
        } finally {
          viewer.setView(saved);
          decorate(viewer);
        }
        const legend: Record<string, string> = {};
        for (const element of new Set(species)) {
          const color = $3Dmol.elementColors.Jmol[element];
          legend[element] = typeof color === "number" ? `#${color.toString(16).padStart(6, "0")}` : String(color ?? "");
        }
        return { views, legend };
      },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [emphasis, highlight, species],
  );

  return (
    <div
      ref={containerRef}
      className="relative h-80 w-full overflow-hidden rounded-md border border-line"
    />
  );
}
