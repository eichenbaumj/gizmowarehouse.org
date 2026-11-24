# Step D, inventory side: design note (2026-11-18)

Design only; nothing run or built. Sources read: the handover's step D items 4 and 6 and its date-evidence paragraph; the ledger at the ranges the brief names, D-94's "Step D's scope", D-95 sections 3 and 5; the code, tests, corrections, records and evidence files named in the brief. Load and sales only.

## 1. How each adopted correction reaches the rebuilt inventory

Principle: the real rebuild's arithmetic stays `build_inventory`'s own (`state_anchor`, `site_mw`, `pick_utilities`). The reading of a correction is `pass_c_expand`'s, imported unchanged. A new `pipeline/facilities/corrections.py` hands the in-progress frame to `px.parse_corrections` (it reads only `fac`, `fixed`, `phases` and the `fy` fids) and uses `px._apply_fields` and `Correction.history`. The scratch rebuild then becomes an independent check (section 4).

- **Assign.** `apply_verified.main` globs `batch_*.json` in sorted order. That puts `batch_c_*` before `batch_r2`, `batch_r3*`, the state sweeps and `batch_v_*`; only `batch_v_` is read last. The handover's "reads batch_c last" is not what the code does. Change: read `batch_c_*` after `batch_v_*`, skipping fids in `pass_c_withdrawn.json`, fids the corrections file reopens (`bi:848-0`), and `bi:941-0`, which D-95 withdrew but which is still in `batch_c_1.json`. Test: every `batch_c` site ends on the corrections file's `assign` target or, for the 33 other records, on its frozen utility.
- **Reopen.** `px._apply_fields`, in `build_inventory.main` after the overrides' utility block and the successor mapping (`bi:848-0` [19325, 14354]; `bi:1257-0` [14401, 27000]). The build fails if a fid named withdrawn is verified without a later record or a reopen.
- **Candidates.** Same place and function (`bi:910-0` and SAT40 add CPS Energy; `bi:1123-0` adds 27058). Central Electric Cooperative's row is `bi:841-0`, which the closing register names and the handover does not. That row is verified, the machinery refuses candidates there, and the file has no entry (R9).
- **Coordinates.** No function exists, and the scratch rebuild never modelled location. New kind `location`, applied before `assign_utility` and the state join, so territory candidates and the map are recomputed. **No corrected coordinate is on file as a number.** The records give parcels instead: Bexar PropIDs 1433662 to 1433664 (`bi:910-0`), 1433747 (`bi:911-0`) and 1370366 (SAT14), plus FedEx's 250 Spectrum Loop (`bi:446-0`). For the NSA row (`bi:937-0`) the register says the point queried "was chosen from general knowledge" (R8).
- **Date interval and convention.** `Correction.history` at the convention, after `apply_overrides` and `site_energy` and before `state_anchor`. This sets `energized_year`, adds interval columns (`date_earliest`, `date_latest`, `date_never_possible`, `date_ends`, `date_convention_is`) and labels `date_basis`: `convention_latest_year_the_evidence_allows` where evidence rules out the inventory year (D-58 1.4), otherwise the convention's source. With no convention: `unresolved_start` (R2).
- **Capacity split.** The `("phases", ...)` history at the convention enters `build_inventory`'s `phases` dict. `bi:837-0` has no convention on either question (R2).
- **Year-built relabel.** The 115 `government_record_years.csv` rows with `record_is == "year built"`, all now `verified_public_source`, take `year_built_on_a_government_record_used_as_start_by_convention`. Test: `facility_year` identical before and after. Their convention year is not a coding question (R1).
- **Six Oregon years.** Five are identifiable: `bi:819-0`, `bi:820-0`, `bi:822-0`, `bi:823-0` and `bi:846-0`, all first fuel. D-17 is outside my permitted ranges, so the sixth is unnamed. They become date entries under R3.

Reproducibility: before any run, the orchestrator snapshots the 2026-11-14 `data/interim` parquet files and `data/frozen/inventory_report.json` with hashes, because `build_inventory` overwrites both. "No corrections reproduces the frozen inventory exactly" is retargeted at that snapshot. Today's `px.reproduce` test reads `data/interim` and would pass vacuously after the rebuild. "No corrections" means no `batch_c`, no corrections file, no relabel and no `location`. `geocode_epoch` fetches on a cache miss, so it runs offline and stops on a miss.

## 2. How `treatment_bounds.py` and the screen consume intervals

**Required by the text.**

- *Reference.* The group and first crossing on the corrected inventory as built, every convention in place, factors recomputed (D-61 5.4, addendum point 6). A reference that turns on a provisional convention is undefined (D-72, D-90).
- *Keeping its place.* In every admissible history (ruling 4's four cases, each date case, each capacity case, as built and with no anchoring), the group is the reference's and a cohort crossing is within one year. A comparison utility stays under 0.5% throughout.
- *Open below* moves only the unresolved phase. Where the phase's capacity is unknown, the whole row is carried, labelled conservative (1528, 1532).
- *Corners* suffice only where earlier means more load; otherwise the joint check (D-58 1.7).
- *The generic screen.* Interval sites leave it. Other still permit-dated sites of 20 MW or more keep the three- and five-year screen, "under both together" (1.5). The factor is recomputed in every screen case, with the old figure beside and utilities moved by that alone listed (1.7).
- *Reporting.* Each place shows the original crossing, the reference and the range, called "tested" unless both ends are evidence (D-63 rule 4). Utilities that fail only open below get their own list, with the screen and the permit-error reach beside, and are called unsettled on timing, not misdated.

**The convention year** fixes the reference and so centres the tolerance. That is one-sided in effect where it sits at the late end (5.4). **A site with no convention**: its utility has a reference only if every admissible history gives the same group and crossing. Otherwise the utility is unsettled (addendum point 5).

**Design.** A new `timing.py` writes the rebuilt inventory's interval columns back as corrections whose conventions equal the current years, so the reference configuration reproduces the rebuild exactly. It then runs `pass_c_exact`'s per-state enumeration (`_State`, `reference_of`), already validated against an exhaustive evaluator, under three settings of the generic screen (none, 3 and 5 earlier, factor recomputed). `treatment_bounds.main` reads the verdicts into its existing `why` lists, so `power_simulation.set_aside` needs no change.

**New choices, not settled by the text:** crossing the screen with the interval settings (R10); the ceiling (R6). One routine choice: running the test at both thresholds, as `treatment_bounds` does now, though the pass's references exist at 2% only.

## 3. The later-start sensitivity

**Definition** (choices marked in R7). Rows counted: every row whose start is a permit-based year. That means `first_generator_permit_plus_lag` rows with no interval, plus interval rows whose convention or late end is a permit-based year, plus a capacity split's rest, which arrives late at the inventory year. For each k in {1, 3, 5}, all of them shift k years later together.

- *An evidence end* (`ends: evidence`, or an operating-by year) stops the shift there, and the site and scenario are listed as incompatible. D-61 section 6: "Nothing is clipped silently".
- *Known phases do not move:* D-28 histories, operator-reported electricity, Epoch timelines, a split's dated first phase.
- *Recomputed:* factors, loads, crossings, then classification by section 2's test against the unshifted reference.
- *A start after 2025* carries no load.

**Outputs, per k:** utilities whose group changes, whose cohort crossing moves two years or more, or whose comparison eligibility changes; set sizes; incompatible sites; factors by state. Reported beside the primary result, with no set-aside (D-65 point 3; D-94).

**Tests on invented inputs, first.** Only listed rows move. Evidence ends hold and are listed. Phased and measured sites stay put. A post-2025 start carries no load. A 2023-or-later shift changes the factor and raises an unshifted site's load. A shift of 0 reproduces the primary exactly.

## 4. Consistency check after the rebuild

`docs/gate1/expansion-test-2026-11-18-s17.json`, `exact[state]["utilities"]["<id>:<st>"]["reference"]`: 3,149 utilities at 2%, criterion either_reading, 4 undefined. Where `defined`, compare `place` and `crossing` with the rebuild's as-built 2% first crossing and its place (group; "comparison" if the largest as-built share is under 0.5%; else "neither"). Separately, every `expansion.utilities[].original` must equal the no-corrections rebuild.

**Legitimate differences**, each traced to a named site:

1. A coordinate correction, which the pass never modelled.
2. The map rerun after a factor change. `build_inventory` reruns `pick_utilities` on scaled loads; the scratch rebuild holds the map fixed (R5).
3. A convention changed by a ruling on R1, R3 or R4.
4. A load within about one part in 10^9 of a threshold.

Undefined references are not compared. They are recomputed on the rebuild and must stay undefined unless 1 to 3 explain why not. Anything else stops the run.

## 5. Where the text does not settle the code

Research decisions for the owner, not resolved here:

- **R1. The 115, and the 43 certificates and 8 other records.** D-63 rule 3 has them keep their labels "until step D reads each record for what the building was built as". D-95 says the closing "does not authorize another search round". D-94's source exception covers only the ownership and supplier tables. The file's 27 provisional entries take the year built as convention (addendum point 1); rule 3.4 would keep the permit-based year when purpose is unknown. Options: (a) open only the cited record; (b) relabel only, so references turning on them stay undefined; (c) apply rule 3.4 to all. Recommend (a), with (b) where the record is silent.
- **R2. Unresolved starts** (`bi:837-0`, `bi:852-0`). "No history is manufactured", but the dose needs one. Recommend a flag with no single history: the utility is unsettled unless every history agrees, and the dose goes to rule 8's protocol (addendum point 5 names it open).
- **R3. The six Oregon years.** Under D-61 5.1, first fuel moves no bound, and a new-source permit is not-before evidence. Options: (a) not before the permit's issue year, permit-based convention, tested late end; (b) first fuel as a labelled convention; (c) unresolved. Recommend (a).
- **R4. Whole-row open below despite a dated later phase.** `bi:1123-0` (expansion 2014) and `bi:446-0` (a building opened 2011) carry `earliest: null` for the whole row. That cuts against "must not move documented later buildings or expansions into 2001". The same answer allows the whole row when capacity history is unknown. Recommend re-entry as a split where shares are on record, otherwise a label.
- **R5. The map after a factor or location change.** Rerun it and list every moved site, or hold unchanged-candidate sites fixed. Recommend rerun and list.
- **R6. The ceiling.** D-58 1.7 sets 50,000 per state, then the envelope. D-65 point 4 sets 100,000 per dependency component, then "conservative retention", which is written for questions, not places. Recommend 100,000, the envelope above it, and anything the envelope cannot settle listed as unsettled on timing.
- **R7. The later-start definition.** Size floor (none, or 20 MW); whether interval conventions and a split's rest count; stop at an evidence end or leave unshifted; whether ruling 4's cases are included. Recommend no floor, both count, stop and list, all four cases.
- **R8. Coordinates.** A one-time parcel-geometry query for the four parcels (centroid, labelled), or leave the points uncorrected and state the limitation. Recommend the query. The NSA row is verified, so leave its point and say so.
- **R9. Central Electric Cooperative on `bi:841-0`.** Record it as a listed candidate with no effect on any case, reopen the row, or do nothing. Recommend recording it.
- **R10. "Under both together"**: the screen crossed with the interval settings, or each passed separately. Recommend crossed.

**To check against D-66 section 4**, which I was not permitted to read: eight provisional rows whose year built is later than the permit-based year (`bi:1021-3`, `bi:1086-3`, `bi:1091-4`, `bi:1274-0`, `bi:1281-1`, `bi:964-0`, `bi:989-6`, `bi:978-0`) have intervals that reach down to the permit-based year. D-61 5.1 and addendum point 1 stop at the year built.

**Routine, mine to make:** names and labels; both thresholds; the offline geocoder; fingerprints; `power_simulation`'s JSON keys kept, with new keys added; an exclusion list in code citing D-95 for `bi:941-0`, so no record file is edited; the permit-error reach recomputed after the rebuild, with the frozen percentiles beside.

## 6. Build plan (tests first in each)

1. `corrections.py` (new). Tests: `location` validation and labels on invented inputs; one real-snapshot test that the adapter gives the same `Correction` objects as `load_frozen`.
2. `apply_verified.py`: `batch_c` read last, with the exclusions. Invented records test order, exclusion and D-48 evidence. **Real run: orchestrator.**
3. `build_inventory.py`: offline geocoder, `location`, dates and splits before anchoring, candidates and reopens after the utility block, relabel, interval columns. Invented frames test that empty corrections leave the frame identical, each kind, the relabel moving no load, and R2. **Real: the snapshot reproduction, then the corrected build.**
4. `timing.py` (new). Invented tests: monotonicity with no anchoring; the factor counterexample; corners against full enumeration; unresolved and provisional starts; the open-below-only list; the ceiling and envelope.
5. `dating_sensitivity.py`, `ten_year.py`: factor per case, old figure beside, interval sites out. Invented tests. **Real: the runs.**
6. `later_start.py` (new): section 3's tests. **Real: the run.**
7. `treatment_bounds.py`: reads `timing.py`; existing list names kept; existing tests pass. **Real: the run.**
8. `step_d_check.py` (new): section 4. **Real only.**

## 7. Risks, and the test that catches each

- **Withdrawn or reopened assignments absorbed from `batch_c`**, or `batch_c` overwritten by older files: the `batch_c` reconciliation test.
- **Map moves after a factor or location change:** the moved-site list, and section 4.
- **Nineteen "unique" sites becoming `verified_by_hand`** can change T4, which fails measured sites placed by the map alone. Test: T4's list differs only on named sites.
- **Relabels shrinking populations filtered on `first_generator_permit_plus_lag`.** These are `dating_sensitivity`, `ten_year`, `dating_report`, and `misdating.py`, which sits in `pipeline/analysis` and belongs to other agents. Test: every population difference equals a named site.
- **New Epoch coordinates fetched by the geocoder:** offline mode.
- **A provisional convention read as firm:** a test that a reference turning on one is undefined.
- **A utility over the ceiling read as keeping its place:** only the envelope settling it may say so.
- **Non-final candidate ids:** each must be a panel unit or be listed off-panel.
- **Screen verdicts moved by the factor recompute alone:** listed by name, old beside new.

## Addendum, 2026-11-18: Joe's rulings on the ten points, as applied in the build

His words are in the coordinator's message of 2026-11-18 and govern. What the code does with each:

- **R1.** Relabel only. The 115 year-built rows keep their years under `year_built_used_as_start_by_convention`, and their record review is recorded as unpursued (`corrections.relabel_year_built`). The 27 keep the provisional conventions and intervals of the corrections file in force, and a reference that turns on one is undefined (`timing.py`). `data/frozen/year_built_rows.csv` accounts for all 115: 27 carry two different years, 22 have one year (12 with a size, 10 without), and 66 have no size and two different years (76 rows have no size in all). None is described as verified.
- **R2.** A row with no convention is LOAD UNKNOWN (`load_unknown`): no single history, and no load in the frame. Its place, reference and eligibility come from the enumeration, with the factor recomputed in each history. `data/frozen/unknown_load_sites_and_affected_utilities.json` lists every utility it reaches, directly or through its state's factor. `treatment_bounds.py` never settles those utilities from the frame.
- **R3.** First generator fuel moves no bound. The five first-fuel rows (`bi:819-0`, `bi:820-0`, `bi:822-0`, `bi:823-0`, `bi:846-0`) have no permit issue year on file, so they are open below with the permit-based year as convention and tested late end. Their entries are proposed to the coordinator, who enters them. D-17's sixth DEQ-dated row is `bi:841-0`, whose record is a statement that the facility "was built in 2012". It is not first fuel and is left as it is.
- **R4.** No record on file establishes the dated phase's capacity for `bi:1123-0` or `bi:446-0`, so neither gets a split. Each whole-row early case becomes a labelled stress scenario (the date entry's `stress` field), reported and never admissible. The entries are proposed to the coordinator.
- **R5.** The map is rerun; candidate conflicts are preserved; every moved site is listed (`step_d_check.py`).
- **R6.** The ceiling is 100,000 configurations, counted across factor configurations and screen cases. Above it the envelope is used, and whatever it cannot settle is unsettled. That uncertainty is described by kind: assignment, timing, capacity, anchoring, comparison eligibility.
- **R7.** There is no size floor. A shift stops at sourced ends and is listed; known phases and provisional conventions do not move (`later_start.py`).
- **R8.** One logged request was made per recorded Bexar parcel id, five in all, with no retries (`pipeline/facilities/leads/step_d_coordinates_log_2026-11-18.csv`). The centroids are labelled coordinate conventions and the geometry is kept (`verified/step_d_locations.json`). Candidates are the union of those at the old and new points. FedEx and NSA are `location_unresolved`.
- **R9.** A note only.
- **R10.** The screen is crossed with every interval, capacity and assignment setting, one setting per site.

## Second addendum, 2026-11-18: three changes from the coordinator

- **R3, replacing the R3 bullet above.** The five Oregon first-fuel rows carry no bounding date evidence. With no permit issue year on file and first fuel bounding nothing (D-61 5.1; D-96 reading (1)), they are not intervals. `apply_verified.py` does not apply their first-fuel years from `batch_r3c_1.json` as start years (`corrections.FIRST_FUEL_NOT_A_START`); the rest of those records still applies. Each row carries its permit-based year under `first_generator_permit_plus_lag` and sits in the generic screen, the ten-year stress test and the later-start sensitivity. `inventory_report.json` names the five, each with the first-fuel year set aside and the permit-based year now carried. `timing.py --compare-oregon-open-below` writes a labelled comparison that decides nothing and is never read by `treatment_bounds.py`.
- **Stress scenarios.** A stress never sets a reference and is never admissible. A utility whose outcome under it is not accepted against its reference is `unresolved_by_stress`, with the reason "unresolved: which building the row carries is not settled (D-96)". It does not keep its place and is listed in `step_d_unresolved_by_a_stress_scenario`, apart from the admissible-history failures and the open-below-only list.
- **The joint check by host (rule 6.4).** It now reads `design.build_with_rules` under the headline rules (`joint_check.headline_design`). The by-state part is unchanged.
