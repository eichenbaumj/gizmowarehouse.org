// The selected-domain composition note: what the filter includes, and (for Legal
// and Protective service) the government-vs-private sub-occupation mix that drives
// the gap. Always visible for the selected domain, so it works on touch too
// (notes 8 and 9).

import type { DomainCompositionData, DomainBreakdownRow } from "@/lib/compgapDomains";

// A domain-specific reading of the mix, shown after the percentages.
const READING: Record<string, string> = {
  legal: "Government legal work skews toward actual attorneys; the private side carries far more paralegals, which pulls the private median down.",
  protective_service: "The large government lead here is mostly a difference in jobs — a state trooper or firefighter versus a mall security guard — not more pay for the same work.",
};

function fmt(rows?: DomainBreakdownRow[]): string {
  if (!rows || !rows.length) return "";
  return rows.map((r) => `${r.label} ${r.pct}%`).join(", ");
}

export default function DomainCompositionNote({
  domain, data,
}: { domain: string; data: DomainCompositionData | null }) {
  const comp = data?.domains?.[domain];
  if (!comp) return null;
  const gov = fmt(comp.breakdown?.government);
  const priv = fmt(comp.breakdown?.private);
  return (
    <div className="mt-3 rounded-md bg-vellum/50 px-3 py-2 text-[11.5px] leading-relaxed text-charcoal/70">
      <span className="font-semibold text-charcoal/80">Who this is:</span> {comp.includes}
      {gov && priv && (
        <>
          {" "}<span className="text-charcoal/80">In government:</span> {gov}.{" "}
          <span className="text-charcoal/80">Private sector:</span> {priv}.
          {READING[domain] ? ` ${READING[domain]}` : ""}
        </>
      )}
    </div>
  );
}
