// InfoTip — a small "ⓘ" affordance that reveals arbitrary content in a popover.
// Like MethodologyInfo, but content-agnostic (takes children instead of a
// disclosure id), for tucking away body copy in condensed/BLUF views. Opens on
// hover (desktop) and click/tap (touch); closes on outside-click or Escape.

import { useEffect, useRef, useState, type ReactNode } from "react";

interface InfoTipProps {
  children: ReactNode;
  /** Accessible label, and visible text when variant === "pill". */
  label?: string;
  align?: "left" | "right" | "center";
  variant?: "icon" | "pill";
}

export default function InfoTip({
  children,
  label,
  align = "left",
  variant = "icon",
}: InfoTipProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
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

  const popoverAlign =
    align === "right"
      ? "right-0 left-auto"
      : align === "center"
      ? "left-1/2 -translate-x-1/2"
      : "left-0";

  return (
    <span
      ref={wrapRef}
      className="relative inline-flex items-baseline"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        aria-expanded={open}
        aria-label={label ?? "More detail"}
        className={
          variant === "pill"
            ? "inline-flex items-center gap-1 rounded-full border border-slate-300 bg-white/95 px-2.5 py-1 font-sans text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-600 shadow-sm transition hover:border-cobalt/40 hover:text-cobalt"
            : "inline-flex h-4 w-4 items-center justify-center align-baseline text-[13px] leading-none text-charcoal/40 transition hover:text-charcoal/90"
        }
      >
        <span aria-hidden>ⓘ</span>
        {variant === "pill" && label ? <span>{label}</span> : null}
      </button>
      {open && (
        <div
          role="dialog"
          onClick={(e) => e.stopPropagation()}
          className={
            "absolute top-[calc(100%+8px)] z-50 w-[320px] max-w-[88vw] rounded-lg bg-white p-4 text-left text-[12.5px] font-normal normal-case leading-relaxed tracking-normal text-slate-700 shadow-2xl ring-1 ring-slate-200 " +
            popoverAlign
          }
        >
          {children}
        </div>
      )}
    </span>
  );
}
