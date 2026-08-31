// MountWhenNear — defer mounting heavy children (e.g. a MapLibre/WebGL map)
// until the reader scrolls near them, and unmount them once scrolled far past,
// so their WebGL context + tile memory is released. On iOS the explore map's
// context is the bulk of the page's memory; not mounting it while the reader is
// still up in the hero is the main fix for the renderer-OOM tab crash.
//
// Desktop (fine pointer) is a PURE PASSTHROUGH: it renders {children} directly,
// with no observer, no placeholder, eager mount, and no unmounting — byte-for-
// byte today's behavior. Only touch-primary devices get the lazy mount/unmount.
//
// Mirrors the repo's IntersectionObserver idiom (src/hooks/useInViewStep.ts):
// construct observers in a useEffect, observe a ref'd element, disconnect on
// cleanup. Uses two observers for hysteresis — mount when within `marginScreens`
// of the viewport, unmount only once more than `unmountMarginScreens` away — so
// small back-and-forth scrolls never thrash (which would re-fetch tile data).

import { useEffect, useRef, useState, type ReactNode } from "react";
import { isTouchPrimary } from "@/lib/isTouchPrimary";

interface MountWhenNearProps {
  children: ReactNode;
  /** Reserved height (px or CSS length) while unmounted, until first measured. */
  placeholderHeight?: number | string;
  /** Screens of lead before mounting. Default 1.5. */
  marginScreens?: number;
  /** Screens of lag before unmounting (must exceed marginScreens). Default 3. */
  unmountMarginScreens?: number;
}

export default function MountWhenNear({
  children,
  placeholderHeight = 1200,
  marginScreens = 1.5,
  unmountMarginScreens = 3,
}: MountWhenNearProps) {
  // Read the gate once. Stable for the component's lifetime, so the early
  // return below never changes the hook order across renders.
  const [touch] = useState(() => isTouchPrimary());
  if (!touch) return <>{children}</>;
  return (
    <MountWhenNearObserved
      placeholderHeight={placeholderHeight}
      marginScreens={marginScreens}
      unmountMarginScreens={unmountMarginScreens}
    >
      {children}
    </MountWhenNearObserved>
  );
}

function MountWhenNearObserved({
  children,
  placeholderHeight,
  marginScreens,
  unmountMarginScreens,
}: Required<Omit<MountWhenNearProps, "children">> & { children: ReactNode }) {
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const [mounted, setMounted] = useState(false);
  // Last measured height of the children while mounted — reused as the
  // placeholder height on unmount so the page doesn't jump.
  const measuredRef = useRef<number | null>(null);

  // Measure children height while mounted.
  useEffect(() => {
    const el = sentinelRef.current;
    if (!mounted || !el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => {
      const h = el.getBoundingClientRect().height;
      if (h > 0) measuredRef.current = h;
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [mounted]);

  // Mount/unmount observers with hysteresis.
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      setMounted(true); // no IO support → mount eagerly, never unmount
      return;
    }
    let mountObs: IntersectionObserver | null = null;
    let unmountObs: IntersectionObserver | null = null;
    const build = () => {
      mountObs?.disconnect();
      unmountObs?.disconnect();
      const vh = window.innerHeight || 800;
      const enter = Math.round(marginScreens * vh);
      const exit = Math.round(unmountMarginScreens * vh);
      mountObs = new IntersectionObserver(
        (entries) => {
          if (entries.some((e) => e.isIntersecting)) setMounted(true);
        },
        { rootMargin: `${enter}px 0px ${enter}px 0px`, threshold: 0 },
      );
      unmountObs = new IntersectionObserver(
        (entries) => {
          if (entries.every((e) => !e.isIntersecting)) setMounted(false);
        },
        { rootMargin: `${exit}px 0px ${exit}px 0px`, threshold: 0 },
      );
      mountObs.observe(el);
      unmountObs.observe(el);
    };
    build();
    // Recompute px margins when the viewport height changes (mobile URL bar
    // show/hide, rotation) so the screen-based margins stay honest.
    const onResize = () => build();
    window.addEventListener("resize", onResize);
    window.addEventListener("orientationchange", onResize);
    return () => {
      mountObs?.disconnect();
      unmountObs?.disconnect();
      window.removeEventListener("resize", onResize);
      window.removeEventListener("orientationchange", onResize);
    };
  }, [marginScreens, unmountMarginScreens]);

  const ph = measuredRef.current ?? placeholderHeight;
  const minHeight = typeof ph === "number" ? `${ph}px` : ph;

  return (
    <div ref={sentinelRef} style={{ minHeight: mounted ? undefined : minHeight }}>
      {mounted ? (
        children
      ) : (
        <div className="flex h-full min-h-[inherit] items-center justify-center py-16 font-sans text-xs uppercase tracking-[0.14em] text-slate-400">
          Loading map…
        </div>
      )}
    </div>
  );
}
