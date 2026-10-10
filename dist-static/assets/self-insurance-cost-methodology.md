# The Price of Insuring Yourself: methodology and sources

Data snapshot 2026-10-08; analysis revised 2026-10-10 after an adversarial review. Companion to the post at gizmowarehouse.org/gizmo/self-insurance-cost. Code, pipeline, and the row-by-row labels and line coding: https://github.com/eichenbaumj/gizmowarehouse.org/tree/main/gizmos/self-insurance-cost

## The question

Do governments that carry their own liability (self-insure) spend more on lawsuits and liability insurance than governments of similar size and type that buy coverage from a public-entity risk pool or a commercial insurer? The comparison is of spending as booked, not of pure loss, and it holds one state's tort law constant.

## Data

**New York State Comptroller, Financial Data for Local Governments.** Account-level bulk files for counties, cities, towns, and villages, fiscal years 1995 to 2026, downloaded 2026-10-08. School and fire district files were downloaded but not analyzed. Liability cost = Unallocated Insurance (account 1910) + Judgments and Claims (1930) + Property Loss (1931) + Excess Insurance (1722), counted line by line:

- Lines in the operating funds count, except operating-fund insurance lines that are a government's charges into its own self-insurance fund (Westchester County, Garden City, Ossining), which would otherwise count the same money twice.
- Lines in the self-insurance fund family (fund prefixes M, MS, S, CS) count only where the government's own statements show they pay liability; lines that pay workers' compensation or employee health are out (for example, covered Madison County's self-funded health plan and Ulster County's workers' compensation pool).
- Excess Insurance (1722) counts only where the statements show it buys liability excess coverage; workers' compensation excess and health stop-loss are out.
- Lines whose purpose the statements leave unclear count as booked, and a sensitivity drops them.

Every coded line, with its quote and page, is in `crosswalks/ny_line_coding.csv` (104 lines). Workers' compensation (9040), self-insurance administration (1710), and benefits and awards (1720) are out. Amounts are deflated to 2024 dollars with CPI-U at each government's fiscal-year end and divided by population (decennial counts and Census subcounty estimates, interpolated). Total spending, used for per-dollar measures and police share, excludes interfund transfers, debt principal, and, from fiscal 2020, the custodial fund (fund TC, account 1935) through which towns and cities pass collected taxes to counties and school districts. Before this was excluded it made up 13 percent of all local governments' reported spending in 2024 (22 percent for counties, cities, towns, and villages) and $3.06 billion of the Town of Hempstead's $3.9 billion.

**Audited financial statements.** The general-liability arrangement of every county outside New York City, the 20 largest cities, the 30 largest towns, and the 10 largest villages by 2015 to 2024 average population, plus 18 more governments read along the way (135 in all), was read from the GASB Statement 10 risk-management note in each government's most recent audited statements (fiscal 2024 for most). The readings were done with AI help and checked by hand; each label carries the document URL, page, and a verbatim sentence. Structures: self-insured; self-insured with excess coverage; pool; commercial; mixed; unclear. A stated liability retention above $100,000 is treated as self-insurance and one at or below it as a deductible, whatever the note calls the arrangement (Putnam County, a NYMIR policyholder with a $250,000 general-liability deductible, is therefore self-insured with excess). Mixed and unclear governments are described but not compared. A premium-only signature, tested as a label for the governments not read, agreed with the documents only about 60 percent of the time, so it is not used anywhere.

**NYMIR subscriber list** (nymir.org, as of July 31, 2026; 1,016 subscribers, about 986 of them counties, cities, towns, and villages). The list does not say which lines each subscriber buys. Twenty-three governments whose own notes say they keep their liability are on it (12 counties, 5 cities, 5 towns, 1 village), buying other lines there; wherever a note describes the liability arrangement, the note governs. Putnam County, which buys a NYMIR policy with a $250,000 liability deductible, counts as self-insured under the $100,000 rule.

**National Transit Database** (Federal Transit Administration, via the DOT open-data portal). Operating expenses by type, 2022 to 2024, object class 506 "Casualty and Liability Costs," joined to vehicle revenue miles and unlinked passenger trips; directly operated service, full reporters only. The structure of the largest agencies was read from their audited statements the same way.

## Held out, and why

Twenty-four labeled governments are left out because their books cannot carry the comparison:

- Their judgments line carries other payments: Nassau County's 2024 line ($86.8 million) is $43.9 million of property-tax refunds plus $42.9 million of suits and damages, per its own statements; Cattaraugus County's carries its self-insured health plan; a few others show a large line that barely moves from year to year, the mark of benefit claims or refunds.
- They self-insure, but their documented liability claims paid exceed everything the Comptroller's lines show for liability that year (Suffolk County, Tonawanda, Hempstead, Brookhaven), or they show no claim payments in ten years and no self-insurance fund that pays them (Erie, Seneca, Otsego, Delaware, West Seneca).
- They buy coverage but book premiums on department lines, averaging under $1 a resident of unallocated insurance (Albany, Chautauqua, Chemung, Herkimer, Oneida, Orleans, and Wyoming counties; Village of Harrison).

Ithaca and Mount Vernon have fewer than eight years of filings. Every held-out government and its reason is in the labels download and under the chart.

## The level comparison

Each government's liability cost per resident is averaged over 2015 to 2024 (at least eight years required). Governments are matched within class and population band (2,500 to 10,000; 10,000 to 50,000; 50,000 to 150,000; 150,000 and up). The ratio averages the within-band log differences between self-insured and covered means, weighting each band by its number of self-insured governments, with each government's average capped at the 99th percentile of its class; the range is from a bootstrap that resamples counties, 2,000 draws.

Headline (spec `ny_core_classbin_cor_liab_pc`): self-insured governments spent 1.22 times as much as covered ones of the same type and size (range 0.83 to 2.02), comparing 35 self-insured with 49 covered governments. Other versions:

- Pre-registered match on class, size band, and region (only 52 governments keep a peer): 1.23 (0.82 to 1.81). The published headline drops region for that reason; the plan was written down before any model ran.
- Counties and towns only: 1.07 (0.72 to 1.81). Most of the gap comes from cities and villages, where only eight governments buy coverage.
- Ratio of medians: 1.20. Regression with size, police, capital spending, class, and region: 1.12 (0.83 to 1.53). Per dollar of spending: 1.13.
- All funds as booked: 1.22 (0.61 to 2.45). Operating funds only: 0.69 (0.30 to 1.14), which drops the funds many self-insurers pay their claims from. Unclear lines left out: 1.13 (0.68 to 1.81).
- Unclear and mixed labels counted as self-insured: 1.15; as covered: 1.28.
- 2015 to 2019: 1.19. 2020 to 2024: 1.28.
- Adding each government's law department: 1.26. Counting claims owed but not yet paid (the change in the judgments-and-claims-payable balance) instead of cash paid: 1.56, though for many governments that balance also holds workers' compensation.
- The mix differs sharply: judgments and claims alone, 2.95 (1.25 to 7.69); premiums alone, 0.65. Covered governments pay most of their claims through premiums, so the judgments-only number is not a like-for-like test of paying more to settle cases.

The self-insurance planning line (1710) was in the pre-registered outcome and was dropped before the first result because in practice it carries county workers' compensation overhead.

Both known measurement biases make self-insurers look cheaper than they are: their lawyers and reserves sit on other lines, and a covered government's premium includes the insurer's overhead (about 27 cents of each premium dollar at NYMIR in 2016 to 2020, per the state's examination).

## The swing

For each government, the standard deviation of its yearly liability cost per resident over 2015 to 2024 divided by its average. Governments with a negative year (a reserve release booked as a negative claim; Onondaga County) have no meaningful average and are left out of this measure. Medians: 0.51 for self-insured governments and 0.23 for covered ones. Within class and population band, the self-insured swing 1.8 times as much (range 1.1 to 2.7); with class and size held equal in a regression, 1.8 times (1.3 to 2.5). The gap appears in every class, though only three cities buy coverage. The worst year is the single costliest year over the government's own average: about 2.0 times for the typical self-insurer and 1.4 times for the typical covered government. A covered government's bill is about 90 percent premium at the median, and what it still pays itself is as lumpy as a self-insurer's claims, so the steadier bill is what the premium buys. Where a self-insurer pays claims from a reserve or internal fund, the swing measured here is in what the fund pays out; steady contributions to the fund can smooth the hit to the budget, though the government still carries the bad years. Against total spending, liability runs under 1 percent for most governments; the typical self-insurer's worst year added about 0.8 percent of a year's spending (1.3 percent under 50,000 residents, 0.6 percent above 150,000).

## Police

A police department means municipal police spending (account 3120) of at least 1 percent of total spending; counties book their sheriffs under 3110, and only Westchester among the compared counties runs a county police department. In a regression of log liability cost per resident on class, size, capital spending, structure, and whether a government has a police department, a department goes with 2.36 times the cost (range 1.70 to 3.27). Within a class, that contrast rests mostly on towns (22 of 33 compared towns have a department; nearly every city and village does). Among governments with a department, each ten points of budget share on police goes with 1.23 times the cost (0.87 to 1.75). In the same regressions the self-insured come out 1.18 to 1.25 times higher, with ranges that include no difference, and structure adds almost nothing to the fit (R-squared 0.549 with it, 0.543 without). Splitting by police department, or counties by sheriff and jail spending, gives ranges that all include no difference (among governments with a department, 1.66, range 0.98 to 2.82); cities and villages together lean toward the self-insured paying more (2.27 times in a regression, range 1.17 to 4.43; 1.57 matched), with eight covered governments. These are associations, not effects.

## Transit

Of the 100 largest directly operated agencies, 90 have clear labels. Adjusted for size, the self-insured spend 1.43 times as much on casualty and liability per vehicle revenue mile (0.99 to 2.06), 0.99 times as much per passenger trip, and 1.01 times as much as a share of operating cost. No covered agency is as large as the 36 biggest self-insured ones, so size, structure, and state law move together; this is a description, not a test.

## The largest governments

The share of labeled governments that self-insure rises with size, from about a quarter under 50,000 residents to all six above 500,000. The largest covered county, town, city, and village are Albany County (about 312,000), Ramapo (about 144,000), Schenectady (about 67,000), and Kiryas Joel (about 32,000); every labeled government above those sizes whose statements are clear carries its own liability. (Ramapo's note describes a $50,000 deductible, yet its general-liability fund paid $2.5 million of claims in 2023, so I am uncertain it belongs with the covered.) Stated retentions rise with size: the median is $1 million at 100,000 to 500,000 residents, and the two above 500,000 that state one keep $2 million (Monroe) and $10 million (Suffolk). Those 23 governments hold about a third of liability cost as booked outside New York City (governments above 312,000 alone hold about a sixth). That share leaves out governments whose judgments lines carry refunds or benefits, Nassau and Islip among them, and Suffolk, Erie, Hempstead, and Brookhaven book claims elsewhere, so it is an undercount.

## What the comparison cannot do

It cannot say what a large self-insured government would pay with an insurer, because none in New York buys coverage from the first dollar. It cannot separate the effect of self-insuring from selection into it: a government that self-insures may be one with low expected losses, or one nobody would cover, and a government with a bad record can be priced out of a pool, as Vallejo was, and would then show up here as a costly self-insurer. The best-documented changes in a government's premium line were accounting reclassifications over an unchanged structure, so there is no within-government evidence here. It holds New York's tort law constant and does not travel.

## Sources

- New York State Comptroller, Financial Data for Local Governments: https://wwe1.osc.state.ny.us/localgov/findata/financial-data-for-local-governments.cfm
- Federal Audit Clearinghouse: https://app.fac.gov
- Nassau County, 2024 Annual Comprehensive Financial Report.
- New York City Comptroller, claims dashboard release, April 30, 2025 (fiscal 2024: $1.04 billion of injury and property-damage claims within $1.94 billion across 13,397 resolved claims).
- NYMIR, Subscriber List by County, July 31, 2026: https://nymir.org/wp-content/uploads/2026/07/SUBSCRIBER-LIST-BY-COUNTY-07.31.26.pdf; New York Department of Financial Services, Report on Examination of the New York Municipal Insurance Reciprocal as of December 31, 2020.
- Federal Transit Administration, National Transit Database: Operating Expenses by Type (j5uj-anzx) and Service by Mode (wwdp-t4re), data.transportation.gov; NTD Glossary.
- Joanna C. Schwartz, "How Governments Pay: Lawsuits, Budgets, and Police Reform," 63 UCLA Law Review 1144 (2016). John Rappaport, "How Private Insurers Regulate Public Police," 130 Harvard Law Review 1539 (2017). Tom S. Clark, "Municipal Liability Insurance as Police Oversight: Evidence from Vallejo, California," working paper dated April 23, 2026.
- Kachalia, Kaufman, Boothman, and colleagues, "Liability Claims and Costs Before and After Implementation of a Medical Error Disclosure Program," Annals of Internal Medicine 153(4) (2010). Schultz, Zhou, Gray, and colleagues, "Patient characteristics of, and remedial interventions for, complaints and medico-legal claims against doctors: a rapid review of the literature," Systematic Reviews 13:104 (2024). Schaffer and colleagues, "Rates and Characteristics of Paid Malpractice Claims Among US Physicians by Specialty, 1992-2014," JAMA Internal Medicine 177(5) (2017). LeCraw, Montanera, Jackson, and colleagues, Journal of Patient Safety and Risk Management 23(1) (2018).
- Elizabeth Wyner, Citizens Budget Commission, "Controlling the Cost of New York City's Settlements and Judgments: A Tale of Two Agencies," August 2014. Los Angeles County Office of Inspector General, Sheriff's Department reform and oversight report, February 2024.
- Christian Science Monitor, "Cities pool their risks and insure themselves," June 20, 1986. Governing, "Massive Legal Costs Weigh on Local Budgets," October 2016. Chicago City Council Office of Financial Analysis, lawsuit cost study, 2019.
- Matthiesen, Wickert & Lehrer, "Municipal/County/Local Governmental Immunity and Tort Liability in All 50 States," last updated February 14, 2022.
