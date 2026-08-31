// MethodologyInfo — an unobtrusive "ⓘ" affordance that opens a popover with
// the disclosure body for a given viz ID. The disclosures themselves live
// in src/lib/methodologyDisclosures.ts. This component is intentionally
// dumb: it looks up the ID and renders the breadcrumb + caveats.
//
// The page must read cleanly without ever clicking these — they're for the
// curious reader who wants to see the synthetic chain.

import { useEffect, useRef, useState } from "react";
import { getDisclosure, METHODOLOGY_DOC_URL } from "@/lib/methodologyDisclosures";

interface Props {
  /** The disclosure ID (see DISCLOSURES in methodologyDisclosures.ts) */
  id: string;
  /**
   * Layout style. "icon" is a 14px ⓘ on its own (legends, headlines).
   * "pill" is a small rounded button reading "ⓘ Methods" (for the map frame).
   * "inline" is "ⓘ Methods" as inline text (for scrollytelling captions).
   */
  variant?: "icon" | "pill" | "inline";
  /** Where the popover hangs relative to the trigger */
  align?: "left" | "right" | "center";
  /** Optional override label for "pill" / "inline" variants */
  label?: string;
}

const COBALT = "#1F1FD6";

export default function MethodologyInfo({
  id,
  variant = "icon",
  align = "left",
  label,
}: Props) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLSpanElement | null>(null);
  const disclosure = getDisclosure(id);

  // Close on outside click + Escape
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!wrapRef.current) return;
      if (!wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!disclosure) {
    return null;
  }

  // Trigger button — three visual variants
  const trigger = (() => {
    if (variant === "pill") {
      return (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setOpen((o) => !o);
          }}
          className="inline-flex items-center gap-1 rounded-full border border-slate-300 bg-white/95 px-2.5 py-1 font-sans text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-700 shadow-sm transition hover:border-cobalt/40 hover:text-cobalt"
          aria-expanded={open}
          aria-label={`Methodology: ${disclosure.title}`}
        >
          <span aria-hidden className="text-[11px]">ⓘ</span>
          <span>{label ?? "Methods"}</span>
        </button>
      );
    }
    if (variant === "inline") {
      return (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setOpen((o) => !o);
          }}
          className="inline-flex items-baseline gap-0.5 align-baseline font-sans text-[12px] font-semibold uppercase tracking-[0.04em] text-cobalt/70 transition hover:text-cobalt"
          aria-expanded={open}
          aria-label={`Methodology: ${disclosure.title}`}
        >
          <span aria-hidden>ⓘ</span>
          <span>{label ?? "Methods"}</span>
        </button>
      );
    }
    // icon (default)
    return (
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        className="inline-flex h-4 w-4 items-center justify-center align-baseline text-[13px] leading-none text-charcoal/40 transition hover:text-charcoal/90"
        aria-expanded={open}
        aria-label={`Methodology: ${disclosure.title}`}
      >
        <span aria-hidden>ⓘ</span>
      </button>
    );
  })();

  // Popover position — absolute relative to the wrap span
  const popoverAlign =
    align === "right"
      ? "right-0 left-auto"
      : align === "center"
      ? "left-1/2 -translate-x-1/2"
      : "left-0";

  return (
    <span ref={wrapRef} className="relative inline-flex items-baseline">
      {trigger}
      {open && (
        <div
          role="dialog"
          aria-label={disclosure.title}
          className={
            "absolute top-[calc(100%+8px)] z-50 w-[340px] max-w-[88vw] rounded-lg bg-white p-4 text-left text-charcoal shadow-2xl ring-1 ring-slate-200 " +
            popoverAlign
          }
          onClick={(e) => e.stopPropagation()}
        >
          {/* Title + close */}
          <div className="flex items-start justify-between gap-3">
            <div className="font-serif text-[15px] font-semibold leading-snug text-cobalt">
              {disclosure.title}
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="-mr-1 -mt-1 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              aria-label="Close methodology"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
                <path
                  d="M3 3l8 8M11 3l-8 8"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          </div>

          {/* Breadcrumb chain */}
          <ol className="mt-3 space-y-2 text-[11.5px] leading-relaxed text-slate-700">
            {disclosure.chain.map((step, i) => (
              <li key={i} className="flex items-start gap-2">
                <span
                  className="mt-[2px] inline-block min-w-[16px] rounded-full bg-cobalt/10 px-1.5 text-center font-mono text-[10px] font-semibold text-cobalt"
                  aria-hidden
                  style={{ lineHeight: "14px" }}
                >
                  {i + 1}
                </span>
                <span>{step}</span>
              </li>
            ))}
          </ol>

          {/* Caveats */}
          {disclosure.caveats.length > 0 && (
            <div className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-[11px] leading-relaxed text-amber-900">
              <div className="mb-1 font-sans text-[10px] font-semibold uppercase tracking-[0.08em] text-amber-700">
                Caveats
              </div>
              <ul className="space-y-1">
                {disclosure.caveats.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Full methodology link */}
          <a
            href={`${disclosure.docUrl ?? METHODOLOGY_DOC_URL}${disclosure.fullMethodologyAnchor ?? ""}`}
            target="_blank"
            rel="noreferrer"
            className="mt-3 inline-flex items-center gap-1 font-sans text-[11px] font-semibold uppercase tracking-[0.06em] text-cobalt transition hover:text-cobalt/80"
            style={{ color: COBALT }}
          >
            Read the full methodology
            <span aria-hidden>→</span>
          </a>
        </div>
      )}
    </span>
  );
}
