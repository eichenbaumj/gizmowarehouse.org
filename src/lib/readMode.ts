// ReadModeContext — lets any embed know whether it's being rendered in the full
// piece or the short-form "BLUF" view, so a component can show condensed copy
// (e.g. tuck body text into tooltips) without the markdown needing per-tag flags.
// GizmoPage provides the value; embeds read it via useReadMode(). Defaults to
// "full" so components render normally outside a GizmoPage (e.g. methodology page).

import { createContext, useContext } from "react";

export type ReadMode = "full" | "bluf";

export const ReadModeContext = createContext<ReadMode>("full");

export function useReadMode(): ReadMode {
  return useContext(ReadModeContext);
}
