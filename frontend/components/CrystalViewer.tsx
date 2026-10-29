"use client";

import type { GLViewer } from "3dmol";
import { useEffect, useRef } from "react";

// 3Dmol.js touches `window`, so it is loaded only in the browser.
export function CrystalViewer({ cif }: { cif: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<GLViewer | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const $3Dmol = await import("3dmol");
      if (cancelled || !containerRef.current) return;
      viewerRef.current ??= $3Dmol.createViewer(containerRef.current, {
        backgroundColor: "white",
      });
      const viewer = viewerRef.current;
      viewer.clear();
      const model = viewer.addModel(cif, "cif");
      viewer.setStyle({}, { sphere: { scale: 0.3 }, stick: { radius: 0.12 } });
      viewer.addUnitCell(model);
      viewer.zoomTo();
      viewer.render();
    })();
    return () => {
      cancelled = true;
    };
  }, [cif]);

  return (
    <div
      ref={containerRef}
      className="relative h-80 w-full overflow-hidden rounded-md border border-line"
    />
  );
}
