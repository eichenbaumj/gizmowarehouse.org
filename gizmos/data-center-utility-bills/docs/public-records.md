# Government records tried for dating large sites

Written 2026-11-11 (session 3). After round 3's lookups, 102 sites of 20 MW or more still had only a permit-based start year. This is the list of record sources that were tried for them without any web search, what each one gave, and how it did against sites that already had an independently sourced year. It exists so the hunt is not repeated. The rule for what became a start year is D-17 in `DECISIONS.md`; the records themselves are in `pipeline/facilities/write_public_records_batch.py`.

"Difference" below is the record's year minus the independently sourced year, one number per validation site. A negative number means the record is earlier.

## Sources that dated at least one site

| Source | What it holds | Differences on validation sites | Sites dated |
|---|---|---|---|
| Oregon DEQ, Air Quality Permits Online (`deqonline.deq.state.or.us/AQPermitsonline/`) | Review reports and annual reports per air permit. Annual reports give generator fuel use by month. | First fuel use: 0, -1, -1. "Built in" statement: 0, -3 (the -3 is against an ENERGY STAR listing, not a start date) | 6 |
| Bexar Appraisal District attributes on the county parcel layer (`maps.bexar.org`) | One year built per account, use code, owner, trade name | -1, -1, -2, and -16 for a 1996 building converted later | 4 |
| Mecklenburg County, Virginia, parcels (the service behind the county's map viewer) | Year built of the first main structure only | -1 (one site) | 3 |
| Arapahoe County, Colorado, assessor | Building style ("Computer (Data) Centers"), year built, percent complete | none in the county | 2 |
| Maricopa County Assessor parcel layer | One construction year per parcel, use code (1507 is data centers), value for two tax years | Year 2015 or later: -1, -1, -1. Year before 2013: 0, -4, -5, -12 | 2 |
| Fairfax County occupancy certificates (PLUS) and tax-office commercial table | Certificates state the zoning use and whether it is the first occupant of a new building | Tax table 0 (one site); certificates had no match for that site | 2 |
| Kansas City, Missouri, permit dataset (`data.kcmo.org`) | Building permits and certificates of occupancy with project names | none in the city | 2 |
| Franklin County, Ohio, auditor building file | Year built per building card | -1, -1 | 1 |
| Harris Central Appraisal District building file | Year erected per building, appraiser notes | -2 (one site) | 1 |
| Loudoun County Existing Structures (already used in `match_county_gis.py`) | Year built per structure | 13 of 16 within one year (earlier pass) | 1 more, matched by parcel and building code |

The common pattern: on purpose-built data centers a year built runs zero to two years before the sourced start, and on converted buildings it is useless. That is why nothing before 2005 is taken and why every record was read against the site before it was used.

## Sources that were open but dated nothing

- **Cook County Assessor commercial valuation data** (Socrata). The year built for the same building changes between reassessments (one site goes from 2022 to 1970). Against eight validation sites the 2022 workbook was within two years on four and the 2025 workbook on five. Not used; six Cook records are kept as leads.
- **City of Santa Clara parcel layer.** Stale for rebuilt sites: differences 0, +1, -34, -57. Not used.
- **Dallas Central Appraisal District** bulk file. Good on purpose-built sites (-1, -1) and wrong on conversions (-17, -28). The one open target with a clean record (CyrusOne DFW6, a 2019 building) predates the operator, so it is a lead.
- **Collin, Denton and Travis appraisal districts; Tarrant roll; Texas statewide parcels.** Open, mixed or failing validation, and the open targets there are older buildings.
- **Texas TDLR project registry (TABS).** No open dataset; the public search form was used. A filed completion date counts only on a record marked Project Closed (D-15). Used here to tie permits to parcels and as corroboration, not as a year on its own. On seven validation sites the earliest closed new-construction record was exact for five, +2 for one, and +9 for one where a later retrofit was filed as new construction.
- **Morrow, Umatilla, Crook and Washington County, Oregon; Laramie County, Wyoming; Dallas County, Iowa; Indiana statewide parcels; Williams County, North Dakota; Douglas, Fulton and Gwinnett County, Georgia; Hayward's copy of the Alameda roll; MassGIS.** Open, but the year-built field is missing, blank or zero for these sites.
- **Grant County, Washington, assessor.** Differences -1, 0, -1 and +7; the one open target has no usable row.
- **San Francisco, Los Angeles County, Miami-Dade, Hillsborough, Boulder, Montgomery County (Pennsylvania), New Jersey MOD-IV, Licking County (Ohio).** Open. The open targets there are old or converted buildings, or could not be tied to a parcel.
- **Prince William County Data Center Buildings layer.** The four leftover sites are listed as under construction or planned in 2026 edits. Kept as leads: Virginia DEQ lists three of them as operating, and the county layer looks stale for at least one.
- **Virginia DEQ air registrations.** No date fields. Used only to tie a permit's building codes to a parcel.

## Not obtained

Each of these refused automated access or needed a login or token, and was left alone (D-7).

- Oregon DEQ's newer document system, Your DEQ Online (login). It holds annual reports filed after November 2024 and would probably date five more Oregon sites.
- Maricopa County Assessor per-building detail (token).
- Polk County, Iowa, assessor and GIS (403); Dallas County, Iowa, and Williams County, North Dakota, assessor sites (bot challenge); Clay County, Missouri, assessor feed (403).
- Santa Clara County roll (not open); Newton County, Georgia, parcels (token); Ward County, Texas, appraisal site (locks out automated clients).
- Franklin County, Ohio, property cards (a disclaimer that has to be accepted); the open building file was used instead.
- Denton and Travis appraisal districts' detail service (token).

## Two things the records turned up that are not dates

- **A possible double count in Franklin Park, Illinois. Settled since: two separate permitted sources in two buildings, nothing dropped (`docs/DECISIONS.md`, D-23).** As first written: The Cook assessor has one 422,063 sq ft data center at 9401 W Grand Ave, formerly addressed 9333 W Grand, owned by Digital Realty. The inventory carries `bi:582-0` (Digital Realty, 9333 Grand Ave, 83 MW) and `bi:583-0` (Microsoft, 9401 W Grand Ave, 40 MW) as two sites on Commonwealth Edison. If Microsoft is a tenant in that building the load is counted twice. Not changed; it needs a check before Gate 1.
- **Phoenix-area sites that may not be running.** On the Maricopa roll for tax year 2027, STACK's 40th Street land is vacant with no building, and the QTS Glendale campus is five partly complete buildings and eleven vacant parcels. A roll is not a dated page, so neither site's status was changed on this evidence.
