export default `
*Up to date as of October 8, 2026. The Comptroller's data refreshes yearly and the structure labels were read from audited statements by hand, so this will drift. We may update or rerun it.*

## Hidden costs

On occasion, people get hurt when using a government service. A bus hits a pedestrian. A police officer uses force. An inmate is hurt in jail. When people are injured, they oftentimes sue whoever is responsible, or rather, whoever is readily liable.

Almost every time, those lawsuits end in settlements rather than jury trials. In New York, local governments outside New York City spend roughly $500 million to $650 million a year on liability insurance and on court judgments and claims, and [New York City alone paid about $1.9 billion](https://comptroller.nyc.gov/newsroom/comptroller-landers-new-dashboard-tracks-city-claims-city-paid-nearly-2b-in-settlements-last-fiscal-year) to settle claims in fiscal 2024. The direct source of that settlement money varies quite widely depending on who you're suing.

My colleague had a hypothesis about government settlement outcomes. She argued that governments that carry their own liability - i.e., those that are self-insured - pay far more to settle cases than governments that buy insurance coverage. A government paying out of its own budget may look like an easier target to plaintiffs' lawyers, and an insurer handles claims for a living, while for most governments it is a sideline. I thought that was probably right.

## How a government buys risk

A government has three ways to pay the claims it will someday lose. It can buy a policy from an insurance company. It can join a risk pool, a few hundred towns forming their own insurer to pay the claims. Or it can keep the risk, budget a reserve, and write the checks when the verdicts come in. That is self-insurance, and most large governments do it.

What separates them is who writes the check when a claim settles, and whether anyone's price moves afterward. In New York, more than a thousand of the state's roughly 1,600 general-purpose local governments belong to one pool, NYMIR. When a town in NYMIR is sued, the town is the defendant but NYMIR handles the claim and pays the first $750,000 of any loss, and next year's premium goes up because of it.

When Nassau County is sued, Nassau is both defendant and payer. It paid $87 million in judgments and claims in 2024 from its own general fund, after its own lawyers decided what each case was worth, and no premium went up afterward.

## The bill is the same

New York is the place to test it, because New York has excellent data going back to 1995. Every local government in New York reports their total insurance premiums, and their judgments and claims, to the State Comptroller. I read the risk-management note in the audited statements of all 57 counties, the 20 largest cities, and the 40 largest towns and villages, then compared governments of the same type and size band over 2015 to 2024.

<sic-core-chart></sic-core-chart>

The chart looks like noise. Dark blue marks, governments that carry their own liability, and light blue marks, governments that buy coverage, are mixed together at every size, and neither color sits consistently above the other.

Cities cannot be tested, since every New York city above about 45,000 residents carries its own liability and only three buy coverage. So I tested counties and large towns. In every size band, the self-insured counties and large towns spent the same or less per resident than the covered ones. Put the bands together, comparing each government only with others of its type and size, and the self-insured spent about as much as the covered. The range the data allow runs from roughly half to roughly 1.8 times.

My colleague's hypothesis is wrong, at least in its strong form. Self-insured governments do not pay far more. But I have only tested the surface. The books understate what self-insurers pay, since lawyers and reserves are booked elsewhere. The biggest governments, New York City among them, have no insured peers to compare against. And while I found no difference overall, there may be one for certain kinds of governments. As it turns out, in police-heavy cities and villages, self-insurers do seem to pay more, but there are only one or two covered governments to compare them with, too few to trust. Where self-insurance clearly does show up is in how much the bill swings, most of all where police spending is high.

## The source is not the signal

The hypothesis assumes a government that pays its own claims draws more of them, or bigger ones. Mostly the bill is set upstream, by what the government does and by state tort law, identical for everyone here. The only thing that moves the bill is police. Each extra ten percent of a budget spent on police raises liability cost per resident by roughly 40 percent. Once that is in the model, how a government pays its claims adds nothing, and no type of government, not counties with big jails, not towns with big police forces, not transit systems, shows a credible self-insurance premium in the public books.

The hypothesis also assumes insurers handle claims better than governments do. The large self-insurers have law departments that do this full time. What a pool does not do is price each member precisely. Tom Clark, a political scientist at Stanford, traces how that played out in [Vallejo, California](https://www.cityofvallejo.net) in [a 2026 working paper](https://www.tomclarkphd.com/files/police_insurance.pdf). Vallejo's pool charged members by payroll, so a city whose claims ran more than two and a half times what the pool expected paid the same rate as everyone else. In 2018 the pool raised Vallejo's share of each claim from $500,000 to $2.5 million, and the city left for market-priced coverage. Its premium went from $392,000 to $2.4 million by 2024. A premium is roughly the claims a government would have paid plus the pool's overhead.

There is a lot I cannot see, and some of it could rescue the hypothesis. Whether self-insurers settle each claim more generously, whether their reserves are honest, whether politics leans on their lawyers, what the hospital counties actually pay. None of that is in public books. The books can only say that the totals look the same and the swings do not.

## What structure actually buys

So what does a pool buy you, if not a lower bill? Coverage buys you a bill that you can plan around. Self-insured governments' liability costs swing about twice as much from year to year as covered governments' do, in every class of government, and worse as the police share of the budget rises.

<sic-volatility></sic-volatility>

Police claims are lumpy. A pool spreads the lump across a thousand members. A self-insurer eats it, and its worst year in the window ran about 40 percent above its average. A county with no police and a billion-dollar budget barely notices. A village with its own police and a twenty-million-dollar budget notices little else. That is the real penalty of self-insurance, and it falls on the governments least able to carry it.

## What a government could do

If the bill is set by exposure, the levers that lower it are operational. Claims data that someone reads, as New York City's ClaimStat and Chicago's 2019 review recommend, and the police practices they point at. The choice between pooling and self-insuring is about keeping the bill steady. Joanna Schwartz, a law professor at UCLA, studied how 100 jurisdictions across the country pay for police lawsuits in [a 2016 article](https://www.uclalawreview.org/wp-content/uploads/2019/09/Schwartz-63-5.pdf). The risk-pool experts she interviewed said governments under about 100,000 residents generally pool or buy insurance. A government that small belongs in a pool, especially a police-heavy one. A large one can keep the risk if it holds a stated retention with excess coverage above it, as NYMIR does, and a reserve sized for its worst year. Whether any of that would move the numbers I cannot say from public books. That part is illustrative.

## Housekeeping

Every label, with its document and quote, and the panels are in the pills above. The code is [public](https://github.com/eichenbaumj/gizmowarehouse.org/tree/main/gizmos/self-insurance-cost). If a number is wrong, tell me at joe@group17a.com.

<details id="methodology">
<summary class="font-serif text-2xl font-bold text-cobalt cursor-pointer select-none mt-8 mb-4">Methodology</summary>

**Data.** New York State Comptroller, Financial Data for Local Governments, account-level files for counties, cities, towns, and villages, fiscal years 1995 to 2026. Cost of risk = Unallocated Insurance (1910) + Judgments and Claims (1930) + Property Loss (1931), all funds, divided by population (Census estimates), in 2024 dollars. Workers' compensation and the self-insurance fund family (benefit claims) are carried separately. Federal Transit Administration, National Transit Database, operating expenses by type (object class 506, casualty and liability) and service by mode, 2022 to 2024, directly operated full reporters.

**Labels.** The general-liability arrangement of all 57 counties, the 20 largest cities, and the 30 largest towns and 10 largest villages was read from the GASB Statement 10 risk-management note in each government's most recent audited financial statements (FY2024 for most), and recorded with the document, page, and a verbatim quote. A retention at or below $100,000 is treated as a deductible, not self-insurance. The NYMIR subscriber list (July 2026) was used only to describe pool membership. Transit labels were read the same way from the largest agencies' statements.

**Comparison.** Entity averages over 2015 to 2024, matched within class and population band, ratio of self-insured to covered means with a county-clustered bootstrap range; a regression with size and service-mix controls as the twin. Entities whose judgments line carries benefit claims (large and smooth), or whose documented claims payments do not appear on the Comptroller's lines, are held out and listed. A premium-only signature was tested as a label for smaller governments and agreed with the documents only about half the time, so it is not used.

**What the comparison cannot do.** It cannot say what a self-insured city would pay with an insurer, because no insurer writes the large ones. It holds New York's tort law constant and does not travel. It is a comparison of spending as booked, not of pure loss.

</details>

<details>
<summary class="font-serif text-2xl font-bold text-cobalt cursor-pointer select-none mt-8 mb-4">Sources</summary>

- New York State Comptroller, Financial Data for Local Governments (account-level bulk files).
- New York City Comptroller, Claims Dashboard, fiscal 2024 ($1.94 billion across 13,397 resolved claims).
- Audited financial statements of each labeled government (Federal Audit Clearinghouse and government websites), cited row by row in the labels download.
- NYMIR subscriber list by county, as of July 31, 2026; NY Department of Financial Services examination report on NYMIR as of December 31, 2020.
- Federal Transit Administration, National Transit Database, 2022 to 2024.
- Joanna Schwartz, "How Governments Pay," 63 UCLA Law Review 1144 (2016). John Rappaport, "How Private Insurers Regulate Public Police," 130 Harvard Law Review 1539 (2017). Tom Clark, "Municipal Liability Insurance as Police Oversight: Evidence from Vallejo, California," working paper, April 2026.
- Christian Science Monitor, "Cities pool their risks and insure themselves," June 20, 1986. Governing, "Massive Legal Costs Weigh on Local Budgets," October 2016. Chicago Office of Financial Analysis, lawsuit cost study, 2019.
- Matthiesen, Wickert & Lehrer, municipal governmental immunity and tort liability chart, February 2022.

</details>
`;
