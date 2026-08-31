const content = `
## We all pay for New York City through real estate taxes

Property tax is the single largest source of revenue for the City of New York, roughly a third of the General Fund. That share has held more or less steady for decades while sales and income tax revenue swing with the business cycle. It is also the most local, most political, and most opaque tax most New Yorkers will ever pay. Renters pay it indirectly through their rent. Owners pay it directly, but rarely understand why their bill is what it is. Businesses pay it at rates that are several times higher per square foot than the brownstone next door, and that gap has consequences for what gets built and where.

In 1981, the State Legislature passed S7000A, a law that capped how fast NYC home assessments (and therefore tax bills) could rise. The original logic was sound: if a therapist and a doctor bought a Brooklyn brownstone in 1985, you probably don't want them taxed out of the neighborhood forty years later just because the house appreciated to \\$5M. That's a real social choice. But forty-five years on, the cumulative shape of that choice has turned strange. Strange enough to warrant a map. Look at your block.

The map below shows ~860,000 taxable parcels across the five boroughs, colored by what each one pays. Click any building to see its assessed value, DOF market value, building class, and effective tax rate, and toggle between five views: tax per square foot, DOF market value, effective rate vs the citywide median, effective rate vs similar buildings, and abatement intensity. If you want to use this for work or for fun, all the code is linked at the bottom.

## How NYC property tax actually works

The fastest way to understand the system is to walk one specific building's tax bill from top to bottom. Then we'll widen out to the building types you'd recognize on any block, and where each one ends up.

### One brownstone's tax bill

A 3-family brownstone on Hicks Street in Brooklyn Heights. Real building (BBL 3002300015, "112 Hicks Street"), real DOF numbers, made-up owners.

Imagine the Smiths bought it for \\$400,000 in 1992. Today the city's Department of Finance (DOF) values the building at **\\$5.49 million**.

A simple percentage of that market value would set the tax bill. The state law says: for a 1–3 family home (the city calls these "Class 1"), the **assessed value** is 6% of the market value. So if the system worked the obvious way, the assessed value would be \\$329,400, and the Class 1 tax rate would produce a bill of about **\\$66,000 per year**.

The Smiths' actual bill is less than half of that, at **about \\$30,000 per year**.

The difference is the **assessment cap**. Under a 1981 state law (formally, S7000A), the city can't raise a Class 1 parcel's assessed value by more than 6% in a single year, or 20% over five years, even if the building's market value triples. The Smiths' assessed value in 1992 was probably around \\$24,000 (6% of \\$400K). It has crept up year after year, but it has crept; it never caught up to the underlying market. Today the cap holds it at roughly \\$150,000, about 2.7% of the building's actual value, when the law's headline number is 6%.

That gap between "the formula says 6%" and "the cap holds it at 2.7%" is the shape of the rest of the map. Every building type bumps into it differently.

### A field guide to NYC buildings, by tax outcome

This is what's actually on the map, sorted from biggest tax break to highest tax burden. Numbers are citywide medians from the FY24/25 DOF data the map uses.

| Type of building | Units | Approx count | Typical \\$/sqft per year | Typical effective rate | Verdict |
|---|---|---|---|---|---|
| **1–3 family townhouse / brownstone** (Class 1) | 1–3 | ~566,000 | ~\\$4 | **0.78%** | **The biggest break by scale.** Cap is doing the work. |
| **Abated tower** (421-a / 485-x; Class 2 large, condo or rental) | 11+ | ~4,000 | **<\\$1** | **~0%** | **The biggest break per parcel, by design. Without it, almost no market-rate large rental gets built.** Hudson Yards, LIC, Downtown Brooklyn, Battery Park City. |
| **Walk-up apartment rental, small** (Class 2A/2B; small-cap protection) | 4–10 | ~50,000 | ~\\$4 | 1.99% | Mid-range. The 8%/year small-Class-2 cap helps. |
| **Walk-up co-op** (no elevator, building class C6/C7) | 4–10 | ~9,000 | ~\\$8 | **4.97%** | **Surprisingly hit hard.** Most don't qualify for the small-co-op cap, so they pay the full Class 2 rate without the assessment cap helping. |
| **Pre-war elevator co-op** (large, iconic UES / UWS / Brooklyn Heights kind) | 11+ | ~6,400 | ~\\$6 | **~5% (but misleading — see below)** | Class 2 large, no cap. The displayed rate is high mainly because DOF systematically undervalues large co-ops; the burden against true market value is much lower. This row deserves its own paragraph below. |
| **Older multifamily rental / unabated condo** (Class 2 large, D-class, no abatement) | 11+ | ~10,000 | ~\\$6 | **5.09%** | **Full freight, every year, forever.** The pre-war rental squeeze. |
| **Office tower** (Class 4) | n/a | ~7,000 | ~\\$9 | 4.46% | Standard Class 4. No cap. |
| **Mixed retail + apartments** (Class 4, store-front type) | mixed | ~19,000 | ~\\$9 | 4.43% | Same Class 4 rate as the Goldman Sachs floor. |
| **Hotel** (Class 4) | n/a | ~1,100 | ~\\$13 | 4.34% | Standard Class 4 + premium real estate. |

Two patterns jump out. First, a 5–7× spread in effective rate across types of building most New Yorkers think of as "kind of similar." Second, the *size* of a co-op flips its tax outcome: small walk-up co-ops pay close to 5%; the iconic pre-war elevator co-ops along the Upper East and West Sides pay something quite different, but how different is genuinely complicated.

The whole table in one line: **the cap protects long-tenured owners; abatements protect new construction; everyone in the middle pays full Class 2 or Class 4 freight.** Co-ops are the one row where that summary breaks down. Worth a longer look.

### The curious case of the pre-war elevator co-op

These are the buildings most non-New-Yorkers picture when they imagine "Manhattan apartments": the Dakota, the San Remo, 740 Park, the Apthorp, hundreds like them. They run from 30 to 300+ units, mostly built between 1900 and 1940. They're Class 2 large for tax purposes, which means **no assessment cap**, and the headline math (~10.7% × 45% of market value = ~4.8% effective) should apply uniformly. Against DOF's published market value, that's roughly what shows up on the map: a median displayed rate around 5%.

But DOF's market value for these buildings is famously, systematically low. DOF values co-ops two ways: stock-sale comparison (matching share sales across similar buildings) and income capitalization (treating the building as a hypothetical rental). Both methods chronically lag what apartments actually trade for. A 4-bedroom in the San Remo that sold in 2023 for \\$15M will show up in DOF's books at maybe \\$5–7M for the underlying share. Aggregate the building and the DOF market value runs roughly 2–3× lower than what the unit sales imply.

So the **displayed effective rate is misleading on the high side**: ~5% mechanically, but probably 1.5–2.5% against true market value. That puts these buildings in the same general neighborhood as a long-tenured Class 1 brownstone owner: different mechanism, similar outcome.

This row of the map is the only one in the typology where the data lies to you. Everywhere else, displayed effective rate is reasonably close to real burden. Here, real burdens can run 2–3× lower than the headline Class 2 math implies, and the gap isn't uniform across the row. Treat the displayed rate as a flag, not a fact. A future version of this map will run a sales-based correction for the co-op denominator and surface a "true rate" toggle; that's the Phase A.5 work in the methodology note.

## Reading the map

**Zoom in.** Most of the interesting variation is at the block scale, not the city scale; from far out Manhattan reads as a single blue mass and Brooklyn as a single brown one, but a block of Brooklyn Heights or the Upper East Side at zoom-15 has half a dozen distinct tax stories on it. Click any parcel for the full numbers.

The default view shades each parcel by **annual property tax per square foot of building**, the cleanest single number for "how heavily is this parcel actually taxed." Cool blue = light per-sqft burden, deep blue = heavy. The other four mode buttons slice the same data different ways: DOF market value, effective rate vs the citywide median (cobalt = below, amber = above), effective rate vs buildings of the same class, and abatement intensity. The "vs similar buildings" mode is the analytically interesting one: it separates over-paying new buyers from under-paying long-tenured owners by lighting them up in opposite colors.

<nyc-tax-map></nyc-tax-map>

A few things worth zooming into:

- **Within a single block, the same kind of building can pay 5–10× different per-square-foot rates.** The story isn't really citywide or neighborhood-vs-neighborhood: it's *block-by-block*. Pick any "fancy" zip code and zoom in on the \\$/sqft view. Brooklyn Heights between Hicks and Henry, on Pierrepont/Remsen/Montague: a long-tenured Class 1 brownstone with the assessment cap fully bitten pays maybe \\$1–2/sqft per year. Two doors down, a Class 2 large rental or a newer condo pays \\$8–15/sqft. Same block, same desirability, same neighbors, wildly different burden because of building form and how long the current owner has been there. The cap doesn't lower taxes for the neighborhood; it lowers them for one specific kind of owner inside that neighborhood.
- **Manhattan as a wall of high \\$/sqft commercial.** Midtown and Lower Manhattan light up uniformly in the \\$/sqft view; that's the Class 4 effective rate (~4.5%) applied to dense, valuable buildings. The exceptions are interesting: a few co-op blocks (Class 2C) read much lighter, which is the DOF MV understatement showing up rather than a real tax break.
- **The brownstone belt.** Park Slope, Bed-Stuy, much of Crown Heights, Carroll Gardens: long stretches of cool-toned 1-3 family homes paying \\$1–3/sqft. These are the structural Class-1-cap winners.

## What incentives does this system create?

Most NYC real estate pays roughly 5% of its market value in tax every year. Class 2 large rentals, Class 4 commercial, all of it sits near that line. That's the legal baseline.

The interesting question is why some specific buildings pay so much less than that, and what behavior those exceptions encourage. Two carve-outs from the baseline shape almost everything we see on the map: which buildings get built, who sells and who holds, where capital goes, which kinds of business survive in storefronts. Each was created on purpose, for a different reason, and they have very different defenses.

**Carve-out one: the 1981 assessment cap** (Class 1 + small Class 2).

The cap is the single biggest reason the brownstone belt is the deep-blue mass on the map. A 1992 buyer in Park Slope and a 2024 buyer in Park Slope, in the same kind of building on the same block, can have bills that differ by a factor of three.

**Carve-out two: tax abatements for new construction** (421-a, 485-x, J-51, ICAP, etc.).

These do the opposite: forward-looking, designed to make new multifamily construction pencil despite the underlying Class 2 large rate. Without them, almost no market-rate large rental gets built in NYC.

**Everyone outside the carve-outs pays the headline rate.**

Pre-war rental landlords whose abatement expired. Co-op shareholders in buildings classed as Class 2 large (most of the iconic UES / UWS / Brooklyn Heights towers, with the methodology caveat from section 3). Walk-up co-ops that don't qualify for 2C status. Office and retail Class 4. Independent storefronts paying the same Class 4 rate as the Goldman Sachs floor above them. They pay roughly 4–5% of market value every year, forever. That is the *baseline* most of the city operates under; the carve-outs bend the math in two specific directions, but most parcels feel none of them.

You can read all of this off the map directly. Switch to **\\$/sqft**, zoom into any pre-war Brooklyn block, and the pattern shows up at the block scale: a long-tenured brownstone at \\$1–2/sqft (carve-out one), a 2018 abated rental tower at \\$1–2/sqft (carve-out two), an unabated 1980s rental next door at \\$8–12/sqft (no carve-out), a Class 4 retail strip at \\$10–15/sqft (no carve-out). Same block, two carve-outs, two different baselines.

The downstream consequences are visible if you know where to look:

- **What gets built.** Private developers in NYC essentially build two things now: luxury condos (sold to Class 1 / 1C buyers who'll benefit from the cap going forward) and abated rental towers. The unabated, market-rate, mid-rise rental that dominated pre-war NYC construction is largely no longer a viable building type. That isn't *only* a tax-policy story (land prices and construction costs do most of the work), but the property-tax piece is the marginal factor that decides go/no-go on a meaningful share of projects.
- **Where it gets built.** The abatement programs are essentially zoning-driven. The map's "abatement intensity" view traces the city's recent rezoning history pretty precisely: Williamsburg, Long Island City, Hudson Yards, Downtown Brooklyn, parts of the South Bronx along the Concourse. Where the city upzoned and offered abatements, towers went up; where it didn't, almost nothing did.
- **Who stays put.** The cap creates a powerful "don't sell" incentive for existing Class 1 owners. Selling resets the assessment, and the buyer's bill is several multiples higher than the seller's. That is part of why long-tenured homeowners in fast-gentrifying Brooklyn neighborhoods pay so little, and part of why "cash out and move" is economically punishing for the next generation if they inherit and choose to stay.

Every piece of this system is a narrowly-targeted exception to a more general rule. Each tool was added to solve a specific problem: *Hellerstein* in 1981, the 1970s fiscal crisis, the post-1990s housing shortage. Each carved a particular building form out of the cliff. The cumulative shape on the map is the result.

## What's been proposed

Every reform of this system makes someone worse off who is plausibly sympathetic. That is the constraint that makes the politics so hard, not the technical complexity. The technical answers have been clear for decades — the Furman Center, IBO, and the 2021 NYC Advisory Commission on Property Tax Reform have all proposed substantively similar reform packages. Almost none of it has moved.

Three reform directions, in roughly increasing order of political difficulty.

### 1. Tighten the abatement programs

The reform proposal: shorten the abatement window, reduce the percentage exemption, and require deeper affordability inclusion. The cost falls on developers and on the future trajectory of multifamily supply, not on existing residents. The substantive disagreement is whether NYC in 2026 still needs the subsidy as broadly as it did in 1971 — defenders argue it's still what moves the marginal project from "won't pencil" to "will pencil"; critics argue that's true mainly in places that haven't been rezoned yet.

Either way, this wouldn't move the structural numbers in the map visibly. It just slows further accumulation of abated stock. The 2024 transition from 421-a to 485-x was a (partial) tightening exercise in this spirit, and abatement reform is the piece with the most actual legislative path of the three.

### 2. Phase out the Class 1 assessment cap, paired with a circuit breaker

Stop using the assessment cap. Every Class 1 home would be taxed at the full statutory rate against its actual market value, the way Class 2 large and Class 4 buildings already are. The deep blue mass on the map would lighten significantly. Many homeowners would see meaningful tax increases, especially in the neighborhoods that have appreciated most over the last thirty years.

This was the 2021 NYC Advisory Commission on Property Tax Reform's central recommendation, and the only reform that directly addresses the cross-neighborhood pattern the rest of this post describes, since that pattern is what the cap produces.

There's a real argument *for* keeping the cap that the technocratic reform analyses tend to skip. The cap is, in effect, a tax break for people who've lived somewhere a long time, paid for by people who arrived more recently — a tax on neighborhood transplants. On those terms, a lot of New Yorkers would defend it: it protects incumbents from being displaced by their own appreciating real estate, and shifts the cost onto whoever moved in last and is driving the appreciation. Whether that's good tax policy depends on what you think the property tax should be doing.

If you do want to phase out the cap, the trade-off on the other side is unmissable. A long-tenured Bed-Stuy homeowner currently protected by the cap (often on a fixed retirement income) would suddenly see a tax bill several times larger than what she's used to paying. "Phase out the cap" with nothing else attached is a tax hike on the most sympathetic group of homeowners in the city, and is therefore politically very hard.

The proposal usually paired with cap removal is a **circuit breaker**: an income-tested cap on the bill, along the lines of "no household earning under \\$X pays more than 6–8% of their income in property tax." The household applies once a year, the city verifies income (the way it already does for STAR), and the bill gets clipped at the affordability threshold. Whatever the homeowner can't pay gets deferred to the property's eventual sale, or covered by the city as an offset.

The design logic of pairing the two is that the fiscal cost stays small. The wealthiest Class 1 owners (the brownstone owner whose house appreciated to \\$5M and has high household income) currently capture the *largest* dollar value of cap benefit. They wouldn't qualify for the circuit breaker. So the circuit breaker concentrates relief on the long-tenured fixed-income households who would otherwise be hit hardest, while everyone else who can afford to pay full freight starts paying full freight. The books roughly balance: more revenue from high-income capped owners, mostly offset by relief paid to low-income capped owners.

Without the circuit breaker, cap-phase-out has no path. With it, you arrive at a system fiscally similar to current practice for fixed-income households and substantially more progressive for everyone else.

### A wrinkle worth its own post

DOF's income approach for Class 2 large rentals systematically assesses regulated buildings below their actual sale prices. In ~5,400 arms-length deeds 2017–2025, DOF MV ran 38–60% of sale price the entire window, even after the 2019 Housing Stability and Tenant Protection Act (HSTPA) crashed stabilized sale prices ~30–50%. The implicit tax break is plausibly what keeps regulated-rental operating economics viable; HSTPA cut these buildings' exit value but didn't touch the operating side. Whether that implicit subsidy should be unwound, or whether it's already self-correcting as sale prices fall toward DOF MV, is its own post.

### Why none of this has happened

The system hasn't been reformed because the New York City Council, and more importantly the State Senate's downstate delegation (which holds the legal authority over assessment caps via S7000A), both answer to constituencies that on average benefit from the current setup. Class 1 owner-occupants are concentrated in identifiable neighborhoods, organized through homeowner associations, and high-turnout. Class 2 large renters and small commercial tenants are diffuse, less organized, much lower-turnout, and frequently not even aware that their rent or lease is partially a property-tax payment. The mystery isn't why nothing has moved; it's what would force movement. The honest answer is either a fiscal crisis severe enough to force the State Senate's hand, or a genuinely competitive Class 1 voting bloc that doesn't currently exist.

If you live in the cool-blue parts of the map above, your representatives are doing what their constituency wants. That's not a moral indictment, just how the math of this particular electorate works out.

---

*The data behind this map: NYC DCP MapPLUTO 25v4 (geometry) + NYC DOF Property Valuation and Assessment Data, dataset 8y4t-faws (current market values, assessments, exemptions). NTA boundary medians via NYC Open Data 9nt8-h7nd. Address geocoding via [NYC PAD geosearch](https://geosearch.planninglabs.nyc/). The data-prep pipeline is in [\`gizmos/nyc-property-tax-map/pipeline\`](https://github.com/eichenbaumj/gizmo-warehouse/tree/main/gizmos/nyc-property-tax-map/pipeline). Tax rates verified against NYC Open Data \`7zb8-7bpk\` (FY24/25).*

<details>
<summary><strong>Methodology + caveats</strong> (click to expand)</summary>

**The denominator.** The "rate" used throughout this post is each parcel's annual tax bill divided by DOF's published Market Value (the FULLVAL field), pulled from the FY24/25 DOF Property Valuation and Assessment Data (NYC Open Data dataset \`8y4t-faws\`). This is the same denominator Furman, IBO, and the 2021 NYC Advisory Commission on Property Tax Reform all use.

**The numerator.** The bill is computed as (billable assessed value − billable exempt) × statutory rate for the parcel's tax class. This captures the major pre-bill exemptions (421-a, 485-x, and similar that reduce the taxable AV directly). It still misses post-bill dollar abatements (ICAP, SCHE/DHE, some J-51 forms) which are credited as a flat amount after the rate is applied; those can show ~5–10% divergence from DOF's published bill on affected parcels.

**Co-op denominators are systematically low.** DOF's stock-comparison method for valuing co-ops chronically lags actual unit sales — see "The curious case of the pre-war elevator co-op" earlier in the post. A 4-unit Brooklyn Heights co-op might be filed at \\$1.3M when individual unit sales suggest \\$5M+. That makes the co-op effective rates on the map look mechanically high. A future version will run a sales-based correction and surface a "true rate" toggle.

**Condos are aggregated to the building.** DOF lists each condo unit, garage space, and storage room as a separate parcel with its own BBL and tax bill. The map combines all of those records into a single building-level total at the lot polygon, so clicking 7 Hubert Street shows what the whole building pays per year, not what one apartment pays. About 10,700 condos citywide are aggregated this way (~2.6 million unit-level DOF records rolled up). Multi-tower complexes that share one condo declaration (Yorkville Towers, Tribeca Green, etc.) are split proportionally by building area across their lot polygons. Without this aggregation step, condo lots would render as blank polygons in any neighborhood with significant condo conversion (Tribeca, SoHo, Hudson Square, parts of UWS / DUMBO / Williamsburg / FiDi).

**What's hidden from the map.** Parcels that are legally tax-exempt and would otherwise produce visual artifacts are filtered out. This includes parks (Prospect Park, Greenwood Cemetery), MTA transit yards, churches and other religious buildings, public schools and most colleges, hospitals, libraries, post offices, and similar government buildings, plus vacant lots and Class 3 utility special franchises. They're real *parcels* but not real *taxpayers* in any meaningful sense; including them at, say, \\$200/sqft (because a tiny maintenance shed divides a millions-of-dollars market value) makes the visualization misleading. Abated 421-a / 485-x towers, by contrast, *are* kept on the map: they're real taxpayers paying reduced amounts, and they're central to the story.

**Tax-class subclass labels.** I generally don't surface the full class system (1, 1A–D, 2, 2A–C, 3, 4) in the popup — most readers don't need it. The translation in the popup is a best-effort plain-English label based on the DOF building class code. A few buildings will be mislabeled as a result; please email me if you spot one.

</details>
`;

export default content;
