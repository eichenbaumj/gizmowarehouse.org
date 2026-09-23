// Build-time data for the static render (tools/prerender.ts via
// src/entry-static.tsx). In the browser the provider is absent, `isStatic`
// is false, and pages fetch their data contexts as they always have. At build
// time the prerenderer passes the JSON files it read from public/ so the
// numbers in the prose are baked into the crawlable HTML.
import { createContext, useContext } from "react";

export interface StaticData {
  isStatic: boolean;
  /** Keyed by the URL a page would otherwise fetch (e.g. "/data/compgap/headline.json"). */
  dataContexts: Record<string, unknown>;
}

export const StaticDataContext = createContext<StaticData>({ isStatic: false, dataContexts: {} });

export function useStaticData(): StaticData {
  return useContext(StaticDataContext);
}
