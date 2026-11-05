// DRAFT v4 (2026-10-21; last third rebuilt around the courthouse and the mall). Prose is real text; numbers are {tokens}. Any remaining <hs-draft> slot carries a
// one-line brief; Joe writes the text. A brief may mention a number only through a {token} the preceding
// visual has already shown (tokens resolve against /data/<slug>/context.json). No em dashes. Tags are the
// hs-* registry in src/components/hoyt/hoytEmbeds.ts; each has a static stand-in in hoyt.static.tsx.
export default `
New York City is one of the safest big cities in the world, and by most measures it is about as safe as it has ever been. In 1990 New York had {opening.murders_1990} murders, more than six a day, and {opening.robberies_1990} robberies, one for every {opening.residents_per_robbery_1990} residents and the highest robbery rate of any large American city. Thirty-five years later, in 2025, the city had [fewer than one murder a day](https://www.governor.ny.gov/news/safer-streets-governor-hochul-mayor-mamdani-police-commissioner-tisch-announce-crime-new-york) and a robbery rate in the middle of the pack of large American cities.

<hs-precinct-map></hs-precinct-map>

This progress was universal, if not evenly distributed. The map above shows every police precinct in the city and how its violent crime, counted as murder, robbery and felony assault, has changed since 1990. Of the {precincts.n_with_change} precincts with a 1990 line, 64 are down 60 percent or more. Three in the northeast Bronx are down only 19 to 26 percent, and the 123rd on Staten Island's South Shore is exactly where it was. Most New Yorkers are dramatically safer than they were in 1990, and nearly all New Yorkers are at least a little safer.

Aggregated tables tell us the scale of the story, but actual people live on blocks. The NYPD's public complaint data carries a location for every complaint from 2006 on, so that is the earliest we can start telling the story at a truly local level. A complaint, in NYPD's vocabulary, is a crime reported to or recorded by the police, with one incident per record. Dozens of communities have been transformed in the past twenty years.

And precincts do not tell anywhere near the full story. Take mine, the 84th. It covers quite a tapestry of northwestern Brooklyn: the tony streets of Brooklyn Heights, the selfie sticks of DUMBO, sleepy Vinegar Hill, the office towers of MetroTech, the brownstones and bars of Boerum Hill, all the way east to Flatbush Avenue.

<hs-scrolly stage="city" id="city">

<hs-step step="all">

Every 0.33-mile cell in the city, shaded by the violent complaints recorded inside it in 2024 and 2025. Murder, robbery and felony assault. The darkest of the three shades covers roughly the busiest tenth of the cells.

</hs-step>

<hs-step step="top20">

Violence is heavily concentrated in a small number of areas. About {improvers.area_pct_20:raw} percent of New York's land, just {improvers.cells_for_20pct} of the city's {improvers.n_cells} cells, holds 20 percent of its violent complaints. About {improvers.area_pct_half:raw} percent of the land, {improvers.cells_for_half} cells, holds half. Those {improvers.cells_for_half} cells are what is left on the map.

</hs-step>

<hs-step step="improvers">

Since {improvers.year_early:raw}, when the block-level data begins, some corners of the city have been transformed. {improvers.decline_1} in {improvers.decline_1_area} went from {improvers.decline_1_early} violent complaints in {improvers.year_early:raw} to {improvers.decline_1_late} in {improvers.year_late:raw}, {improvers.decline_2} in {improvers.decline_2_area} from {improvers.decline_2_early} to {improvers.decline_2_late}, and {improvers.decline_3} in {improvers.decline_3_area} from {improvers.decline_3_early} to {improvers.decline_3_late}. Citywide over the same span, robbery fell {improvers.city_robbery_change_pct_abs:raw} percent, felony assault rose {improvers.city_fel_assault_change_pct:raw} percent, and the total barely moved.

</hs-step>

<hs-step step="precinct">

Here is the 84th measured the same way. Violent crime in the precinct fell 72 percent from 1990 to {improvers.year_late:raw}, but it is up {improvers.p84_change_pct:raw} percent from {improvers.year_early:raw} to {improvers.year_late:raw}. The city overall has barely moved since {improvers.year_early:raw}. Within the precinct, {improvers.p84_n_up:raw} cells rose and {improvers.p84_n_down:raw} fell. One cell did most of the work: Downtown Brooklyn, from {improvers.this_cell_early} violent complaints in 2006 to {improvers.this_cell_late} in 2025.

</hs-step>

<hs-step step="dive">

The Downtown Brooklyn cell ranks #{cell.rank_all} of {cell.n_cells} citywide for 2024 and 2025, with {cell.count_2024_25} violent complaints in two years, behind only Times Square at {cell.times_square_count_2024_25}. Inside it: Fulton Mall, the Hoyt-Schermerhorn station and the courthouse on Schermerhorn Street.

</hs-step>


</hs-scrolly>

About {density.residents} people live in this cell, but {density.jobs} work here, and during the weekday the population booms at MetroTech, the courts and the stores. Per resident, the cell ranks #{density.rank_residents} of {density.n_cells_residents} in the city, about {density.per_1000_residents:raw} violent complaints a year for every 1,000 people who live there.

Many of those residents live in some of the most expensive new apartments in Brooklyn, a ten-minute walk from the quiet blocks of Brooklyn Heights. In the past year I have spoken with three couples with young children who moved out of this square, each naming crime and disorder as part of the reason. Counted by violent complaints per resident, the cell they left ranks #{density.rank_residents} of {density.n_cells_residents} in the city.

I focus on count rather than rate because I am as interested in perceptions of safety as I am in precise likelihoods of victimization. Rates are useful for comparing across cities, but a crowd does not shield you from your own feelings of discomfort on your own street. If violent disorder on a streetscape is palpable, it is no comfort that the people around you might be the victim instead.

Hover a cell for its count and rank, click to pin it, and zoom in until the complaints appear as dots sized by how many landed at each spot.

<hs-city-explore></hs-city-explore>

<hs-photo photo="arrive-fulton-east" bleed="true"></hs-photo>

We can walk through a typical month. This is all real data from {timelapse.month_name} {timelapse.year:raw}, as recorded by the NYPD. You can see, by time and by place, where crime piles up, and how that drives your perception of safety in the immediate surroundings.

<hs-timelapse>

<hs-step step="month">

Grey dots are larcenies and misdemeanor assaults; colored dots are the violent complaints. Watch where the grey piles up: two store corners on Fulton Street end the month holding 98 of the 163 larcenies and misdemeanor assaults in this circle. Every so often one of those piles turns a color, a shoplifting that became a robbery. The gold pile at Schermerhorn and Smith is 120 Schermerhorn, the Criminal Court and Central Booking, assaults recorded at the building's address at hours like 6am and 11pm, most likely inside it. The residential blocks south of Schermerhorn stay almost empty, and only two violent complaints land after 9pm. By the 31st: {timelapse.violent} violent complaints, {timelapse.petit_larceny} petit larcenies, {timelapse.grand_larceny} grand larcenies and {timelapse.misd_assault} misdemeanor assaults within 400 meters of the station.

</hs-step>

</hs-timelapse>

Violent complaints here happen disproportionately on weekday afternoons, when the stores are open and the courts are in session.

<hs-hour-bars></hs-hour-bars>

So why did this one cell climb while the rest of Brooklyn held steady? Most of the answer is two places a few hundred feet apart, a courthouse and a mall.

**The courthouse.** Brooklyn's Criminal Court and Central Booking sit at 120 Schermerhorn Street, and every arrest in the borough passes through the building. Four of every five assaults on an officer within 400 meters of the station are recorded at that address, along with a steady run of felony assaults, at hours like six in the morning and eleven at night, with no premise recorded. These almost certainly happen inside, in holding, in processing, in the hallways. They make up {core.courthouse_point_share_2024_25:%0} of the count that puts the cell at #{cell.rank_all}. Set that one address aside and the cell falls to #{cell.rank_no_courthouse}. It is also the one series still rising this year, with {h1.courthouse.2026} complaints in the first half of 2026 against {h1.courthouse.2025} and {h1.courthouse.2024} in the same months of 2025 and 2024.

<hs-rank-ladder></hs-rank-ladder>

<hs-photo photo="albee-square"></hs-photo>

**The mall.** City Point opened at Albee Square in 2016. Before it opened, the NYPD logged no more than {plaza.pl_pre_max} petit larcenies a year at this point. In 2017, the first full year, it logged {plaza.pl_2017}, and in 2024 it logged {plaza.pl_2024}. A small share of those thefts turn violent. Of the {plaza.violent_2024_25} violent complaints recorded here in 2024 and 2025, {plaza.robberies_2024_25} were robberies, and {plaza.shoplift_share_2024_25:%0} of those began as shoplifting. The other {plaza.assaults_2024_25} were felony assaults, {plaza.officer_assaults_2024_25} of them on officers. The busiest hour is {plaza.peak_hour_label}

<hs-ledger stop="s06"></hs-ledger>

The city's Human Resources Administration also listed an EBT card office at 227 Schermerhorn Street, steps from the station, from 2023 into 2025. Violence within 200 meters of it barely changed after it opened. Across the city, I compared the blocks around every HRA and Social Security office with similar shopping blocks and found no sign that the offices push crime onto nearby streets.


With the courthouse set aside, violent complaints within 400 meters of the station run at {index.core_ex_courthouse_2024_25_vs_2010s:1dp} times their 2010s level, while Brooklyn as a whole sits at {index.brooklyn_2024_25_vs_2010s:1dp}. Two kinds of crime account for the rise. Robberies in stores went from about {growth.retail_robbery_2010s:raw} a year in the 2010s to {growth.retail_robbery_2024_25:raw} a year in 2024 and 2025, and felony assaults went from about {growth.other_assault_2010s:raw} a year to {growth.other_assault_2024_25:raw}. Street robbery, the mugging most people picture when they think about crime, ran about {growth.street_robbery_2010s:raw} a year in the 2010s and {growth.street_robbery_2024_25:raw} a year in 2024 and 2025.

<hs-lines></hs-lines>

<hs-photo photo="close-stairs"></hs-photo>

I suspect two things could help.

**Weekday afternoons.** Violent complaints here peak on weekday afternoons. Only {clock.night_core_pct:raw} percent fall between 10 p.m. and 6 a.m., against {clock.night_city_pct:raw} percent citywide. Police and private security on Fulton Street should be heaviest then, at the City Point plaza and the two big store corners. I don't know how the NYPD schedules officers here now.

**The store doors.** Most of the rise is shoplifting that turns into robbery, and fights inside stores. That calls for security at the doors of the busiest stores and closer work between the stores and the 84th Precinct. Street robbery on the surrounding blocks has not risen, so more patrols there would not reach the problem.

So that is the trouble with Hoyt-Schermerhorn. Most of it is one courthouse and one mall, a short walk from some of the most expensive new apartments in Brooklyn.

<hs-methods-note></hs-methods-note>

<hs-downloads></hs-downloads>
`;
