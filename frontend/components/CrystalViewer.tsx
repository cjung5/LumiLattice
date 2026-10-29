"use client";

import type { GLViewer } from "3dmol";
import { useEffect, useRef } from "react";

// Jmol colors cover every element; 3Dmol's default scheme paints many cations the same pink.
const STICK = { radius: 0.12, colorscheme: "Jmol" };
const BASE_STYLE = { sphere: { scale: 0.3, colorscheme: "Jmol" }, stick: STICK };
const EMPHASIS_STYLE = { sphere: { scale: 0.42, colorscheme: "Jmol" }, stick: STICK };
const HIGHLIGHT_STYLE = { sphere: { scale: 0.48, color: "#e11d8f" }, stick: STICK };

type Props = {
  cif: string;
  /** Site indices to draw larger (e.g. substituted sites). */
  emphasis?: number[];
  /** Site indices to color and label (e.g. atoms in a selected check). */
  highlight?: number[];
  /** Element symbol per site index, for labels. */
  species?: string[];
};

// 3Dmol.js touches `window`, so it is loaded only in the browser.
// The CIF is P1, so atom index i in the viewer is site i in the backend.
export function CrystalViewer({ cif, emphasis = [], highlight = [], species = [] }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<GLViewer | null>(null);
  const loadedCif = useRef<string | null>(null);

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
        // A small tilt shows depth instead of looking straight down an axis.
        viewer.rotate(-20, "x");
        viewer.rotate(25, "y");
        loadedCif.current = cif;
      }

      viewer.removeAllLabels();
      viewer.setStyle({}, BASE_STYLE);
      if (emphasis.length) viewer.setStyle({ index: emphasis }, EMPHASIS_STYLE);
      if (highlight.length) {
        viewer.setStyle({ index: highlight }, HIGHLIGHT_STYLE);
        for (const atom of viewer.selectedAtoms({ index: highlight })) {
          viewer.addLabel(`${species[atom.index ?? 0] ?? ""}${atom.index}`, {
            position: { x: atom.x ?? 0, y: atom.y ?? 0, z: atom.z ?? 0 },
            fontSize: 11,
            backgroundOpacity: 0.7,
            inFront: true,
          });
        }
      }
      viewer.render();
    })();
    return () => {
      cancelled = true;
    };
  }, [cif, emphasis, highlight, species]);

  return (
    <div
      ref={containerRef}
      className="relative h-80 w-full overflow-hidden rounded-md border border-line"
    />
  );
}
