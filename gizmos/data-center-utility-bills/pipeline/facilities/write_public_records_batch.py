#!/usr/bin/env python3
"""Start years for large sites from government records that need no web search.

After round 3's lookups, 102 sites of 20 MW or more still had only a
permit-based year. Ordinary web sources were close to exhausted for them, so
this pass went to the records themselves: county assessor and GIS services,
state air-permit files, and the Texas project registry. Each record below was
found by address, parcel or facility number, and then opened and read by the
session model before it was written here (docs/DECISIONS.md, D-15 and D-17).
The sources that were tried and gave nothing are listed in
docs/public-records.md so the hunt is not repeated.

What a record is worth (D-17): medium confidence, and it fills gaps only. It
never replaces a year a checker sourced from a page, and it never overrides a
site a dated page shows as not yet operating. Like the county layers in
match_county_gis.py, most of these are the building's year, which on the
validation sites runs zero to two years before first load.

Rules a record had to pass to be listed under RECORDS:
  * the record is for this site: same street address, or the permit's own
    facility code or owner name on the record, stated in `site_match`;
  * the building is finished on the record (not "partly complete", not land only);
  * the record calls it a data center, or the owner on the record is the operator;
  * year 2005 or later (an older building may be a later conversion);
  * for Oregon DEQ annual reports on a new-source permit, the year is the first
    year with generator fuel use, which is when the first building's generators
    were commissioned.
Records that fail a rule but bear on a site are under LEADS. They are shown to
lookup agents by make_date_worklist.py and are never read by apply_verified.py.

Outputs:
  pipeline/facilities/verified/batch_r3c_1.json     the records, for sites still without a year
  pipeline/facilities/leads/public_record_leads.csv   the leads

Run:  python3 -I pipeline/facilities/write_public_records_batch.py
      python3 -I pipeline/facilities/write_public_records_batch.py --check
          re-fetches every record that is a JSON query and confirms the year is still there
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

VER = ROOT / "pipeline" / "facilities" / "verified"
LEADS_OUT = ROOT / "pipeline" / "facilities" / "leads" / "public_record_leads.csv"
UA = {"User-Agent": "research-data-fetch/1.0"}
BUILT = "government_record_year_built_or_construction_complete"
OPERATING = "government_record_operating_or_opened"


def arcgis(base: str, where: str, fields: str) -> str:
    """A query URL that returns just the one record, so a reader can check it."""
    return base + "/query?" + urllib.parse.urlencode(
        {"where": where, "outFields": fields, "returnGeometry": "false", "f": "pjson"})


DEQ = "https://deqonline.deq.state.or.us/AQPermitsonline/"
MARICOPA = "https://gis.mcassessor.maricopa.gov/arcgis/rest/services/MaricopaDynamicQueryService/MapServer/3"
MARICOPA_F = "APN_DASH,OWNER_NAME,PHYSICAL_ADDRESS,CONST_YEAR,PUC,TAX_YR_CUR,FCV_CUR,FCV_PREV"
ARAPAHOE = "https://gis.arapahoegov.com/arcgis/rest/services/CustomCAMA_WM/MapServer/37"
ARAPAHOE_F = "PARCEL_ID,Yr_Built,Eff_Year,Bld_Style,Heated_Area,Pct_Complete"
BEXAR = "https://maps.bexar.org/arcgis/rest/services/Parcels/MapServer/0"
BEXAR_F = "PropID,Situs,Owner,DBA,LglDesc,ImprVal,GBA,YrBlt,PropUse"
MECK = "https://services.arcgis.com/O8ZpeBC0xLM5nL34/arcgis/rest/services/MeckParcels_TammyTest20221101/FeatureServer/0"
MECK_F = ("PRN,AccountName,SitusAddressNumber,SitusAddressStreet,Legal1,CrtMainStructures,"
          "MainStructure1HeatedSqFt,MainStructure1YearBuilt,AssessmentYear")
LOUDOUN = "https://logis.loudoun.gov/gis/rest/services/Projects/BuildOut_LandUse/MapServer/0"
LOUDOUN_F = "LU_ADDRESS,LU_MCPI,LU_USE,LU_DEVELOP_STATUS,LU_DEMOG_YEAR_BUILT"
FAIRFAX_CO = "https://plus.fairfaxcounty.gov/CitizenAccess/urlrouting.ashx?type=1000&Module=Building&agencyCode=FFX&FromACA=Y&"

# fid, state, site, year, basis, source, url, quote (from the record), site_match, note,
# check = (field, value) for --check on JSON records
RECORDS: list[dict] = [
    # ---- Oregon DEQ air-permit files (Amazon campuses in Morrow and Umatilla counties; Apple) ----
    dict(fid="bi:820-0", state="OR", site="Amazon PDX62, 75300 Lewis & Clark Dr, Boardman", year=2018, basis=OPERATING,
         source="Oregon DEQ, permit 25-0029-ST-01, 2018 annual report", url=DEQ + "25-0029-ST-01_AR_2018.PDF",
         quote="Site Name: PDX62. Site-wide monthly diesel usage (gallons), 2018: January to August 0.00; September 4,225.00; "
               "October 60.98; November 3,390.39; December 752.34.",
         site_match="The report's site address is 75300 Lewis & Clark Drive, Boardman, the permit address. DEQ's 2018 review "
                    "report calls it 'a new permit for a new source'. The Morrow County assessor lists the improvements at "
                    "this address as built in 2018.",
         note="First generator fuel use at a new source: the first building's generators were commissioned in September 2018."),
    dict(fid="bi:822-0", state="OR", site="Amazon PDX80, 28803 NW Livestock Rd, Hermiston", year=2018, basis=OPERATING,
         source="Oregon DEQ, permit 30-0054-ST-01, 2018 annual report", url=DEQ + "30-0054-ST-01_AR_2018.PDF",
         quote="Site Name: PDX80. Site-wide monthly diesel usage (gallons), 2018: January 0.00; February 2,499.00; March 1,558.00; "
               "April 181.00; then use in every month from June to December.",
         site_match="The report's site address is 28803 NW Livestock Road, Hermiston, the permit address.",
         note="First generator fuel use at a new source, February 2018. DEQ files this site under Umatilla County."),
    dict(fid="bi:823-0", state="OR", site="Amazon PDX63, 81712 Lind Rd, Hermiston", year=2019, basis=OPERATING,
         source="Oregon DEQ, permit 30-0071-ST-01, 2019 annual report (revised)", url=DEQ + "30-0071-ST-01_AR_2019.PDF",
         quote="Site Name: PDX 63. Site-wide monthly diesel usage (gallons), 2019: January 0.00; February 3,713.00; use in every "
               "later month; emergency usage 2,337.8 in August.",
         site_match="The report's site address is 81712 Lind Road, Hermiston, the permit address. The permit was issued in "
                    "November 2018, so there is no earlier report.",
         note="First generator fuel use at a new source, February 2019. The report is a scan and was read from the page image."),
    dict(fid="bi:819-0", state="OR", site="Amazon PDX109, 75242 Gar Swanson Rd, Boardman", year=2021, basis=OPERATING,
         source="Oregon DEQ, permit 25-0062-ST-01, 2021 annual report", url=DEQ + "25-0062-ST-01_AR_2021.PDF",
         quote="2021 Annual Report: PDX109. Monthly diesel usage (gallons): Jan-21 to Oct-21 0; Nov-21 5,621.00; Dec-21 3,276.00. "
               "Permanent change log: generators 'began operation at PDX109'.",
         site_match="The report's site address is 75242 Gar Swanson Road, Boardman, the permit address.",
         note="Generators were commissioned in November 2021, so first load may fall in 2022; inside the two-year tolerance."),
    dict(fid="bi:846-0", state="OR", site="Amazon PDX130, 34820 Wanapa Rd, Umatilla", year=2022, basis=OPERATING,
         source="Oregon DEQ, permit 30-0086-ST-01, 2022 annual report", url=DEQ + "30-0086-ST-01_AR_2022.PDF",
         quote="Site Name: PDX130/131. Annual Reporting Period: January 1, 2022 - December 31, 2022. Monthly diesel usage (gallons): Jan-22 to Apr-22 0; May-22 9,242. Permanent change log, "
               "May-22: 10 Caterpillar 3516 C-HD 2,500 kW ... 'began operation at PDX130'.",
         site_match="The report's site address is 34820 Wanapa Road, Umatilla, the permit address. The 2021 annual report for "
                    "the same permit shows zero fuel in every month.",
         note="First generators began operation in May 2022."),
    dict(fid="bi:841-0", state="OR", site="Apple Prineville Data Center, 1600 SW Baldwin Rd", year=2012, basis=BUILT,
         source="Oregon DEQ, permit 07-0046-ST-01, 2019 review report", url=DEQ + "07-0046-ST-01_RR_2019.PDF",
         quote="The permittee operates a data center (electronic data processing center). The facility was built in 2012.",
         site_match="The review report is for Apple, Inc., 'a data center located at 1600 SW Baldwin Road in Prineville', the "
                    "permit address.",
         note="The same wording in DEQ's report for the neighbouring Meta campus matches that site's sourced year exactly."),
    # ---- Arapahoe County, Colorado, assessor ----
    dict(fid="bi:435-0", state="CO", site="JPMorgan Chase, 23505 E 6th Ave, Aurora", year=2019, basis=BUILT,
         source="Arapahoe County Assessor, building record", url=arcgis(ARAPAHOE, "PARCEL_ID='1977-06-3-01-001'", ARAPAHOE_F),
         quote="PARCEL_ID 1977-06-3-01-001 | Bld_Style Computer (Data) Centers | Yr_Built 2019 | Eff_Year 2019 | "
               "Heated_Area 208010 | Pct_Complete 1",
         site_match="The county parcel file gives this parcel's address as 23505 E 6TH AVE and its owner as JPMORGAN CHASE BANK.",
         note="No Arapahoe site has an independent year to check the assessor against.", check=("Yr_Built", 2019)),
    dict(fid="bi:434-0", state="CO", site="QTS Aurora, 1160 N Gun Club Rd", year=2023, basis=BUILT,
         source="Arapahoe County Assessor, building record", url=arcgis(ARAPAHOE, "PARCEL_ID='1977-06-2-04-001'", ARAPAHOE_F),
         quote="PARCEL_ID 1977-06-2-04-001 | Bld_Style Computer (Data) Centers | Yr_Built 2023 | Eff_Year 2024 | "
               "Heated_Area 346867 | Pct_Complete 1",
         site_match="The county parcel file gives this parcel's address as 1160 N GUN CLUB RD and its owner as QTS AURORA LLC.",
         note="No Arapahoe site has an independent year to check the assessor against.", check=("Yr_Built", 2023)),
    # ---- Maricopa County, Arizona, assessor (one construction year per parcel) ----
    dict(fid="bi:19-0", state="AZ", site="Microsoft, 3785 N Citrus Rd, Goodyear", year=2020, basis=BUILT,
         source="Maricopa County Assessor, parcel record", url=arcgis(MARICOPA, "APN_DASH='502-30-934'", MARICOPA_F),
         quote="502-30-934 | MICROSOFT CORPORATION | 3785 N CITRUS RD GOODYEAR 85395 | CONST_YEAR 2020 | PUC 1507 | "
               "tax year 2027 full cash value 156,609,182",
         site_match="Same street address as the permit, and the geocoded point falls in this parcel. The assessor's use code "
                    "1507 is data centers.",
         note="Parcel-level year. On Maricopa parcels with a year of 2015 or later the roll ran one year before the sourced "
              "year at all three validation sites.", check=("CONST_YEAR", "2020")),
    dict(fid="bi:15-0", state="AZ", site="Aligned Continuum, NEC Price Rd and Innovation St, Chandler", year=2023, basis=BUILT,
         source="Maricopa County Assessor, parcel record", url=arcgis(MARICOPA, "APN_DASH='303-36-988'", MARICOPA_F),
         quote="303-36-988 | ALIGNED DATA CENTERS CONTINUUM PROPCO LLC | 2900 W INNOVATION ST CHANDLER 85286 | CONST_YEAR 2023 | "
               "PUC 1507 | tax year 2027 full cash value 130,056,816",
         site_match="The owner on the roll is the company named on the permit, Aligned Data Centers (Continuum) PropCo LLC, "
                    "and the parcel is the northeast corner of Price Rd and Innovation St, which is the permit's location.",
         note="Parcel-level year. The owner's second parcel south of Innovation St is coded partly complete (2024).",
         check=("CONST_YEAR", "2023")),
    # ---- Bexar County, Texas (appraisal district attributes on the county parcel layer) ----
    dict(fid="bi:914-0", state="TX", site="Amazon ALE60, 7400 Potranco Rd, San Antonio", year=2021, basis=BUILT,
         source="Bexar Appraisal District, parcel record", url=arcgis(BEXAR, "PropID=1124141", BEXAR_F),
         quote="PropID 1124141 | 1511 NW CROSSROADS | COPT SAN ANTONIO LP | DBA AMAZON DATA CENTER | YrBlt 2021 | GBA 109425",
         site_match="The geocoded point falls in this parcel. The state registry's project TABS2021003290, facility 'ALE060 - CS' "
                    "at 7400 Potranco Road, a 109,600 sq ft core and shell 'for future data center fit-out', is marked "
                    "Project Closed with a filed completion of 12/6/2021; the permit names the site ALE60.",
         note="Year built agrees with the closed registry project.", check=("YrBlt", "2021")),
    dict(fid="bi:907-0", state="TX", site="Amazon ALE61, 11625 Old Corpus Christi Hwy, San Antonio", year=2021, basis=BUILT,
         source="Bexar Appraisal District, parcel record", url=arcgis(BEXAR, "PropID=1350409", BEXAR_F),
         quote="PropID 1350409 | 12807 DONOP RD | AMAZON DATA SERVICES INC | DBA AMAZON DATA CENTER | YrBlt 2021 | GBA 109725",
         site_match="The permit names the site ALE61. The state registry files 'ALE061' (new data center, 109,600 sq ft, Amazon "
                    "Data Services) at the permit address and 'ALE061 - Room 2' at 12807 Donop Road, the address of this "
                    "parcel, which is 830 m from the geocoded point. The permit address itself is vacant land on the roll.",
         note="The registry's new-construction record is not marked closed, so the year is the appraisal district's alone.",
         check=("YrBlt", "2021")),
    dict(fid="bi:918-0", state="TX", site="Amazon ALE62, State Highway 211 and Lambda Dr, San Antonio", year=2021, basis=BUILT,
         source="Bexar Appraisal District, parcel record", url=arcgis(BEXAR, "PropID=1357675", BEXAR_F),
         quote="PropID 1357675 | 2200 STATE HWY 211 | AMAZON DATA SERVICES INC | DBA AMAZON DATA CENTER NC | YrBlt 2021 | GBA 109685",
         site_match="The permit names the site ALE62 and gives an intersection. The state registry files 'ALE062 - Room 2' "
                    "(Amazon Data Services) at 2200 State Hwy 211, the address of this parcel.",
         note="No closed new-construction project in the registry, so the year is the appraisal district's alone.",
         check=("YrBlt", "2021")),
    dict(fid="bi:928-0", state="TX", site="Microsoft, 5200 Rogers Rd, San Antonio", year=2008, basis=BUILT,
         source="Bexar Appraisal District, parcel record", url=arcgis(BEXAR, "PropID=1123010", BEXAR_F),
         quote="PropID 1123010 | 5200 ROGERS RD | MICROSOFT CORPORATION | DBA MICROSOFT | YrBlt 2008 | GBA 296874",
         site_match="Same street address as the permit, and the geocoded point falls in this parcel.",
         note="The neighbouring Microsoft building at 5150 Rogers Rd reads 2007 on the roll against a sourced 2008.",
         check=("YrBlt", "2008")),
    # ---- Harris County, Texas ----
    dict(fid="bi:1200-0", state="TX", site="Serverfarm (built for HP), 15555 Cutten Rd, Houston", year=2006, basis=BUILT,
         source="Harris Central Appraisal District, 2026 building file, account 1200060010001",
         url="https://download.hcad.org/data/CAMA/2026/Real_building_land.zip",
         quote="building_other.txt, acct 1200060010001, bld 1: date_erected 2006 | eff 2006 | yr_roll 2007 | 225,144 sq ft | "
               "notes: 'SECT 1 IS DATA CENTER AREA'",
         site_match="The district's parcel layer gives account 1200060010001 as 15555 CUTTEN RD, owner SF HOUH LLC, the address "
                    "and company on the permit.",
         note="The year is in the district's bulk building file, not on a page of its own. First on the roll in 2007."),
    # ---- Virginia: Fairfax, Mecklenburg, Loudoun ----
    dict(fid="bi:1012-4", state="VA", site="Amazon IAD-165 campus, 13640 EDS Dr, Herndon", year=2024, basis=BUILT,
         source="Fairfax County, certificate of occupancy NONRUP-2024-01134",
         url=FAIRFAX_CO + "capID1=REC24&capID2=00000&capID3=020OD",
         quote="Certificate of Occupancy (Non-RUP), issued 2024-08-15. Work Location 13600 EDS DR HERNDON. Zoning Use: Data "
               "Center. First occupant in a new building?: Yes. Building Permit Number for New Building: BLDC-220190181.",
         site_match="The certificate is on parcel 0244 01 0006B8, which the county's address list gives for 13640 EDS Dr and "
                    "which the tax office names 'AWS DATA CENTER CAMPUS'.",
         note="First occupancy certificate for a new data center building on the parcel. The tax office's year built for the "
              "campus has moved between 2023 and 2025 across rolls."),
    dict(fid="bi:985-3", state="VA", site="Amazon IAD-134 campus, 3980 Virginia Mallory Dr, Chantilly", year=2023, basis=BUILT,
         source="Fairfax County, certificate of occupancy NONRUP-2023-01087",
         url=FAIRFAX_CO + "capID1=REC23&capID2=00000&capID3=0238R",
         quote="Certificate of Occupancy (Non-RUP), issued 2023-07-28. Work Location 3980A VIRGINIA MALLORY DR CHANTILLY. Zoning "
               "Use: Data Center. First occupant in a new building?: Yes. Building Permit Number for New Building: BLDC-221170091.",
         site_match="Same street address as the permit; parcel 0341 03 0013, which the tax office names 'AMAZON DATA CENTER' "
                    "with a year built of 2024.",
         note="First occupancy certificate for a new data center building on the parcel."),
    dict(fid="bi:978-0", state="VA", site="Microsoft LVL campus, 960 Prison Rd (now Herbert Dr), Boydton", year=2021, basis=BUILT,
         source="Mecklenburg County, parcel record", url=arcgis(MECK, "PRN=38595", MECK_F),
         quote="PRN 38595 | MICROSOFT CORPORATION | 960 HERBERT DRIVE LVL1-7 | PT LVL 1-7 CAMPUS MICROSOFT CORP | "
               "MainStructure1YearBuilt 2021 | MainStructure1HeatedSqFt 241392 | AssessmentYear 2026",
         site_match="The permit names the site 'LVL Datacenter' and the parcel is the LVL 1-7 campus; Virginia DEQ's "
                    "registration 52820, 'Microsoft Corp - LVL Data Center', falls in the same parcel. The county renamed "
                    "960 Prison Rd to 960 Herbert Dr.",
         note="The county exposes the year of the first main structure only. On Microsoft's older Boydton campus the same "
              "field reads 2011 against a sourced 2012.", check=("MainStructure1YearBuilt", 2021)),
    dict(fid="bi:1280-0", state="VA", site="Microsoft AVC09-13 campus, Roanoke River Regional Business Park, La Crosse",
         year=2022, basis=BUILT,
         source="Mecklenburg County, parcel record", url=arcgis(MECK, "PRN=39027", MECK_F),
         quote="PRN 39027 | MICROSOFT CORPORATION | 1 AVC 09 | AVC09-13 CAMPUS | MainStructure1YearBuilt 2022 | "
               "MainStructure1HeatedSqFt 244684 | AssessmentYear 2026",
         site_match="The permit gives only the business park. Virginia DEQ's registration 52973, 'Microsoft Corp DCS - "
                    "AVC09-AVC13 Datacenter' at Roanoke River Regional Business Park, falls in this parcel.",
         note="The county exposes the year of the first main structure only.", check=("MainStructure1YearBuilt", 2022)),
    dict(fid="bi:1057-0", state="VA", site="Microsoft AVC43 campus, 2 Butts St, South Hill", year=2024, basis=BUILT,
         source="Mecklenburg County, parcel record", url=arcgis(MECK, "PRN=39166", MECK_F),
         quote="PRN 39166 | MICROSOFT CORPORATION | 260 BUTTS STREET | AVC43-44 CAMPUS PT PAR- MICROSOFT CORP | "
               "MainStructure1YearBuilt 2024 | MainStructure1HeatedSqFt 244683 | AssessmentYear 2026",
         site_match="The permit names the site 'AVC43 Datacenter' and the parcel is the AVC43-44 campus on Butts Street; "
                    "Virginia DEQ's registration 53071 for AVC43 falls in the same parcel.",
         note="The county exposes the year of the first main structure only.", check=("MainStructure1YearBuilt", 2024)),
    dict(fid="bi:1089-2", state="VA", site="Amazon IAD-163 campus, 21099 Atlantic Blvd, Sterling", year=2021, basis=BUILT,
         source="Loudoun County, Existing Structures", url=arcgis(LOUDOUN, "LU_ADDRESS LIKE '21195 ATLANTIC%'", LOUDOUN_F),
         quote="21195 ATLANTIC BLVD | COM_DATA_CENTER | Existing or Permitted | Demographic Year Built 2021",
         site_match="The permit address is not in the county's address list. The geocoded point falls in the parcel of 21195 "
                    "Atlantic Blvd, and a county electrical permit at that address is titled 'IAD 163'; Virginia DEQ registers "
                    "'Amazon Data Services Inc - IAD-163/164/174' at 21099 Atlantic Boulevard. The next building, 21205 "
                    "Atlantic Blvd, was built in 2022.",
         note="Same county layer as match_county_gis.py, matched by parcel and building code, not by street number.",
         check=("LU_DEMOG_YEAR_BUILT", 2021)),
    # ---- Franklin County, Ohio, and Kansas City, Missouri ----
    dict(fid="bi:794-0", state="OH", site="Amazon CMH091 campus, 4600 Cosgray Rd, Hilliard", year=2022, basis=BUILT,
         source="Franklin County Auditor, appraisal extract of 2026-10-15, parcel 050-011455-00",
         url="https://apps.franklincountyauditor.com/Outside_User_Files/2026/2026-10-15%20Appraisal/Build.xlsx",
         quote="Build table, PARCEL ID 050-011455-00: card 1, 214,800 sq ft, YRBLT 2022; cards 2 to 7 YRBLT 2023; card 8 YRBLT 2025.",
         site_match="The auditor's parcel layer gives parcel 050-011455 as 4580 - 4640 COSGRAY RD, owner AMAZON DATA SERVICES "
                    "INC, class 'data center'; the permit address is 4600 Cosgray Rd and the geocoded point falls in the parcel.",
         note="The year is in the auditor's county-wide building file. On two other Amazon campuses in the county the same "
              "file reads one year before the sourced year."),
    dict(fid="bi:658-0", state="MO", site="Oracle (built as Cerner's data center), 3200 Rockcreek Pkwy, Kansas City", year=2008,
         basis=BUILT, source="Kansas City, Missouri, certificate of occupancy CICO-200811959",
         url="https://data.kcmo.org/resource/ntw8-aacc.json?$where=permitnum='CICO-200811959'",
         quote="Certificate of Occupancy (Commercial) | 3200 Rock Creek Pkwy | CERNER WORLD HEADQUARTERS, DATA CENTER | "
               "Construct new building | 130878 sq ft | issued 2008-02-29 | Closed",
         site_match="Same street address as the permit. The new-building permit for the same project, CPBB-200632635, was "
                    "issued in 2006 and closed on the same day in 2008.",
         note="Occupancy certificate for a new building the city's record names a data center. No Kansas City site has an "
              "independent year to check the city's records against.", check=("coissueddate", "2008-02-29T00:00:00.000")),
    dict(fid="bi:659-0", state="MO", site="Oracle KC-7/8 (built as Cerner KC-7), 3512 NE 33rd Terrace, Kansas City", year=2011,
         basis=BUILT, source="Kansas City, Missouri, certificate of occupancy CICO-201210283",
         url="https://data.kcmo.org/resource/ntw8-aacc.json?$where=permitnum='CICO-201210283'",
         quote="Certificate of Occupancy (Commercial) | 3512 NE 33rd Ter | CERNER KC-7 DATA CENTER | Tenant finish | "
               "21432 sq ft | issued 2011-08-01 | Closed",
         site_match="Same street address as the permit, which names the site Oracle KC-7/8 Data Centers; the county parcel's "
                    "owner is CERNER CHOUTEAU DATA CENTER INC.",
         note="The data center was fitted out inside an existing building; 2011 is when that use was certified.",
         check=("coissueddate", "2011-08-01T00:00:00.000")),
]

# Records that bear on a site but do not pass the rules. Shown to lookup agents as leads.
LEADS: list[dict] = [
    dict(fid="bi:1301-0", source="Maricopa County Assessor, tax year 2027 roll",
         url=arcgis(MARICOPA, "OWNER_NAME LIKE 'QTS GLENDALE%'", MARICOPA_F),
         record="The permit address, 17501 W Bethany Home Rd (QTS GLENDALE I DC16 LLC), is vacant commercial land with no "
                "construction year. Five other QTS Glendale parcels (DC1, DC2, DC9, DC13, DC14) are coded partly complete "
                "with construction years 2024 to 2026; ten more and the infrastructure parcel are vacant.",
         caution="The roll is not a dated page and a partly complete campus can carry load. Needs a dated page either way."),
    dict(fid="bi:32-0", source="Maricopa County Assessor, tax year 2027 roll",
         url=arcgis(MARICOPA, "APN_DASH='121-13-007G'", MARICOPA_F),
         record="No 800 N 40th St on the roll. STACK's land there (SI PHXL2 LLC, 888 N 40th St, 51 acres) is vacant "
                "industrial land with no construction year and a flat value. The finished data centers next door are QTS's.",
         caution="The roll is not a dated page. Needs a dated page saying the site is not yet operating, or an opening."),
    dict(fid="bi:36-0", source="Maricopa County Assessor, tax year 2027 roll",
         url=arcgis(MARICOPA, "APN_DASH='501-42-994'", MARICOPA_F),
         record="8807 N Reems Rd, ALIGNED DATA CENTERS (GLENDALE) PROPCO LLC: coded partly complete, construction year 2024, "
                "value up from $221M to $328M between rolls.",
         caution="Partly complete on the roll is not proof of no load."),
    dict(fid="bi:13-0", source="Maricopa County Assessor, tax year 2027 roll",
         url=arcgis(MARICOPA, "APN_DASH IN ('303-36-989','303-36-988')", MARICOPA_F),
         record="Owner ALIGNED DATA CENTERS CHANDLER PROPCO LLC holds 2501 S Price Rd, a 1985 office building; the geocode "
                "points at the neighbouring Continuum parcel (data center, 2023).",
         caution="Cannot tell which building the permit covers."),
    dict(fid="bi:1182-0", source="Dallas Central Appraisal District, 2026 roll",
         url="https://www.dallascad.org/AcctDetailCom.aspx?ID=422225900003A0000",
         record="1510 E Lookout Dr, Richardson: COMPUTER DATA CENTER, year built 2019, 130,039 sq ft, 100% complete, property "
                "name KDC, owner GI ETS RICHARDSON I LLC. CyrusOne's own registry projects (DFW6 phases 1 and 2) are additions "
                "registered in 2024 and 2025.",
         caution="The 2019 building predates CyrusOne; who ran it, and from when, is not on the record."),
    dict(fid="bi:935-0", source="Tarrant Appraisal District, 2026 roll, account 43259149",
         url="https://www.tad.org/content/data-download/PropertyData(Delimited)_C.ZIP",
         record="14100 Park Vista Blvd (Tarrant County, not Denton), QTS INVESTMENTS PROPERTIES FORT WORTH LLC: year built 2008, "
                "261,836 sq ft. A 2009 registry project at the address was filed by Health Care Service Corporation for "
                "'CDC2'.",
         caution="The record does not say the 2008 building was a data center from the start."),
    dict(fid="bi:1258-0", source="Dallas Central Appraisal District, 2026 roll (status at 1 January 2026)",
         url="https://www.dallascad.org/DataProducts.aspx",
         record="Both Amazon lots on Ezell Drive, DeSoto, are LAND ONLY / VACANT. The registry project is Review Complete, "
                "not closed.", caution="The roll is not a dated page."),
    dict(fid="bi:926-0", source="Bexar Appraisal District and Texas TDLR project registry",
         url=arcgis(BEXAR, "PropID=1449195", BEXAR_F),
         record="Microsoft, Lambda Dr: year built 2024 on the roll, 1,002,338 sq ft. Registry: SAT15 Inspection Completed with "
                "a filed completion of 5/2026; SAT16 and SAT17 only registered.",
         caution="On new builds the Bexar year records construction, and no registry project is closed."),
    dict(fid="bi:1177-0", source="Bexar Appraisal District and Texas TDLR project registry", url=BEXAR,
         record="CyrusOne SAT8/SAT9, 14677 Omicron Dr: year built 2024 on the roll; registry project Registered, filed "
                "completion 12/2025.", caution="No closed project; not shown finished."),
    dict(fid="bi:910-0", source="Bexar Appraisal District and Texas TDLR project registry", url=BEXAR,
         record="Vantage TX11, 14270 Omicron Dr: year built 2024 on the roll; registry project Inspection Completed, filed "
                "completion 9/2026.", caution="No closed project; not shown finished."),
    dict(fid="bi:976-0", source="Mecklenburg County, parcel record", url=arcgis(MECK, "PRN=39040", MECK_F),
         record="AVC17-24 LAKESIDE COMMERCE CAMPUS, Microsoft: first main structure year built 2024, heated area a placeholder "
                "(2 sq ft), structures assessed at $466M for 2026.",
         caution="The building record is incomplete, so it is not shown finished."),
    dict(fid="bi:1003-0", source="Prince William County, Data Center Buildings layer (edited 2026)",
         url="https://gisweb.pwcva.gov/arcgis/rest/services/CountyMapper/LandDevelopment/MapServer/10",
         record="NTT VA10, 14300 John Marshall Hwy: listed as Under Construction.",
         caution="Virginia DEQ lists the registration as Operating. Needs a dated page."),
    dict(fid="bi:1004-3", source="Prince William County, Data Center Buildings layer (edited 2026)",
         url="https://gisweb.pwcva.gov/arcgis/rest/services/CountyMapper/LandDevelopment/MapServer/10",
         record="Village Place Technology Park buildings 1 to 4, 14495 John Marshall Hwy: listed as Under Construction.",
         caution="Virginia DEQ lists the registration as Operating. Needs a dated page."),
    dict(fid="bi:1031-2", source="Prince William County, Data Center Buildings layer (edited 2026)",
         url="https://gisweb.pwcva.gov/arcgis/rest/services/CountyMapper/LandDevelopment/MapServer/10",
         record="Amazon IAD-59, 7600 Doane Dr: listed as Planned, yet the county taxes 115,000 to 128,000 sq ft of building "
                "there.", caution="The layer looks stale for this site."),
    dict(fid="bi:817-0", source="Oregon DEQ, permit 25-0007-ST-01 (Amazon PDX01)", url=DEQ,
         record="73575 Lewis & Clark Dr, Boardman: running by November 2013; construction began in 2012.",
         caution="Brackets the start to 2012 or 2013 without stating it."),
    dict(fid="bi:848-0", source="Oregon DEQ, permit 30-0028-ST-01 (Amazon PDX02)", url=DEQ,
         record="2400 Beach Access Rd, Umatilla: running by January 2014; no 2013 annual report is online.",
         caution="Brackets the start to 2012 through 2014 without stating it."),
    dict(fid="bi:853-0", source="Oregon DEQ annual report for 2023", url=DEQ,
         record="77860 Bombing Range Rd, Boardman: no generator fuel use in any month of 2023.",
         caution="Started in 2024 or later, if at all; later reports sit behind a login."),
    dict(fid="bi:816-0", source="Oregon DEQ", url=DEQ,
         record="No DEQ facility at 100 SE Olson Rd. Amazon's PDX90 at 79386 Olson Rd, about 0.5 km away, first ran "
                "generators in October 2019.", caution="Different address; not matched."),
    dict(fid="bi:1122-0", source="Laramie County, Wyoming, parcel layer", url="https://maps.laramiecounty.com/arcgis/rest/services/features/CountyBaseMapFeatures/MapServer/2",
         record="Microsoft, south of Cheyenne: the geocoded parcel is commercial vacant land with no improvement value for 2024.",
         caution="The geocode may be on the wrong parcel; not proof the site is idle."),
    dict(fid="bi:1333-0", source="Los Angeles County Assessor", url="https://portal.assessor.lacounty.gov/",
         record="900 N Alameda St: a 1938 building and a new 2020 building on one parcel.",
         caution="The 1938 building was converted earlier; 2020 would be late for the site."),
    dict(fid="bi:1220-0", source="City of Santa Clara project layer", url="https://www.santaclaraca.gov/",
         record="2600 De La Cruz Blvd: a 703,450 sq ft data center listed as Approved (2019) with no completion date; the "
                "parcel layer still shows the 1954 building.", caution="No completion on record."),
    dict(fid="bi:1049-0", source="Fairfax County tax office", url="https://www.fairfaxcounty.gov/taxes/real-estate",
         record="12100 Sunrise Valley Dr, Reston: the permit's building is a 1982 building converted later; the purpose-built "
                "one on the campus dates from 2015.", caution="Conversion year not on record."),
    dict(fid="bi:1019-0", source="Loudoun County, Existing Structures", url=LOUDOUN,
         record="19935 Sycolin Rd, Leesburg: the earliest data center building on the parcel Virginia DEQ points at is 2021.",
         caution="Nothing on the record ties that parcel to Microsoft."),
    dict(fid="bi:575-0", source="Cook County Assessor, commercial valuation data",
         url="https://datacatalog.cookcountyil.gov/resource/csik-bsws.json",
         record="Microsoft, 201 Innovation Dr, Elk Grove Village: year built 2021 in the 2022 workbook, 2022 in the 2025 workbook.",
         caution="Cook's year built changes between reassessments and agreed with only half the validation sites."),
    dict(fid="bi:583-0", source="Cook County Assessor, commercial valuation data",
         url="https://datacatalog.cookcountyil.gov/resource/csik-bsws.json",
         record="9401 W Grand Ave, Franklin Park: a 422,063 sq ft data center, owner Digital Realty, year built 2021 in the 2022 "
                "workbook (then addressed 9333 W Grand) and 2019 in the 2025 workbook.",
         caution="Cook's year is unreliable. This may be the same building as bi:582-0 (Digital Realty, 9333 Grand Ave), with "
                 "Microsoft as tenant: check for double counting before dating it."),
    dict(fid="bi:1170-0", source="Cook County Assessor, commercial valuation data, 2025 workbook",
         url="https://datacatalog.cookcountyil.gov/resource/csik-bsws.json",
         record="Iron Mountain, 1700 E Touhy Ave, Des Plaines: new construction, partial, year built 2025.",
         caution="Partly complete on the roll is not proof of no load."),
    dict(fid="bi:584-0", source="Cook County Assessor, commercial valuation data and permits",
         url="https://datacatalog.cookcountyil.gov/resource/csik-bsws.json",
         record="Microsoft, 2200 Lakewood Blvd, Hoffman Estates: new construction, partial, year built 2025; an occupancy "
                "permit closed 2025-11-17.", caution="Cook's year is unreliable; the occupancy permit is the better lead."),
    dict(fid="bi:580-0", source="Cook County Assessor, commercial valuation data and permits",
         url="https://datacatalog.cookcountyil.gov/resource/csik-bsws.json",
         record="800 E Devon Ave, Elk Grove Village: a warehouse built 2005 to 2008, owned by Prologis, with data center "
                "conversion permits issued 2024-07 and 2025-06.", caution="Conversion; no completion on record."),
    dict(fid="bi:572-0", source="Cook County Assessor, commercial valuation data",
         url="https://datacatalog.cookcountyil.gov/resource/csik-bsws.json",
         record="Stream, 1925 Busse Rd, Elk Grove Village: year built 2013.",
         caution="The building may predate its data center use, and Cook's year is unreliable."),
    dict(fid="bi:797-0", source="Licking County, Ohio, parcel layer", url="https://www.lickingcountyohio.us/",
         record="8833 Smith's Mill Rd is not on the roll. The likely parcel, VADATA's 2550 Beech Rd, was built in 2015.",
         caution="Matched by adjacency only."),
    dict(fid="bi:1222-0", source="Montgomery County, Pennsylvania, parcel layer", url="https://www.montgomerycountypa.gov/",
         record="Flexential, 101 Troutman Rd, Collegeville: year built 2009.",
         caution="The record does not say it was built as a data center."),
    dict(fid="bi:611-0", source="Indiana statewide parcels", url="https://www.indianamap.org/",
         record="6350 Prairie School Dr, Portage: vacant land with no improvement value in an October 2022 copy of the county "
                "parcels.", caution="Old snapshot; later status unknown."),
    dict(fid="bi:679-0", source="Williams County, North Dakota, parcel and tax records", url="https://www.williamsnd.com/",
         record="2317 2nd St W, Williston: an existing oilfield-services building bought by deed on 2022-11-01.",
         caution="No year for the data center use."),
    dict(fid="bi:549-0", source="Dallas County, Iowa, GIS", url="https://www.dallascountyiowa.gov/",
         record="Microsoft Ginger West, West Des Moines: new-building permits from 2021 and building value on the 2025 roll, "
                "no year built.", caution="No completion on record."),
]


def already_settled() -> set[str]:
    """Sites with a year sourced from a page, or a verified status, in any other committed file."""
    from pipeline.facilities.apply_verified import usable
    out: set[str] = set()
    for p in sorted(VER.glob("batch_*.json")):
        if p.name.startswith("batch_r3c_"):
            continue
        for r in json.loads(p.read_text()):
            if r.get("energized_year") is not None and usable(r.get("energized_year_source_url"), r.get("year_confidence")):
                out.add(r["fid"])
            elif r.get("operating_status") == "not_yet_operating" and usable(r.get("status_source_url"), r.get("status_confidence")):
                out.add(r["fid"])
            elif r.get("fid") in out and r.get("energized_year") is None and r.get("operating_status") is None:
                pass  # a later file with nothing verified does not unsettle an earlier one
    return out


def batch_records() -> list[dict]:
    settled = already_settled()
    recs = []
    for r in RECORDS:
        if r["fid"] in settled:
            continue
        recs.append({
            "fid": r["fid"], "group": "public_record", "state": r["state"], "is_data_center": True, "site_name": r["site"],
            "energized_year": r["year"], "energized_year_source_url": r["url"], "year_confidence": "medium",
            "year_basis": r["basis"], "year_evidence_quote": r["quote"], "year_site_match": r["site_match"],
            "record_source": r["source"],
            "load_mw_2025": None, "load_basis": None, "load_source_url": None,
            "serving_utility": None, "utility_source_url": None, "utility_confidence": None,
            "notes": r["note"],
        })
    return recs


def check() -> int:
    """Re-fetch the records that are JSON queries and confirm the year field still reads the same."""
    bad = 0
    for r in RECORDS:
        if "check" not in r:
            continue
        field, want = r["check"]
        url = r["url"].replace("f=pjson", "f=json")
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as resp:
            data = json.load(resp)
        rows = data if isinstance(data, list) else [f["attributes"] for f in data.get("features", [])]  # Socrata or ArcGIS
        got = [row.get(field) for row in rows]
        ok = any(str(g).strip() == str(want) for g in got)
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} {r['fid']:10s} {field} = {got} (recorded {want})")
    print("records checked:", sum("check" in r for r in RECORDS), "| changed:", bad)
    return 1 if bad else 0


def main() -> int:
    if "--check" in sys.argv:
        return check()
    assert len({r["fid"] for r in RECORDS}) == len(RECORDS), "a site is listed twice"
    assert not {r["fid"] for r in RECORDS} & {r["fid"] for r in LEADS}, "a site is both a record and a lead"
    recs = batch_records()
    (VER / "batch_r3c_1.json").write_text(json.dumps(recs, indent=1, ensure_ascii=False) + "\n")
    pd.DataFrame(LEADS)[["fid", "source", "record", "caution", "url"]].to_csv(LEADS_OUT, index=False)
    print(f"batch_r3c_1.json: {len(recs)} sites dated from public records ({len(RECORDS) - len(recs)} already settled "
          f"by a page) | leads: {len(LEADS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
