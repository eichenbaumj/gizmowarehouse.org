// Shared domain metadata + the per-domain composition feed for the comp-gap
// gizmo. Labels live here so the explorer, the locality card, and the tooltips
// all agree. Composition data (what each filter includes, plus the
// government-vs-private sub-occupation mix for Legal and Protective service)
// comes from /data/compgap/domain_composition.json (pipeline stage 07).

import { useEffect, useState } from "react";

export const DOMAIN_LABELS: Record<string, string> = {
  all: "All occupations",
  software_it: "Software & IT",
  legal: "Legal",
  finance: "Finance & Accounting",
  engineering: "Engineering",
  management: "Management",
  healthcare: "Healthcare",
  education: "Education",
  protective_service: "Protective service",
  skilled_trades: "Skilled trades",
  admin_clerical: "Office & admin",
};

export const DOMAIN_ORDER = [
  "all", "software_it", "legal", "finance", "engineering", "management",
  "healthcare", "education", "protective_service", "skilled_trades", "admin_clerical",
];

export const ELITE_DOMAINS = new Set([
  "software_it", "legal", "finance", "engineering", "management",
]);

export interface DomainBreakdownRow { label: string; pct: number }
export interface DomainComposition {
  includes: string;
  breakdown?: { government?: DomainBreakdownRow[]; private?: DomainBreakdownRow[] };
}
export interface DomainCompositionData {
  year: number;
  domains: Record<string, DomainComposition>;
}

let cache: DomainCompositionData | null = null;

// Fetch domain_composition.json once and share it across mounts.
export function useDomainComposition(): DomainCompositionData | null {
  const [data, setData] = useState<DomainCompositionData | null>(cache);
  useEffect(() => {
    if (cache) { setData(cache); return; }
    let live = true;
    fetch("/data/compgap/domain_composition.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) cache = d; if (live) setData(d); })
      .catch(() => {});
    return () => { live = false; };
  }, []);
  return data;
}
