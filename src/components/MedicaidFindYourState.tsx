// MedicaidFindYourState — small CTA strip rendered after the main embed.
// Lets the reader pick a state and either jump back to the map with that
// state preselected, or download the per-state PDF brief.
//
// Communicates with the embed via a CustomEvent on window:
//   window.dispatchEvent(new CustomEvent("medicaid-select-state", { detail: { fips } }))
// The embed listens and updates its selectedStateFips + scrolls into view.

import { useEffect, useMemo, useState } from "react";

interface StateRow {
  state_fips: string;
  state_abbr: string;
  state_name: string;
  expansion: boolean;
  subject_via_waiver?: boolean;
  waiver_listed?: boolean;
  already_work_conditional?: boolean;
  waiver_note?: string | null;
  subject_count_strict: number;
  loss_exposure_strict: number;
}

const BRIEF_BASE = "https://data.gizmowarehouse.org/medicaid-work-requirements/briefs";

function briefUrl(abbr: string): string {
  return `${BRIEF_BASE}/medicaid_brief_${abbr.toUpperCase()}.pdf`;
}

export default function MedicaidFindYourState() {
  const [states, setStates] = useState<StateRow[]>([]);
  const [fips, setFips] = useState<string>("");

  useEffect(() => {
    fetch("/data/medicaid-state-summary.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
      .then((j) => setStates(j.states))
      .catch(() => setStates([]));
  }, []);

  const sorted = useMemo(
    () => [...states].sort((a, b) => a.state_name.localeCompare(b.state_name)),
    [states],
  );

  const selected = states.find((s) => s.state_fips === fips);

  const briefDownloadUrl =
    selected && selected.expansion ? briefUrl(selected.state_abbr) : null;

  const onShowMe = () => {
    if (!fips) return;
    window.dispatchEvent(new CustomEvent("medicaid-select-state", { detail: { fips } }));
    // Smooth-scroll to the embed
    const embed = document.querySelector(".medicaid-map-embed-anchor");
    if (embed) {
      embed.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <div
      className="not-prose my-10 rounded-xl border border-cobalt/15 bg-cobalt/[0.04] px-6 py-6 sm:px-8 sm:py-8"
      style={{
        width: "min(100vw - 1.5rem, 80rem)",
        marginLeft: "calc(50% - min(50vw - 0.75rem, 40rem))",
        marginRight: "calc(50% - min(50vw - 0.75rem, 40rem))",
      }}
    >
      <h3 className="font-serif text-xl font-semibold text-cobalt">
        Get the brief for your state
      </h3>
      <p className="mt-1 text-sm leading-relaxed text-slate-700">
        PDF brief: top 10 counties, exemption summary, operational checklist
        for state Medicaid agencies with the December 31 deadline.
      </p>

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[220px]">
          <label className="block font-sans text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
            State
          </label>
          <select
            value={fips}
            onChange={(e) => setFips(e.target.value)}
            className="mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-sans text-sm shadow-sm focus:border-cobalt focus:outline-none focus:ring-1 focus:ring-cobalt"
          >
            <option value="">Pick your state…</option>
            {sorted.map((s) => (
              <option key={s.state_fips} value={s.state_fips}>
                {s.state_name}
                {s.expansion
                  ? ""
                  : s.subject_via_waiver
                    ? "  (1115 waiver)"
                    : s.waiver_listed
                      ? "  (1115 waiver — not quantified)"
                      : "  (non-expansion)"}
              </option>
            ))}
          </select>
        </div>

        <button
          type="button"
          onClick={onShowMe}
          disabled={!fips}
          className="inline-flex items-center gap-1.5 rounded-md bg-cobalt px-4 py-2 font-sans text-sm font-semibold text-white shadow-sm transition hover:bg-cobalt/90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Show me on the map
          <span aria-hidden>→</span>
        </button>

        {briefDownloadUrl && (
          <a
            href={briefDownloadUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md border border-cobalt bg-white px-4 py-2 font-sans text-sm font-semibold text-cobalt shadow-sm transition hover:bg-cobalt/[0.05]"
          >
            Download {selected!.state_abbr} brief (PDF)
            <span aria-hidden>↓</span>
          </a>
        )}
      </div>

      {selected && !selected.expansion && (
        <p className="mt-3 text-[12px] italic leading-relaxed text-slate-600">
          {selected.subject_via_waiver
            ? selected.already_work_conditional
              ? `${selected.state_name} didn't adopt Medicaid expansion but is subject to the OBBBA work requirement through its Section 1115 Pathways waiver, which already imposes an 80-hour work requirement — so the federal rule adds no net-new loss for current enrollees. The brief covers that waiver population.`
              : `${selected.state_name} didn't adopt Medicaid expansion, but its Section 1115 waiver population is subject to the OBBBA work requirement (CMS's June-2026 list). The brief models that waiver slice, sized from administrative enrollment — treat it as a projection.`
            : selected.waiver_listed
              ? `${selected.state_name} is on CMS's June-2026 list only through TennCare's 1115 parent/caretaker group (~17,700 to 100% FPL). OBBBA exempts parents of a child under 14, so almost none are actually subject — we flag it as in-scope but model no loss.`
              : `${selected.state_name} hasn't adopted Medicaid expansion and has no subject 1115-waiver population, so the OBBBA work requirement doesn't reach it. The brief covers the working-age uninsured analysis instead.`}
        </p>
      )}
    </div>
  );
}
