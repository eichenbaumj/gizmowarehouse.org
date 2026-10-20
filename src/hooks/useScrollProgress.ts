import { useEffect, useState, type RefObject } from "react";

/**
 * 0..1 progress of a tall section through the viewport: 0 when its top reaches the viewport top,
 * 1 when its bottom reaches the viewport bottom. Drives time-lapse style stages where a sticky child
 * animates continuously with scroll. SSR-safe (0).
 */
export function useScrollProgress(ref: RefObject<HTMLElement | null>): number {
  const [p, setP] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof window === "undefined") return;
    let raf = 0;
    const update = () => {
      raf = 0;
      const r = el.getBoundingClientRect();
      const total = r.height - window.innerHeight;
      const v = total <= 0 ? 1 : Math.min(1, Math.max(0, -r.top / total));
      setP(v);
    };
    const on = () => { if (!raf) raf = requestAnimationFrame(update); };
    update();
    window.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => { window.removeEventListener("scroll", on); window.removeEventListener("resize", on); cancelAnimationFrame(raf); };
  }, [ref]);
  return p;
}
