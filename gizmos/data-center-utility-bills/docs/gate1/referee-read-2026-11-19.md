# Step G: the read-only referee read of the pre-analysis plan (session 18, 2026-11-19)

For Joe. Written by a fresh session that did not write the plan. It reads, reports and decides nothing. What to do about any finding is his.

**The plan is a DRAFT and is not frozen.** Nothing was run for this report: no pipeline step, no test, no simulation, no search, no fetch. Committed files were read as text.

## How this was read, and its limits

- **Read cold, in this order:** `HANDOVER_step_g_2026-11-18.md`; the "Hard rules" section of `HANDOVER.md` and no other part of it; `docs/gate1/referee-prompt-DRAFT-2026-11-18.md`; `PREANALYSIS.md` whole; `step-e-rules`; `step-d-inventory-design` with both addenda; `stop2-closing-statement`; `stop3-report`; ledger entries D-94, D-95, D-96, D-98 (sections 1 to 6 and 8 to 10), D-99 and D-100 (sections 1 to 4, 6 and 7).
- **The ledger.** D-81 was located from the headings first (lines 3226 to 3281 on the day) and was never read, printed, searched or quoted. Every range read began at or after D-94's heading. D-97, D-98 section 7 and D-100 section 5 are verbatim transcriptions of plan text and code and were not read.
- **The step F draft was read in part:** its header, section 0 (the set changes), sections 4.15 to 4.17, decision D29, its list of stale statements and its end notes. The rest is proposed text that is now in the plan, which was read whole. Each decision's options were read from D-99, which gives every question as it was put.
- **Supporting files read as text:** `data/frozen/power_simulation.json` and its superseded copy (selected fields), `headline_set.csv` (header and first rows), `assignment_evidence_sites.csv` (one row), `design_support.json` (one block), `step_d_check_reference.json`, `step_d_check_reproduce.json`, `pipeline/analysis/ownership.csv` (rows for the headline hosts and their heaviest matches), and parts of `power_simulation.py`, `misdating.py`, `inference_check.py`, `inference_comparison.py`, `ownership.py` and `pass_c_exact.py`. For the two assessments, the files the handover names.
- **Commands used, all reading:** the handover's heading listing; `git show 90c722a -- tests/test_power_simulation.py`; `git log` of commit ids and dates for six named files, none of them the ledger; `shasum` of four named files outside every barred folder; `grep`, `sed` and `awk` on named files.
- **Not opened:** D-81, `docs/prior-work-detail.md`, `data/blind`, `data/interim/availability`, `data/interim/water/pilot`, `docs/tariff-check.md`, any tariff, rate case, resource plan or utility report. No web search and no fetch.
- **One thing the session could not avoid.** The project memory's index of one-line summaries is loaded into a session's context automatically. The note itself was not opened. Two of its lines bear on this study: one repeats facts that are in the handover, and one repeats Joe's remark about which effect size matters, which is also in D-98 section 4.
- **A limit on every answer.** Entries before D-94 were outside the range given. Where a question turns on an earlier entry (D-26, D-46, D-49, D-58, D-59, D-65, D-82, D-83), the answer rests on the plan's own statement of it and says so.

**The three classes** are Joe's. Where the record itself shows the class (the plan's own requirement, a ruling of his, or a contradiction inside the plan), the finding is placed without comment. Where it does not, the finding carries the words "referee's reading" and the reason, so that he can move it.

---

# Part 1. The twelve answers

## 1. The estimand and the set

**Found.** The headline number is about seven named utilities, each with its first crossing year (plan, "The set on the design as it stands"). The reason each of the other 34 cohort utilities is out is on file, utility by utility, in `data/frozen/headline_set.csv` (`why_not_in_the_headline_set`). The plan itself names only the ten that are unsettled on assignment and Umatilla. The one table that sorts all 34 by kind of reason is in the Stop 3 report, section 4, and it describes the design before Joe's Stop 3 answers (Arizona Public Service is in its "ceiling only" row and Umatilla is not in it).

**Found.** The estimand paragraph speaks of "utilities that became data center hosts in 2011 to 2022" and the sentence that must follow every headline says "It covers [N] utilities in [S] states that first reached 2% data center load in 2011 to 2022". Neither says that N is 7 of 41, or that the 7 are the ones whose serving utility, dates and enumeration could be settled.

**Inferred: three grounds of exclusion that could correlate with the outcome and that the plan does not name as such.**

1. *The enumeration ceiling removes the largest and most complicated buildouts.* Umatilla is out because five rows multiply its histories to 99,574,272 a case (plan, "Five Oregon rows"; D-98 section 8). The number of configurations grows with the number of sites and the width of their date intervals. Both are features of how much data center load arrived and kept arriving, which is the treatment's intensity after the event year.
2. *The assignment screen removes hosts where territories overlap.* Of the ten hosts unsettled on assignment, nine are municipal systems or cooperatives by their names (plan, same paragraph). The headline set is four investor-owned, two public and one cooperative. The two papers the plan reconciles first disagree precisely on whether the effect sits at investor-owned or at public and cooperative utilities (plan, rows M and U). I am uncertain about the ownership mix of all 41: I read it for the first rows of `headline_set.csv` only.
3. *A utility whose own count of its data center load fixes its first crossing is not set aside for an unverified load history* (plan, headline-set rule 2, D-34). A utility publishes such a count when the load matters to its planning. I am uncertain whether any of the seven is in on this ground; the documents read do not say.

None of these biases the comparison for the seven. Each changes which hosts the average is over, in a direction that could matter, and the plan's sentences do not tell the reader so.

**Found, by arithmetic from the plan's cohort years.** Four of the seven have headline years inside 2021 to 2023 (Arizona Public Service 2022 and 2023; Omaha and Public Service of New Mexico 2021 and 2022; Walton 2023 and 2024). The exercise that drops 2021 to 2023 (E3) therefore leaves three hosts: Sierra Pacific, Garland and PacifiCorp in Utah.

**Inferred from the plan's region definitions and the hosts' states.** No headline host is in PJM, MISO, NYISO, ISO-NE or California. I did not read the file's region field for all seven.

**Uncertain.** The future-host criterion is said to make every design result provisional, but the plan does not say how it reaches the headline design (answer 9, and finding C2).

## 2. Unresolved evidence carried as exclusion

**The estimate.** Found: a host whose place could change is on neither side, and a comparison utility must be under 0.5% in every admissible history (plan, "Comparison utilities", rule 2). So the withholding does not put a doubtful host among the comparisons. Inferred: for the seven, the withholding does not bias the difference. It trades variance for a smaller risk of misdating. The simulation shows both sides of that trade: the 36-utility set has a half-width of 3.11% against 6.65%, and with start years redrawn it recovers 78% of a planted 5% where the headline set recovers 98% (D-98 section 10; `power_simulation.json`).

**The range.** Found: the range is conditional on the set. It carries no uncertainty about which hosts belong in it. The sets reported beside the headline (17 with the unsettled hosts put back, 41 as built) carry that uncertainty descriptively and decide nothing (plan, "Reported beside the headline every time").

**The description of coverage.** This is where the treatment costs most. The rule is one-sided: a utility is withheld wherever its place *could* change, including under a bounding assumption (four Oregon rows taken as at full load from 2001) and under a count too large to enumerate. Joe's own words on this are in the plan: "A run without Umatilla may describe sensitivity, but it does not substitute for correctly implementing the dating rule." The headline is, for now, a run without Umatilla.

**What the write-up should say** (the wording is his): that the estimate covers 7 of the 41 utilities the inventory shows crossing in those years; that the other 34 are left out because a serving utility, a start date or a load history could not be settled, or because the possible histories were too many to check, and not because they were found not to be hosts; that the utilities left out include the largest buildouts; and that the set with all of them is shown beside it with what it could detect.

## 3. Stopping rules closed with avenues unpursued

**Found: what the headline claim rests on that is recorded as unpursued or not done.**

- *The comparison side.* 433 questions were never looked up and 72 in part (D-95 section 4). The plan turns this into a stated condition on every headline: "Our findings are conditional on those omissions". That dependence is disclosed.
- *Rows with no size.* 66 year-built rows have no size and "carry no load in any history" (plan, "Year-built rows"); the closing register counts 66 capacity-coverage rows as never examined (Stop 2 statement, section 2). I am uncertain whether those are the same 66. The two sites with no start year are treated as "unknown, not zero" and every utility they reach is carried as unsettled (D-96 item 2). A row with no size is treated as zero. The documents read do not show whether any of the 42 comparison units in the headline design is the assigned or candidate utility of an unsized row.
- *The conflict test was applied unevenly.* "The national compilation was queried for some records and not for others, so the test has not been applied evenly across the 73. Not repaired: a stated limitation" (Stop 2 statement, section 6). Assignments on headline hosts rest on layer records (the eight Omaha records, D-94). Which headline sites were never checked against the compilation is not in the documents read.
- *A site in one territory outside ERCOT is taken as resolved,* "which is an assumption" (plan, headline-set rule 3). How many of the headline hosts' sites are resolved that way and not by a page naming the utility is not stated in the plan.
- *The NSA site's location.* Joe ruled the NSA point (`bi:937-0`) "explicitly uncorrected and unresolved on location" and not to be treated as verified (D-96). `data/frozen/assignment_evidence_sites.csv` shows that row on PacifiCorp in Utah, a headline host, as a determining site carrying 0.84 of the threshold in the crossing year, placed "verified_by_hand", with two candidate territories. I am uncertain whether the hand verification rests on the point or on a page that names the utility; the documents read do not say. The plan states the point is unresolved and does not say that a headline host's first crossing rests on that row.
- *Eight provisional rows* were flagged in the step D design note "to check against D-66 section 4" (their intervals reach below the year built). The documents read hold no record that the check was made.
- *Statements carried into the plan unchecked,* by the session's own account (D-100 section 4): that the joint-check files were rerun on the rebuilt inventory, the count of 59 systems, and the scope of the labelled simulation run.

**Not dependent, by construction.** A headline host whose reference turns on a provisional year-built convention is undefined and out, so the unopened year-built records cannot move a headline host's place (plan, "Year-built rows"). They can still bear on a comparison utility's 0.5% test.

**What the write-up would have to say.** That the check of each host's place covers "modeled loads and enumerated uncertainties only" (Stop 2 statement, section 6); and the counts above, once taken from the quantity files. No search is needed for any of them.

## 4. The inference comparison

**Are the rules fixed tightly enough?** Found: seeds, counts, the 241 threshold, the tie rules, the budget ladder, the 11% standard and the three reporting outcomes were written before the runs they govern, with one disclosed exception (outcome 3, ruled in D-99 after both runs, neither of which reached it). I found no place where a choice among candidates is left to be made after a result.

**Paths the rules do not intend.**

1. *The rerun rule permits a rerun after every pre-freeze design correction* (D-99, "The rerun rule"), and at least one design change is known to be coming. The rule forbids result-driven changes and repeated attempts. It does not require that all design-changing work be finished first and the comparison run once. The margin is thin: the highest upper bound is 10.25% against 11% (D-98 section 10). The people implementing the remaining items will know that.
2. *"Validated" is established on one design.* Stage 2 ran on the headline set at 2%. The plan then reports "its range under the selected procedure" for the companion sets, the 5% sets, E1 to E7, every deletion and the later-start runs. Joe ruled that the validation does not transfer to the subgroup contrasts (D-99, D28). The plan says nothing of the kind for the other runs. The simulation file shows the procedure behaving differently on small sets: on the five-host set at 5% the early-years test failed none of 2,000 flat histories on never-host prices, and the range covered zero in 90.2% (D-98 section 10; `power_simulation.json`). E3 will run on three hosts.
3. *The second number's range.* The plan still says "clustered by state with the same bootstrap" (plan, "The second number"). The step F draft left that line unchanged (section 4.15). "The same bootstrap" is now the bootstrap as built, which the stage 1 screen excluded on the headline design in both runs. The Stop 3 report says the second number's range "is not under the validated procedure, which the comparison did not cover". The plan does not say which procedure gives that range in the analysis or how it is labelled.
4. *A rule adopted and, by the record, not fully applied.* E1.5 says `inference_check._chunk` "is changed before step E runs". D-98 section 3 lists as a carried limitation that it "still draws from one generator for job U". I could not establish from the documents what job U is or whether it is part of stage 1 or stage 2.

**Are the made-up processes an adequate stress?** Found: thirteen processes cover unequal variances, more and less persistence, rate-case steps, ownership shocks, heavy noise where the weight is, company and supplier shocks, unequal regional exposure, own linear trends, and fuel shocks linear and not linear in the gas share (`inference_check.py`, `GRID`; `inference_comparison.py`). Every component is drawn with mean zero.

**What they do not cover.** A difference in price paths between utilities like the hosts and their matches that is systematic and not random. The one check on real prices speaks to this, and its result is on file but not in any report read. With nothing planted, on never-host utilities' prices, the mean estimate (the code's own print line calls it "drift") is:

| Set | Mean estimate, nothing planted | Its standard deviation across draws | Range covers zero | Flat history fails the early-years test |
|---|---|---|---|---|
| Headline, 2% (7) | -0.15% | 3.07% | 95.0% | 3.3% |
| With the ten-year case, 2% (6) | -1.19% | 2.99% | 94.0% | 1.6% |
| Every cohort utility, 2% (36) | -0.38% | not read | 97.6% | 9.8% |
| Headline, 5% (5) | -1.47% | 4.89% | 90.2% | 0.0% |
| Every cohort utility, 5% (30) | -0.70% | not read | 92.0% | 5.2% |
| Side run, own-state comparisons, headline | +0.69% | not read | 92.5% | 5.4% |

For the headline set the mean is small. For the six hosts common to both designs it is -1.19%, which is 0.4 of the estimate's standard deviation and more than half of the 2% reference line. Inferred: stand-ins are never-host utilities from the host's own state, so this is a state-level difference from the regional size matches that the design does not absorb. The plan knows the phenomenon (it cites D-32 for a gap of "about two and a half points" between own-state and regional comparisons) and does not carry these figures.

**Also found.** The simulation's own size check on made-up flat prices measured the range missing zero in 11.6% of 1,000 datasets on the headline set (D-98 section 10 lists it as an open point). It is not the validation and it is inside what 1,000 draws allow around 10%. **Not found in the documents read:** how often the early-years test catches a drift of 1% a year under CR2 on the design as it stands, and G12's mean estimate with nothing planted. The plan promises both.

## 5. Numerical failures and incomplete searches

**Found.** In calibration a failure stays in the denominator as a miss and a rejection; in power it counts as no detection; for ranking an incomplete or failed side is infinitely wide and stays in the median; coverage is decided by the test at the true value and that test's own failure is never coverage (plan, "Numerical failures and endpoints"; step E rules, sections 3 and 4). Every run on file has zero failures and zero incomplete searches (D-98 section 10).

**Inferred.** A procedure cannot look better by failing under these rules. In ranking, a minority of infinite widths does not move a median, but it does not help it either: the same datasets would sit in the upper tail if they had completed. A tie between B and C goes to the lower share of incomplete and failed ranges.

**Gaps, none of which changes a result on file.**

- The rules "do not say how small a standard error is zero"; one test is marked an expected failure for it (D-98 sections 1 and 3).
- The plan says what an incomplete side reads in the analysis. It does not say what is printed if the selected procedure itself fails numerically on the real data, for the headline or for a deletion.
- E7 reports percentiles of point estimates across 200 draws. The plan says a host can drop out of a draw. It does not say that a draw whose fit cannot be computed is counted and reported, and that is the one place where failing could tighten a reported spread.
- "Search incomplete" for candidate B includes a p-value that is not monotone (D-98 section 3). It matters only if a rerun selects B.

## 6. The controls

**The fuel control's assumption.** Found: it is stated in one sentence a reader can evaluate, with the proxy named as a proxy and the reason for the change on the record (plan, "Fuel-mix control"). The share is fixed at 2008 to 2010, so no later value can be chosen.

**Extrapolation.** Found: on the design as it stands the control does nothing for Garland (all ten matches are in Texas) and extrapolates for Omaha (0.014 against 0.049 to 0.491) and Sierra Pacific (0.681 against 0.101 to 0.469) (D-98 section 9). So for three of seven hosts it either cannot act or acts outside its support. The plan's treatment is to name each such host and to report two labelled sensitivities (the categorical form, and no fuel control). Inferred: that is sufficient as disclosure and thin as protection. Omaha's headline years are 2021 and 2022, when the calendar-year slope on gas share is likely to be at its largest; that last clause is my inference from general knowledge of gas prices and not from the documents.

**The non-linear process.** Found: G12's mean with nothing planted "is reported beside the rates and read separately, since a mean away from zero there is a failure of the adjustment". No size is given at which it counts as away from zero, and no consequence follows except that the specification is not changed. The figure itself is not in the documents read.

**Fully absorbed hosts.** Found: the rank test precedes any inversion, absorbed hosts are named for every design, and none is absorbed on the design as it stands. Not found: whether a host with zero weight still counts in the "[N] utilities" of the headline sentence. The deletion runs say the estimate is "over the rest"; the headline sentence does not.

**Concentration.** Found: Arizona Public Service and Public Service of New Mexico share all ten matches, and El Paso Electric's two units carry 0.43 of the comparison side's net weight (D-98 section 9). `ownership.csv` shows El Paso Electric changed owner on 2020-07-29, inside both hosts' windows and just before their headline years. Leave-one-company-out is specified and will show what that company moves. The plan forbids calling ten matches ten independent comparisons. That is the record's own limitation and it is stated.

## 7. Ownership and suppliers

**Does "unknown, not independent" protect the comparison?** Found: an investor-owned unit with no row is not eligible for an investor-owned host; each of the four investor-owned hosts loses the same five candidates for it (D-98 section 9). `design_support.json` shows PacifiCorp's units excluded from Sierra Pacific's pool as "same ultimate parent as the host in a year of its window", which is the rule working on a documented spell.

**What it costs.** Five candidates from each investor-owned host's pool, so matches further in size, by an amount the documents do not give. And two headline hosts whose own parent is known only today (Arizona Public Service, Public Service of New Mexico), kept and named.

**Where the distinction between documented and assumed is carried, and where it stops.**

- Carried: into the exclusion (both kinds enter, labelled), into the count of selected comparisons that rest on an assumed spell (two, Black Hills Colorado and Idaho Power, for all four investor-owned hosts; D-99 section 3), into the host-side sensitivity, and into the wording "eligible under the ownership convention".
- Not carried: *partial coverage on the comparison side.* The plan says 25 units "have a row for some spells and none for others", and "A missing row means ownership is unknown". The code bars a comparison only if it "has no row covering any year of the window" (`ownership.py`, line 112). So a comparison with a row for part of a host's window is eligible, and its uncovered years are treated as unaffiliated. A host in the same position is called unresolved. The plan does not state this, and no count of selected comparisons with an uncovered window year is on file.
- Not carried: *the second estimator.* Callaway and Sant'Anna's never-treated group is "the comparison-eligible units of the main design". Ownership and full-window usability are defined against one host's window. For a pooled comparison group the plan does not say against which.

**Suppliers.** Found: 141 units are unknown in every year; Omaha and Public Service of New Mexico are unknown in every year and Sierra Pacific in every year but 2017 (Stop 3 report, section 5). A pair is "unknown" if either side is unknown in any window year. So for three of seven hosts the exercise can detect nothing, and its result for them is a count of unknown pairs. Joe's qualification is in the plan: a negative finding means "no shared-supplier link detected in this table". The write-up should give the share of host and comparison pairs that could be tested at all.

## 8. Availability

**Found.** The flag requires residential sales present, the customer floor met, revenue present where sales are positive, a supply price where there are delivery-only customers, a price above zero, and no EIA imputation (plan, "Missing data"). Joe authorized its use in words: "This explicitly authorizes use of the outcome-derived flag" (D-94).

**Does using it before the freeze risk selecting on the outcome?** Inferred: not on its level. Every condition is about presence or sign, the same rule applies to hosts and comparisons, and it was applied before matching. It is a complete-case rule, and missingness can move with price paths in three ways the plan partly names: utilities that moved to EIA's short form after 2019 are small ones; a missing supply price arises in retail-choice states; and merged units are blended. None of these is tuned by anyone, and the rerun rule covers any change to the flag.

**Is the disclosure enough?** Nearly. The plan says the flag was "written without any price being displayed". It does not say in so many words that the flag is computed from the outcome's own revenue and sales fields, that this was authorized as an exception to D-58 rule 6.4's source, or how many hosts and comparisons it removes. The count is promised "at the freeze" in the text and is not among the nineteen required items. The audit behind the flag (D-82, D-83) is before D-94 and its record is protected; I cannot assess it.

## 9. Exercises defined but not yet run

**Precise enough to build without a further choice:** E1 (windows, reference, hosts left out, the ownership window), E2's fake date, E3's full-window rule and the 2024 to 2025 endpoint, E4(b), E6's list, E7's rows, draws, seed and ramp, the later-start shifts, the six trend illustrations, leave-one-out, the unresolved-ownership sensitivity, and the supplier selection as coded.

**Still need a choice, and so could be shaped after the fact.**

1. *E3, "If insufficient support remains, it is reported as not estimable."* No definition. On the headline set E3 is three hosts.
2. *E4(a)* carries a sentence in the first person: "I am uncertain whether the slow path is among the capacity cases of the place test". That is an open question about the code inside plan text. It can be settled by reading the code.
3. *E5.* An undefined or fallback factor is "flagged". Whether such a state is dropped or kept is not said.
4. *E7.* "Reproduced" is not defined (the same year, or within one). The headline sentence that uses it, "the recorded first crossing matched in X% of redraws for this set", needs one figure for a set and the plan defines one per host. Holding a redraw at a sourced bound is the session's choice (D-100 section 4). The sign convention of the errors is still to be read from the code.
5. *The four conditions.* "Load share of 10% or more" is not dated. "Retail-choice state" has no source or year. "Past utilization" has no years, no data source and no statement of which set its median is over. These may be fixed in D-26, which was outside my range; the plan does not carry them.
6. *Callaway and Sant'Anna.* "A fixed seed" has no value. The gas share enters "after a test on made-up data" with no pass criterion. The never-treated group is not defined against the pairwise rules (answer 7).
7. *C5.* Its verdict turns on a "90% interval" whose variance estimator is not named.
8. *The exclusion below five.* Whether it extends from E3, E5 and E6 to the supplier exercise and leave-one-out "is not ruled" (D-100 section 4).
9. *The supplier exercise's "known omissions"* are pairs where "existing evidence identifies" a link the table cannot hold. That list is a judgement and is not fixed before outcomes.
10. *Smaller.* The longer horizon does not say whether comparisons are rematched for thirteen usable years. "Affiliates readmitted" does not say whether the no-row bar stays. "Future hosts as a second comparison group" does not say whether they join the pool or form a second estimate. The 1% run does not say on which set, and the place test exists at 2% and 5% only.
11. *The regional layer* promises an estimate of pass-through "from state-month data" with no specification.

**The future-host criterion.** The plan says it is "in force and not yet implemented" and that implementing it "can remove comparison utilities, which changes matches and the design's fingerprint". But comparison rule 2 already requires a share "under 0.5% in every year in every admissible history", and a utility that first crosses 2% in 2023 or later cannot meet that. Read as written, the criterion can only add future hosts to a side run and define E2's sample; it cannot remove anyone from the headline design. Either rule 2 as built is narrower than rule 2 as written, or the provisional label rests on something the plan does not state. I could not tell which from the plan, the step F draft (D29, section 4.16) or D-95.

**The second number's two alternatives** have no scenario. The plan says so and lists them as required before the freeze.

## 10. What the piece may say

**Found: the evidence the sentences must fit.** Seven hosts; a 90% range of about plus or minus 6.65% with nothing to find; a planted 5% detected in a quarter of draws; the smallest increase detected four times in five about 10% (D-98 section 10).

**Sentences the plan permits that the evidence would support only with a companion.**

- *"When the range excludes zero ... about X% higher."* On this set a range excludes zero only when the estimate is beyond roughly 6.65%. If the true difference were 5%, every estimate that cleared that bar would overstate it. The plan requires three assumptions and a coverage sentence beside the headline and nothing about this.
- *"That range includes zero."* The sentence about what the set could detect is conditional ("Where the write-up says what the set could detect"). With this precision an includes-zero result cannot rule out 5%, and a reader will take it as a null unless the detectable-effect sentence is next to it every time.
- *The reconciliation rows.* A row is "reproduced" if our estimate has the paper's sign and falls inside the paper's band. Our own uncertainty plays no part. The plan permits "On an open facility list the closest published design does not return its published answer" when our range may contain theirs.
- *C5, "the instrument passes this check"* where the interval includes zero and the point is under half, in a test the plan itself says "may have low power".
- *"With start years as uncertain as they are."* `misdating.py` redraws only rows whose basis is `first_generator_permit_plus_lag`. Rows on any other basis are not redrawn (year-built rows, interval rows such as the five Oregon rows, sourced rows), and a host whose crossing rests on its own count has no error. For the headline set 94.4% of drawn errors are zero. The label promises more than is modeled.

**A sentence the plan neither permits nor forbids and probably should allow.** A plain statement of whether the range includes an increase of 5%. "Any increase is under about U%" is rightly forbidden. For water Joe required exactly such a statement (W-8). D-98 keeps "ruling out 5% after an estimate" as one of two goals.

**Smaller.** The outcome 1 template has one X% for a rate measured in thirteen processes. The reference line is 2%, and Joe's later remark was that 5% "is really where i think people notice" (D-98 section 4); the session rightly took that as a view and not an instruction, and the two now sit unreconciled.

**Nothing forbidden that should be allowed** beyond the 5% statement. The ban on causal verbs in the headline is right for this design.

## 11. Disclosures

**Described with more certainty than the record supports.**

- *"No host utility's price has been read."* The plan's header, the Stop 3 report and the handover say this without qualification. The D-96 addendum records that twelve fetched filings were a utility's own or combined annual or quarterly report, that each went through a script showing 250 characters either side of an ownership fragment with money and rate figures masked, that two figures passed the mask, that the windows were read by an agent and their raw output deleted, and that "Whether a window from a utility's own report carried anything beyond the ownership sentence has not been established either way." Joe's instruction was: "do not claim certainty that nothing beyond ownership was exposed." The ledger keeps to that. The plan's sentence does not.
- *"A headline host's among them"* (Stop 3 report, section 7). By my reading of the D-96 table against the set as it stands, three headline hosts are among the twelve: Arizona Public Service (lead01, Pinnacle West's combined 10-K for 2025), Public Service of New Mexico (lead62, a combined 10-Q of 2005) and PacifiCorp (lead54, its own 10-K of 2006). Arizona Public Service entered the headline set after the disclosure was written, and its report is the most recent of the twelve.
- *The test "is repaired with the rerun"* (D-98 section 8). The files show otherwise; see assessment 1.

**Described with the right amount of certainty.** The EIA archive an agent downloaded (D-95 section 6: what the agent reports, what the folder showed, and no more); the correction of 46 to 44; the readings adopted after the simulation's results were available; the support thresholds chosen after the counts were seen; the ceiling amended "with its design consequences known"; outcome 3 written after both runs; the two step E runs "never described as independent confirmations"; the access list "not verified" after the move; water's obstacles "as they were met under one collection method".

**A pattern the disclosures show and the plan does not answer.** Twice in session 17 frozen outputs were found to have been "generated by code older than that commit" (D-98 section 8). `step_d_check_reproduce.json` still records a corrections-file hash (`b30f25c7…`) that is not the current file's (`724d08ce…`). Three plan statements were carried over unchecked (D-100 section 4). The plan says its lists "are frozen with this file" and has no step that regenerates every quantity file at the freeze commit and confirms it.

**Not assessable from what I was given.** The scratch-copy incident of 2026-11-16 (D-65) and the availability audit (D-82, D-83).

## 12. Anything else

- **Timestamp.** The plan's discipline is that it is committed before the regression. The repository is private and a commit's date is set by its author. A skeptical reader has no way to confirm the order. A hash of the frozen file lodged anywhere public and dated by a third party would answer it.
- **The placebo result on real prices** (answer 4) is the first thing a reviewer of a difference-in-differences design would ask for, and it is on file and unreported.
- **Tariff collection comes after the main estimate** in the order of unblinding, and "how it is to be done is open" (required item 17). Water showed the access wall. I did not open `docs/tariff-check.md`, so I cannot say whether it fixes a search budget and a rule for missing coverage. If it does not, effort on that check would be chosen with the headline known.
- **Matching is on size and region only.** Ownership type is a tested condition and not a matching variable, so an investor-owned host can be compared with public systems whose rates move by a different process.
- **The outcome list** has residential usage, bill and customer counts. A reviewer would ask for commercial and industrial revenue per kWh beside them, described and not tested, since the cost-shift question is about who pays.
- **Who is asking.** The plan states the author's prior. It does not state who paid for the work or whether the firm has clients with a stake.
- **Scale of the claim.** One host in each of seven states. The plan's own sentence stands: an average over these hosts cannot establish "mostly no".

---

# Part 2. The findings, consolidated

Each finding once, with the questions that raised it. "A1" and "A2" are the two assessments in part 3.

## Necessary corrections

| # | Finding | From | Why this class |
|---|---|---|---|
| C1 | **The second number's inference is stale text.** "The same bootstrap" now names a procedure the stage 1 screen excluded on the headline design. The plan must say which procedure gives the second number's range and how the range is labelled. | 4, 9, 10 | A contradiction inside the plan |
| C2 | **The future-host criterion's reach is not stated.** The plan says implementing it can remove comparison utilities and makes every design result provisional. Comparison rule 2 as written already excludes any future host. The plan must say what in the headline design the criterion changes, or that it changes nothing there. | 1, 4, 9 | The plan's first required item cannot be built from its text |
| C3 | **The exact attribution on the five Oregon entries.** The plan requires a rerun or "a logged explanation that the change cannot affect it". The explanation on file does not cover the attribution's own output, and a rerun needs a change to the driver. | 3, 11, A2 | The plan's own required item 12 |
| C4 | **The blinding statement and the lapse.** "No host utility's price has been read" is unqualified in the plan; the record says the point "has not been established either way". The disclosure counts one headline host among the twelve reports; on the set as it stands there are three. | 11 | Joe's instruction in the D-96 addendum |
| C5 | **E4(a) carries an open question about the code** in the first person. Settle it by reading the code and state the answer. | 9 | A plan cannot be frozen with an unresolved fact about what an exercise does |
| C6 | **Definitions that still need a choice:** E3's "insufficient support"; E5's undefined or fallback states; E7's "reproduced", its set-level figure and its failed draws; the four conditions' variables; Callaway and Sant'Anna's seed, test criterion and comparison group; C5's interval; whether the exclusion below five extends to two more runs; the supplier exercise's list of known omissions; partial ownership coverage on the comparison side; the longer horizon, affiliates readmitted, future hosts as a second group and the 1% run; the regional layer's pass-through estimate. | 5, 7, 9, 12 | Referee's reading. Question 9's own standard; one item is recorded as "not ruled" (D-100 section 4) |
| C7 | **What "validated" covers.** The validation is on the headline design at 2%. Every other range reported under the selected procedure needs a sentence saying the validation was not made on its design. The file shows the procedure behaves differently on five hosts. | 4, 9, 10 | Referee's reading. Joe ruled this for the subgroup contrasts (D-99, D28); the record is silent for the rest |
| C8 | **Frozen files against the code at the freeze.** Regenerate every quantity-side frozen file at the freeze commit and confirm it; check the three statements carried over unchecked; regenerate the access list after the move; take the counts answer 3 names. | 3, 11 | Referee's reading. The plan freezes these files with itself, and the record shows stale outputs twice |

## Accepted limitations

The record states each; the plan can carry it as written. Where a sentence is owed to the reader, it is noted.

| # | Limitation | From | Owed in the write-up |
|---|---|---|---|
| L1 | The headline is 7 of 41, chosen by what could be verified and enumerated; plus or minus 6.65%; about 10% detectable. | 1, 2, 10 | That it is 7 of 41, why the rest are out by kind, that a ceiling is a computational reason, and that the largest buildouts are among those left out |
| L2 | The comparison side is conditional on omissions; 433 questions never looked up; unsized rows carry no load; the conflict test was applied unevenly; year-built records unopened; single-territory sites taken as resolved. | 3 | That the place check covers modeled loads and enumerated uncertainties only |
| L3 | PacifiCorp in Utah's first crossing rests on a site (`bi:937-0`, 0.84 of the threshold) whose location is on record as unresolved. | 3 | That a headline host is the one affected. I am uncertain whether its assignment depends on the point |
| L4 | Two headline hosts with unresolved ownership; two comparisons on assumed spells; 33 units with no row. | 7 | As the plan has it |
| L5 | Suppliers unknown for 141 units; the exercise can test nothing for three of seven hosts. | 7 | The share of pairs that could be tested |
| L6 | El Paso Electric's two units carry 0.43 of the comparison weight; two hosts share all ten matches. | 6, 12 | As the plan has it |
| L7 | The fuel control does nothing for Garland and extrapolates for Omaha and Sierra Pacific. | 6 | As the plan has it |
| L8 | Eligibility is read from a flag computed from the outcome's inputs, by Joe's authorization. | 8 | That it is outcome-derived, and the counts it removes |
| L9 | The validation speaks only to thirteen made-up processes, all mean zero; the margin is thin. | 4 | As the plan has it |
| L10 | The second number's two alternatives have no scenario. | 9 | On the plan's required list |
| L11 | The tariff check will meet the access wall; water is closed. | 12 | As the plan has it |
| L12 | The lapses the record describes correctly (answer 11's second list); two incidents this read could not assess. | 11 | None further |

## Optional improvements

The freeze does not depend on any of these.

| # | Improvement | From | Note |
|---|---|---|---|
| O1 | Report the mean estimate with nothing planted and the coverage, on never-host prices, beside every detectable-effect figure: -0.15% for the headline set, -1.19% and -1.47% for the six- and five-host sets. | 4, 10, 12 | Referee's reading: for the companion sets this is close to necessary, since their ranges are shown beside the headline every time |
| O2 | Headline wording: a sentence on overstatement when the range excludes zero; the detectable-effect sentence unconditional when it includes zero; a permitted plain statement on 5%. | 10 | |
| O3 | Reconciliation wording: our range beside each band; "did not detect" for C5 in place of "passes". | 10 | |
| O4 | Finish every design-changing item, then run the comparison, validation and simulation once. | 4 | |
| O5 | The restated test: check the exact cost-free cases, add a direct check that date errors were applied, and correct the ledger's description. | 11, A1 | |
| O6 | Name "start years as uncertain as they are" for what it models: permit-dated rows redrawn from measured permit errors. | 10, A1 | |
| O7 | Fix how small a standard error is zero; say what is printed if the selected procedure fails on the real data. | 5 | |
| O8 | State the set's regions and that four of seven hosts have headline years in 2021 to 2023. | 1, 12 | |
| O9 | Lodge a hash of the frozen plan somewhere public and dated by a third party. | 12 | |
| O10 | Reconcile the 2% reference line with the later remark about 5%. | 10 | His alone |
| O11 | Enter the figures the plan promises and the record does not yet hold: the drift detection rate under CR2, G12's mean with nothing planted, what job U is. One rate for thirteen processes in the outcome 1 sentence. | 4, 6 | |
| O12 | A sentence on funding and clients; commercial and industrial price beside the other outcomes, described only. | 12 | |

---

# Part 3. The two documentary assessments

## A1. The restated simulation-test assertions

**What was changed** (`git show 90c722a -- tests/test_power_simulation.py`).

1. The test now requires the report to name the selected procedure, its range text, both stage 2 verdicts as "passed", and a replication count of none under CR2. Before, it required `bootstrap_replications == 999`.
2. For every set it required the share of a planted 5% recovered with misdated start years to be strictly below one. Now it requires "no more than with exact start years", and strictly below one only where `within_1_year` for the set is under 1.0.
3. It required the smallest increase detected with misdated start years to be strictly above the figure with exact ones. Now strictly above only under the same condition; otherwise "no less than".
4. A second test of the labelled run for the bootstrap as built was added, which skips while that file does not exist.

**What the permitted documents establish.**

- *The restated checks hold on both committed reports, and the old ones fail on both for one set.* The set with the ten-year case shows, in the current file and in the superseded one, a recovered share of 1.0 and 11.37 against 11.37, with 98.1% of drawn errors exact, all within one year and none two or more years earlier. Every other set shows a share below one. So the old strict checks were false of the earlier design's report as well as the current one.
- *The agent's explanation is correct as far as it goes.* `planted_path` adds nothing before the true event year and the full effect from two years after it. The reference year is three years before the recorded crossing and the headline is years two and three after it. A true crossing one year earlier than recorded leaves the reference untouched and the headline years at full effect, so it costs nothing.
- *The test was not fitted to the rerun's numbers.* It was changed at 90c722a (20:25); the rerun's file was committed at ec34007 (22:03). It was fitted to a property the earlier report already had.
- *The ledger's sentence is not what happened.* D-98 section 8 says the failing test "describes the committed simulation and is repaired with the rerun". The report under CR2 was first committed at cc02b62 (19:16) with `"bootstrap_replications": null`; the test as it then stood asserted 999. So, by inference from the two texts and not from a run, the test failed at its first assertion from cc02b62 until 90c722a. By the commit times that hour includes Joe's Stop 3 answers, which were applied at 307c3ca (20:11); I am uncertain of the exact time the report reached him. D-98 section 2 says the session "ran subsets after that and not the whole suite". The repair was a change to the test, needed whatever the rerun showed.
- *The same code path serves every set* (the function that runs one set, `power_simulation.py` lines 1592 to 1649; `_host_chunk` calls `draw_errors` for each draw). I saw no branch by set in the lines read; I did not read `one_draw` or `assemble` whole.

**What they do not establish.**

- *Whether the date errors were applied in the ten-year set.* Identical figures to three decimals are what a cost-free error would give. They are also what unapplied errors would give. For that set the restated test can no longer tell the two apart, and that was the one thing the strict checks guarded. The file shows that errors were drawn for the set (1.9% not exact), and the other sets, through the same code, show a loss. That is evidence and not proof.
- *Whether the condition is the right one.* By `planted_path` the cost-free errors are zero, one year earlier and two years earlier. An error of one year later costs a sixth of the effect; three or more years earlier contaminates the reference year. The test's condition is "all within one year". It is too loose on one side: a set whose only errors are one year later passes the weaker check though its loss is real. The five-host set at 5% looks like such a case in the current file: every error within one year as rounded, none two or more years earlier, and a share of 0.998, so by inference some of its errors are one year later. It is too strict on the other: a set whose only larger errors are two years earlier would fail a strict check with nothing wrong. And `within_1_year` is rounded to three decimals before it is compared with 1.0.
- *The split of one-year errors by sign.* The report records the share two or more years earlier and not the share one year later.

**The specific uncertainty that remains.** No figure in the committed report depends on the test, and none is shown wrong by anything read. What is not established is that the simulation applies date errors correctly in a set where all errors are small, because the only check of that was removed for exactly those sets. Establishing it needs either a run or a direct assertion on invented inputs, and neither was made here.

**A related point for the write-up.** "As uncertain as they are" means permit-dated rows redrawn from measured permit errors (answer 10). For the headline set that is 5.6% of host draws. The near-equality of 9.95% and 10.09% says the headline set is assumed well dated more than it says misdating is harmless.

**Class.** The record flags the change "for review" and shows none since. This assessment is a documentary review and not a run. Referee's reading: it does not block the freeze; the tightening is O5.

## A2. The exact attribution not rerun on the five Oregon entries

**What was changed and what was left undone.** At Stop 3 five `date` entries were added to `pass_c_corrections_s17.json` (61 to 66): `bi:820-0` with an early end of 2018 and a late end of 2019; `bi:823-0` and `bi:822-0` open below with a late end of 2019; `bi:819-0` and `bi:846-0` open below with a late end of 2022. Each has `never_is_possible: false` and a convention equal to its permit-based year. The attribution's CSV (`pass_c_exact_attribution.csv`) was last written at a715f0f, before those entries (`git log` of the file), and D-98 section 8 says the attribution was not rerun. Its JSON (`expansion-test-2026-11-18-s17.json`) has the hash the step D check recorded.

**What the permitted documents establish.**

- *The reference check was in fact made on the 66-entry file, and it is clean.* `step_d_check_reference.json` records the corrections file's hash as `724d08ce…`, which is the current file's, and reports no differences and nothing unexplained. So the rebuilt inventory with the five entries gives every utility the place and first crossing that the attribution on file gives as its reference. The record's sentence "The step D reference check is unaffected, because no load changed" is supported by a result and not only by an argument. The brief explains why (section 4): the reference takes each date question at its convention, and the five conventions are the years the inventory already carried.
- *The reference check is not the attribution.* The attribution's subject is which open questions can change a utility's outcome across their settings (brief, section 1). A `date` correction is a question whose settings are "every start year from its early end to its late end", with a start at or before 1999 as one setting (brief, section 2). The five entries add five questions with 2, 21, 21, 24 and 24 settings.
- *A rerun would change the attribution's result for Umatilla, and the change can be shown by arithmetic.* The product of those settings is 508,032. Before the entries Umatilla kept its place on 196 configurations a case (D-98 section 8). 508,032 times 196 is 99,574,272, exactly the count `timing.py` reports for Umatilla in each screen case; the looser reading's 903,168 is 4,608 times 196 in the same way. `timing.py` runs the attribution's own enumeration (step D design note, section 2), and the attribution's ceiling of 100,000 for each dependency component is unchanged (D-98 section 8). So, by inference and not from a run, the attribution would count Umatilla far over its ceiling, its method would become "conservative" under section 5 of the brief, and it would keep the conservative check's questions. The attribution on file shows it as it stood at Stop 2, where D-95 section 5 records "Umatilla keeps its place and keeps no question"; the CSV has no row for any of the five sites. So the output on file is known to misdescribe Umatilla for the corrections in force. "The change cannot affect it" is not true of the attribution's own output.
- *"It stops on its own count of hosts" is an obstacle and not an explanation.* `pass_c_exact.py` sets `HOSTS_EXPECTED = 26` and exits if the rows at 2% that are in the headline set, or out of it for ruling 4's reasons only, do not number 26. By the plan's counts they are now 7 and 10. The driver cannot run on the design as it stands without an edit, and `pass_c_exact.py` is among the files the step D check fingerprints.
- *The sets do not read the stale file.* Among the Python files under `pipeline` and `tests`, only `step_d_check.py` and `pass_c_exact.py` name the attribution's two output files. Set membership comes from `timing.py`, which ran on the 66-entry file and put Umatilla out.
- *Other Oregon utilities are, by the brief's rules, not reached.* A site's date reaches another utility only through the state's 2024 anchoring (brief, section 5). Every setting of the five has the row at full load by 2024 (the latest start is 2022 and the ramp is three years), and "never" is not possible. So the factor does not move with them.

**What they do not establish.**

- Which questions Umatilla would keep under the conservative method, and how many. That needs the run.
- Whether any of the five rows is also an unresolved assignment in the inventory. The corrections file has only a date entry for each, and the record says all five are on Umatilla. If one were unresolved, its new date settings would reach its other candidates. I am uncertain; the documents read do not show how `assignment.resolved` reads them.
- Whether anything still to be built will read the attribution's kept sets. The closing register is "generated ... from the attribution run on the corrections in force" (Stop 2 statement), so its 661 rows and the counts Joe closed on describe the 61-entry file and omit these five questions. The future-host criterion is to be built on "every admissible history the sets test"; whether its build will use the attribution or `timing.py` is not written anywhere I read.
- Whether editing the driver changes any fingerprint that step E's results carry. `pass_c_exact.py` is in the step D check's list; I did not read the step E fingerprint's file list.

**The specific uncertainty that remains.** The design is not shown to depend on the stale attribution, and the one consumer that was checked is clean. The attribution itself is out of date for one utility in a way the record does not say, and the record's two sentences do not amount to the explanation the plan requires. The consequence that cannot be bounded from documents is for anything built later on the attribution's kept questions or on the register's counts.

**Class.** C3, a necessary correction, because the plan's own item 12 requires either the rerun or the explanation and has neither.

---

# Corrections to this report, 2026-11-19 (after Joe's instruction of that day, D-101)

Joe received this report as advice. Its classes are the referee's and are not adopted wholesale. He named three statements in it to correct. They are corrected here and the text above is left as it was written, so the record shows both.

1. **The claim that the withholding does not bias the estimate was too strong.** Answer 1 says the three grounds of exclusion do not bias "the comparison for the seven", and answer 2 says that "for the seven, the withholding does not bias the difference". Neither is established. The rules that decide membership read the inventory through 2025 and evidence gathered long after each event year, so who is in the set depends in part on what happened after the event. Selection of that kind can be related to how prices moved, for the seven as well as for the 41. What can be said is narrower: the withholding keeps a doubtful host out of the comparison group, and whether it biases the estimate, for the seven or as a description of the cohort, is not known. The plan now says this ("What the headline set is not").
2. **The reassurance about availability was too strong.** Answer 8 infers that using the flag does not select on the outcome's level and that "none of these is tuned by anyone". The flag is computed from the outcome's own inputs, and requiring a full usable window is selection on a variable derived from them. That a price is present can move with a utility's price path. The report should have said that the selection may be related to the outcome and that nothing read establishes otherwise. The plan now says this ("What the flag is, said plainly").
3. **A simulated width was treated as a threshold.** Answer 10 says a range on this set "excludes zero only when the estimate is beyond roughly 6.65%" and reasons from that about overstatement and about what an includes-zero result could rule out; finding O2 repeats it. The 6.65% is the mean half-width across simulated draws on stand-in utilities. The range from the real data will have its own width. Nothing follows from a simulated width about what the real range will or will not exclude. Joe's rule, now in the plan: any statement about an increase of 5% is made from the actual interval, and it keeps apart a 5% difference in price, a 5% difference in the bill per customer, and the 5% load-share threshold.

**Four findings the correction pass settled, so that this report is not read as still asserting them.**

- *C2, the future-host criterion.* It does not reach the headline design. The headline comparison rule (under 0.5% in every panel year, in every admissible history) excludes every utility the criterion could admit; the criterion governs the side run and E2 only (D-26, D-29, D-86 list 1 item 11, D-90; `power_simulation.design`; `tests/test_future_host_scope_invented.py`).
- *L3, the NSA site.* The uncertainty stated there is resolved. The closing register records that "The site's verification rests on the statement on file", a report naming Rocky Mountain Power as the seller to the Utah Data Center, and the layers at the point are classed as a lead that verifies nothing. The unresolved point does not establish the assignment.
- *C5, E4(a).* The slow path is not among the place test's capacity cases. Headline-set rule 2 covers it through `buildout.py`, with each state's factor held as built.
- *A1, the cost-free errors.* The statement that errors of zero, one and two years earlier cost the headline nothing is exact where every stand-in carries the same error or the fit has no controls. With controls and differing errors it is nearly and not exactly so. An error of one year earlier also changes recorded event year 1, which the assessment did not say.
