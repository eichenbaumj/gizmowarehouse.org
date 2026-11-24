This is the long version: the design, the sets, the inference, every listed run with its label, the comparison with earlier papers, the limits, and what was not built or not obtained. The short version for a general reader is [the main page](/gizmo/data-center-utility-bills). Section 14 says where the code, the plan and the run records live.

Every number in this document is copied from a saved result record or a frozen design file, or is a unit conversion of one. Log points are converted to percent by 100 × (exp(x) − 1). Nothing was re-estimated to write it.

## 0. The plan, the blinding and the headline

**The plan.** The analysis plan is frozen in the project's repository (freeze commit ea426c4, approved specification ed3a2ff). It was frozen inside the project and was not registered with any outside registry.

**The blinding statement.** No host utility's price in the outcome data was read before 2026-11-21T00:41:06+00:00, with one lapse in source access disclosed in the plan. At that time the whole outcome file was loaded once through the guarded coordinator, and rows U and C were computed. At 2026-11-21T04:12:18+00:00 the same fingerprinted file was loaded a second time, whole, through the same coordinator, and the remaining implemented entries of the registry were run, from `inventory_against_sales` through `influence_five_highest_load_utilities_dropped`; the three entries with no code (`tariff_check`, `regional_layer`, `exploratory_work`) wrote their not-built records. The outcome file has been read twice.

**The lead was chosen after results.** The plan put the comparison with earlier papers first and allowed me to revisit the lead once results were in, on the condition that the write-up says so. I did, so I am saying it here. The lead of this piece, the finding read against 5% and 10%, was chosen after the results were seen. The two sizes themselves were not. I named 5% and 10% as the sizes that matter before any outcome was read.

**What validation covers.** The method that produces the range and the early-years test was selected and validated on made-up prices before the freeze, on the headline design alone. Headline validation covers only the selected procedure on the validated headline design: the 90% range and the early-years test of the headline set at 2%, on residential price. Every other range in this document is on a design, an outcome or a procedure for which no validation was made, and says so.

**The headline,** as the main page puts it:

> From what I checked, data centers probably do not raise household electricity prices by more than 5%, and very unlikely by more than 10%.

At the seven utilities I could verify best, a 5% rise falls just outside the range and a 10% rise far outside it. Across all 36 utilities I could analyze, a 5% rise is inside the range and a 10% rise is not.

"Rise" means a rise relative to similar utilities in the same market region over the same years, at utilities where data centers first reached 2% of sales in 2011 to 2022, two to three years after that point. "Probably" is a judgment from the range and the limits in sections 6 and 12. It is not a probability this study calculated.

**The headline sentence the plan fixed in advance,** quoted as the plan file keeps it:

> "At the 7 utilities in our set that became data center hosts between 2011 and 2022, residential prices two to three years later differed from those at the similar utilities we compared them with by about -1.6% (90% range -7.1% to 4.2%). That range includes zero."
>
> "This is a difference between hosts and comparison utilities. It covers 7 utilities in 7 states that first reached 2% data center load in 2011 to 2022, looks three years out, and leaves out costs that fall on a whole region."
>
> "Some utilities may host data centers missing from our inventory, including utilities used for comparison. Our findings are conditional on those omissions not materially changing treatment timing or comparison-group exposure; state totals cannot establish that condition. A small estimated difference would therefore not, by itself, show that data centers do not raise residential bills."

## 1. The question and what it covers

Does a utility that takes on material data center load charge its residential customers more afterward than it otherwise would have?

**The estimand.** The additional change in residential price at utilities that became data center hosts in 2011 to 2022, relative to low-load utilities in the same market region, through three years.

It is not the total effect of data centers on bills. Region-wide wholesale and capacity costs fall on hosts and comparison utilities alike and are differenced out. It is not a pure local-grid-cost effect either, because procurement and pass-through differ between utilities in one region. It also leaves out two groups of hosts. The 32 long-time hosts were already above the load threshold before 2011, the utilities of northern Virginia among them, and 21 utilities first cross in 2023 or later.

Of the inventory's 2025 data center load, the long-time hosts carry 49.5%, the 41 cohort utilities 36.3% (of which the headline set carries 9.8 points), the late hosts 10.8%, and utilities that never reach the threshold 3.4%. So the headline set speaks for about a tenth of the load in the inventory.

An average over these hosts cannot by itself show that most of them saw little or no effect. A small average does not show that most utilities have small effects.

The planned water analysis could not be completed because adequate historical rate coverage was not obtained.

## 2. Data

**Unit.** Distribution utility by state by year, from the Energy Information Administration's Form EIA-861, 2001 to 2025, for utilities with at least 2,000 residential customers. A utility that absorbed another is one unit for every year, with the predecessor's sales and revenue added in.

**Outcome.** The natural log of residential price, where price is residential revenue per kWh, with competitive supply added for delivery-only customers at the state's observed supplier average. It is not a tariff. It moves when usage per customer moves against a fixed charge, when customers switch supplier, and when a supply price is filled in. It is reported next to kWh per customer and the bill per customer for that reason. The plan also promised the three pieces of that price reported separately, and that was not built (section 11).

**Treatment.** Data center load on a utility as a share of its 2009 to 2011 retail sales. The inventory has 2,244 site rows. A site's load follows the operator's own reported electricity where the operator publishes it by site and year, an outside dated timeline (Epoch's), a hand-verified phased history, or a three-year ramp from its start year. Cryptocurrency mines are not counted. A utility becomes a host in the first year that share reaches 2%, which I call its first crossing. Start years are uncertain by a year or two, and a large part of the design work went into testing how far each utility's place depends on what the inventory does not know.

**Cohorts.** 41 utilities first reach 2% in 2011 through 2022. These are the cohort utilities.

## 3. The design

**Matching.** Each host is matched to the ten comparison utilities in its wholesale market region that are closest to it in residential customers in the reference year. A comparison utility must be under 0.5% data center load in every year in every admissible history of the inventory, must share no ultimate parent with the host in any year of the host's window, and must have a usable price in all ten years of the window. Eligibility does not show that a comparison utility has no data center load.

**Why the same region.** Market region is the wholesale market a utility buys in: PJM, MISO, SPP, ERCOT, NYISO, ISO-NE, California, Southeast, West. Fuel costs and market design move prices by region. Year effects are by region within each matched set, so a regional swing hits a host and its matches alike and drops out.

**The window.** Six years before first crossing to three after. The reference year is three years before. The headline is the mean of event years 2 and 3. Years 0 and 1 are left out of the headline because start years are uncertain by a year or two and rate cases lag. Years −2 and −1 are the anticipation window: the design assumes effects do not begin earlier than two years before first crossing, and if construction or rate preparation began earlier the reference year is contaminated and the estimate is too small.

**Stacking.** One sub-experiment per host, each with its own ten matches and its own ten calendar years. The sub-experiments are stacked and fitted together by ordinary least squares, with utility effects, market-region-by-year effects within each matched set, the state's 2008 to 2010 natural gas share of generation times calendar-year indicators, and heating and cooling degree days.

**The fuel-mix control's assumption.** After the other controls, differences in outcomes are modeled as linear in the state's 2008 to 2010 gas share, with a slope free to differ by calendar year. A state's generation mix is a proxy for what a utility is exposed to; the adjustment does not establish that it measures any utility's own power supply. Two of the seven hosts lie outside the range of their matches' gas shares, which is extrapolation: Omaha Public Power District (Nebraska, 1.4%, against 4.9% to 49.1% among its matches' states) and Sierra Pacific (Nevada, 68.1%, against 10.1% to 46.9%).

**Weights.** Each host utility counts once; the estimate is an average over host utilities, not over their customers. The seven hosts' weights in the headline run from 0.121 to 0.154. No host's rows are fully absorbed and none has zero weight, on the headline design or on any other stacked design in the saved records.

The figures that explain the design for a general reader are on [the main page](/gizmo/data-center-utility-bills#how-i-tested-it), and are schematic where they say so.

**The seven and their matches.**

| host utility | state | ownership | market region | first crossing of 2% | eligible comparison utilities in its region, reference year | its ten matches |
|---|---|---|---|---|---|---|
| PacifiCorp | UT | investor_owned | West | 2015 | 193 | Idaho Power Co (ID); City of Seattle (WA); PUD No 1 of Snohomish County (WA); El Paso Electric Co (TX); PUD No 1 of Clark County (WA); City of Tacoma (WA); Black Hills Colorado Electric, LLC (CO); El Paso Electric Co (NM); City of Eugene (OR); City of Fort Collins (CO) |
| City of Garland (TX) | TX | public | ERCOT | 2017 | 37 | City of Bryan (TX); Magic Valley Electric Coop Inc (TX); Brownsville Public Utilities Board (TX); South Plains Electric Coop Inc (TX); City of College Station (TX); Central Texas Elec Coop, Inc (TX); Nueces Electric Cooperative (TX); City of New Braunfels (TX); Medina Electric Coop, Inc (TX); Mid-South Electric Coop Assn (TX) |
| Sierra Pacific Power Co | NV | investor_owned | West | 2017 | 127 | El Paso Electric Co (TX); PUD No 1 of Snohomish County (WA); City of Seattle (WA); Idaho Power Co (ID); PUD No 1 of Clark County (WA); City of Tacoma (WA); El Paso Electric Co (NM); Black Hills Colorado Electric, LLC (CO); City of Eugene (OR); City of Fort Collins (CO) |
| Omaha Public Power District | NE | public | SPP | 2019 | 107 | Evergy Kansas Central, Inc (KS); Evergy Kansas South, Inc (KS); Evergy Metro (MO); Southwestern Public Service Co (TX); Southwestern Electric Power Co (LA); Southwestern Electric Power Co (TX); Empire District Electric Co (MO); City Utilities of Springfield (MO); Southwestern Public Service Co (NM); City of Lubbock (TX) |
| Public Service Co of NM | NM | investor_owned | West | 2019 | 133 | Idaho Power Co (ID); City of Seattle (WA); PUD No 1 of Snohomish County (WA); El Paso Electric Co (TX); PUD No 1 of Clark County (WA); City of Tacoma (WA); PacifiCorp (WY); PacifiCorp (WA); El Paso Electric Co (NM); Black Hills Colorado Electric, LLC (CO) |
| Arizona Public Service Co | AZ | investor_owned | West | 2020 | 133 | Idaho Power Co (ID); City of Seattle (WA); PUD No 1 of Snohomish County (WA); El Paso Electric Co (TX); PUD No 1 of Clark County (WA); City of Tacoma (WA); PacifiCorp (WY); PacifiCorp (WA); El Paso Electric Co (NM); Black Hills Colorado Electric, LLC (CO) |
| Walton Electric Member Corp | GA | cooperative | Southeast | 2021 | 342 | EnergyUnited Elec Member Corp (NC); City of Lakeland (FL); Duke Energy Progress (NC) (SC); City of Tallahassee (FL); Volunteer Electric Coop (TN); Snapping Shoals El Member Corp (GA); City of Chattanooga (TN); South Carolina Public Service Authority (SC); Clay Electric Cooperative, Inc (FL); Gainesville Regional Utilities (FL) |

The seven hosts have 70 host-and-match pairs and 42 distinct comparison utilities. The four West hosts share nearly one set of ten: eight comparison utilities are matched to all four. A host's ten matches are not ten strong or independent comparisons.

**Inference.** Standard errors are clustered by state (19 state clusters on the headline design, 770 stacked rows). The range is a 90% CR2 t range with Satterthwaite degrees of freedom. The early-years test is an approximate Hotelling test on event years −6, −5 and −4, failing at p below 0.10.

## 4. Which utilities are in each set

**The headline set** is seven hosts in seven states: Arizona Public Service (first crossing 2020), Garland in Texas (2017), Omaha Public Power District (2019), PacifiCorp in Utah (2015), Public Service of New Mexico (2019), Sierra Pacific in Nevada (2017) and Walton EMC in Georgia (2021). Four investor-owned, two public, one cooperative. Their regions are the West (four), ERCOT, SPP and the Southeast. None buys in PJM.

A cohort utility is in the headline set only if its place in the design holds up under every admissible history of the inventory: its large permit-dated sites started three and five years earlier, its unresolved sites moved on and off it, state totals anchored and not anchored. The rules were fixed before any outcome was read, and I did not aim for any particular number of utilities.

**What the headline set represents.** It is the 7 of the 41 cohort utilities at 2% that remain after rules that turn on what could be verified and enumerated. A utility over the enumeration ceiling is out because the check could not be completed, not because it was found to be wrongly placed. The rules read the inventory through 2025, so membership depends in part on what was built and documented after a utility's event year, and the hosts left out include those with the most sites and the widest date intervals. So I do not describe the headline estimate as unbiased for the 41 or as free of selection. I do not know whether the seven differ from the rest in ways related to price. Which cohort utilities are in the headline set, and the rule each of the other 34 failed, are in [`data/frozen/headline_set.csv`](https://github.com/eichenbaumj/gizmowarehouse.org/blob/main/gizmos/data-center-utility-bills/data/frozen/headline_set.csv).

**The other sets.** Four more sets are reported next to the headline, each labelled for what it rests on.

- *With the ten-year case: 6.* The seven less Arizona Public Service, which leaves only when the screen also starts large permit-dated sites ten years earlier. It is a stress case.
- *With the hosts unsettled on assignment put back: 17.* The seven plus ten hosts whose serving utility could not be settled.
- *Every cohort utility as built: 36 in the estimate.* All 41, less five that are out of its reference design: Grand River Dam Authority (no usable outcome in every year of its window), the City of Hamilton in Ohio and Orange and Rockland Utilities (too few matches in region under the support rule), and Portland General Electric and Umatilla Electric (load unknown).
- *The timing run: 9.* The seven plus Public Service of Colorado and Ohio Power at their no-anchoring years.

The sets are nested. The seven are inside the 17 and inside the 36.

**Why the seven carry the headline.** There are three reasons. The rules that select them were fixed before any outcome was read. The inference procedure was validated on that design and on no other. And they are better dated, which I can say only because of the date stress test. In that test the recorded first crossing matched in 95.5% of redraws for this set, against 53.8% for every cohort utility (over the 36 hosts of its reference design; 55.8% over its roster of 41). With start years redrawn in the mirror direction, which rests on an assumption, the figures are 99.4% against 56.4% (59.4%).

## 5. How the range was built and tested

Three candidate procedures were compared on made-up prices built on the headline design, with no real price used. Thirteen price processes were tried, among them unequal variances, persistent shocks, rate-case steps, shocks common across states, company and supplier shocks, own trends and fuel shocks. One procedure was selected, then validated on fresh made-up data: 20,000 datasets for each process.

**The validation rates.** In checks on made-up prices built on this design, a range built this way missed the true value in at most 9.9% of 20,000 datasets under any process (95% upper bound 10.3%), within the 11% tolerance set in advance; the test of the early years wrongly failed a flat history in at most 5.9% (upper bound 6.2%). The lowest rates were 6.9% and 2.8%. All thirteen are in [`data/frozen/inference_validation_stage2.json`](https://github.com/eichenbaumj/gizmowarehouse.org/blob/main/gizmos/data-center-utility-bills/data/frozen/inference_validation_stage2.json). Meeting the tolerance says nothing about price processes outside the grid.

**Where the validation does not transfer.** It was made on the headline set at 2%, for the main specification. It is not a validation of the procedure on any other design: the other sets, any set at 5% or 1%, E1 to E7, the later-start re-estimates, the deletion runs, the longer horizon, the own-state side run or the subgroup contrasts. A range on any of these carries the words "under the procedure validated on the headline set; no validation was made on this design".

**What the sets could detect.** From the simulation on stand-in prices drawn from never-host utilities, run before the freeze: the smallest increase detected in the correct direction four times in five was 9.95% for the headline set (10.09% with permit-dated start years redrawn from measured permit errors), and 4.83% (6.30%) for every cohort utility as built. "Detected" means the 90% interval lay entirely above zero under a planted positive effect; it is not a one-sided 10% test. No simulation run failed numerically. A set of seven would often fail to tell a true 5% increase from zero.

## 6. Results

### 6.1 The headline

For the seven hosts, the change in residential price from three years before first crossing to two to three years after was 1.60% below the change at their matched comparison utilities over the same years. The 90% range runs from −7.12% to +4.25%. The range includes zero. This is record 6, the one range on the validated design.

This is a relative change in price. It is not a statement that hosts' prices are lower, or higher, than comparison utilities' prices in level. A negative figure means the hosts' prices rose less, or fell more, than their matches' did.

**Read against 5% and 10%.** The upper end, +4.25%, is 0.75 points under 5% and 5.75 points under 10%. Both sizes lie outside the range. That supports saying a relative rise of more than 10% is very unlikely at these seven, and a rise of more than 5% probably did not happen. Both are judgments, and three cautions go with them. A 90% range is expected to miss the true value about one time in ten, so a value outside it is not impossible. The margin to 5% is small against what changing one specification choice does (section 9). And the statement is about seven utilities chosen by what could be verified.

**The early-years test** did not detect a difference in the years before (p 0.621). On a set this small it would miss a large one.

**Year by year.** The record holds one coefficient for each event year and no range for a single year.

| event year | saved coefficient (log points) | the same in percent | what the plan calls these years |
|---|---|---|---|
| -6 | +0.01501 | +1.51% | early years (the early-years test) |
| -5 | +0.01527 | +1.54% | early years (the early-years test) |
| -4 | +0.02228 | +2.25% | early years (the early-years test) |
| -3 | +0.00000 | +0.00% | the reference year, zero by construction |
| -2 | +0.01225 | +1.23% | the anticipation window |
| -1 | -0.01000 | -1.00% | the anticipation window |
| +0 | -0.00091 | -0.09% | left out of the headline (start years uncertain, rate cases lag) |
| +1 | -0.00042 | -0.04% | left out of the headline (start years uncertain, rate cases lag) |
| +2 | -0.01180 | -1.17% | the headline is the mean of these two |
| +3 | -0.02044 | -2.02% | the headline is the mean of these two |

![The seven hosts, year by year](/assets/data-center-utility-bills/fig7_year_by_year.png)

The coefficients for the three early years, +1.5% to +2.3%, are as large in size as the two that make the headline. That is the scale of the year-to-year movement between seven hosts and their matches when no data center load has arrived.

**The trend illustrations,** fixed by the plan. Each is an assumed continuation of pre-existing drift, not an estimated bias, a bound or a correction. If hosts had been drifting away from the comparison utilities by 0.5% a year, the estimate would move by 2.75 points; by 1% a year, 5.5 points, in either direction. If half of the largest early year-to-year change continued, the estimate would move by 6.13 points, and if all of it continued, by 12.25.

### 6.2 The other sets of hosts

| record | set | hosts | relative change in residential price | 90% range | upper end's gap to 5% (points) | upper end's gap to 10% (points) | early-years test p | the range's standing |
|---|---|---|---|---|---|---|---|---|
| 6 | Headline set (the seven) | 7 | -1.60% | -7.12% to +4.25% | +0.75 | +5.75 | 0.621 | the validated design |
| 7 | With the ten-year case | 6 | -1.94% | -7.78% to +4.26% | +0.74 | +5.74 | 0.653 | no validation was made on this design |
| 8 | Plus hosts unsettled on assignment | 17 | +0.22% | -3.62% to +4.21% | +0.79 | +5.79 | 0.718 | no validation was made on this design |
| 9 | Every cohort utility as built | 36 | +3.08% | -0.72% to +7.02% | -2.02 | +2.98 | 0.261 | no validation was made on this design |
| 10 | Timing run | 9 | -3.82% | -8.92% to +1.56% | +3.44 | +8.44 | 0.704 | no validation was made on this design |
| 11 | Customer-weighted (descriptive) | 7 | -0.71% | no range, by design | n/a | n/a | n/a | a point estimate with no range |

![The headline and every other set](/assets/data-center-utility-bills/fig5b_result_all_sets.png)

I read each set on its own. The six: −1.94% (−7.78% to +4.26%). The 17: +0.22% (−3.62% to +4.21%). The timing run: −3.82% (−8.92% to +1.56%). Each of those ranges has an upper end under 5%. The 36: +3.08% (−0.72% to +7.02%), a range that includes zero and 5% and whose upper end is 2.98 points under 10%. By the saved comparison of the stacked sets (record 31), the range for the 36 lies above the point estimates for the seven and for the six, and no other stacked range excludes another set's estimate. The plan says of these sets: "They estimate somewhat different averages and need not agree."

Because the sets share hosts, their agreement on 10% does not count as several independent findings. They are one body of data, cut several ways.

**I do not know why the 36 and the seven differ.** It could be that the other hosts saw larger relative changes in price; that their start years or serving utilities are wrong in ways that move the estimate; that the unvalidated procedure behaves differently with 36 hosts; or chance. The saved records hold each host's weight and no estimate host by host, and I did not break the difference down.

**The customer-weighted estimate** on the seven is −0.71%, a descriptive point estimate with no range by design.

### 6.3 Usage, bills and customer counts

| record | outcome (natural log of the level) | hosts | relative change | 90% range | early-years test p | the range's standing |
|---|---|---|---|---|---|---|
| 12 | kWh per residential customer | 7 | -1.91% | -3.87% to +0.09% | 0.454 | no validation was made for this outcome |
| 13 | Bill per residential customer | 7 | -3.47% | -8.75% to +2.11% | 0.993 | no validation was made for this outcome |
| 14 | Residential customers | 7 | -0.21% | -3.89% to +3.61% | 0.518 | no validation was made for this outcome |

The relative change in use per customer is −1.91%, with a range that just includes zero. The relative change in the bill per customer, which combines price and use, is −3.47% (−8.75% to +2.11%); its upper end is 2.89 points under 5%. Residential customer counts show a relative change near zero. These are reported next to price and not as placebos, since a data center can plausibly move them. No validation was made for these outcomes. I report the pattern without an explanation for it.

Price, the bill and the load-share threshold are three different things. The 5% and 10% of the headline are sizes of a relative change in price. The bill has its own range, above. The 2% and 5% thresholds decide which utilities count as hosts and are not effect sizes.

## 7. Three assumptions I cannot verify

"Reading that difference as the effect of data centers takes three things we cannot verify: that hosts' prices would otherwise have moved as the comparison utilities' did, that the comparison utilities had no data center load we missed, and that our start years are right to within a year or two." None of the checks below can veto the headline, and none shows its assumption to hold.

**1. Hosts' prices would otherwise have moved as the comparison utilities' did.**

- *The early-years test* (record 6): no difference detected in event years −6 to −4, p 0.621. It can show that no large, clear divergence was found. It cannot show that hosts and matches were on the same path; on seven hosts it would miss a large drift.
- *The trend illustrations* (section 6.1) show how much an assumed drift would move the estimate. They say nothing about whether a drift existed.
- *Fake events* (E1, E2). With events placed six years early, the seven give +1.42% (−4.95% to +8.20%). With fake events for six future hosts, +6.71% (−2.03% to +16.23%). Both ranges include zero. They show the design does not find a clear difference where none should be. They also show that a point estimate of several percent can arise on a handful of hosts with no event behind it.
- *Each market region left out* (record 53): estimates from −2.08% to +1.42%; leaving out SPP moves it most; each range includes zero. Leaving out the West removes four of the seven.
- *Each state left out* (record 54): nineteen deletions, from −3.98% (New Mexico out) to +1.42% (Nebraska out). Leaving out Virginia changes nothing, since no host or match is there, so it is not a check that passed.
- *One comparison utility or one parent company left out* (records 24, 25): estimates from −2.81% to −0.69%, and from −3.87% to −0.69%.
- *The fuel-mix control* (records 37, 38): with the categorical specification, +0.09% (−5.41% to +5.91%); with no fuel-mix control, −3.07% (−10.31% to +4.76%).
- *The second estimator.* The plan specified Callaway and Sant'Anna's estimator as a cross-check. It was not obtained as specified: the package did not use every covariate in every cell. Its record labels the number it returned (−3.53%) "not the specified estimator" and gives it no range, and no other specification was substituted. So the study has no second estimator to check the first against, and that gap is unresolved. Section 11 says what the plan allows.

**2. The comparison utilities had no data center load I missed.**

- *Rows with no size.* 1,105 of the inventory's 2,244 rows have no size and so carry no load. Of the 42 comparison utilities in the headline design, 15 are the assigned or a candidate utility of at least one such row, and they hold 40.0% of the comparison side's net weight. Both El Paso Electric units are among them, with 14.5% together. No result of the influence runs shows that the missing load is harmless.
- *The joint check* ([`data/frozen/joint_check_by_host.csv`](https://github.com/eichenbaumj/gizmowarehouse.org/blob/main/gizmos/data-center-utility-bills/data/frozen/joint_check_by_host.csv)): for each host, how many of its ten matches could fail the 0.5% rule if each state's unassigned remainder of data center load sat on them. For Garland, all ten could. It is a worst case for each host on its own, and the largest number is not the expected number.
- *The inventory against sales* (record 5): the slope of the hosts' own excess non-residential sales growth on the inventory's added load is 0.602, inside the band of 0.5 to 1.5 the plan set. "The inventory's load shows up in the utilities' own sales." It cannot show that the inventory is complete.
- *Shared suppliers removed* (record 23): −1.23% (−6.85% to +4.74%) with two pairs removed. Only 18 of 70 host-and-match pairs could be tested at all.
- *Affiliates readmitted* (record 22): −1.90% (−5.91% to +2.28%).

**3. My start years are right to within a year or two.**

- *The date stress test* (E7) on the quantity side is reported in section 4.
- *The date stress test, price side.* Permit-dated start years were redrawn 200 times from measured permit errors, and the point estimate recomputed, with no range for a draw. For the seven, redrawn earlier, the 5th to 95th percentiles are −2.08% to −0.44% and the saved draws run from −2.64% to +0.55%; redrawn later, the saved draws run from −1.60% to −0.07%. For the 36, redrawn earlier, the percentiles are +0.93% to +4.34% and the saved draws run from −0.50% to +5.70%; later, +1.16% to +3.98%, with draws from −0.23% to +4.72%. The lists for the two sets are separate. No draw-by-draw difference between the sets was saved or computed, so these summaries do not show whether the gap between the sets closes. They are not confidence intervals.
- *Later starts* (records 27 to 29): with every permit-dated phase one year later the headline is unchanged; three or five years later, −1.21% (−6.54% to +4.43%).
- *The two alternative inventories* (E4a, the slow path; E4b, anchoring off): −1.42% (−7.47% to +5.03%) and −0.07% (−5.49% to +5.67%) on the seven.

## 8. A second test across 1,182 utilities

The plan's second number asks a different question of a different sample. Across 1,182 utilities, long-time hosts included, how does the change in residential price from 2008 to 2010 to 2023 to 2025 go with the change in data center load share over the same span?

The unit is percent of residential price per one point of data center load share, a point being data center load equal to one percent of the utility's 2009 to 2011 retail sales. In the primary run, with each year's load share counted at no more than 25 points: −0.023% of price per point (90% range −0.387% to +0.353%). As an illustration over ten points of load share: −0.23% (−3.81% to +3.59%).

The plan also promised this number translated at the median host's load share. I did not make that translation, because the plan defines no median and the second number's sample and endpoint changes differ from the headline design. I did not invent a definition.

Its ranges come from a wild cluster bootstrap that the inference comparison did not calibrate. In the stored simulation on stand-in prices its range covered zero with nothing planted in 96.6% of draws at the 25-point cap, 94.9% at the 50-point cap and 84.9% uncapped. Capping changes the regressor, so the three forms are not three estimates on one scale. The cap gives up any reading of whether price keeps moving above 25 points. One result has a range that excludes zero and is named as its own: the uncapped form with the ten highest-leverage unsettled utilities left out, +0.150% per point (+0.057% to +0.236%). It is not a calibrated finding, and its narrower range is no reason to rank the second number above the headline. All seven runs at all three forms are in appendix B, and the class counts and leverage shares are in [`data/frozen/second_number_design.json`](https://github.com/eichenbaumj/gizmowarehouse.org/blob/main/gizmos/data-center-utility-bills/data/frozen/second_number_design.json) and [`second_number_leverage.csv`](https://github.com/eichenbaumj/gizmowarehouse.org/blob/main/gizmos/data-center-utility-bills/data/frozen/second_number_leverage.csv).

## 9. The other planned runs

Every run the plan listed in advance was run, and each is in appendix A with its own range, or in appendix C with the reason it has none. Each is one result on an unvalidated design. They share hosts and data with the headline and with each other, so they are not counted as confirmations of anything. They show how far the estimate and its upper end move when one choice is changed.

**On the seven, the upper end moves across 5% under several single changes.** The categorical fuel-mix specification (+5.91%), anchoring off (+5.67%), the slow path (+5.03%), comparison utilities from the host's own state on five hosts (+5.81%). Under others it moves down: affiliates readmitted (+2.28%), the size-band form of the size adjustment (+2.04%), hosts with unresolved ownership excluded, which leaves five (+1.01%). The margin of 0.75 points between the headline's upper end and 5% is smaller than this movement.

**The runs whose range includes 10%.** E5, which drops states where the inventory was scaled up most, leaves four of the seven (+0.50%; −21.55% to +28.75%) and 22 of the broad set (+3.59%; −2.82% to +10.43%). E2, the fake events for future hosts, is not a real-event estimate.

**On the broad as-built sets, three runs have a range that excludes zero.** Comparison utilities from the host's own state (+4.83%; +0.90% to +8.91%; 30 hosts), the slow path (+3.65%; +0.22% to +7.19%; 35 hosts), and the exploratory 1% threshold (+2.65%; +0.19% to +5.19%; 41 hosts). At the 5% threshold the estimate for every cohort utility as built is −1.18% (−4.17% to +1.90%; 28 hosts), and for the headline rules −0.98% (−6.22% to +4.55%; five hosts).

**The longer horizon.** For the five of the seven with six years of data: −3.79% at six years (−14.69% to +8.50%), against −2.11% at three years on the same five (−8.67% to +4.92%). For 28 of the broad set: +4.02% at six years (−1.35% to +9.68%), against +2.74% at three (−1.38% to +7.02%). The six-year ranges are wide.

**The four conditions.** These are descriptive contrasts between two groups of hosts, with no range and no test. Two groups' estimates side by side are not evidence that the two differ. In log points times 100: hosts at 10% load share or more in event year 3 minus those under, +5.00 on the seven and −2.55 on the 36; investor-owned minus public and cooperative, +0.19 and −1.54; the retail-choice proxy, not estimable on the seven (no headline host is in the group) and +2.07 on the 36 (+8.05 on the state reading); past utilization above the median minus at or below it, −7.24 and −5.59.

**Results with no range, and why.** E3 on the headline set (three hosts, −0.35%) and the deletion of the five highest-load hosts (two hosts left, +1.81%): the selected procedure failed numerically, so no range and no test result is reported. Both are descriptive.

## 10. How this compares with earlier papers

Three recent papers reach different answers. As the plan records them: Meeks, Pless, Qi and Wang (MIT CEEPR) find residential prices 2.1% higher (standard error 0.8), and 5.2% higher at investor-owned utilities (1.4). Ryu and Hiatt (USC) find the effect at cooperatives and municipal utilities and none at investor-owned utilities. Scalera, Bosetti and Pecci (CEPR) report the largest residential estimate, 13% per ten facilities. The first paper's figures are the paper's and are given as context only. I do not compare my own numbers with them, and the headline is not a test of any paper.

For the second and third papers the plan ran two comparison rows, U and C: a stated specification of mine, built toward each paper's on my panel and my inventory, with one choice changed at a time. They were run first, before any other outcome was seen. Both rows are comparison-only, support no reproduction verdict and validate nothing about the headline procedure. Five points apply to everything I say about them.

1. **Row U's pooled estimate is numerically close to the paper's under my comparison specification:** 0.0086 (standard error 0.0040) at U0, against the paper's 0.0095 (0.0026). That does not establish equivalent data construction or make data differences an unlikely explanation for a later headline difference. In my estimates without controls, the cooperative and municipal coefficients are each above the investor-owned one (at U1: 0.0053, 0.0262 and −0.0114). The paper estimates its ownership split with six controls that I do not build, so the uncontrolled ownership comparison neither confirms nor contradicts the paper's controlled result.
2. **Row C's larger estimates are findings under my comparison specification, not a reproduction failure.** At C0, uninstrumented, 0.187 (0.081) against the paper's 0.061 (0.018); at C1, instrumented, 0.927 (0.171) against 0.182 (0.034). Their causes are undiagnosed. The discrepancy already appears at C0, so it cannot be attributed solely to the instrument's numerical construction. No alternative specification was investigated.
3. **Capping changes the regressor and its first stage,** so the coefficients at different caps are not alternative estimates on an unchanged exposure scale: 0.412 with no cap, 0.577 at the 99.9th percentile, 0.927 at the 99.5th, 1.414 at the 99.0th. The first-stage F is low at uncapped C2 (6.06) and at C4 (8.85). These are reported with no new threshold, exclusion or inference rule.
4. **C5 concerns utilities classified as never hosting under the inventory's operational rule,** not places proven to contain no data centers. My instrument also predicts price changes among them: a reduced-form estimate of 0.341 (90% interval 0.234 to 0.447) among never-host utility-states, against 0.366 in the full sample. The relationship does not distinguish spillovers, missed facilities or other correlated influences, and does not establish whether the paper's differently constructed instrument identifies hosting effects.
5. **The two spending series give close results that are not equal to the second decimal at every instrumented step:** C4 is 44.88 against 44.77.

Row U's sample excludes Short Form unit-years by the adopted rule, with the incomplete Short Form exclusion for 2019: the year as a whole is not excluded. A unit-year kept has no record of a Short Form filing, which is no claim about whether it filed. Ownership is the modal reported type over a utility's own filings.

## 11. What I planned and did not finish

- **The tariff check.** Not built. No tariff was collected and no module rebuilds bills from rate schedules. It is the one promised check that would test the outcome measure itself, by asking whether revenue per kWh moved the way published rates moved. A pilot is scoped and not begun.
- **The regional layer.** Not built. It would account for costs that fall on a whole region, such as PJM capacity cost per residential customer, compared with the market monitor's own attribution to data centers. The headline differences those costs out, and none of the seven hosts buys in PJM. An accounting is scoped and not begun.
- **The second estimator.** Specified and not obtained (section 7). The plan allows two courses. If the cause is a coding failure in a covariate, the plan calls for "a bounded repair and not for leaving it out". Otherwise the write-up "reports that limitation and no other specification is substituted". I have not diagnosed which applies. That outcomes have now been seen is not by itself a reason to rule a repair out, and a repair would be a dated change after the freeze, disclosed as such. No diagnosis or repair was begun.
- **The price's three pieces** (bundled price, delivery-only price, filled-in supply price) reported separately. No run computes them.
- **The second number at a median host's load share.** The plan does not define it, so it was not made.
- **A range for single event years.** The records hold none.
- **Exploratory work.** None was specified and none was done.
- **Water.** The planned water analysis could not be completed because adequate historical rate coverage was not obtained.

## 12. Limitations

1. Seven utilities, selected by what data was available and verifiable. Not shown to stand for hosts in general.
2. Two to three years after first crossing. Rate cases can take longer.
3. Relative to utilities in the same market region. Costs that fall on a whole region are not in the estimate.
4. Long-time hosts, northern Virginia among them, and utilities that first crossed after 2022 are outside the study.
5. Price is revenue per kWh, not a tariff, and the check against tariffs was not built.
6. The inventory is incomplete in ways that cannot be bounded from state totals. Half its rows carry no size.
7. The comparison rests on an assumption about what hosts' prices would otherwise have done, and the test of that assumption is weak on seven hosts.
8. The set of seven would often fail to detect a 5% increase.
9. One range is on a validated design. Every other range is not.
10. There is no second estimator to check the first against.
11. A small estimated difference would not, by itself, show that data centers do not raise residential bills.

## 13. What this study does not show

It does not show any of the following, and nothing in it should be read that way.

- That data centers do not raise residential bills.
- Anything about hosts beyond the set each number was estimated on.
- That hosts' prices are lower or higher than comparison utilities' in level.
- That a value outside a range is impossible.
- That overlapping runs confirm one another.
- That rows U and C reproduce a paper or fail to, or that they validate the headline.
- That the study was preregistered.
- That a result on an unvalidated design is a calibrated finding.

## 14. Code, plan and data

The code, the frozen plan, the design files and the run records are public in [the project folder on GitHub](https://github.com/eichenbaumj/gizmowarehouse.org/tree/main/gizmos/data-center-utility-bills).

- The frozen plan: [`PREANALYSIS.md`](https://github.com/eichenbaumj/gizmowarehouse.org/blob/main/gizmos/data-center-utility-bills/PREANALYSIS.md), with its deviations log.
- The pipeline and its tests: [`pipeline/`](https://github.com/eichenbaumj/gizmowarehouse.org/tree/main/gizmos/data-center-utility-bills/pipeline) and [`tests/`](https://github.com/eichenbaumj/gizmowarehouse.org/tree/main/gizmos/data-center-utility-bills/tests). The folder's README says what can and cannot be rebuilt from the shipped files.
- The frozen design-side files: [`data/frozen/`](https://github.com/eichenbaumj/gizmowarehouse.org/tree/main/gizmos/data-center-utility-bills/data/frozen).
- The saved result records, 59 of them, with the manifest and report: [`data/results/session28_uc/`](https://github.com/eichenbaumj/gizmowarehouse.org/tree/main/gizmos/data-center-utility-bills/data/results/session28_uc).
- The data sources and their credits: [`DATA_SOURCES.md`](https://github.com/eichenbaumj/gizmowarehouse.org/blob/main/gizmos/data-center-utility-bills/DATA_SOURCES.md).
- The test evidence is the project's test suite on the execution commit, with nine files excluded: 105 named files under the machine's Python, 3,091 passed, none failed, 4 skipped, 1 expected failure; sixteen named files under the project environment, 768 passed. It is not a pass of the whole suite.

## Appendix A. All stacked results on residential price

One row for each stacked result with a range, outside the two leave-one-out lists. Only the first row is on the validated design. E1 and E2 are fake events.

| record | entry | result | hosts | relative change | 90% range | note |
|---|---|---|---|---|---|---|
| 6 | main_headline_set | headline_set at 2% | 7 | -1.60% | -7.12% to +4.25% | the validated design |
| 7 | main_ten_year_set | headline_set_with_the_ten_year_case at 2% | 6 | -1.94% | -7.78% to +4.26% |  |
| 8 | main_plus_unsettled | headline_set_plus_hosts_unsettled_on_assignment at 2% | 17 | +0.22% | -3.62% to +4.21% |  |
| 9 | main_every_cohort_utility | every_cohort_utility at 2% | 36 | +3.08% | -0.72% to +7.02% |  |
| 10 | timing_run_no_anchoring_years | headline_set at 2% | 9 | -3.82% | -8.92% to +1.56% |  |
| 22 | affiliates_readmitted | headline_set at 2% | 7 | -1.90% | -5.91% to +2.28% |  |
| 23 | shared_suppliers_removed | headline_set at 2% | 7 | -1.23% | -6.85% to +4.74% |  |
| 26 | unresolved_ownership_excluded | headline_set at 2% | 5 | -3.93% | -8.64% to +1.01% |  |
| 26 | unresolved_ownership_excluded | every_cohort_utility at 2% | 31 | +2.18% | -1.04% to +5.52% |  |
| 27 | later_start_plus_1 | headline_set at 2% | 7 | -1.60% | -7.12% to +4.25% |  |
| 28 | later_start_plus_3 | headline_set at 2% | 7 | -1.21% | -6.54% to +4.43% |  |
| 29 | later_start_plus_5 | headline_set at 2% | 7 | -1.21% | -6.54% to +4.43% |  |
| 32 | longer_horizon | headline_set at 2% / six_years | 5 | -3.79% | -14.69% to +8.50% |  |
| 32 | longer_horizon | headline_set at 2% / three_years_same_utilities | 5 | -2.11% | -8.67% to +4.92% |  |
| 32 | longer_horizon | every_cohort_utility at 2% / six_years | 28 | +4.02% | -1.35% to +9.68% |  |
| 32 | longer_horizon | every_cohort_utility at 2% / three_years_same_utilities | 28 | +2.74% | -1.38% to +7.02% |  |
| 33 | future_hosts_as_comparisons | headline_set at 2% | 7 | -2.02% | -7.48% to +3.77% |  |
| 34 | own_state_comparisons | headline_set at 2% | 5 | +1.90% | -1.86% to +5.81% |  |
| 34 | own_state_comparisons | every_cohort_utility at 2% | 30 | +4.83% | +0.90% to +8.91% |  |
| 35 | threshold_1pct | every_cohort_utility at 1% | 41 | +2.65% | +0.19% to +5.19% |  |
| 36 | threshold_5pct | headline_set at 5% | 5 | -0.98% | -6.22% to +4.55% |  |
| 36 | threshold_5pct | every_cohort_utility at 5% | 28 | -1.18% | -4.17% to +1.90% |  |
| 37 | fuel_mix_categorical | headline_set at 2% | 7 | +0.09% | -5.41% to +5.91% |  |
| 38 | fuel_mix_none | headline_set at 2% | 7 | -3.07% | -10.31% to +4.76% |  |
| 39 | size_band_side_run | headline_set at 2% | 7 | -3.03% | -7.84% to +2.04% |  |
| 40 | E1 | headline_set at 2% | 7 | +1.42% | -4.95% to +8.20% | fake events six years early |
| 40 | E1 | every_cohort_utility at 2% | 30 | +3.16% | -0.93% to +7.41% | fake events six years early |
| 41 | E2 | e2_eligible_future_host_sample at 2% | 6 | +6.71% | -2.03% to +16.23% | fake events for future hosts |
| 42 | E3 | every_cohort_utility at 2% | 23 | +3.19% | -1.70% to +8.31% |  |
| 43 | E4a | headline_set at 2% | 7 | -1.42% | -7.47% to +5.03% |  |
| 43 | E4a | every_cohort_utility at 2% | 35 | +3.65% | +0.22% to +7.19% |  |
| 44 | E4b | headline_set at 2% | 7 | -0.07% | -5.49% to +5.67% |  |
| 44 | E4b | every_cohort_utility at 2% | 33 | +2.11% | -2.22% to +6.63% |  |
| 45 | E5 | headline_set at 2% | 4 | +0.50% | -21.55% to +28.75% |  |
| 45 | E5 | every_cohort_utility at 2% | 22 | +3.59% | -2.82% to +10.43% |  |
| 46 | E6 | headline_set at 2% | 7 | -1.49% | -6.97% to +4.30% |  |
| 46 | E6 | every_cohort_utility at 2% | 36 | +3.31% | -0.53% to +7.29% |  |
| 53 | influence_each_market_region_left_out | headline_set at 2%, region ERCOT left out | 6 | -2.08% | -8.71% to +5.02% |  |
| 53 | influence_each_market_region_left_out | headline_set at 2%, region SPP left out | 6 | +1.42% | -5.15% to +8.46% |  |
| 53 | influence_each_market_region_left_out | headline_set at 2%, region Southeast left out | 6 | -1.60% | -7.88% to +5.11% |  |
| 53 | influence_each_market_region_left_out | headline_set at 2%, region West left out | 3 | -0.73% | -7.23% to +6.22% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state AZ left out | 6 | -1.94% | -7.78% to +4.26% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state CO left out | 7 | -1.38% | -7.11% to +4.70% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state FL left out | 7 | -1.68% | -7.19% to +4.15% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state GA left out | 6 | -1.60% | -7.88% to +5.11% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state ID left out | 7 | -1.62% | -7.38% to +4.49% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state KS left out | 7 | -1.75% | -7.50% to +4.35% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state LA left out | 7 | -1.36% | -6.67% to +4.24% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state MO left out | 7 | -1.96% | -8.01% to +4.48% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state NC left out | 7 | -1.72% | -7.23% to +4.12% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state NE left out | 6 | +1.42% | -5.15% to +8.46% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state NM left out | 6 | -3.98% | -8.37% to +0.62% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state NV left out | 6 | -0.17% | -5.08% to +4.99% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state OR left out | 7 | -1.63% | -7.34% to +4.43% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state SC left out | 7 | -1.68% | -7.23% to +4.20% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state TN left out | 7 | -1.58% | -6.92% to +4.06% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state TX left out | 6 | -2.03% | -9.36% to +5.89% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state UT left out | 6 | -1.41% | -7.80% to +5.41% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state WA left out | 7 | -0.23% | -6.40% to +6.35% |  |
| 54 | influence_each_state_left_out | headline_set at 2%, state WY left out | 7 | -1.62% | -6.81% to +3.86% |  |
| 55 | influence_virginia_left_out | headline_set at 2%, state VA left out | 7 | -1.60% | -7.12% to +4.25% |  |

## Appendix B. All runs of the second test

| record | run | form of the load share | percent of price per point of load share | 90% range | over ten points of load share (illustration) | its range | utilities |
|---|---|---|---|---|---|---|---|
| 15 | as assigned (the primary run) | capped at 25 points (the second number) | -0.0229% | -0.3873% to +0.3533% | -0.23% | -3.81% to +3.59% | 1182 |
| 15 | as assigned (the primary run) | uncapped (beside it) | -0.0222% | -0.0654% to +0.0217% | -0.22% | -0.65% to +0.22% | 1182 |
| 15 | as assigned (the primary run) | capped at 50 points (beside it) | +0.0224% | -0.1421% to +0.2005% | +0.22% | -1.41% to +2.02% | 1182 |
| 16 | classes 2 to 4 only | capped at 25 points (the second number) | +0.1489% | -0.2649% to +0.5938% | +1.50% | -2.62% to +6.10% | 1102 |
| 16 | classes 2 to 4 only | uncapped (beside it) | +0.0938% | -0.1633% to +0.3501% | +0.94% | -1.62% to +3.56% | 1095 |
| 16 | classes 2 to 4 only | capped at 50 points (beside it) | +0.1168% | -0.1131% to +0.3411% | +1.17% | -1.13% to +3.46% | 1098 |
| 17 | ten highest-leverage not-settled utilities left out | capped at 25 points (the second number) | -0.0379% | -0.4825% to +0.4056% | -0.38% | -4.72% to +4.13% | 1172 |
| 17 | ten highest-leverage not-settled utilities left out | uncapped (beside it) | +0.1496% | +0.0569% to +0.2364% | +1.51% | +0.57% to +2.39% | 1172 |
| 17 | ten highest-leverage not-settled utilities left out | capped at 50 points (beside it) | +0.1294% | -0.0283% to +0.2862% | +1.30% | -0.28% to +2.90% | 1172 |
| 18 | sensitivity scenario A, runner-up placement | capped at 25 points (the second number) | +0.1138% | -0.0976% to +0.3221% | +1.14% | -0.97% to +3.27% | 1184 |
| 18 | sensitivity scenario A, runner-up placement | uncapped (beside it) | -0.0223% | -0.0474% to +0.0009% | -0.22% | -0.47% to +0.01% | 1184 |
| 18 | sensitivity scenario A, runner-up placement | capped at 50 points (beside it) | +0.0284% | -0.1087% to +0.1667% | +0.28% | -1.08% to +1.68% | 1184 |
| 19 | sensitivity scenario B, other end of every dated interval | capped at 25 points (the second number) | -0.0669% | -0.5484% to +0.3977% | -0.67% | -5.35% to +4.05% | 1184 |
| 19 | sensitivity scenario B, other end of every dated interval | uncapped (beside it) | -0.0262% | -0.0652% to +0.0144% | -0.26% | -0.65% to +0.14% | 1184 |
| 19 | sensitivity scenario B, other end of every dated interval | capped at 50 points (beside it) | -0.0074% | -0.2372% to +0.2322% | -0.07% | -2.35% to +2.35% | 1184 |
| 20 | after period 2024 to 2025 (E3) | capped at 25 points (the second number) | -0.0072% | -0.4100% to +0.3967% | -0.07% | -4.03% to +4.04% | 1188 |
| 20 | after period 2024 to 2025 (E3) | uncapped (beside it) | -0.0210% | -0.0844% to +0.0427% | -0.21% | -0.84% to +0.43% | 1188 |
| 20 | after period 2024 to 2025 (E3) | capped at 50 points (beside it) | +0.0334% | -0.1467% to +0.2261% | +0.33% | -1.46% to +2.28% | 1188 |
| 21 | year by year, 2005 to 2025 (side run) | capped at 25 points (the second number) | -0.0380% | -0.2634% to +0.1843% | -0.38% | -2.60% to +1.86% | 1168 |
| 21 | year by year, 2005 to 2025 (side run) | uncapped (beside it) | -0.0054% | -0.0309% to +0.0201% | -0.05% | -0.31% to +0.20% | 1168 |
| 21 | year by year, 2005 to 2025 (side run) | capped at 50 points (beside it) | -0.0015% | -0.1090% to +0.1117% | -0.01% | -1.08% to +1.12% | 1168 |

## Appendix C. All result records, in the order they were written

For each record, this table shows separately whether it was written, whether an estimate was produced, whether a range and a test were produced, and whether the design is the validated one. Capitals mark what is missing.

| # | entry | result within the entry | record written | estimate produced | range produced | early-years test produced | design and validation, in the record's words | failure, noncomputable or unbuilt |
|---|---|---|---|---|---|---|---|---|
| 1 | read_time_checks | the record made before any estimate (not a registry entry) | yes | none: not an estimate | none | none | not applicable | none |
| 2 | reconciliation_row_U | 4 steps (U0 to U3), pooled and by ownership | yes | yes, every step; steps not computed: 0 | no range in the row: estimates with clustered standard errors; the band shown beside is the paper's figure plus or minus two of its standard errors | none specified | comparison-only; the record: "not applicable: an estimator other than the selected procedure, so no validation is claimed (None is kept for the validated headline alone)" | numerical failures in any step: 0 |
| 3 | reconciliation_row_C | 19 step records (C0 to C4 under two spending series, the ownership split, C5) | yes | yes, every step; steps with a failure: 0 | C0 to C4: no range, estimates with clustered standard errors. C5: the row's own 90% interval (t on clusters less one), not one of the inference comparison's candidates | none specified | comparison-only; the record: "not applicable: an estimator other than the selected procedure, so no validation is claimed (None is kept for the validated headline alone)" | none |
| 4 | read_time_checks | the record made before any estimate (not a registry entry) | yes | none: not an estimate | none | none | not applicable | none |
| 5 | inventory_against_sales | headline_set at 2% (a quantity-side check; reads no outcome) | yes | a slope and a share, not an estimate on price | none specified | none specified | not applicable: a quantity-side check that reads no outcome and estimates nothing on price | none |
| 6 | main_headline_set | headline_set at 2% (7 hosts) | yes | yes: -1.60% | yes: -7.12% to +4.25% | yes: p 0.621, does not fail at p below 0.10 | "the validated design: checked: the design's inputs and rules are those the procedure was validated on" | none |
| 7 | main_ten_year_set | headline_set_with_the_ten_year_case at 2% (6 hosts) | yes | yes: -1.94% | yes: -7.78% to +4.26% | yes: p 0.653, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 8 | main_plus_unsettled | headline_set_plus_hosts_unsettled_on_assignment at 2% (17 hosts) | yes | yes: +0.22% | yes: -3.62% to +4.21% | yes: p 0.718, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 9 | main_every_cohort_utility | every_cohort_utility at 2% (36 hosts) | yes | yes: +3.08% | yes: -0.72% to +7.02% | yes: p 0.261, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 10 | timing_run_no_anchoring_years | headline_set at 2% (9 hosts) | yes | yes: -3.82% | yes: -8.92% to +1.56% | yes: p 0.704, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 11 | customer_weighted | headline_set at 2% | yes | yes: -0.71% (a descriptive point estimate) | NO RANGE, by design. The record: "no range is reported: the selected procedure (CR2, Satterthwaite) was validated on the unweighted headline design and has no weighted path" | none | "not applicable: a descriptive point estimate with no range, so no validation is claimed (None is kept for the validated headline alone)" | none |
| 12 | other_outcome_kwh_per_customer | headline_set at 2% (7 hosts) | yes | yes: -1.91% | yes: -3.87% to +0.09% | yes: p 0.454, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 13 | other_outcome_bill_per_customer | headline_set at 2% (7 hosts) | yes | yes: -3.47% | yes: -8.75% to +2.11% | yes: p 0.993, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 14 | other_outcome_residential_customers | headline_set at 2% (7 hosts) | yes | yes: -0.21% | yes: -3.89% to +3.61% | yes: p 0.518, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 15 | second_number_as_assigned | uncapped | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 15 | second_number_as_assigned | capped_at_25_points | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 15 | second_number_as_assigned | capped_at_50_points | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 16 | second_number_settled_only_classes_2_to_4 | uncapped | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 16 | second_number_settled_only_classes_2_to_4 | capped_at_25_points | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 16 | second_number_settled_only_classes_2_to_4 | capped_at_50_points | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 17 | second_number_ten_highest_leverage_left_out | uncapped | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 17 | second_number_ten_highest_leverage_left_out | capped_at_25_points | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 17 | second_number_ten_highest_leverage_left_out | capped_at_50_points | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 18 | second_number_sensitivity_scenario_a_runner_up_placement | uncapped | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 18 | second_number_sensitivity_scenario_a_runner_up_placement | capped_at_25_points | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 18 | second_number_sensitivity_scenario_a_runner_up_placement | capped_at_50_points | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 19 | second_number_sensitivity_scenario_b_other_end_of_every_dated_interval | uncapped | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 19 | second_number_sensitivity_scenario_b_other_end_of_every_dated_interval | capped_at_25_points | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 19 | second_number_sensitivity_scenario_b_other_end_of_every_dated_interval | capped_at_50_points | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 20 | second_number_e3_after_period_2024_2025 | uncapped | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 20 | second_number_e3_after_period_2024_2025 | capped_at_25_points | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 20 | second_number_e3_after_period_2024_2025 | capped_at_50_points | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 21 | second_number_year_by_year | uncapped | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 21 | second_number_year_by_year | capped_at_25_points | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 21 | second_number_year_by_year | capped_at_50_points | yes | yes | yes (bootstrap-t) | none specified | not the validated design or procedure: "not calibrated by the inference comparison" | none |
| 22 | affiliates_readmitted | headline_set at 2% (7 hosts) | yes | yes: -1.90% | yes: -5.91% to +2.28% | yes: p 0.813, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 23 | shared_suppliers_removed | headline_set at 2% (7 hosts) | yes | yes: -1.23% | yes: -6.85% to +4.74% | yes: p 0.615, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 24 | leave_one_comparison_out | headline_set at 2%: 42 deletions | yes | 42 of 42 deletions | 42 of 42 deletions | none reported per deletion | "under the procedure validated on the headline set; no validation was made on this design" | deletions with a numerical failure: 0; not computed: 0; with inadequate support: 0; with a host not estimable: 0 |
| 25 | leave_one_company_out | headline_set at 2%: 36 deletions | yes | 36 of 36 deletions | 36 of 36 deletions | none reported per deletion | "under the procedure validated on the headline set; no validation was made on this design" | deletions with a numerical failure: 0; not computed: 0; with inadequate support: 0; with a host not estimable: 0 |
| 26 | unresolved_ownership_excluded | headline_set at 2% (5 hosts) | yes | yes: -3.93% | yes: -8.64% to +1.01% | yes: p 0.882, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 26 | unresolved_ownership_excluded | every_cohort_utility at 2% (31 hosts) | yes | yes: +2.18% | yes: -1.04% to +5.52% | yes: p 0.294, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 27 | later_start_plus_1 | headline_set at 2% (7 hosts) | yes | yes: -1.60% | yes: -7.12% to +4.25% | yes: p 0.621, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 28 | later_start_plus_3 | headline_set at 2% (7 hosts) | yes | yes: -1.21% | yes: -6.54% to +4.43% | yes: p 0.732, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 29 | later_start_plus_5 | headline_set at 2% (7 hosts) | yes | yes: -1.21% | yes: -6.54% to +4.43% | yes: p 0.732, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 30 | callaway_santanna | headline_set at 2% | yes | a number was produced (-0.03596 log points, -3.53% by pct), but the record labels it "not the specified estimator: the package did not use every covariate in every cell" | NO RANGE. The record: "no range: 2 covariate warning(s) from the package" | none specified | "not applicable: an estimator other than the selected procedure, so no validation is claimed (None is kept for the validated headline alone)" | NUMERICAL FAILURE recorded: "2 covariate warning(s) from the package" (state-clustered call); "61 covariate warning(s) from the package" (unit-level call) |
| 31 | estimators_agree | a table of five rows built from entries 6 to 9 and 30 (no new fit) | yes | a table, not an estimate: 5 rows, 10 gaps | range comparisons among the four stacked rows only; rows in no range comparison: 1 | none specified | "not applicable: an estimator other than the selected procedure, so no validation is claimed (None is kept for the validated headline alone)"; only the headline-set row is on the validated design | row "Callaway and Sant'Anna: headline_set at 2%": status "failed", "2 covariate warning(s) from the package" |
| 32 | longer_horizon | headline_set at 2% / six_years (5 hosts) | yes | yes: -3.79% | yes: -14.69% to +8.50% | yes: p 0.785, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 32 | longer_horizon | headline_set at 2% / three_years_same_utilities (5 hosts) | yes | yes: -2.11% | yes: -8.67% to +4.92% | yes: p 0.717, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 32 | longer_horizon | every_cohort_utility at 2% / six_years (28 hosts) | yes | yes: +4.02% | yes: -1.35% to +9.68% | yes: p 0.332, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 32 | longer_horizon | every_cohort_utility at 2% / three_years_same_utilities (28 hosts) | yes | yes: +2.74% | yes: -1.38% to +7.02% | yes: p 0.290, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 33 | future_hosts_as_comparisons | headline_set at 2% (7 hosts) | yes | yes: -2.02% | yes: -7.48% to +3.77% | yes: p 0.640, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 34 | own_state_comparisons | headline_set at 2% (5 hosts) | yes | yes: +1.90% | yes: -1.86% to +5.81% | yes: p 0.987, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 34 | own_state_comparisons | every_cohort_utility at 2% (30 hosts) | yes | yes: +4.83% | yes: +0.90% to +8.91% | yes: p 0.322, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 35 | threshold_1pct | every_cohort_utility at 1% (41 hosts) | yes | yes: +2.65% | yes: +0.19% to +5.19% | yes: p 0.323, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 36 | threshold_5pct | headline_set at 5% (5 hosts) | yes | yes: -0.98% | yes: -6.22% to +4.55% | yes: p 0.671, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 36 | threshold_5pct | every_cohort_utility at 5% (28 hosts) | yes | yes: -1.18% | yes: -4.17% to +1.90% | yes: p 0.779, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 37 | fuel_mix_categorical | headline_set at 2% (7 hosts) | yes | yes: +0.09% | yes: -5.41% to +5.91% | yes: p 0.489, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 38 | fuel_mix_none | headline_set at 2% (7 hosts) | yes | yes: -3.07% | yes: -10.31% to +4.76% | yes: p 0.809, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 39 | size_band_side_run | headline_set at 2% (7 hosts) | yes | yes: -3.03% | yes: -7.84% to +2.04% | yes: p 0.661, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 40 | E1 | headline_set at 2% (7 hosts) | yes | yes: +1.42% | yes: -4.95% to +8.20% | yes: p 0.185, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 40 | E1 | every_cohort_utility at 2% (30 hosts) | yes | yes: +3.16% | yes: -0.93% to +7.41% | yes: p 0.513, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 41 | E2 | e2_eligible_future_host_sample at 2% (6 hosts) | yes | yes: +6.71% | yes: -2.03% to +16.23% | yes: p 0.657, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 42 | E3 | headline_set at 2% (3 hosts) | yes | yes: -0.35% | NO RANGE | NO TEST RESULT | "under the procedure validated on the headline set; no validation was made on this design" | NUMERICAL FAILURE. The record: "descriptive: the selected procedure failed numerically, so no range and no test result is reported"; "the degrees of freedom are undefined or not finite (undefined_or_non_finite_degrees_of_freedom, at early_years_test): AHT eta = 1.7872237248329008" |
| 42 | E3 | every_cohort_utility at 2% (23 hosts) | yes | yes: +3.19% | yes: -1.70% to +8.31% | yes: p 0.228, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 43 | E4a | headline_set at 2% (7 hosts) | yes | yes: -1.42% | yes: -7.47% to +5.03% | yes: p 0.807, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 43 | E4a | every_cohort_utility at 2% (35 hosts) | yes | yes: +3.65% | yes: +0.22% to +7.19% | yes: p 0.720, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 44 | E4b | headline_set at 2% (7 hosts) | yes | yes: -0.07% | yes: -5.49% to +5.67% | yes: p 0.672, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 44 | E4b | every_cohort_utility at 2% (33 hosts) | yes | yes: +2.11% | yes: -2.22% to +6.63% | yes: p 0.444, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 45 | E5 | headline_set at 2% (4 hosts) | yes | yes: +0.50% | yes: -21.55% to +28.75% | yes: p 0.980, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 45 | E5 | every_cohort_utility at 2% (22 hosts) | yes | yes: +3.59% | yes: -2.82% to +10.43% | yes: p 0.163, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 46 | E6 | headline_set at 2% (7 hosts) | yes | yes: -1.49% | yes: -6.97% to +4.30% | yes: p 0.690, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 46 | E6 | every_cohort_utility at 2% (36 hosts) | yes | yes: +3.31% | yes: -0.53% to +7.29% | yes: p 0.418, does not fail at p below 0.10 | "under the procedure validated on the headline set; no validation was made on this design" | none |
| 47 | E7_earlier | headline_set at 2% | yes | point estimates in 200 of 200 draws | NO RANGE, by design: "point estimates only, no range per draw (E7)" | none, by design | "under the procedure validated on the headline set; no validation was made on this design" | draws that could not be computed: 0 |
| 47 | E7_earlier | every_cohort_utility at 2% | yes | point estimates in 200 of 200 draws | NO RANGE, by design: "point estimates only, no range per draw (E7)" | none, by design | "under the procedure validated on the headline set; no validation was made on this design" | draws that could not be computed: 0 |
| 48 | E7_later | headline_set at 2% | yes | point estimates in 200 of 200 draws | NO RANGE, by design: "point estimates only, no range per draw (E7)" | none, by design | "under the procedure validated on the headline set; no validation was made on this design" | draws that could not be computed: 0 |
| 48 | E7_later | every_cohort_utility at 2% | yes | point estimates in 200 of 200 draws | NO RANGE, by design: "point estimates only, no range per draw (E7)" | none, by design | "under the procedure validated on the headline set; no validation was made on this design" | draws that could not be computed: 0 |
| 49 | condition_1_load_share | headline_set at 2% | yes | yes: a difference between two groups (+5.00, log points x 100) | NO RANGE, by design (a descriptive contrast) | none, by design | "not applicable: a descriptive contrast with no range and no test, so no validation is claimed (None is kept for the validated headline alone)" | none |
| 49 | condition_1_load_share | every_cohort_utility at 2% | yes | yes: a difference between two groups (-2.55, log points x 100) | NO RANGE, by design (a descriptive contrast) | none, by design | "not applicable: a descriptive contrast with no range and no test, so no validation is claimed (None is kept for the validated headline alone)" | none |
| 50 | condition_2_investor_owned | headline_set at 2% | yes | yes: a difference between two groups (+0.19, log points x 100) | NO RANGE, by design (a descriptive contrast) | none, by design | "not applicable: a descriptive contrast with no range and no test, so no validation is claimed (None is kept for the validated headline alone)" | none |
| 50 | condition_2_investor_owned | every_cohort_utility at 2% | yes | yes: a difference between two groups (-1.54, log points x 100) | NO RANGE, by design (a descriptive contrast) | none, by design | "not applicable: a descriptive contrast with no range and no test, so no validation is claimed (None is kept for the validated headline alone)" | none |
| 51 | condition_3_retail_choice_proxy | headline_set at 2% | yes | NO | NO RANGE, by design (a descriptive contrast) | none, by design | "not applicable: a descriptive contrast with no range and no test, so no validation is claimed (None is kept for the validated headline alone)" | NOT ESTIMABLE. The record: "no host in this design is in the group(s) ['delivery-only residential activity observed (retail-choice proxy)']" |
| 51 | condition_3_retail_choice_proxy | headline_set at 2%, the state reading beside it | yes | NO | NO RANGE, by design (a descriptive contrast) | none, by design | "not applicable: a descriptive contrast with no range and no test, so no validation is claimed (None is kept for the validated headline alone)" | NOT ESTIMABLE. The record: "no host in this design is in the group(s) ['delivery-only residential activity observed (retail-choice proxy)']" |
| 51 | condition_3_retail_choice_proxy | every_cohort_utility at 2% | yes | yes: a difference between two groups (+2.07, log points x 100) | NO RANGE, by design (a descriptive contrast) | none, by design | "not applicable: a descriptive contrast with no range and no test, so no validation is claimed (None is kept for the validated headline alone)" | none |
| 51 | condition_3_retail_choice_proxy | every_cohort_utility at 2%, the state reading beside it | yes | yes: a difference between two groups (+8.05, log points x 100) | NO RANGE, by design (a descriptive contrast) | none, by design | "not applicable: a descriptive contrast with no range and no test, so no validation is claimed (None is kept for the validated headline alone)" | none |
| 52 | condition_4_past_utilization | headline_set at 2% | yes | yes: a difference between two groups (-7.24, log points x 100) | NO RANGE, by design (a descriptive contrast) | none, by design | "not applicable: a descriptive contrast with no range and no test, so no validation is claimed (None is kept for the validated headline alone)" | none |
| 52 | condition_4_past_utilization | every_cohort_utility at 2% | yes | yes: a difference between two groups (-5.59, log points x 100) | NO RANGE, by design (a descriptive contrast) | none, by design | "not applicable: a descriptive contrast with no range and no test, so no validation is claimed (None is kept for the validated headline alone)" | none |
| 53 | influence_each_market_region_left_out | headline_set at 2%: 4 deletion(s) | yes | 4 of 4 | 4 of 4 | 4 of 4 | "under the procedure validated on the headline set; no validation was made on this design" | deletions with a numerical failure: 0 |
| 54 | influence_each_state_left_out | headline_set at 2%: 19 deletion(s) | yes | 19 of 19 | 19 of 19 | 19 of 19 | "under the procedure validated on the headline set; no validation was made on this design" | deletions with a numerical failure: 0 |
| 55 | influence_virginia_left_out | headline_set at 2%: 1 deletion(s) | yes | 1 of 1 | 1 of 1 | 1 of 1 | "under the procedure validated on the headline set; no validation was made on this design" | deletions with a numerical failure: 0 |
| 56 | influence_five_highest_load_utilities_dropped | headline_set at 2%, the two hosts left | yes | yes: +1.81% by pct (saved: +0.01794 log points), labelled descriptive | NO RANGE | NO TEST RESULT | "under the procedure validated on the headline set; no validation was made on this design" | NUMERICAL FAILURE. The record: "descriptive: the selected procedure failed numerically, so no range and no test result is reported"; "the degrees of freedom are undefined or not finite (undefined_or_non_finite_degrees_of_freedom, at early_years_test): AHT eta = 1.1925980724853231" |
| 57 | tariff_check | (the registry's record for an entry with no code) | yes | no | no | no | not applicable | NOT BUILT. The record's words: "no tariff is collected before the freeze and no module rebuilds bills from rate schedules" |
| 58 | regional_layer | (the registry's record for an entry with no code) | yes | no | no | no | not applicable | NOT BUILT. The record's words: "no module computes PJM capacity cost per customer or the exploratory description of bills after June 2025; nothing in the plan specifies the latter" |
| 59 | exploratory_work | (the registry's record for an entry with no code) | yes | no | no | no | not applicable | NOT BUILT. The record's words: "not specified by the plan, so there is nothing to build" |
