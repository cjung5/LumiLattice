import { useTranslations } from "next-intl";
import type { EvidenceStatus, PropertyValue } from "@/lib/api";

// Color is never the only signal: each tag also has its own icon, text, and border style.
const TAG_STYLE: Record<EvidenceStatus, { icon: string; className: string; key: string }> = {
  Experimental: { icon: "●", className: "border-tag-exp text-tag-exp", key: "experimental" },
  "DFT-computed": { icon: "◆", className: "border-tag-dft text-tag-dft", key: "dftComputed" },
  Heuristic: {
    icon: "≈",
    className: "border-dashed border-tag-heur text-tag-heur italic",
    key: "heuristic",
  },
  Unknown: { icon: "?", className: "border-tag-unknown text-tag-unknown", key: "unknown" },
};

export function EvidenceTag({ status }: { status: EvidenceStatus }) {
  const t = useTranslations("Evidence");
  const style = TAG_STYLE[status];
  return (
    <span
      title={t(style.key)}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 text-xs ${style.className}`}
    >
      <span aria-hidden>{style.icon}</span>
      {status}
    </span>
  );
}

export function formatValue(pv: PropertyValue): string {
  if (pv.value != null) return pv.units ? `${pv.value} ${pv.units}` : String(pv.value);
  if (pv.value_range) return `≈ ${pv.value_range[0]}–${pv.value_range[1]}${pv.units ? ` ${pv.units}` : ""}`;
  return "—";
}

export function PropertyValueView({ pv }: { pv: PropertyValue }) {
  const tooltip = [pv.conditions, pv.provenance?.source, pv.provenance?.method]
    .filter(Boolean)
    .join(" · ");
  return (
    <span className="inline-flex items-center gap-1.5" title={tooltip}>
      <span
        className={`tabular-nums ${pv.status === "Heuristic" ? "italic text-tag-heur" : ""} ${
          pv.status === "Unknown" ? "text-tag-unknown" : ""
        }`}
      >
        {formatValue(pv)}
      </span>
      <EvidenceTag status={pv.status} />
    </span>
  );
}
