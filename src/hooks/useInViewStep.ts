import { RefObject, useEffect, useState } from "react";

/**
 * Track which "step" element is currently in view within a scrollytelling
 * sequence. Returns the index (0-based) of the most-visible step, or -1
 * if none are within range.
 *
 * Adapted from the multi-city-crime-explorer's HeroFlyover pattern.
 */
export function useInViewStep(
  stepRefs: RefObject<(HTMLElement | null)[]>,
  opts: { threshold?: number; rootMargin?: string } = {},
) {
  const { rootMargin = "-30% 0px -30% 0px" } = opts;
  const [activeStep, setActiveStep] = useState(-1);

  useEffect(() => {
    const els = (stepRefs.current ?? []).filter(
      (el): el is HTMLElement => el != null,
    );
    if (els.length === 0) return;

    const visibility = new Map<HTMLElement, number>();

    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          visibility.set(e.target as HTMLElement, e.intersectionRatio);
        }
        let bestIdx = -1;
        let bestRatio = 0;
        els.forEach((el, idx) => {
          const r = visibility.get(el) ?? 0;
          if (r > bestRatio) {
            bestRatio = r;
            bestIdx = idx;
          }
        });
        setActiveStep(bestRatio > 0 ? bestIdx : -1);
      },
      { threshold: [0, 0.25, 0.5, 0.75, 1], rootMargin },
    );

    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [stepRefs, rootMargin]);

  return activeStep;
}
