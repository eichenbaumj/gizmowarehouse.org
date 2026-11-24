// "Do Data Centers Raise Your Electric Bill?" Every result figure below is copied from the saved
// result records in gizmos/data-center-utility-bills/data/results/session28_uc and was checked
// phrase by phrase against them before publication. The long version is
// gizmos/data-center-utility-bills/TECHNICAL.md, served at /gizmo/data-center-utility-bills/methodology.
const A = "/assets/data-center-utility-bills";

const fig = (file: string, w: number, h: number, alt: string, caption: string) =>
  `<figure class="not-prose my-8"><img src="${A}/${file}" width="${w}" height="${h}" loading="lazy" alt="${alt}" class="w-full h-auto rounded-md border border-slate-200 bg-white" /><figcaption class="mt-2 text-sm text-steel">${caption}</figcaption></figure>`;

const quote = (text: string, who: string, source: string) =>
  `<figure class="rounded-md border-l-4 border-cobalt bg-slate-50 px-5 py-4"><blockquote class="font-serif text-lg leading-snug text-charcoal">${text}</blockquote><figcaption class="mt-3 text-sm text-steel">${who}, ${source}</figcaption></figure>`;

const link = (href: string, text: string) =>
  `<a class="text-carolina hover:underline" href="${href}">${text}</a>`;

const aside = (html: string) =>
  `<p class="not-prose my-6 border-l-2 border-carolina/50 pl-4 text-sm leading-relaxed text-steel">${html}</p>`;

export default `
## The one thing everyone agrees on

It is hard to find a subject where Senator Sanders and President Trump sound alike. The relationship between data centers and your electric bill might be the firmest common ground in America.

<div class="not-prose my-8 grid gap-4 sm:grid-cols-2">
${quote("“I never want Americans to pay higher Electricity bills because of Data Centers.”", "<strong>President Trump</strong> (R)", link("https://truthsocial.com/@realDonaldTrump/115884759090137876", "Truth Social, January 12, 2026"))}
${quote("“…data centers will have a profound impact on land and water use, and will drive up electricity costs.”", "<strong>Senator Sanders</strong> (I-Vt.)", link("https://www.sanders.senate.gov/press-releases/news-sanders-yes-we-need-a-moratorium-on-data-center-construction/", "statement, February 23, 2026"))}
${quote("“American families should not have to shoulder the burden of the rising electricity costs produced by data centers in Missouri and across the country. This is unacceptable.”", "<strong>Senator Hawley</strong> (R-Mo.)", link("https://www.hawley.senate.gov/hawley-blumenthal-introduce-bill-to-prevent-data-centers-from-increasing-electricity-costs-for-americans", "press release, February 11, 2026"))}
${quote("“…driving up demand and causing Americans’ energy bills to skyrocket.”", "<strong>Senator Blumenthal</strong> (D-Conn.), on the build-out of data centers", link("https://www.blumenthal.senate.gov/newsroom/press/release/blumenthal-introduces-bill-to-protect-americans-from-increasing-electricity-costs", "press release, February 12, 2026"))}
${quote("A new Florida law “prevents data center costs from being passed on to consumers, including electricity costs.”", "<strong>Governor DeSantis</strong> (R-Fla.)", link("https://www.flgov.com/eog/news/press/2026/governor-ron-desantis-signs-law-protect-floridians-subsidizing-data-centers", "signing statement, May 7, 2026"))}
${quote("“We have seen […] data center construction inflate electric bills in communities across the country.”", "<strong>Representative Ocasio-Cortez</strong> (D-N.Y.)", link("https://www.sanders.senate.gov/press-releases/news-sanders-ocasio-cortez-announce-ai-data-center-moratorium-act/", "press release, March 25, 2026"))}
</div>

Voters seem to agree. In a Pew Research Center survey in March 2026, three in four Americans said their home energy costs had gone up. Among those people, 43% called data centers a major reason ([Pew topline](https://www.pewresearch.org/wp-content/uploads/sites/20/2026/05/SR_26.05.01_home-insurance-energy_W189_topline_FINAL.pdf)).

The worry is reasonable and intuitive. A data center is an enormous customer. When one connects, the utility may have to build power lines, substations and power plants, and regulators can spread part of that cost across everybody. But an enormous customer also pays an enormous bill, and that money helps cover costs the utility would otherwise collect from households.

Either story could be true, and which one is true matters. If data centers raise families' electricity costs by a lot, the rules on who pays for the power lines and plants built to serve them need to get much tighter. If the increase is modest, it can be measured, and that puts a ceiling on what developers would owe the households around them to make up for it.

I tried to come up with the most rigorous answer I could.

## The short answer

<div class="not-prose my-8 rounded-md border border-cobalt/30 bg-cobalt/5 p-6">
<p class="font-serif text-xl font-bold leading-snug text-cobalt sm:text-2xl">From what I checked, data centers probably do not raise household electricity prices by more than 5%, and very unlikely by more than 10%.</p>
<p class="mt-4 leading-relaxed text-charcoal">At the seven utilities I could check most carefully, household prices ended up about 1.6% <em>lower</em> than at similar utilities without data centers, two to three years after data centers became a big customer. A gap that small is what you would expect from ordinary ups and downs, so I read it as no clear difference. In a wider, shakier group of 36 utilities, prices ended up about 3% higher, and there I cannot rule out a 5% rise. Neither group shows a sign of 10%.</p>
<p class="mt-4 text-sm leading-relaxed text-steel">“Probably” and “very unlikely” are my judgment from the evidence below. They are not probabilities I calculated. The answer also has real limits, which get ${link("#what-this-does-not-tell-you", "their own section")}.</p>
</div>

## 2,244 data centers

I started by finding every data center in the United States that I could. I ended up with 2,244 of them, pulled from building permits, public maps, an industry tracker and my own state-by-state searches. Virginia has the most (395), then California (304) and Texas (211). This is a recent build-out. Of the data centers I could put a date on, about nine in ten opened in 2005 or later.

${fig("map_data_centers.png", 2000, 1260, "A map of the lower 48 states with one dot per data center. The densest clusters are northern Virginia, the Bay Area, Dallas, Phoenix, Chicago, Atlanta and the New York area. Darker dots mark data centers served by the seven utilities studied most closely, in Utah, Nevada, Arizona, New Mexico, Nebraska, Texas and Georgia.", "Each dot is one data center in my inventory. 2,218 of the 2,244 are shown. The rest are outside the lower 48 states or have no usable location. Dark blue marks the data centers served by the seven utilities I checked most carefully.")}

Then I asked a narrower question that public data can answer. Pick out the utilities where data centers went from a small customer to a big one. In the years right after, did household prices there move differently from prices at similar utilities where that never happened?

## I am not the first to ask

At least ten research papers in 2026 tried to measure the same thing. Most found small effects on household prices, somewhere between 1.5% lower and 2.1% higher. An [MIT working paper](https://ceepr.mit.edu/workingpaper/who-pays-for-growth-evidence-from-datacenters-and-the-grid/) by Meeks, Pless, Qi and Wang landed on 2.1% higher, which they put at about $3.21 a month. A [CEPR discussion paper](https://cepr.org/publications/dp21854) by Scalera, Bosetti and Pecci found much more, about 13% for every ten data centers in a utility's territory. The papers also disagree about where the effect shows up. Two find it at investor-owned utilities. One finds it only at co-ops and city-owned utilities.

The scariest numbers in the news come from somewhere else. They describe wholesale power markets, where utilities buy electricity, or they are forecasts. A [Dallas Fed working paper](https://www.dallasfed.org/research/papers/2026/wp2606) by Kay, Reaser and Taylor estimates that data centers raised wholesale prices 6.9% nationally in 2025. Wholesale power is one ingredient in a household bill. It is a different thing from the bill.

Most of these papers bought their lists of data centers from vendors and let a map decide which utility serves each one. I found this method useful, but incomplete. When I checked a map's answer by hand against utility and company documents, it was wrong for about one large data center in four. So I tied the big ones to their utilities by hand, used only public data, and wrote down my full plan before I looked at a single price.

## How I tested it

Find utilities where data centers became a big customer. Then see whether household prices there changed more than they did at look-alike utilities with no data centers.

### Step one. Find the moment data centers got big.

For every utility, I added up how much electricity its data centers used each year. I marked the first year that reached 2% of everything the utility sold. Forty-one utilities hit that mark between 2011 and 2022. Those are the ones I can test, because I can see their prices both before and after.

${fig("fig1_first_crossing.png", 2000, 1320, "Top: a schematic line showing data centers' share of a utility's electricity sales rising over ten years and crossing a dashed line at 2%. The year it crosses is year zero. Three years earlier is marked before, and two and three years later are marked after. Bottom: a row of dots showing the real year each of 41 utilities reached that mark between 2011 and 2022, with the seven checked most carefully highlighted.", "Top: an illustration with invented shapes. Bottom: the real years from my design files.")}

Two groups are left out. Thirty-two utilities were already past 2% before 2011, the utilities of northern Virginia among them, so there is no “before” to measure from. Twenty-one more crossed in 2023 or later, which is too recent to see what followed.

### Step two. Give each one ten look-alikes.

Electricity prices rise and fall for many reasons, like the price of natural gas, the weather, or a new rate decision. Most of those reasons hit every utility in the same part of the country. So each data center utility is compared with ten utilities from its own regional power market that are about the same size and have almost no data centers. Whatever hits the whole region hits both sides and cancels out.

${fig("fig2_one_host_ten_matches.png", 2000, 1240, "A schematic. One blue line for a data center utility and ten grey lines for similar utilities, with a dashed line for their average. The gap between the blue line and the dashed line in the after years is what the study measures.", "An illustration with invented shapes. No real utility’s prices are drawn here.")}

### Step three. Compare the change, before and after.

I do not ask whether the data center utility is more expensive than its look-alikes. Some utilities are always pricier than others. I ask whether its price *changed* more than theirs did, from three years before data centers got big to two to three years after. Each utility gets its own comparison, and then I average them. Every utility counts once, whatever its size.

${fig("fig3_seven_timeline.png", 2000, 1320, "Seven utilities, each shown as a row of ten years. In each row one square marks the year data centers reached 2% of the utility's electricity sales, between 2015 and 2021. A darker square three years earlier is the before price and two squares two and three years later are the after prices.", "The seven utilities and their years are real.")}

### Step four. Report a range along with the number.

With only a handful of utilities, ordinary bounce in prices can produce a gap of a few percent with no data center involved. So every number here comes with a range. My range is built so that ranges made this way catch the true answer about nine times in ten. I tested that claim before looking at any real result, on made-up prices where I knew the true answer. The range missed at most 9.9% of the time.

${fig("fig4_what_a_range_is.png", 2000, 980, "Ten imagined repetitions of a study, each with a dot and a bar. Nine bars cover the true answer and one misses it.", "An illustration with invented shapes.")}

So a value outside my range is unlikely, but it is not impossible.

${aside("“Price” here means what a utility collects from households for each kilowatt-hour it sells them. It comes from a yearly federal survey of every utility (the Energy Information Administration’s Form EIA-861), for 2001 through 2025. It is not the rate printed on a rate sheet and it is not the monthly bill.")}

## What I found

${fig("fig5_result_seven_and_36.png", 2000, 1040, "Two estimates with ranges. The seven utilities checked most carefully: 1.6% lower, with a range from 7.1% lower to 4.2% higher. All 36 utilities analyzed: 3.1% higher, with a range from 0.7% lower to 7.0% higher. Reference lines mark no difference, 5% and 10%.", "Real results. The same numbers are in the table below.")}

<div class="overflow-x-auto">

| Group of utilities | Best estimate | Range | Is a 5% rise inside the range? | Is 10%? |
|---|---|---|---|---|
| **The seven I checked most carefully** | 1.6% lower | 7.1% lower to 4.2% higher | No, by a little | No |
| All 36 I could analyze (includes the seven) | 3.1% higher | 0.7% lower to 7.0% higher | Yes | No |

</div>

**At the seven utilities I checked most carefully,** household prices changed by about 1.6% *less* than prices at their look-alikes. The range runs from 7.1% less to 4.2% more. No difference at all sits comfortably inside that range. A 5% rise sits just outside it, and a 10% rise sits far outside.

**Across all 36 utilities,** prices changed by about 3.1% *more* than at their look-alikes, with a range from 0.7% less to 7.0% more. No difference is inside that range too. So is 5%. Ten percent is outside.

Price is only half of a bill. A bill is price times how much electricity a household uses. At the same seven utilities, the average household bill ended up about 3.5% lower than at the look-alikes (range: 8.8% lower to 2.1% higher). My method was tested for price and not for bills, so I hold that one more loosely.

### Why there are two groups

${fig("fig6_seven_and_36.png", 2000, 919, "Forty-one dots in four groups: 7 checked most carefully, 10 where it is unclear which utility serves the data centers, 19 where the opening date or size is unclear, and 5 that could not be analyzed. The first three groups together are the 36.", "Real counts from my design files.")}

Everything in this study depends on two facts about each data center. Which utility sells it power, and when did it switch on? Both are harder to pin down than they sound. A campus can sit on the border between two utilities. A building permit can come years before the servers are running.

Before looking at any prices, I wrote rules for which utilities I was sure enough about. Seven passed every rule. As a stress test I shuffled the opening dates by the size of typical permit errors. The key year stayed the same 95.5% of the time for the seven and 53.8% of the time for the wider group.

That makes the seven my most trustworthy comparison, and also a small and hand-picked one. They were chosen by what I could verify, not at random, and I do not know whether they are typical. The 36 are broader and shakier, and some of their dates or utilities are probably wrong. The two groups give different answers on 5%, and I do not know why. They also overlap, because the seven are inside the 36. Their agreement on 10% is one body of evidence read two ways. It is not two separate confirmations.

## What would it cost to keep households whole?

Here is another way to read these numbers. Suppose data centers did raise household prices by as much as my ranges allow. What would it take to pay households back?

Take a household with a $150 monthly electric bill, the yardstick my plan used.

<div class="overflow-x-auto">

| If prices rose by | That household pays an extra | Per year |
|---|---|---|
| 4.2% (the top of my range for the seven) | about $6.40 a month | about $76 |
| 5% | $7.50 a month | $90 |
| 7.0% (the top of my range for the 36) | about $10.50 a month | about $126 |
| 10% | $15 a month | $180 |

</div>

Now scale it up. The seven utilities serve about 3.4 million households. Paying every one of them back for a 5% rise would cost about $305 million a year. The data centers at those seven utilities use about 8,000 gigawatt-hours of electricity a year by my count. Spread across that, the payback comes to a little under 4 cents on every kilowatt-hour the data centers use. For a 10% rise, double it to about $610 million a year, or 7.6 cents per kilowatt-hour.

For scale, industrial customers in the United States paid 8.51 cents per kilowatt-hour on average in 2025 ([Energy Information Administration](https://www.eia.gov/electricity/annual/html/epa_02_10.html)). So a 5% rise in household prices would be worth close to half of what a typical industrial customer pays for power, and a 10% rise would be worth nearly all of it.

That is the price of the worst case. My best estimate for the seven is that there was nothing to pay back, and my range puts the most it could plausibly have been at about $260 million a year across those 3.4 million households.

### Could data centers afford that?

Probably, though it depends on the data center.

For the big AI data centers going up today, I used a [cost model](https://epoch.ai/data-insights/ai-datacenter-cost-breakdown) published by Epoch AI, a research group, and built by Amelia Michael and Ben Cottier. It puts a new one-gigawatt AI data center at about $8.5 billion a year to own and run. Chips and servers are 60% of that. Electricity is about $600 million, or 7 cents of every dollar. Paying households back for a 5% rise, at the rate I worked out above, would add about $270 million a year. That is about 3 cents on top of every dollar the data center already spends. Paying back a 10% rise would add about 6 cents. I have not seen any one project's books, but a cost that size is unlikely to decide whether a project like that gets built.

Older, conventional data centers have less room. Landlords in the biggest markets ask about $196 per kilowatt per month for space in one ([CBRE](https://www.cbre.com/insights/books/north-america-data-center-trends-h2-2025)). The same 5% payback would come to about 11% of that rent, and a 10% payback to about 23%. That is a real cost. If it arrived through the power bill, most of it would land on the tenants and not the landlord. Digital Realty, a large data center landlord, tells its investors that the vast majority of its utility costs are passed directly through to its customers ([2024 annual report](https://www.sec.gov/Archives/edgar/data/1297996/000155837025001424/dlr-20241231x10k.htm)).

It also depends on how many households there are for each data center. At the one utility among my seven where data centers were the biggest share of electricity sales, a 5% payback works out to about 1 cent for every kilowatt-hour the data centers use. At the two where they were the smallest share, it works out to about 8 cents, which is close to everything a typical industrial customer pays for power.

The largest companies have already promised something like it. In March 2026, Amazon, Google, Meta, Microsoft, OpenAI, Oracle and xAI signed a [White House pledge](https://www.whitehouse.gov/fact-sheets/2026/03/fact-sheet-president-donald-j-trump-advances-energy-affordability-with-the-ratepayer-protection-pledge/) to pay for the new power and the grid upgrades their data centers need, so that those costs are not passed on to households. The pledge is voluntary.

${aside("This section is arithmetic, not a finding. It applies one $150 bill to every household, and real bills at these utilities differ. The data center electricity use is my own estimate, and about half the data centers in my inventory have no size on record. The comparison with data center costs uses Epoch AI’s model of a new AI data center and quoted asking rents, not any company’s books, and it assumes a conventional data center draws power at the same rate as the one in that model.")}

## What Congress is doing about it

On November 19, 2026, the Senate passed the Bipartisan American Affordability and Jobs Act, known as BAAJA, by 62 to 33. It is not law. It still has to pass the House ([Senate Energy Committee release](https://www.energy.senate.gov/press/dem/heinrich-senate-passage-of-landmark-bipartisan-permitting-deal-will-lower-electricity-bills-hold-data-centers-accountable-create-over-one-hundred-thousand-jobs-reduce-carbon-emissions/); [Newsweek](https://www.newsweek.com/what-baaja-bill-means-data-centers-12746240)).

The bill goes at the same worry from the other end. It does not send households a check. According to its sponsors, it tells the Federal Energy Regulatory Commission to make utilities set rates so that large data centers “pay for both the cost of serving them and the grid upgrades needed to handle them” ([sponsor's fact sheet](https://www.energy.senate.gov/press/dem/fact-sheet-heinrich-details-how-bipartisan-american-affordability-jobs-act-holds-data-centers-accountable-lowers-utility-bills-for-american-families/)). The Bipartisan Policy Center reads it as making new data centers of 20 megawatts or more pay the full added cost of the power plants, storage and lines built to serve them ([explainer](https://bipartisanpolicy.org/explainer/explaining-the-affordability-in-the-bipartisan-american-affordability-and-jobs-act/)). The World Resources Institute says the latest version covers data centers of any size ([explainer](https://www.wri.org/insights/bipartisan-american-affordability-jobs-act-energy-permitting-bill-explained)). States could also put data centers in their own rate class and charge them more than it costs to serve them.

The money collected is meant to lower everyone else's rates. The fact sheet says states “can use” it that way. The Bipartisan Policy Center says the bill “would direct” it there. None of the summaries I read describes a direct payment from data centers to households.

The sponsors cite an outside estimate, from the Rhodium Group, that the whole bill would lower household electric bills by $50 to $78 a year by 2040. That is in the same range as the paybacks in my table above. It is a projection for the whole bill, most of which is about permitting, and it comes to me through the sponsor's office.

My study and the bill look in opposite directions. I measured what already happened at utilities where data centers arrived between 2011 and 2022. The bill writes rules for what gets built next. A small effect in the past does not settle what a much bigger build-out will do. The explainers also note what the bill leaves alone. Its effects depend on federal rules and state decisions that will take years, and it does not reach fuel prices.

${aside("I have not read the bill text. This section summarizes what the sponsors and three outside groups say about it, and those summaries do not fully agree with each other. It is not legal analysis.")}

## What this does not tell you

- **Nothing about costs shared across a whole region.** In some power markets, the cost of securing enough power plants is split among every utility in the region. If data centers push that cost up, the data center utilities and their look-alikes all pay it, and my comparison cannot see it. None of my seven is in PJM, the Mid-Atlantic market where this worry is sharpest. I planned a separate accounting of those regional costs and have not built it.
- **Nothing about the places with the most data centers.** Northern Virginia and other places that were full of data centers before 2011 are not in the test.
- **Nothing about the newest wave.** Utilities where data centers got big in 2023 or later, during the AI build-out, are too recent to measure.
- **Only the first two to three years.** Utility rates change slowly. For the five utilities with six years of data, the range was too wide to say much, from about 15% lower to 8.5% higher.
- **Seven is a small number.** In trial runs on stand-in data, a group this size reliably caught a rise only when it was about 10% or larger. It would often miss a true 5% rise.
- **The comparison rests on an assumption I cannot prove.** I assume that without data centers, prices at these utilities would have moved the way prices at their look-alikes did. A test on the years before found no sign of trouble. With seven utilities, that test would miss a good deal.
- **My inventory has holes.** About half of its 2,244 entries have no size, so they count for nothing. Some of my look-alike utilities may serve data centers I missed, which would blur the comparison.
- **My price is money collected per kilowatt-hour.** I planned to check it against published rate sheets. That check has not been done.
- **I have one method.** I planned to cross-check with a second statistical method. The software could not run it the way I specified, so that cross-check is missing.
- **I planned to study water bills too.** I could not find enough historical water rates to do it.

Put together, a small estimated difference does not prove that data centers leave household bills alone. What it shows is narrower. At the utilities I could measure best, in the first few years, compared with their neighbors, I did not find a large increase.

## How I tried to keep myself honest

I wrote down the full analysis plan and froze it in the project's own records. Only then did I look at prices for any utility with data centers. The plan was not registered with an outside body. I decided before seeing results that 5% and 10% were the sizes that would matter to a household, and I chose to lead this piece with those two sizes after I saw the results. Every analysis the plan listed that I built was run and is reported in the [technical version](/gizmo/data-center-utility-bills/methodology), including the ones that cut against the summary above. The pieces I did not build are named there too. The code, the frozen plan and the saved results are [on GitHub](https://github.com/eichenbaumj/gizmowarehouse.org/tree/main/gizmos/data-center-utility-bills).

### Who did the work

I built this with Claude, Anthropic's AI model, over more than thirty working sessions. Claude wrote the code, did the bulk of the research legwork, ran the tests and drafted this page with me. I set the question, made the calls on what counted and what didn't, and read the results. Wherever this piece says “I”, read it as the two of us. The mistakes are mine.

<p class="not-prose mt-8"><a class="inline-flex items-center gap-1.5 rounded-md bg-cobalt px-4 py-2 font-sans text-sm font-semibold text-white transition-colors hover:bg-cobalt/90" href="/gizmo/data-center-utility-bills/methodology">Read the technical version →</a></p>
`;
