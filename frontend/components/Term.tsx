"use client";

import { useTranslations } from "next-intl";
import { useId, useRef, useState, type MouseEvent, type ReactNode } from "react";

export type TermId =
  | "n"
  | "band_gap"
  | "host"
  | "candidate"
  | "swap"
  | "cell"
  | "experimental"
  | "dft"
  | "heuristic"
  | "unknown"
  | "mix";

const WIDTH = 288;
const GUTTER = 16;

// A popover in the top layer, so a scrolling table or a sticky bar cannot clip it. Click or
// keyboard, not hover, so it works on phones. Click outside or Escape closes it.
export function Term({ id, children, bare = false }: { id: TermId; children: ReactNode; bare?: boolean }) {
  const t = useTranslations("Glossary");
  const popoverId = useId();
  const popover = useRef<HTMLSpanElement>(null);
  const [place, setPlace] = useState({ top: 0, left: 0, width: WIDTH });

  function position(event: MouseEvent<HTMLButtonElement>) {
    event.stopPropagation(); // A term can sit in a clickable table row.
    const rect = event.currentTarget.getBoundingClientRect();
    const width = Math.min(WIDTH, window.innerWidth - 2 * GUTTER);
    setPlace({
      top: rect.bottom + 6,
      left: Math.max(GUTTER, Math.min(rect.left, window.innerWidth - width - GUTTER)),
      width,
    });
    window.addEventListener("scroll", () => popover.current?.hidePopover(), { once: true, capture: true });
  }

  return (
    <>
      <button
        type="button"
        popoverTarget={popoverId}
        onClick={position}
        aria-label={t("about", { term: t(`${id}.name`) })}
        className={bare ? "cursor-help" : "cursor-help underline decoration-dotted underline-offset-2"}
      >
        {children}
      </button>
      {/* Spans: a term can sit inside a paragraph or a heading. */}
      <span
        id={popoverId}
        ref={popover}
        popover="auto"
        style={{ position: "fixed", inset: "auto", margin: 0, ...place }}
        className="rounded-lg border border-line-strong bg-surface p-3.5 text-left text-sm font-normal text-foreground shadow-lg"
      >
        <span className="block font-semibold">{t(`${id}.name`)}</span>
        <span className="mt-1 block">{t(`${id}.text`)}</span>
      </span>
    </>
  );
}
