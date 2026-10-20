import { useEffect, useState } from "react";

/** True below `maxWidth` px. Lifted from the sic loader so other gizmos can share it. */
export function useIsNarrow(maxWidth = 640): boolean {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia(`(max-width: ${maxWidth}px)`);
    const on = () => setNarrow(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [maxWidth]);
  return narrow;
}
