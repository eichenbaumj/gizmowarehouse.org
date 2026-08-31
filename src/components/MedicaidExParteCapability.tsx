// MedicaidExParteCapability — the "Ex parte capability" standalone asset.
//
// Split out of MedicaidLossSankey (v8 design-asset pass) so ex parte capability
// and coverage loss are two separate, independently-addressable sections. The
// cartogram primitive (ExParteCartogram) still lives in MedicaidLossSankey and
// is imported here; this wrapper owns the data fetch, the view toggle, and the
// explanatory copy.
//
// Data source: /data/medicaid-loss-breakdown.json (the ex_parte_table array).

import { useEffect, useState } from "react";
import { ExParteCartogram, type ExParteRow } from "@/components/MedicaidLossSankey";
import { type CartogramView, CARTOGRAM_VIEW_LABELS } from "@/lib/medicaidExParteViews";

export default function MedicaidExParteCapability() {
  const [rows, setRows] = useState<ExParteRow[] | null>(null);
  const [view, setView] = useState<CartogramView>("composite");

  useEffect(() => {
    fetch("/data/medicaid-loss-breakdown.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
      .then((j) => setRows(j.ex_parte_table ?? []))
      .catch(() => setRows(null));
  }, []);

  if (!rows) {
    return (
      <div className="not-prose my-8 rounded-lg border border-slate-200 bg-slate-50 px-6 py-10 text-center text-sm text-slate-500">
        Loading the ex parte capability index…
      </div>
    );
  }

  return (
    <div
      className="not-prose my-10 rounded-xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8"
      style={{
        width: "min(100vw - 1.5rem, 80rem)",
        marginLeft: "calc(50% - min(50vw - 0.75rem, 40rem))",
        marginRight: "calc(50% - min(50vw - 0.75rem, 40rem))",
      }}
    >
      <p className="mb-3 text-sm leading-relaxed text-slate-600">
        <strong>Ex parte verification</strong> is how a state checks an enrollee's
        work hours or exemption against administrative data it already holds, so the
        enrollee doesn't have to track down proof. OBBBA §1902(xx)(4)(D) requires
        states to attempt this check first, before asking the enrollee to do anything.
      </p>
      <p className="mb-3 text-sm leading-relaxed text-slate-600">
        The 0–100 composite leads with each state's <strong>observed ex parte
        rate</strong>: the share of Medicaid renewals it actually completed
        automatically during the 2023–2026 unwinding (CMS data). That's a realized
        measure of whether a state can clear someone without making them act, so it
        carries 50% of the score. <strong>Data sources</strong>
        <sup className="text-cobalt">*</sup>, the work-requirement-specific feeds that
        income renewals didn't test (UI wage records, Medicaid claims, behavioral-health
        MCO enrollment, SNAP/TANF compliance, vital records, corrections, child-welfare,
        and workforce-development records), carry 35%, and documented prior Section 1115
        work-requirement <strong>churn</strong>{" "}carries 15%.
      </p>
      <p className="mb-4 text-sm leading-relaxed text-slate-600">
        High-score states (≥70) project low procedural disenrollment; below 45
        projects Arkansas-grade churn. Cells marked{" "}
        <span className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full border border-slate-700 bg-white align-middle text-[7.5px] font-bold text-slate-900">H</span>
        {" "}have documented prior Section 1115 experience. Hover any state for its
        observed rate, sub-scores, and eligibility system. We publish the scores, not
        a predicted administrative-churn rate.
      </p>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="font-sans text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          View
        </span>
        <div className="inline-flex gap-1.5">
          {(["composite", "observed_ex_parte", "data_sources"] as CartogramView[]).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setView(v)}
              className={
                "rounded-md px-3 py-1.5 font-sans text-[12px] transition " +
                (view === v
                  ? "bg-cobalt text-white shadow-sm"
                  : "border border-slate-300 bg-white text-slate-700 hover:border-cobalt/40 hover:bg-slate-50")
              }
            >
              {CARTOGRAM_VIEW_LABELS[v]}
            </button>
          ))}
        </div>
      </div>

      <ExParteCartogram rows={rows} view={view} />

      <p className="mt-3 text-[11px] leading-snug text-slate-400">
        The seven states with no subject population (AL, FL, KS, MS, SC, TX, WY)
        render hatched gray. Three non-expansion states are subject through a
        Section 1115 waiver per CMS's June-2026 list — Wisconsin and Georgia
        (sized waiver slices) and Tennessee (reached only via its 1115
        parent/caretaker group, which OBBBA largely exempts) — and
        are not scored here, since no work-requirement-specific verification-feed
        data exists for these waiver populations yet. Sources: observed ex parte renewal rates from CMS
        eligibility-processing data (2023–2026); the KFF / Georgetown CCF "Early Look at Policy Decisions"
        (Apr 2026) + state vendor filings for the data-source flags; and prior Section
        1115 work-requirement experience (Sommers 2019 and court records) for
        historical churn. Vital-records and workforce-development flags are populated
        only for states with documented evidence; see methodology §3.5 for the
        per-state research status.
      </p>

      <p className="mt-2 text-[11px] leading-snug text-slate-400">
        <span className="text-cobalt">*</span> A better version of this analysis would
        compare states on their supplemental income-verification tools, and specifically
        their use of consent-based verification, the only mechanism that reaches gig and
        self-employment income. We don't score it here: credit-agency income data
        (Equifax's The Work Number) is available to every state through the federal data hub, so
        it doesn't differentiate, and reliable per-state data on consent-based adoption
        isn't yet available. For more on CBV design, see 17A's{" "}
        <a
          href="https://group17a.substack.com/p/introducing-our-consent-based-verification"
          target="_blank"
          rel="noopener noreferrer"
          className="font-semibold text-cobalt hover:underline"
        >
          CBV Buying Guide
        </a>
        .
      </p>

      <p className="mt-3 rounded-md border-l-4 border-amber-300 bg-amber-50/60 px-4 py-3 text-[12.5px] leading-relaxed text-slate-600">
        <strong className="text-slate-700">A note on Pennsylvania.</strong>{" "}
        PA's national-floor ex parte score reflects the disrupted 2023–24 unwinding, when
        a faulty household-level auto-renewal process (flagged by federal officials) and a
        concurrent CHIP-to-Medicaid system integration sharply depressed its
        automatic-renewal rate, rather than the state's underlying capability. State
        officials expected ex parte rates to climb, and most states' rates have improved
        since, so PA is likely to perform better than this baseline in the coming renewal
        cycle. See{" "}
        <a
          href="https://www.spotlightpa.org/news/2023/10/pennsylvania-medicaid-chip-health-insurance-covid-pandemic-unwinding/"
          target="_blank"
          rel="noopener noreferrer"
          className="font-semibold text-cobalt hover:underline"
        >
          Spotlight PA
        </a>
        .
      </p>
    </div>
  );
}
