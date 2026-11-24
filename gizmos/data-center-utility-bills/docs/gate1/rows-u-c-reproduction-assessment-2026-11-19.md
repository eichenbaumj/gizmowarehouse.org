# Rows U and C: what the pooled estimate and C0 can claim, and drafted wording (session 21, 2026-11-19)

Written by a session 21 build agent (model claude-opus-5-5) for Joe. **It adopts nothing.** It is the assessment his clarification of 2026-11-19 asks for, the drafts of section 4 item 3 of the session 21 handover, and the exact text of R8's changes to rows U and C for the session to apply. The plan is a DRAFT pre-analysis plan, not frozen and not registered with anyone outside. No host utility's price in the outcome data has been read; one lapse in source access is disclosed in the plan and qualifies that statement. Nothing here reads a price or depends on one.

His words that govern it (D-107): "For R5, the uncontrolled ownership ordering cannot count as reproduction or failure to reproduce the controlled result. Assess any pooled claim separately against its own specification. The instrumented comparisons cannot support reproduction claims given the spatial-construction difference and the spending-unit approximation. Retain them only as explicitly labelled comparisons under our specification; C0 remains separately assessable." And: "Retaining the pooled U and C0 comparison bands does not itself establish that either supports a reproduction verdict; assess each against its own specification as ruled."

Sources. The outcomes of each element are those of D-106 section 6 (outcome 1 settled from the paper, outcome 2 a labelled approximation of ours, outcome 3 exact reproduction unavailable), with D-107's adoption of R5 turning each outcome 2 element into this study's approximation. The passages relied on were checked again in the papers' text on 2026-11-19, on the bounded read's questions only: Ryu and Hiatt, `docs/research/papers/ryu_hiatt_usc/2026-05-22 Data Center Entry and US Electricity Prices.pdf`, and Scalera, Bosetti and Pecci, `docs/research/papers/scalera_cepr_dp21854/DP21854.pdf`, both through `pdftotext -layout` into a scratch folder. Page numbers are the papers' printed pages. Readings that are mine and not a source's are marked "the agent's reading".

What the code does now, whatever he rules (pipeline/analysis/reconciliation_mu.py and reconciliation_c.py): neither row returns "reproduced" or "not reproduced" anywhere. The pooled row U estimate at U0 and C0 come back as labelled comparisons with the paper's band beside them; row U's ownership estimates and every instrumented result of row C come back as labelled comparisons under our specification with the reason no reproduction claim attaches. A test scans every output for verdict words.

## 1. The pooled row U estimate against its own specification

Its own specification is the paper's column with no controls: Table A4a, row A "Through 2024 (primary)", column "No controls", +0.0095 (0.0026), N 16,163 (p. 25). The caption: "The dependent variable is the natural log of residential price (cents per kWh). Treatment is ln(DC MW + 1). Utility and year fixed effects, standard errors clustered by state." The comparison band is the plan's, 0.0043 to 0.0147.

| Element | What the paper says, and where | Outcome |
|---|---|---|
| Outcome | Residential price as "revenue divided by sales (cents per kWh) within each utility-state-year", "restricting to bundled-service utilities" (p. 6); its log (p. 25) | 1 |
| Which of our columns | `res_price_default_service`, bundled revenue over bundled sales; the paper does not name its columns | 2, ours (D-107) |
| Regressor | ln(DC MW + 1), "the cumulative operating data center capacity in the utility's service territory in the given year" (Table A3 note, p. 23) | 1 |
| How capacity is dated | Not stated; the vendor records "utility power capacity (kW), operational status, build year" (p. 5) | 2, ours: the inventory's site-year load (D-107) |
| The vendor's capacity against our estimated load | S&P Global 451 Research's capacity on a purchased list (p. 5); ours is load estimated from permits and public sources | 3 |
| Facility scope | "operational hyperscale and colocation facilities, excluding cryptocurrency miners, powered shells, and telecom facilities" (p. 5) | 1 for the scope; 3 for the list |
| Assignment, layer and priority | HIFLD retail service territory layer; the polygon that "strictly contains the facility's location, prioritizing retail providers over wholesale-only territories" (p. 5) | 1 |
| Assignment, several retail polygons, none, wholesale-only alone | Not stated | 2, ours: the smallest; listed and in no utility; unassigned (D-107) |
| Assignment, the layer's vintage | Not given (endnote 6 is a link only) | 3 |
| Sample: ownership type | "reporting ownership-type data" (p. 6) | 1 |
| Sample: Short Form filers | "excluded from the residential-rate regressions" (endnote 10, p. 17) | 1; for which years' filings, still open (not among R5's items) |
| Sample: three years | "dropping utilities that appear in fewer than 3 years of the panel" (p. 6) | 1; counted after every other restriction, ours (D-107) |
| Jurisdictions | "51 jurisdictions" (p. 6); "51 clusters" (p. 23); not listed | 1 for the count; the 50 states and DC, ours (D-107) |
| Window and panel | "2015-2024"; unbalanced, 16,163 observations (p. 6) | 1 |
| Multi-state utilities | "identical utility-level data center capacity" in each state (p. 6; p. 8) | 1 |
| Fixed effects | Utility and year (Table A4a caption, p. 25; Table A3 col. 1, p. 23) | 1 |
| Weights | None stated; the equation (p. 8) has none | 2, ours: unweighted (D-107) |
| Standard errors | Clustered by state (p. 25); no small-sample factor or software named | 1 for clustering; 3 for the factor; ours is the usual clustered correction for clusters and parameters (D-107) |

Two further points, both from the text. First, the plan's band test reads our point estimate against the paper's band, so the elements that bear on standard errors (the factor, the software) do not bear on it. Second, the paper's "No controls" figure in Table A4a, +0.0095 (0.0026), is the same pair of numbers the paper prints in Table A3a, Panel A, column (2), for residential price with the Henry Hub interaction added to the full controls (p. 24). That may be a coincidence of rounding. I am uncertain about this; it does not change the assessment below, and it is reported so that no one discovers it later and wonders whether it was seen.

A third point is from the code and not the paper. The polygon table's class column, as the job 4 module reads the territory layer today (`pipeline/analysis/reconciliation_inputs.py`, `TYPE_CLASS`), classes all ten `TYPE` values as ambiguous: no value's own text names retail service or wholesale-only service. Row U's assignment now leaves out, and names, every site whose unit depends on how an ambiguous polygon is classed, and with every value ambiguous that is nearly every site inside a polygon (a site inside one polygon is assigned if that polygon is retail and unassigned if it is wholesale-only). So the paper's own retail priority cannot be applied until the mapping is resolved, and U0 cannot place sites. I am uncertain whether that module's mapping is final; the session owns it.

**Can a result inside or outside the band be called "reproduced" or "not reproduced"?** My assessment is no, as things stand: only a labelled comparison. Two of the elements that move the point estimate are not the paper's. The regressor is a different measure of data center size (our estimated load against the vendor's capacity, outcome 3) and is dated by our rule, and the assignment cannot yet apply the paper's own retail priority. With ln(MW + 1) and most unit-years at or near zero MW, the plan's own known-mismatch note says a constant ratio between the two measures matters exactly there, so a result inside or outside the band would mix the measure with the finding. This is the same kind of reason Joe gave for the instrumented steps of row C, where the regressor's instrument is built differently unit by unit.

**What would have to be true for a verdict.** The territory types resolved, so that the paper's retail priority is applied as the paper states it; and Joe accepting a verdict worded as one on the paper's no-controls specification applied to a different measure of size, for example "With the paper's no-controls specification on our inventory's estimated load, the pooled coefficient is (is not) inside the band." It could never be worded as reproducing the paper's estimate.

**The strongest point against this assessment.** The plan defined reproduction from the start as running the paper's specification "on our panel and our inventory", with the facility list's difference as a stated caveat, and named the load and capacity mismatch at the same time. The pooled column has no controls, so, unlike the ownership split, nothing in it is left unbuilt. The approximations of ours are on elements the paper does not state, which D-105 allows with labels, and the band is wide (plus or minus about 55% of the paper's estimate). On that view a verdict qualified by the measure is defensible once the types are resolved, and withholding it treats a difference the plan accepted as if it were new.

## 2. C0 against its own specification

C0 is uninstrumented, so neither the fiber share nor the spending series enters it. Its own specification is Table 1, Panel A, column (1): "Number of data centers" 0.0610 (0.018), 12,370 observations, 1,237 utility-states (p. 13); "Average Electricity Prices (cents/kWh)" in real 2024 dollars (Table 1 notes). The comparison band is the plan's, 0.025 to 0.097.

| Element | What the paper says, and where | Outcome |
|---|---|---|
| Price definition | "dividing total revenue by total sales, specific to each sector" from the EIA 861 "Sales to Ultimate Customers" files (S1.3, p. 29) | 1 |
| Whether delivery-only or energy-only rows enter that price | Not stated | 3 |
| Real dollars | "We convert to real, 2024 dollars using the Consumer Price Index (CPI)" (section 2.1, p. 4) | 1 |
| The deflator's series | The CPI series is not named | 2 in D-106; **not among the items R5 lists, so not adopted**; the code supplies CPI-U annual averages from the file on hand and the choice stays the caller's |
| Levels | Cents per kWh, in levels (Table 1) | 1 |
| The count, cumulative from the start year | "the cumulative stock of data center activity among all facilities that had begun operation by that year" (S1.2, p. 28) | 1 |
| The cap | "We winsorize the data center stock measure at the 99.5th percentile within-year" (footnote 3, p. 8) | 1 |
| The percentile's population | "that year's distribution" (S2.8, p. 50), population not named | 2, ours: the step's estimation sample in that year with zeros (D-107) |
| The percentile's formula | Not stated | 2, ours: the order statistic (D-107) |
| Fixed effects and clusters | Utility-state and state-by-year effects; clustered by utility-state (footnote 10, p. 10) | 1 |
| Balanced panel and states | Ten years of non-missing residential price, 2015 to 2024, contiguous states (S1.3, p. 30; section 2.1, p. 4) | 1 |
| The fall from 1,243 units to 1,237 | Not explained; "additional sample restrictions in the final regressions based on the availability of additional data" (S1.3, p. 31) | 3 |
| Singleton groups | Not stated | 2, ours: dropped (D-107) |
| Assignment | "In cases where two or more polygons overlap, we attribute the intersected region to the smallest polygon", over 3,805 territories (S1.1, p. 25; section 2.1, p. 4) | 1; the type of a polygon plays no part (the agent's reading of those passages, which speak of "all utility service territories"), so the ambiguous `TYPE` values do not touch C0 |
| Small-sample correction and software | Not stated | 3; it does not bear on a band read on point estimates |

**Which of these can move the point estimate.** Singleton groups do not: a group with one row is fitted exactly by its own effect and contributes nothing to the slope. The small-sample correction does not. The cap's population and formula touch only the top half percent of unit-years in each year (8 units on our stand-in panel, the number the paper reports for its own, `data/frozen/reconciliation_c_design.json`). Six units of 1,243 is under half a percent of the sample. The deflator's series moves every price by a factor close to one in each year. The element that can move it by more is the price's definition. In states with retail choice, a delivery-only utility has no bundled price, and summing delivery-only revenue (wires only) with bundled revenue gives a different price; the paper does not say which it did, and our panel holds both constructions (`res_price_default_service` and `res_price`). Texas's ERCOT wires utilities, where many data centers sit, are of this kind (the agent's reading of how EIA-861 reports them; I am uncertain about this for every such utility).

**Can a result inside or outside the band be called "reproduced" or "not reproduced"?** My assessment is not yet, but C0 is much closer to supporting one than the pooled row U estimate. Every element that bears on its point estimate is settled from the paper or is an approximation of ours that touches a small part of the sample, except the price's definition, which is unavailable and can matter. Until that is settled, only a labelled comparison.

**What would have to be true for a verdict.** The price construction settled for C0, either by Joe choosing one of the panel's two constructions as a labelled approximation, or by Joe ruling that a verdict is claimed only when C0 falls on the same side of the band under both (a new choice, his); and the deflator's series named. The verdict would then be worded with the plan's caveat on the facility list, for example "The paper's uninstrumented specification, on our panel and our inventory, returns (does not return) a coefficient inside its band; our facility list is not theirs."

**The strongest point against this assessment.** An approximation adopted for the outcome's own definition is of the same kind as the spending-unit approximation that Joe said blocks a reproduction claim at the instrumented steps, so consistency could argue that C0 too should stay a comparison whatever is settled. From the other side, a larger difference than any in the specification is in the inputs. 920 of our 2,203 data center sites have no start year and enter no count (58% dated), against the paper's 91% of sites with a year (S1.2, p. 28), and a count regressor in cents per facility is scaled directly by coverage. The plan accepted the facility list's difference with a caveat, but on a count it is not a nuisance.

## 3. Drafts for Joe (each adopts nothing)

Each gives the plan's current sentence from `PREANALYSIS.md`, "The reconciliation rows", and a proposed one. They are written so that they hold whatever he rules on sections 1 and 2; where his ruling would change a draft, a second version is given.

**(i) Row U, "Reproduced if".**

Current: "*Reproduced if:* pooled coefficient between 0.0043 and 0.0147, and the co-op and municipal coefficients are each larger than the investor-owned one."

Proposed (draft A, if the pooled estimate stays a comparison): "*Compared, not tested for reproduction:* our pooled coefficient at U0 is shown beside the paper's no-controls figure and its band, 0.0043 to 0.0147, as a comparison under our specification. Our ownership coefficients are shown beside the paper's with-controls figures; our split has no controls and the paper's has six (Table A3, p. 23), so the ordering counts neither as reproducing the paper's ownership result nor as failing to."

Proposed (draft B, if Joe rules that the pooled estimate can carry a qualified verdict): "*Reproduced if, for the pooled estimate only:* with the paper's no-controls specification on our inventory's estimated load, the pooled coefficient at U0 is between 0.0043 and 0.0147. The ownership coefficients are compared and not tested: our split has no controls and the paper's has six (Table A3, p. 23), so the ordering counts neither as reproducing the paper's ownership result nor as failing to."

**(i) Row U, "What we will say" (the sentences at U1).**

Current: "*What we will say:* if co-op and municipal still exceed investor-owned at U1, "the co-op and municipal result survives correcting which utility serves each site." If the ordering reverses or the three are indistinguishable at U1, "the co-op and municipal result does not survive correcting which utility serves each site.""

Proposed: "*What we will say:* at each step, how far the pooled coefficient and each ownership coefficient moved from the step before, with the three ownership coefficients and their errors. At U1, if our co-op and municipal coefficients are each above our investor-owned coefficient, we say: "In our estimates without controls, the co-op and municipal coefficients are each above the investor-owned one when the inventory's own assignment replaces the polygon." Otherwise: "In our estimates without controls, the co-op and municipal coefficients are not each above the investor-owned one when the inventory's own assignment replaces the polygon." Either sentence is followed by: "The paper estimates its ownership split with six controls that we do not build, so this neither confirms nor contradicts its result.""

This drops "or the three are indistinguishable", as R5 proposed (that D-107's acceptance of R5's labelled approximations covers this strike is the session's reading, given to me in my brief, and I am uncertain about it); the paper tests no difference between ownership coefficients, only each against zero (Table A3a Panel B, p. 24; Table A4b, p. 25). The code chooses no sentence at U1 until wording is adopted.

**(ii) Row C, "Reproduced if".**

Current: "*Reproduced if:* uninstrumented coefficient between 0.025 and 0.097; instrumented coefficient between 0.114 and 0.250 with a first-stage F of at least 10."

Proposed: "*Compared, not tested for reproduction:* the instrumented coefficients (C1 to C4, and the ownership split at C1 and C3) are shown beside the paper's, with the band 0.114 to 0.250 and our first-stage F beside the paper's 59, as comparisons under our specification. Our fiber share places each census block by its internal point in every territory that contains it, where the paper counts the blocks that intersect each territory after overlaps are given to the smallest polygon, so the two instruments differ unit by unit; and the unit of spending inside the log is ours. No reproduction claim attaches to them. The uninstrumented coefficient at C0 is shown beside the paper's 0.061 and the band 0.025 to 0.097; whether it can be called reproduced is assessed against its own specification and is Joe's ruling."

If Joe rules that C0 can carry a verdict on the conditions of section 2, the last sentence becomes: "*Reproduced if, for C0 only:* the uninstrumented coefficient is between 0.025 and 0.097 [under the price construction he settles, or under both of the panel's constructions]."

**(ii) Row C, C5's sentence about the 13%.**

Current (the first of C5's sentences): "The instrument predicts price increases at utilities that host no data center. Region-wide costs from data centers can reach those utilities too, so this does not show that data centers played no part. It does show the instrument is not isolating what happens at hosts, so the 13% cannot be read as the effect of hosting."

Proposed: "Our version of the paper's instrument predicts price increases at utilities that host no data center. Region-wide costs from data centers can reach those utilities too, so this does not show that data centers played no part. It does show that our instrument is not isolating what happens at hosts. The paper's 13% rests on its own construction of the instrument, which differs from ours unit by unit, so this raises the question whether the 13% can be read as the effect of hosting and does not settle it."

The 13% itself is the paper's: 0.182 times "a one standard deviation increase in the post-2021 data center stock (10 data centers)", 1.82 cents over a post-2021 mean of 14.01 cents (section 4.1, p. 12). The second sentence of C5 ("The test did not detect a relationship...") and its qualifier make no claim about the paper and need no change on this ground.

## 4. R8's four changes touching rows U and C and steps M1, U1 and C3, as exact text for the session

R8 is adopted (D-107). Each change gives the current text and the new text; each was checked against the paper's passage named.

**1. Steps M1, U1 and C3: "the inventory's own assignment".**

The plan's M1 does not carry the words "hand-verified serving utility"; they are in U1 and C3, and the plan's own paragraph "As built" names all three steps. The count: `data/interim/facilities.parquet` has 181 rows with `utility_assign` "verified_by_hand" on 2026-11-19, of which 159 are data center sites and 22 are cryptocurrency mines, which no row counts. R8 says 181; the session may prefer 159, which is the count that bears on these steps (the agent's reading).

- M1, current: "(M1) the one utility that serves the site in place of every utility touching the county." New: "(M1) the inventory's own assignment, one utility per site (hand-verified for 181 sites, the rest placed by the inventory's map rules), in place of every utility touching the county."
- U1, current: "(U1) the hand-verified serving utility in place of the polygon." New: "(U1) the inventory's own assignment (hand-verified for 181 sites, the rest placed by the inventory's map rules) in place of the polygon."
- C3, current: "(C3) hand-verified serving utility in place of the polygon." New: "(C3) the inventory's own assignment (hand-verified for 181 sites, the rest placed by the inventory's map rules) in place of the polygon."

**2. Row U, U0's tie rule** (checked against p. 5: "a facility was matched to the utility whose polygon strictly contains the facility's location, prioritizing retail providers over wholesale-only territories").

Current: "(U0) their assignment rule, the territory polygon that contains the site, smallest retail polygon where several do (the tie rule is ours; they do not state one)." New: "(U0) their assignment rule, the territory polygon that strictly contains the site, with retail providers before wholesale-only territories (theirs); where several retail polygons contain the site, the smallest (ours; they do not say how they chose among several retail polygons)."

**3. Row U, "Their specification"** (checked against p. 6: "restricting to bundled-service utilities reporting ownership-type data, and dropping utilities that appear in fewer than 3 years of the panel"; endnote 10, p. 17, on Short Form filers).

Current: "*Their specification:* log residential price (bundled revenue over bundled sales, our `res_price_default_service`) on log of cumulative operating data center MW plus one; utility and year fixed effects; clustered by state; utility-state-years 2015-2024; no customer-count floor; a multi-state utility's capacity entered in each of its states. We match their no-controls column, which they print." New: "*Their specification:* log residential price (revenue over sales at bundled-service utilities; ours is `res_price_default_service`, bundled revenue over bundled sales) on log of cumulative operating data center MW plus one; utility and year fixed effects; clustered by state; utility-state-years 2015-2024; no customer-count floor; utilities reporting an ownership type only, Short Form filers excluded, and utilities that appear in fewer than three years of the panel dropped; a multi-state utility's capacity entered in each of its states. We compare with their no-controls column, which they print."

The last sentence's change from "match" to "compare with" is mine and not R8's; it follows D-107, and the session may leave it out.

**4. Row C, "Instrument inputs"** (checked against S1.1, p. 25, "we attribute the intersected region to the smallest polygon", and S1.5, p. 34, "calculate how many of the fiber-containing Census blocks intersect each utility territory"; the 205% is `data/frozen/fiber_share_by_unit.csv`, `fiber_share_dec` summing to 2.0465 over 3,551 units, checked 2026-11-19).

Current: "...technology code 50, blocks placed in HIFLD territories by their internal point, national total over the 48 states and D.C.; ... Our fiber shares match the paper's summary table in part and their scale is unresolved, which does not affect an instrumented estimate." New, for the first clause: "...technology code 50, blocks placed by their internal point in every HIFLD territory that contains it, national total over the 48 states and D.C.;" and, for the last sentence: "The paper counts the fiber blocks that intersect each territory after giving overlapping areas to the smallest polygon; ours places a block by its internal point in every territory that contains it, so our shares sum to 205% of the national total. Our shares match the paper's summary table in part, and the two constructions differ unit by unit and not by one scale, so the difference can move an instrumented estimate."

R8's fifth change (row M's "a data center above 5 MW enters a county") is left as it is until the row M read is done, as R8 says.
