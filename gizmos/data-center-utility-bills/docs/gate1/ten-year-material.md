# The ten-year material for Gate 1 (2026-11-14)

From load and sales only. No price was read. Nothing here is applied to anyone: the screen that decides the headline set is still D-20's at three and five years, as D-40's addendum left it until Joe confirms a rule. Numbers are from `data/frozen/ten_year_screen.json` (`pipeline/facilities/ten_year.py`).

The shifts start every still permit-dated site of 20 MW or more 3, 5 and 10 years before its permit-based year. There are 78 such sites carrying load (5,438 MW) on 35 utilities; 30 of them are filed as an update to an existing source.

## 1. What the ten-year screen moves

**Among hosts, at the 2% threshold.**

| | As built | 3 years earlier | 5 years earlier | 10 years earlier |
|---|---|---|---|---|
| Early hosts (before 2011) | 32 | 32 | 32 | 36 |
| Cohort utilities (2011 to 2022) | 42 | 46 | 46 | 42 |
| Late hosts | 21 | 18 | 18 | 18 |
| Utilities whose place changes | | 7 | 9 | 15 |

Nine utilities change place at three or five years (four of them cohort utilities); that is the standard screen. Six more change only at ten years, all six cohort utilities:

| Utility | As built | Ten years earlier | In the headline set today |
|---|---|---|---|
| Arizona Public Service | 2020 | 2015 | yes |
| Umatilla Electric Cooperative | 2013 | 2009, an early host | yes |
| Salt River Project | 2016 | 2013 | no (D-46, ruling 2) |
| Ohio Power | 2019 | 2017 | no (D-46, ruling 2) |
| Guadalupe Valley Electric Cooperative | 2021 | 2015 | no (unsettled on assignment) |
| Cheyenne Light | 2016 | 2012 | no (unsettled on assignment) |

So with the ten-year case as a screen the headline set would be 9 hosts and not 11: Arizona Public Service and Umatilla would leave. At 5% three utilities move only at ten years (Commonwealth Edison, Umatilla, Guadalupe Valley) and the headline set would be 7 and not 8.

**Among comparison utilities: nothing moves, at any shift.** None of the 3,013 eligible comparison utilities carries a permit-dated site of 20 MW or more. A 20 MW site is 175 GWh a year, so a utility carrying one and still under 0.5% of its sales would have to sell 35 TWh or more. The ten-year screen is therefore a question about hosts only. It says nothing about small undated sites on comparison utilities, which D-20 never tested on either side.

## 2. Each headline host's permit-dated sites of 20 MW or more, and what is on file

Eight of the 11 hosts have none: Garland, Omaha Public Power District, PacifiCorp in Oregon and in Utah, Palo Alto, Public Service of New Mexico, Sierra Pacific and Walton. The other three have nine between them. (As first written this said seven and four; the list and the table were right and the counts were not. Corrected 2026-11-15, D-55.) None of the nine is filed as an update to an existing source.

| Host (first crossing) | Site | MW | Permit-based start | On file about older operation |
|---|---|---|---|---|
| Arizona Public Service (2020) | QTS, Litchfield Park (`bi:1301-0`) | 406 | 2025 | Against it. The Maricopa assessor's roll shows the permit address as vacant land and five other parcels of the campus partly built with construction years 2024 to 2026. Not a dated page; this is one of the four sites whose operating status is unsettled (D-28). |
| Arizona Public Service (2020) | Aligned, Waddell (`bi:36-0`) | 135 | 2025 | Against it. The assessor's roll codes it partly complete with a construction year of 2024. |
| Portland General (2021) | Aligned, Hillsboro (`bi:839-0`) | 28 | 2025 | Nothing on file. |
| Umatilla (2013) | Amazon, Umatilla (`bi:848-0`) | 56 | 2024 | **For it.** Oregon DEQ's permit file for Amazon PDX02 at this address shows it running by January 2014. The record brackets the start to 2012 through 2014 without stating it, which is why it was a lead and not a start year (D-17). |
| Umatilla (2013) | Amazon, Boardman (`bi:817-0`) | 22 | 2019 | **For it.** Oregon DEQ's permit file for Amazon PDX01 shows it running by November 2013, with construction begun in 2012. Its serving utility is also unresolved. |
| Umatilla (2013) | Amazon, Boardman (`bi:853-0`) | 58 | 2024 | Against it. Oregon DEQ's annual report shows no generator fuel use in any month of 2023. |
| Umatilla (2013) | Amazon, Boardman (`bi:816-0`) | 46 | 2020 | Nothing that matches. A different Amazon address 0.5 km away first ran generators in October 2019. |
| Umatilla (2013) | Amazon, Umatilla (`bi:847-0`) | 58 | 2023 | Nothing on file. |
| Umatilla (2013) | Amazon, Boardman (`bi:818-0`) | 58 | 2023 | Nothing on file. |

What this shows before any rule is applied: Arizona Public Service fails the ten-year shift on two campuses whose records point to construction in 2024 and later, so ten years earlier is not a credible history for it. Umatilla is the opposite case: two of its sites have a government record of operation five and ten years before their permit-based year.

## 3. A proposal for the site-specific check (withdrawn)

**Withdrawn on 2026-11-15 (D-56, ruling 1) before it was applied to anyone. The rule that replaces it is rule 1 of D-58 in `docs/DECISIONS.md`.** Two things in this file do not stand: "a record of no generator activity" does not rule out older operation at a grid-fed site, so the entry for `bi:853-0` in the table above ("Against it") is not evidence either way; and ten years back is not a lower end where a record gives no date. The text below is left as written, for the record.

**The screens.** Three and five years earlier stay the standard screen, on hosts and comparison utilities alike. Ten years earlier is run and reported every time, for both sides, as a stress test that sets no one aside. Passing three and five years is never described as showing a site is correctly dated.

**What counts as evidence of older operation at a site.** Any one of these, from a record or page the session model has opened, written down with its source, its quote and the date opened:

1. The site's first permit on file is filed as an update to an existing source, or the permit record itself gives an installation or construction date more than two years before the first permit on file.
2. A government record for the site's address (assessor, air-permit file, a state or federal registry) showing a building or operation more than two years before the permit-based year, including records that bracket a start without stating it and so did not pass D-17's rules for a start year.
3. A dated page showing the site or campus operating more than two years before the permit-based year.

A directory listing does not count. Evidence about a different address, even nearby, does not count.

**What rules a long backdating out for a site.** A government record of a new building with a construction year within two years of the permit-based year; a record of no generator activity in a year before it; or a dated page showing the site as planned or under construction. A site with such a record is not shifted in the wider check.

**The wider check.** It is run for a utility that has at least one site with evidence of older operation, and it replaces the generic screen for that utility where the two differ. Each such site is started at every year from the earliest year its evidence supports up to its permit-based year: where the evidence brackets the start, the bracket; where it shows only that the site is older (an update to an existing source with no date), every year back to ten years before the permit-based year, and never before 2001. Sites ruled out are left where they are. Every other permit-dated site of 20 MW or more on the utility takes the standard screen. The utility keeps its place only if its group and, for a cohort utility, its first crossing within one year are the same over that whole range as on the inventory as built. A utility that fails is set aside on both sides, as under D-20, and a sourced start year is how it comes back. A comparison utility with such a site has to stay under 0.5% throughout over the same range.

**What it does not do.** It does not test sites under 20 MW, where permit years are no better (D-39). It does not date anything: the inventory's year is still the year used. And it rests on what happens to be on file; a site with no record is not shown to be new.

**What Joe would be confirming.** The three definitions above, the two-year margin, ten years as the reach where evidence gives no date, and that the wider check overrides the generic screen for that utility in both directions (it can set aside a utility that passes three and five years, and it lets a utility stay that fails only a ten-year shift its records rule out).
