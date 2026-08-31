export default `
*Up to date as of August 15, 2026. The restriction landscape moves fast enough that parts of this will be stale within months. We may update or rerun it.*

## The town that said no

On August 6, 2025, the Tucson City Council voted 7-0 to stop all work on Project Blue, a proposed $3.6 billion data center campus. The council was responding to real concerns, water above all. [Press accounts](https://www.tucsonsentinel.com/local/report/071425_project_blue/tucson-deal-project-blue-data-centers-would-thirst-water-electricity/) said the campus would have been Tucson Water's largest customer. On the other side, [Pima County estimated](https://www.pima.gov/3552/Project-Blue-FAQ) it would bring in $250 million in tax revenue over ten years, and a few dozen permanent jobs.

The land was never inside the city. The campus was planned for a 290-acre county-owned parcel awaiting annexation, and when the vote killed the annexation, the developer closed on that same parcel in December after the county approved a revised deal 3-2, and construction began in April. Opponents sued the county over open-meetings violations in how that approval was reached, and the suit was dismissed. Tucson gave up the revenue and every negotiated benefit, including a reclaimed-water pipeline worth over $100 million, and kept the grid and water exposure it had voted against.

This gizmo attempts to price that trade nationally. When a town says no, what exactly does it give up? In Tucson's case, the revenue and not the project. A town owes nobody a yes. But every no has a price, and a town should know it before the vote.

## What one campus pays a town

The largest local economic benefit from a data center is property and equipment tax, not jobs. A typical large facility employs about 50 permanent workers. The real jobs event is construction, which employs one to four thousand workers for one to three years. The jurisdiction's collected revenue is driven mostly by the local tax regime, and those regimes vary *widely*:

| Regime | Anchor case | What one campus pays locally |
|---|---|---|
| Aggressive abatement | Morrow County, OR enterprise zone | ~$2&ndash;3M/yr in fees, in exchange for over $1B in abated property taxes |
| Partial abatement | Georgia state audit, representative metro-Atlanta campus | $33.6M/yr gross, $5.9M abated, **$27.8M collected** |
| Partial abatement, big campus | El Paso Meta ($10B, 80% abated for 35 years) | ~$56M/yr blended across local entities |
| Unabated equipment tax | Loudoun County, VA | $894.5M actual (FY25) and $1,135.7M budgeted (FY26), 42% of local tax funding |

After collecting nearly $900 million in data center tax revenue in FY25, Loudoun County budgeted more than $1.1 billion for FY26. That FY26 number is a ceiling though, not a guarantee. Most of the revenue is tax on the servers themselves, which lose taxable value in three to five years, so it moves with the hardware cycle. In June 2026, the county tallied its taxable equipment at [$10.1 billion against a forecast $11.2 billion](https://www.datacenterdynamics.com/en/news/loudoun-county-budget-hit-by-data-center-60m-tax-revenue-shortfall/), erasing about $60 million of the revenue it had budgeted.

The revenue is one side of a ledger. The other side is years of construction traffic, a permanent hum, a claim on the water supply, and new load on a grid everyone shares. Whether a deal nets out for residents depends on the terms. At Morrow County's $2–3M a year, it plausibly does not. Get the utility terms wrong and electric bills can eat the gain. The calculator below prices only the revenue side. The costs of hosting are just as real and much harder to put a national number on.

<dcr-town-calc></dcr-town-calc>

The calculator assumes the proposal is real. Some jurisdictions pass moratoria with nothing on the table, in places where land and power made construction unlikely anyway. For them, the foregone revenue is close to zero. The calculator prices the simpler case, like Tucson's, where a live proposal was on the table and the vote decided only who shared in it. State tax policy does shape whether construction comes at all, but the two best state audits land far apart on how much: roughly 90% of Virginia's investment needed the exemption per [JLARC](https://jlarc.virginia.gov/landing-2024-data-centers-in-virginia.asp), against 30% implied by [Georgia's audit](https://www.audits.ga.gov/ReportSearch/download/33298). Either way, the effect is large.

## The map of no

<dcr-map></dcr-map>

The red family is restrictions: moratoria, bans, zoning exclusions, project rejections. The blue family is conditions: noise and setback ordinances, ratepayer protections, utility tariffs, the things that say yes, if. Gray means no enacted state law, and the charcoal rings show each state's data center [electricity use in 2024](https://powering-intelligence.epri.com/dashboard/).

Nearly three quarters of data center power sits in ten states. Virginia alone, at 18%, runs more than the bottom thirty-five states combined.

<dcr-footprint-bars></dcr-footprint-bars>

The map shows documented actions in force today, and it is growing weekly: 7 moratoria in 2023, 6 in 2024, 59 in 2025, 294 in the first seven months of 2026. Three things surprised me.

**This is not a partisan story.** Local officials opposing projects are 55% Republican, per [Data Center Watch](https://www.datacenterwatch.org/), an industry-adjacent tracker. A third of Indiana's counties are on the blocked list.

**Legislatures are choosing conditions, not bans.** By mid-2026: 24 states with approved large-load tariffs (per the trade association [EEI](https://www.eei.org/-/media/Project/EEI/Documents/Issues%20and%20Policy/List%20of%20Large%20Customer%20Projects%20and%20Tariffs)), a dozen-plus ratepayer-protection statutes, zero repeals of a data center exemption.

**Blocked projects go quiet more than they resurface.** Of the 28 best-documented fights since 2023 (toggle them on the map), 13 are still pending or in court and 4 were delayed, then built, including the Tucson campus that opens this piece, built on the very parcel the city declined to annex. Of the 11 where a block stuck, one project moved, about 12 miles, measured town to town. Nine left no documented second act, including the two largest at $24.7 billion and $19.2 billion of claimed investment, and one turned into a company promising a replacement site it has not named a year later. That does not mean saying no kills the demand: in a market this supply-constrained, blocked capital likely builds somewhere else, invisibly, because siting consultants screen out hostile jurisdictions before a proposal ever goes public. The town that says no stops getting proposals. That is an inference from market conditions rather than a measured fact. No systematic study has traced where blocked capital lands, and our own trace could document a destination in one settled case of eleven. The inference holds while demand outruns supply, as it does today, and whether that lasts depends on the long-term future of AI demand, which nobody knows.

## What to demand instead

Many of the complaints driving these restrictions are fair. Data centers hum at night, they drink water in dry places, and once the construction crews leave they are nearly empty, vast blank boxes with a few dozen jobs inside. But if AI is oil, data centers are the rigs. Towns that decide to say yes can write most of those complaints into revenue-generating contracts and fund schools and services with the proceeds. The asks below are real-world examples of how jurisdictions can maximize data center value for residents.

**Minimum-take tariffs.** Data center developers routinely ask utilities for far more power than they will ever build, because asking has been free. A minimum-take tariff puts a price on the request. [AEP Ohio's](https://puco.ohio.gov/news/puco-orders-aep-ohio-to-create-data-center-specific-tariff) makes any large customer pay for at least 85% of the capacity it reserves, for up to 12 years, whether or not they end up using it. Under that rule, speculative requests collapsed from [30 gigawatts to 13](https://ohiocapitaljournal.com/2026/02/20/aep-ohio-says-new-data-center-tariff-is-working-critics-arent-buying-it/), and 5,600 megawatts of real demand signed. The phantom problem is national. ERCOT, the Texas grid, has a request queue past 470 gigawatts, largely the same projects filed with multiple utilities. A tariff is a utility rule, so a town cannot write one, but it can withhold approval until one with these terms exists.

**Curtailment.** Texas's [SB 6](https://www.mcguirewoods.com/client-resources/alerts/2025/7/texas-senate-bill-6-significantly-expands-regulatory-oversight-over-large-loads-in-ercot/) requires loads over 75 megawatts to accept curtailment in grid emergencies. Google already pauses training workloads on request. Flexibility is cheap for training and valuable to everyone else.

**Ratepayer protection.** The fear is that a data center raises everyone else's electric bill. It is well founded: PJM, the grid operator for the mid-Atlantic and parts of the Midwest, buys future power through annual capacity auctions, and [its independent market monitor](https://www.utilitydive.com/news/pjm-data-centers-capacity-auction-imm-bowring/825626/) attributes $9.3 billion of one year's increase to data center load. The risk comes from forecasts of future demand, and minimum-take terms are what keep those forecasts honest.

**Water and noise, in writing, with numbers.** Chandler, Arizona caps water at 115 gallons per day per 1,000 square feet. Pennsylvania's Chester and Montgomery County [model ordinance](https://files.dep.state.pa.us/PublicParticipation/Citizens%20Advisory%20Council/CACPortalFiles/Meetings/2026_05/2026%20Data%20Center%20Ordinance%20Guide.pdf): night noise limits in A- and C-weighting at the property line, 1,000-foot residential separation, closed-loop cooling, decommissioning within a year of end-of-life.

**Fiscal terms with teeth.** Payments in lieu of taxes with revenue guarantees and clawbacks, never blanket abatements. DeForest, Wisconsin negotiated a guaranteed $1.2 billion assessed value for 15 years and a 110% home-buyback for harmed neighbors.

**Process transparency.** DeForest negotiated the strongest fiscal terms on this list, and the deal still [collapsed over the secrecy of the negotiation](https://wisconsinwatch.org/2026/08/wisconsin-deforest-data-center-deal-guaranteed-tax-revenue-river-improvements-affordable-housing/). Some of the most effective opposition is opposition to being handled. The tenant's name, the water number, and the megawatts belong on the public record before the vote.

And the prize for getting it right is real. On Virginia-style terms, one campus can pay a town tens of millions of dollars a year, money a county can put into schools, clinics, and roads. Stillwater, Oklahoma raised its Google payment 25% by asking. The fear that fills this map is negotiating power for any town willing to use it.

Some towns will run the numbers and still say no. With the price on the table, that is a fair decision.

## Housekeeping

The dataset, coding rules, and methodology are downloadable up top. The widgets read the same files. Every count is as of August 15, 2026, and likely undercounts. If a number is wrong, tell me. joe@group17a.com.

<details id="methodology">
<summary class="font-serif text-2xl font-bold text-cobalt cursor-pointer select-none mt-8 mb-4">Methodology</summary>

### What the map counts

One row per formal government action: an adopted moratorium, ban, zoning exclusion, project rejection, referendum, conditions ordinance, enacted state law, executive order, or commission-approved tariff. Proposals and failed bills are excluded, with two flagged exceptions (Maine's vetoed LD 307 and Georgia's SB 410, which passed one chamber) carried for context and marked by status. Each row is coded restriction or condition. State preemption of local control is its own class. The judgment calls are logged in a decisions file in the repository.

The county shading works like this: every local action is assigned to a county by locating its coordinates inside Census county boundaries (Virginia's independent cities count as county-equivalents, and a short list of consolidated city-counties like Indianapolis and Nashville count as county-wide). A county is shaded even when the action is a single town's, and the striped treatment marks exactly that case. Pending and lapsed measures are excluded from the default view and available by toggle. Anchorage and any unassignable rows appear as points only (the boundary file has no Alaska county polygons), and tribal and utility-district actions shade the county containing their location. The build log records the two coordinate corrections made by hand and every assignment the pipeline could not make automatically.

### Layers and sources

The local layer combines two databases other people built and published openly: the [Moratorium Nation tracker](https://mjbommar.github.io/moratorium-data-2026/) by Michael Bommarito of the ALEA Institute (CC-BY-4.0, built from roughly 4,600 primary documents) and [datacentertracker.org](https://datacentertracker.org/) by Cam Acosta and George Ingebretsen (CC-BY-4.0, community-assembled and marked as such on every row it contributes). The map's local layer starts from their work; the merge, dedup, audit, and classification are ours. The state layer is hand-curated from primary documents and legal analyses, with bill numbers. The utility layer is hand-curated from commission dockets. The 24-approved / 6-pending state count is attributed to EEI's July 2026 tracker rather than reconstructed. The footprint rings carry EPRI's per-state 2024 actuals, and the 2030 figures in the popups are EPRI's medium scenario. Coordinates come from the source datasets where present, county centroids otherwise, and the file records which.

Known limits, stated plainly: this is documented actions, not a census. Coverage depends on news and document trails, which are thinner in small jurisdictions. For the community-assembled rows, we audited a 25-row random sample against primary documents and local press: every sampled action was real, but among the rows that reach the map, two carried wrong dates and one described a project approval miscoded as a restriction. All three were corrected or removed, one duplicate instrument was also caught and removed, and the corrections ship in the pipeline as reviewable overrides. The dataset attribution on each row lets you weigh the remainder yourself.

### The outcome trace

We took the 28 best-documented blocked or disrupted projects (2023 through mid-2026), and traced each to its status using local press and government records, with at least one source per project in the download (full trace August 8, 2026, open cases re-checked August 15, and a displacement audit August 19 that re-verified every settled case against pre-registered tests, with adversarial review of each claimed relocation). Coding is conservative: a project counts as rerouted only with a documented destination, and as died only when abandoned with no documented relocation. The audit moved one project between categories: Tucson's Project Blue, first coded as a reroute, was in fact built on the same parcel it was always planned for, so it now counts as delayed, then built. Several entries rest partly on advocacy compilations and carry a medium-confidence flag.

The full status breakdown: 13 pending or litigating, 10 died, 4 delayed then built in place, and 1 confirmed reroute, about 12 miles, measured town to town. Of the 10 that died, 9 left no documented second act and 1 is a company still promising a replacement site it has not named. The scarcity of documented second acts is not evidence that blocking kills demand. The market is severely supply-constrained (record-low 1.4% vacancy and roughly three quarters of construction pre-leased per CBRE, turbines sold out through 2030), so blocked capital most plausibly builds somewhere else and the displacement is mostly invisible: siting consultants screen out hostile jurisdictions before a proposal ever goes public, so the counterfactual proposal is never filed, and never makes the news.

### The calculator

The calculator's ranges are case-anchored per-campus annual revenue figures from the named jurisdictions, not a per-megawatt model. The per-megawatt version requires county assessment rolls and is the planned next phase. The size slider is denominated in announced build cost because that is what the anchors are quoted in. The calculator assumes a live proposal and applies no counterfactual discount: the two best state audits (Georgia's 30% attribution and JLARC's roughly 90%) disagree too widely to average, so the assumption is stated rather than modeled. The ten-year horizon is a choice, explained in the widget: past 2030 the underlying demand forecasts disagree by 2x, and past 2036 responsible modeling ends. Equipment-tax revenue is volatile and plateaus: Loudoun keeps a $114 million revenue stabilization fund against assessment swings, and the county's own guidance says growth flattens within five to ten years.

### Claims discipline

Numbers in this piece that come from advocacy or industry-funded sources are attributed inline every time (Data Center Watch, Good Jobs First, E3, EEI). Developer-announced investment figures are labeled as such and never treated as realized investment. Three figures circulating widely are deliberately absent from the body. The first is the claim that Georgia's audit found a $2.5 billion annual exemption cost: the audit's own figure is $474.2 million forgone in FY25, and the larger number comes from separate state estimates. The second is any national aggregate loss figure, because in a supply-constrained market a local block mostly redirects investment rather than destroying it. The third is Data Center Watch's widely quoted $64 billion in blocked-or-delayed projects: developer-announced value compiled by an industry-funded tracker, 72% of it delay rather than death, with the research firm SemiAnalysis finding the cancellations concentrated in speculative announcements without financing, site control, or interconnection. Both things are true: the wave is real, and the dollars overstate the damage.

### Cut for length, kept for the record

Detail that earlier drafts carried in the body, with sources below:

- **Jobs.** Virginia's JLARC put permanent employment at roughly 50 per facility (about 35 is the observed number in Quincy, Washington). Of the 74,000 jobs JLARC attributes to the industry in Virginia annually, 59,000 are construction-phase.
- **Loudoun's ceiling.** In FY26, budgeted data center revenue surpassed all residential real property tax combined for the first time. The workhorse is a personal property tax on computer equipment at $4.15 per $100 of value, which carries roughly three quarters of the revenue.
- **Forecast spread.** EPRI's 2026 scenarios put US data center demand at 380 to 790 terawatt-hours by 2030 (9 to 17% of US electricity, versus 4 to 5% today). BloombergNEF revised its 2035 capacity projection 2.5x in fifteen months. NERC projects 224 gigawatts of peak growth through 2035, the fastest it has ever tracked. Anyone selling a point estimate for 2036 is selling. Virginia is the only state where data centers exceed 20% of electricity use today, and seven more could cross by 2030, a politically mixed list.
- **Where the divergence lands.** The multi-gigawatt campuses are going to Louisiana, Mississippi, Wyoming, Indiana, and Ohio, for power, land, and permitting speed. The tilt predates the restriction wave, and restrictions reinforce a gradient they did not create. The bankable divergence is already in county budgets: Loudoun's billion a year, Prince William's $280 million, and the neighbors that screened themselves out.
- **Statewide instruments.** Governor Hochul's Executive Order 62 in New York, and Maine's LD 307, vetoed by Governor Mills. Per EEI, 6 more large-load tariff states are pending beyond the 24 approved, and 38 states still offer data center incentives. There have been zero repeals of a state exemption.
- **Tariff diffusion.** Amazon, Microsoft, and Google signed Indiana's settlement paralleling the AEP Ohio terms, and Georgia and Virginia require similar terms.
- **Curtailment headroom.** Duke's Nicholas Institute estimates the existing grid could absorb 76 to 126 gigawatts of load that curtails at most one percent of its annual energy.
- **Ratepayer detail.** JLARC found Virginia's data centers pay full cost of service today. Oregon adds an equity kicker: a surcharge on 100-megawatt-plus loads funds low-income energy programs (data center rates projected up 29%, residential slightly down).
- **Water and noise numbers.** Loudoun runs about 40 data centers on reclaimed water. The Pennsylvania model ordinance's night limits are 40 dB(A) and 50 dB(C) at the property line, because C-weighting catches the hum A-limits miss.
- **Fiscal terms.** Stillwater, Oklahoma pushed its Google PILOT up 25% by asking. Independence, Missouri flips to full taxation if construction stalls 90 days.
- **Transparency.** Minnesota officials signed NDAs with code-named shell companies.
- **Tucson.** The $250 million ten-year figure splits $97 million to the city, $60 million to the county, $93 million to the state, and the developer's 180-job claim was dated to 2029. Amazon walked away as anchor tenant after the city vote, but the project, which never moved, kept going under county approvals at a reported fraction of its announced size.

</details>

<details>
<summary class="font-serif text-2xl font-bold text-cobalt cursor-pointer select-none mt-8 mb-4">Sources</summary>

- [JLARC, Data Centers in Virginia, Report 598 (Dec 2024)](https://jlarc.virginia.gov/landing-2024-data-centers-in-virginia.asp) — jobs, local revenue, exemption cost, cost-of-service and 2040 ratepayer scenarios
- [Georgia DOAA / Carl Vinson Institute, Data Center Tax Exemption evaluation (Dec 2025)](https://www.audits.ga.gov/ReportSearch/download/33298) — $474.2M FY25 forgone, 70% but-for finding, representative-campus tax figures
- [Pima County Project Blue FAQ](https://www.pima.gov/3552/Project-Blue-FAQ) — Tucson capex, tax, and jobs figures · [Tucson Sentinel on Project Blue's water and power demands (July 2025)](https://www.tucsonsentinel.com/local/report/071425_project_blue/tucson-deal-project-blue-data-centers-would-thirst-water-electricity/) — the largest-customer water claim
- [Moratorium Nation](https://mjbommar.github.io/moratorium-data-2026/) by Michael Bommarito, ALEA Institute — local moratorium inventory, CC-BY-4.0; the map's largest single source
- [datacentertracker.org](https://datacentertracker.org/) by Cam Acosta and George Ingebretsen — community-assembled local action tracker, CC-BY-4.0
- [Data Center Watch](https://www.datacenterwatch.org/) — blocked/delayed tallies (industry-adjacent, attributed, not relied on)
- [SemiAnalysis, "Stop Saying Half of 2026 US Datacenter Capacity Is Canceled" (June 2026)](https://newsletter.semianalysis.com/p/stop-saying-half-of-2026-us-datacenter) — the speculative-tier counterweight
- [EEI, Large Load Projects and Tariffs (July 2026)](https://www.eei.org/-/media/Project/EEI/Documents/Issues%20and%20Policy/List%20of%20Large%20Customer%20Projects%20and%20Tariffs) — 24 approved / 6 pending tariff-state counts
- [PUCO, AEP Ohio data center tariff order (July 2025)](https://puco.ohio.gov/news/puco-orders-aep-ohio-to-create-data-center-specific-tariff) and [Ohio Capital Journal on the Feb 2026 compliance figures](https://ohiocapitaljournal.com/2026/02/20/aep-ohio-says-new-data-center-tariff-is-working-critics-arent-buying-it/)
- [Indiana Capital Chronicle on the I&M settlement (Nov 2024)](https://indianacapitalchronicle.com/2024/11/26/ratepayer-advocates-hail-landmark-settlement-with-data-centers-utility-company/)
- [Georgia PSC large-load rules (Jan 2025)](https://psc.ga.gov/site/assets/files/8617/media_advisory_data_centers_rule_1-23-2025.pdf) · [Virginia SCC GS-5 order (Nov 2025)](https://www.scc.virginia.gov/about-the-scc/newsreleases/release/scc-issues-order-on-dev-biennial-review-2025/scc-rules-in-dev-biennial-review-case.html) · [Oregon PUC / PGE Schedule 96 (May 2026)](https://www.utilitydive.com/news/oregon-puc-approves-pges-large-load-tariff-framework-for-data-centers/821361/)
- [Texas SB 6 analysis (McGuireWoods, July 2025)](https://www.mcguirewoods.com/client-resources/alerts/2025/7/texas-senate-bill-6-significantly-expands-regulatory-oversight-over-large-loads-in-ercot/)
- [Duke Nicholas Institute, Rethinking Load Growth (2025)](https://nicholasinstitute.duke.edu/events/rethinking-load-growth-assessing-potential-integration-large-flexible-loads-us-power-systems)
- [Monitoring Analytics capacity-auction attribution via Utility Dive](https://www.utilitydive.com/news/pjm-data-centers-capacity-auction-imm-bowring/825626/) · [Harvard ELI, Extracting Profits from the Public (Mar 2025)](https://eelp.law.harvard.edu/wp-content/uploads/2025/03/Harvard-ELI-Extracting-Profits-from-the-Public.pdf) · [E3 rate-drivers whitepaper (May 2026, Data Center Coalition-funded)](https://www.ethree.com/wp-content/uploads/2026/05/Understanding-the-Drivers-of-Rising-Electricity-Rates-and-the-Role-of-Data-Centers_E3-2026.pdf)
- [EPRI, Powering Intelligence 2026 update](https://restservice.epri.com/publicattachment/97025) and the [state-level dashboard](https://powering-intelligence.epri.com/dashboard/) (the map's footprint rings: per-state 2024 actuals + 2030 scenarios) · [NERC 2025 Long-Term Reliability Assessment](https://www.nerc.com/globalassets/our-work/assessments/nerc_ltra_2025.pdf) · [Grid Strategies, National Load Growth Report 2025](https://gridstrategiesllc.com/wp-content/uploads/Grid-Strategies-National-Load-Growth-Report-2025.pdf)
- [CBRE North America Data Center Trends H2 2025](https://www.cbre.com/press-releases/fast-growing-north-american-data-center-market-set-records-in-2025) — vacancy and preleasing
- [Loudoun County budget compilation (Loudoun Coalition, Oct 2025)](https://loudouncoalition.org/wp-content/uploads/2025/10/Loudouns-Fiscal-Strategy-FY27-FY30-FINAL.pdf), cross-checked with the [county's own data center FAQ](https://www.loudoun.gov/), and [Data Center Dynamics on the June 2026 assessment shortfall](https://www.datacenterdynamics.com/en/news/loudoun-county-budget-hit-by-data-center-60m-tax-revenue-shortfall/)
- [El Paso Matters on the Meta campus tax terms (May 2026)](https://elpasomatters.org/2026/05/31/how-much-will-meta-data-center-el-paso-texas-pay-in-property-taxes/) · [Morrow County enterprise-zone reporting (Baker City Herald, 2023)](https://bakercityherald.com/2023/05/11/morrow-county-approves-1-billion-in-tax-breaks-for-amazon-data-centers/) · [Washington DOR Data Center Workgroup findings (Oct 2025)](https://dor.wa.gov/sites/default/files/2025-10/DataCenterWorkgroup_AdoptedFindingsMeeting5.pdf)
- [Chester + Montgomery County PA Data Center Ordinance Guide v1.0 (Apr 2026)](https://files.dep.state.pa.us/PublicParticipation/Citizens%20Advisory%20Council/CACPortalFiles/Meetings/2026_05/2026%20Data%20Center%20Ordinance%20Guide.pdf) · [NACo county considerations primer (Feb 2026)](https://www.naco.org/resource/naco-informational-primer-and-county-considerations-data-centers)
- [Wisconsin Watch on the DeForest deal terms and collapse (Aug 2026)](https://wisconsinwatch.org/2026/08/wisconsin-deforest-data-center-deal-guaranteed-tax-revenue-river-improvements-affordable-housing/) · [Star Tribune on NDA and shell-company practices](https://www.startribune.com/ndas-code-names-and-shell-companies-how-minnesota-officials-support-data-center-secrecy/601499182)
- [NY Executive Order 62 (July 2026)](https://www.governor.ny.gov/executive-order/no-62-establishing-temporary-moratorium-data-centers-new-york-while-state-develops) · [Maine Morning Star on the LD 307 veto (Apr 2026)](https://mainemorningstar.com/2026/04/29/despite-initial-support-legislature-fails-to-override-mills-veto-of-landmark-data-center-ban/)
- [Texas Tribune on the exemption's cost (Apr 2026)](https://www.texastribune.org/2026/04/08/texas-data-centers-sales-tax-break-billion-dollars/) · [NCSL, Data Centers: Legislative Trends (May 2026)](https://static.legmt.gov/Divisions/LFD/Committees/MARA/NCSL-Data-Centers-Legislative-Trends-May2026.pdf)
- Outcome-trace project sources: one or more per project, in the downloadable dataset.

</details>
`;
