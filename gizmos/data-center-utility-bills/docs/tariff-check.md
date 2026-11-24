# Tariff check for electricity: proposal

**Status: proposal for Joe (D-26, job D). Nothing has been collected.** A tariff is a price. Collecting a host utility's tariff unblinds it, so no tariff is collected until the sampling rule and the usage level below are confirmed and `PREANALYSIS.md` is committed. The sample in `data/frozen/tariff_check_sample.csv` was drawn from load, sales and customer counts only (`pipeline/tariffs/sample.py`).

## Why

The study's outcome is revenue per kWh from EIA-861. That is not a tariff: it moves when usage per customer moves against a fixed charge, when customers switch between default service and a competitive supplier, and when we fill in a supply price for delivery-only customers (the outside review's point 4). The tariff check rebuilds what a household at a fixed usage was actually charged, from the utilities' own rate schedules, for a set of hosts and comparison utilities chosen in advance. It answers one question: does the EIA measure move the way published rates moved?

## Who is in it (the sampling rule)

- **Hosts: every cohort utility at the 2% threshold,** 42 as of 2026-11-14 (11 in the headline set; the rest set aside under D-20, D-28 or D-46, or unsettled on assignment, D-50). All of them, so no host is picked by notoriety and the check covers both the main estimate and the every-cohort-utility run.
- **One comparison utility for each host,** chosen without any price:
  - never a host (load under 0.5% throughout, no crypto load of 2% or more), not set aside, and reporting residential sales in every year of the host's ten-year window;
  - same state and same ownership group; if none, same state; if none, same market region and ownership group; if none, same market region. Same state comes first because rates are set, and riders approved, state by state;
  - among those, the closest in residential customers three years before the host's first crossing;
  - used once.
- **Order.** Hosts are taken in a fixed random order (seed 20261112). That is the order of collection, so a collection that stops part-way is a random sample of the hosts and not the easy ones.

What the rule gives today, after the load histories of D-34 to D-36: all 46 hosts get a comparison utility, 43 in the same state and ownership group and 3 in the same state. (Bonneville Power Administration, which had none, is no longer a host: the Apple site the territory map had put on it is PacifiCorp's.) The median gap in size is 0.33 log points (about a third). It is large where a state has one dominant utility: Pacific Gas and Electric against Liberty Utilities, PacifiCorp in Utah against the City of Bountiful. The pairs are in 24 states; 17 hosts are public, 15 cooperatives, 14 investor-owned.

Not proposed: a smaller sample of the largest or best-known hosts (it would validate the measure where it matters least for the estimate, which is mostly small public and cooperative systems); two comparison utilities per host (double the collection for a check, not an estimate).

## The bill that is rebuilt

- **Customer.** A year-round residential customer on the utility's standard schedule: not time-of-use, not electric-heat or all-electric, single phase, no net metering, no low-income discount. Where a utility has summer and winter rates, both are collected.
- **Usage level, proposed: two levels, fixed per pair before collection.**
  - *The pair's own typical usage:* the host's average monthly residential use in its reference year (three years before first crossing), rounded to the nearest 50 kWh, applied to the host and its comparison utility alike. It ranges from 500 to 1,500 kWh across the 46 hosts, median 900. This is the level that should track revenue per kWh, because it is the usage the EIA figure was earned on.
  - *1,000 kWh a month for everyone,* the level many utilities and state commissions use for "typical bill" comparisons (common practice; no single source). This is the one a reader can compare across utilities.
  - The first is the check's primary level. The second is reported next to it.
- **What is in the bill.** The customer charge, every energy block, and every rider, adjustment clause and surcharge that applies to all residential customers on the schedule (fuel and purchased power, transmission, storm, environmental, energy efficiency). For a retail-choice utility, delivery charges plus the utility's default-service supply price. Not in: taxes and franchise fees, one-time credits and refunds unless they run twelve months or more (each recorded, with the reason).
- **When.** The bill is computed for the rates in force on 1 January and 1 July of each year in the host's window (six years before first crossing to three after), so twenty dated bills per utility. Base rates are recorded once per change. Riders that move monthly or quarterly are recorded at the value in force on those two dates. The year's bill is the mean of the two.

## Collection sheet

`pipeline/tariffs/collection_sheet_template.csv`. One row per charge component per change. Columns: pair id; utility id, state and name; rate schedule; component (customer charge, energy block, named rider); charge type (base or rider); season; block from and to (kWh); value and unit (dollars a month, cents per kWh, percent); effective date and the date it was superseded; source URL; archived copy URL; document title; document date; docket or order number; date collected; collector; second keyer; confidence; note.

Rules for collectors, carried over from the water plan and the facility work:

- Every value has a source URL, a document date and a confidence. A value without them is not used.
- The collector is given a list of utilities, not told which of a pair is the host. One utility in five is keyed a second time by someone else and the two are compared.
- Sources are the utility's own tariff book, the state commission's tariff or docket system, and the board minutes or ordinances of public systems and cooperatives. No working around access controls. A year that cannot be found is recorded as not obtained with the pages tried, never filled in.
- Bills are computed by code from the sheet, never typed in.

## What is reported, and what will be said

Written before any tariff is collected.

1. **Coverage:** how many utility-years were obtained, by ownership group. Public systems and cooperatives rarely post old rate schedules (expectation from the water scoping, not measured), so coverage will be uneven and the write-up says for whom the check exists.
2. **Does the EIA price track the tariff?** For every utility with both, the change in the tariff bill per kWh at the pair's own usage against the change in EIA revenue per kWh, over the same years. Reported as the share of utility-windows where the two changes are within two percentage points of each other, and the correlation.
   - If at least three quarters are within two points: "The EIA price measure moved with published rates."
   - If fewer: "The EIA price measure and published rates diverge for N of M utilities," with the components that explain it (usage per customer, the fixed charge, the filled-in supply price), and the tariff-based comparison below is given equal billing with the main estimate.
3. **The same comparison on tariffs:** host minus comparison utility, change in the bill from the reference year to the mean of years two and three after first crossing, averaged over pairs, with its range from a bootstrap over pairs. It is a check on sign and rough size, on fewer utilities and with one comparison each. It is not a second headline.
   - If it has the main estimate's sign and is at least half its size, or both ranges include zero: "Rebuilt bills agree with the main estimate."
   - Otherwise: "Rebuilt bills do not agree with the main estimate," both are shown, and the headline wording steps down from "raised" to "was associated with" (the rule in `PREANALYSIS.md`).
4. **The three pieces of the EIA price, separately,** for every utility in the panel and not only this sample: bundled price, delivery-only price, and the filled-in supply price.

## Size of the job

95 utilities, about twenty dated bills each. Investor-owned utilities' tariffs are in state commission systems and most can be collected; the 33 public and cooperative hosts and their comparison utilities are where years will be missing. Joe has said time is not the constraint (D-26). The first twelve pairs in collection order are a reasonable pilot: they show the coverage rate before the rest is committed to.

## For Joe to confirm

1. The sampling rule: every cohort utility at 2%, one comparison utility each by the rule above, fixed random order.
2. The usage level: the pair's own typical usage as the primary level, 1,000 kWh a month alongside.
