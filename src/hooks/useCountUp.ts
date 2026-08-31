// useCountUp — animate a numeric value from its current displayed value to
// `target` over `durationMs`, using cubic ease-out.
//
// Uses requestAnimationFrame for smooth 60 FPS animation. The starting point
// for each new animation is the value as of the most recent render, not the
// previous target — so rapid changes feel continuous rather than jerky.

import { useEffect, useRef, useState } from "react";

export function useCountUp(target: number, durationMs = 600): number {
  const [value, setValue] = useState<number>(0);
  const valueRef = useRef<number>(0);
  valueRef.current = value;

  useEffect(() => {
    if (!Number.isFinite(target)) return;
    const start = valueRef.current;
    if (start === target) return;
    const startTime = performance.now();
    let raf = 0;
    const tick = () => {
      const elapsed = performance.now() - startTime;
      const t = Math.min(1, elapsed / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(start + (target - start) * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, durationMs]);

  return value;
}
