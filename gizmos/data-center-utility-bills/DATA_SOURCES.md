# Data sources

Every outside source the pipeline uses is listed here. For each one I give what it is, who publishes it, the URL the code uses, the script that fetches or reads it, its license or terms as far as this project's own files state them, and whether a copy is in this repository.

Where this project's files do not state a license, the entry says "license not stated in this project's files". That is not a claim that no license exists. Check the publisher's own terms before you reuse the data.

Three manifests in `data/frozen/` record what the main fetch scripts downloaded, with each file's URL, size, last-modified header and SHA-256 hash. They are `fetch_manifest_eia861.json`, `fetch_manifest_facilities.json` and `fetch_manifest_instrument.json`.

## Electricity

### EIA Form 861, raw files

- **What it is.** EIA Form 861 is the federal government's yearly survey of every electric utility. It reports sales, revenue and customers by utility, state and customer class. The residential price in this study is revenue divided by sales.
- **Publisher.** U.S. Energy Information Administration (EIA).
- **URLs.** `https://www.eia.gov/electricity/data/eia861/zip/f8612025.zip`, `https://www.eia.gov/electricity/data/eia861/archive/zip/f8612024.zip` and `https://www.eia.gov/electricity/data/eia861/archive/zip/f8612023.zip`.
- **Fetched by.** `pipeline/electricity/fetch_eia861.py`. The raw files are used to add years PUDL has not yet ingested and to cross-check PUDL against the source.
- **Terms.** License not stated in this project's files. It is a U.S. government publication.
- **In this repository.** No. Fetch it. Derived panel reports are in `data/frozen/` (for example `panel_construction_report.json` and `succession_report.json`).

### EIA Form 861 through PUDL

- **What it is.** Cleaned EIA Form 861 tables for every year, as parquet files. The pre-2012 EIA files change layout almost every year, and PUDL has already lined them up. The study uses ten tables. They cover sales, service territory, utility data, operational data, balancing authority, the Short Form and EIA's schedule of mergers.
- **Publisher.** Catalyst Cooperative, the Public Utility Data Liberation project (PUDL).
- **URL.** `https://s3.us-west-2.amazonaws.com/pudl.catalyst.coop/stable/<table>.parquet`. The table names are listed in `PUDL_TABLES` in the fetch script.
- **Fetched by.** `pipeline/electricity/fetch_eia861.py`.
- **Terms.** CC-BY-4.0, as `fetch_eia861.py` states.
- **In this repository.** No. Fetch it.

### EIA state net generation by energy source

- **What it is.** Net electricity generation by state and fuel. The study uses 2008 to 2010 to compute each state's natural gas share of generation, which becomes a control in the main estimate.
- **Publisher.** EIA.
- **URL.** `https://www.eia.gov/electricity/data/state/annual_generation_state.xlsx`, linked from `https://www.eia.gov/electricity/data/state/`.
- **Fetched by.** `pipeline/electricity/fetch_fuel_mix.py`.
- **Terms.** License not stated in this project's files. It is a U.S. government publication.
- **In this repository.** The raw workbook is not. The derived groups and report are, in `data/frozen/fuel_mix_groups.csv` and `data/frozen/fuel_mix_report.json`.

### NOAA heating and cooling degree days

- **What it is.** Degree days measure how much heating or cooling a year's weather called for. This product weights them by state population (2010 Census). The study sums the daily values to calendar years, 2001 to 2025, and uses them as weather controls.
- **Publisher.** NOAA Climate Prediction Center (CPC).
- **URL.** `https://ftp.cpc.ncep.noaa.gov/htdocs/degree_days/weighted/daily_data/<YEAR>/StatesCONUS.Heating.txt` and `.../StatesCONUS.Cooling.txt`. The script also saves the product's description pages and NOAA's nClimDiv state readme (`https://www.ncei.noaa.gov/pub/data/cirs/climdiv/state-readme.txt`) to record why this product was chosen.
- **Fetched by.** `pipeline/electricity/fetch_degree_days.py`.
- **Terms.** License not stated in this project's files. It is a U.S. government publication.
- **In this repository.** The raw files are not. The annual figures and report are, in `data/frozen/degree_days.csv` and `data/frozen/degree_days_report.json`.

### Market regions and utility mergers

- **What it is.** Which wholesale market each utility buys in, by year. From 2013 this is read from the balancing authority each utility reports on Form 861 (through PUDL). Before 2013 it comes from a hand-built table of dated market entries and exits, `pipeline/electricity/market_moves.csv`. Utility mergers come from a second hand-built table, `pipeline/electricity/succession.csv`. Both tables carry a source URL and quote for every row.
- **Publisher.** The underlying pages are published by the market operators, utilities and regulators named row by row.
- **Read by.** `pipeline/electricity/market_region.py`, `pipeline/electricity/market_zones.py` and `pipeline/electricity/succession.py`.
- **Terms.** License not stated in this project's files for the pages cited.
- **In this repository.** Yes, the two tables. The cited pages are not.

## Data center sites

### OpenStreetMap, through the Overpass API

- **What it is.** Map objects in the United States tagged as data centers (`telecom=data_center`, `building=data_center` or `man_made=data_center`). The study trusts them for location and footprint, not for dates or load.
- **Publisher.** OpenStreetMap contributors. The query runs against the public Overpass API.
- **URL.** `https://overpass-api.de/api/interpreter`. The query is `OVERPASS_QUERY` in the fetch script.
- **Fetched by.** `pipeline/facilities/fetch_facilities.py`.
- **Terms.** Open Database License (ODbL), as `fetch_facilities.py` and `pipeline/facilities/sources.py` state. Credit "© OpenStreetMap contributors".
- **In this repository.** The raw download is not. Rows derived from it (ids beginning `osm:`) appear in the inventory's verification and frozen files.

### Epoch AI Frontier Data Centers

- **What it is.** About a hundred very large AI data center sites, with construction timelines that Epoch AI built from imagery and permits. The study trusts it for dates and load at the sites it covers.
- **Publisher.** Epoch AI.
- **URL.** `https://epoch.ai/data/data_centers/data_centers.zip`.
- **Fetched by.** `pipeline/facilities/fetch_facilities.py`.
- **Terms.** Creative Commons Attribution 4.0 (CC BY 4.0), as `fetch_facilities.py` and `pipeline/facilities/sources.py` state. Credit Epoch AI.
- **In this repository.** The raw download is not. Rows derived from it (ids beginning `epoch:`) appear in the verification and frozen files.

### Business Insider data center permit census (2025)

- **What it is.** A 2025 census of U.S. data centers that Business Insider built from state air permits for backup generators. The study uses it for derived variables only, the permit year and the permitted generator capacity, and trusts it for whether a site exists and its rough size. A permit year is when a generator was permitted, not when the site started drawing power.
- **Publisher.** Business Insider.
- **URL.** `https://tbimedia.s3.us-east-1.amazonaws.com/bistudios/_00/dev_edit/graphics/2025/09/2025-09-datacenters-map-table/index.js`.
- **Fetched by.** `pipeline/facilities/fetch_facilities.py`. `pipeline/facilities/sources.py` reads the table out of the file as text and runs none of its code.
- **Terms.** No license is stated. The project's files say so, and for that reason the raw file stays in `data/raw/` and is never committed or redistributed.
- **In this repository.** Not in raw form. Rows derived from it (ids beginning `bi:`) appear in the inventory's verification and frozen files. They are credited to Business Insider here.

### EPRI state totals of data center electricity use

- **What it is.** Each state's total data center electricity use by year. `build_inventory.py` scales permit-based load in each state so that the 2024 total matches EPRI's, and the treatment-history bounds read the earlier years.
- **Publisher.** EPRI (Electric Power Research Institute).
- **URL.** None in this project's code. The file is read from `data/raw/epri/epri_state_dashboard.json`.
- **Fetched by.** No script in this folder fetches it.
- **Terms.** License not stated in this project's files.
- **In this repository.** No. The state totals used and the state scale factors are summarized in `data/frozen/inventory_report.json`.

### Census Bureau geocoder

- **What it is.** A public service that turns a street address into coordinates. The study used it to place Epoch AI sites from their addresses.
- **Publisher.** U.S. Census Bureau.
- **URL.** `https://geocoding.geo.census.gov/geocoder/locations/onelineaddress`.
- **Read by.** `pipeline/facilities/build_inventory.py`, through a cache at `data/raw/facilities/epoch/geocode_cache.json`. As shipped the build does not call the geocoder. It stops if an address is missing from the cache.
- **Terms.** License not stated in this project's files. It is a U.S. government service.
- **In this repository.** No.

### Census cartographic boundary file of states (2023)

- **What it is.** Simplified state outlines, used to place sites in states.
- **Publisher.** U.S. Census Bureau.
- **URL.** `https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_20m.zip`.
- **Fetched by.** `pipeline/facilities/build_inventory.py`, the first time it runs, saved as `data/raw/territories/states.gpkg`.
- **Terms.** License not stated in this project's files. It is a U.S. government publication.
- **In this repository.** No.

### Electric Retail Service Territories (HIFLD)

- **What it is.** Polygons of each electric utility's retail service area, from about the 2022 Form 861 vintage. The polygons overlap. The study uses them to find which utility serves each site, and for the instrument and the reconciliation rows. The original HIFLD Open portal was retired in August 2025, so the script pulls a public ArcGIS copy of the same layer.
- **Publisher.** Built by Oak Ridge National Laboratory for the U.S. Department of Energy's Office of Cybersecurity, Energy Security, and Emergency Response (CESER), and published through HIFLD.
- **URL.** `https://services3.arcgis.com/OYP7N6mAJJCyH6hd/arcgis/rest/services/Electric_Retail_Service_Territories_HIFLD/FeatureServer/0/query`.
- **Fetched by.** `pipeline/facilities/fetch_territories.py`.
- **Terms.** License not stated in this project's files.
- **In this repository.** No. `pipeline/electricity/pjm_late_zones.csv` is derived from it.

### EPA ENERGY STAR certified data centers

- **What it is.** A public registry of certified data centers, with address, owner and year constructed. The study uses it as a lead for dating sites, never as a verdict on its own.
- **Publisher.** U.S. Environmental Protection Agency, ENERGY STAR.
- **URL.** `https://www.energystar.gov/buildings/certified-data-centers`.
- **Fetched by.** `pipeline/facilities/match_energystar.py`.
- **Terms.** License not stated in this project's files.
- **In this repository.** The page is not. The matches are, in `pipeline/facilities/leads/energystar_matches.csv`.

### County GIS layers in Northern Virginia

- **What it is.** Two counties publish a record for each data center building with the year it was built. Loudoun County's "Existing Structures" layer and Prince William County's "Data Center Buildings" layer.
- **Publisher.** Loudoun County and Prince William County, Virginia.
- **URLs.** `https://logis.loudoun.gov/gis/rest/services/Projects/BuildOut_LandUse/MapServer/0/query` and `https://gisweb.pwcva.gov/arcgis/rest/services/CountyMapper/LandDevelopment/MapServer/10/query`.
- **Fetched by.** `pipeline/facilities/match_county_gis.py`.
- **Terms.** License not stated in this project's files.
- **In this repository.** The layers are not. The matches are, in `pipeline/facilities/leads/county_gis_matches.csv`, and the accepted ones in `pipeline/facilities/verified/`.

### Other government records for large sites

- **What it is.** County assessor and GIS services, state air-permit files and city permit systems, used to date large sites that had only a permit-based year. Examples are the Maricopa County assessor, Oregon DEQ air permits, the Harris County and Tarrant County appraisal data, and Cook County's open data.
- **Publisher.** The county, state and city offices named record by record.
- **URLs.** Listed in `RECORDS` in `pipeline/facilities/write_public_records_batch.py`. `docs/public-records.md` lists every source tried, including the ones that gave nothing.
- **Fetched by.** `pipeline/facilities/write_public_records_batch.py` (`--check` fetches the records again).
- **Terms.** License not stated in this project's files.
- **In this repository.** The records are not. The years taken from them are, in `pipeline/facilities/verified/`.

### Operator-reported electricity use

- **What it is.** Meta and Apple publish the electricity each of their data centers used each year. Where they do, the study uses that figure in place of the generator-based size.
- **Publisher.** Meta and Apple.
- **URLs.** One per row in the `source_url` column of `pipeline/facilities/verified/site_energy.csv`.
- **Fetched by.** `pipeline/facilities/site_energy.py --check`, which fetches each cited document again and checks that each printed value appears in it.
- **Terms.** License not stated in this project's files.
- **In this repository.** The documents are not. The figures read from them are, in `pipeline/facilities/verified/site_energy.csv`.

### Hand verification of sites

- **What it is.** Operator pages, press releases, trade press, regulatory filings and public map layers used to confirm a site's serving utility, start year and size. The build accepts a finding only if it carries a source URL and a confidence of high or medium.
- **Publisher.** Many. Each is named row by row.
- **URLs.** In the `pipeline/facilities/verified/` files, and for the territory layers checked during verification, in `pipeline/facilities/leads/pass_c_layers_*.json`.
- **Fetched by.** `pipeline/facilities/pass_c_precision.py` queries the public map layers. The other pages were opened during the work and are not fetched by a script.
- **Terms.** License not stated in this project's files.
- **In this repository.** The pages are not. The findings are.

## Instrument inputs for one replication row

Row C of the plan compares this study with the shift-share instrument in Scalera, Bosetti and Pecci (CEPR). These four sources rebuild that instrument.

### FCC Form 477 fixed broadband deployment

- **What it is.** Where providers report broadband service, by census block. The study uses the six filings of 2017 to 2019 and keeps only the blocks with fiber to the end user (technology code 50).
- **Publisher.** Federal Communications Commission (FCC).
- **URLs.** `https://opendata.fcc.gov/resource/<dataset id>`, with dataset ids `9r8r-g7ut`, `pq3u-a6vs`, `ehbi-rr4z`, `kydr-hyy5`, `c67e-jknh` and `whue-6pnt`.
- **Fetched by.** `pipeline/instrument/fetch_instrument_inputs.py`.
- **Terms.** License not stated in this project's files. It is a U.S. government publication.
- **In this repository.** The raw files are not. The derived shares are, in `data/frozen/fiber_share.csv` and `data/frozen/fiber_share_by_unit.csv`.

### Census LODES 7 geography crosswalk

- **What it is.** A list of every 2010 census block with its internal point. The study uses the points to place fiber blocks inside utility territories.
- **Publisher.** U.S. Census Bureau, Longitudinal Employer-Household Dynamics (LEHD) program.
- **URL.** `https://lehd.ces.census.gov/data/lodes/LODES7/<st>/<st>_xwalk.csv.gz`, one file per state.
- **Fetched by.** `pipeline/instrument/fetch_instrument_inputs.py`.
- **Terms.** License not stated in this project's files. It is a U.S. government publication.
- **In this repository.** No.

### Census Value of Construction Put in Place

- **What it is.** Monthly private construction spending, not seasonally adjusted. The study uses the "Data center" column, published from 2014.
- **Publisher.** U.S. Census Bureau.
- **URL.** `https://www.census.gov/construction/c30/xlsx/privtime.xlsx`.
- **Fetched by.** `pipeline/instrument/fetch_instrument_inputs.py`.
- **Terms.** License not stated in this project's files. It is a U.S. government publication.
- **In this repository.** The workbook is not. The annual series is, in `data/frozen/dc_construction_spending.csv`.

### BLS Consumer Price Index (CPI-U)

- **What it is.** Annual averages of the consumer price index for all urban consumers (series `CUUR0000SA0`). Used to put spending and row C's prices in 2024 dollars.
- **Publisher.** U.S. Bureau of Labor Statistics (BLS).
- **URL.** `https://api.bls.gov/publicAPI/v2/timeseries/data/CUUR0000SA0`.
- **Fetched by.** `pipeline/instrument/fetch_instrument_inputs.py`.
- **Terms.** License not stated in this project's files. It is a U.S. government publication.
- **In this repository.** No.

## Credit

Thanks to the U.S. Energy Information Administration for Form 861 and the state generation data. Thanks to Catalyst Cooperative for PUDL. Thanks to NOAA's Climate Prediction Center for the degree days. © OpenStreetMap contributors, whose data is available under the Open Database License. Thanks to Epoch AI for the Frontier Data Centers data, used under CC BY 4.0. Thanks to Business Insider for its 2025 data center permit census. Thanks to EPRI for its state totals. Thanks to Oak Ridge National Laboratory, the Department of Energy and HIFLD for the retail service territory map. Thanks to the U.S. Census Bureau for the geocoder, the state boundaries, the LODES crosswalk and the construction spending series. Thanks to the FCC for Form 477 and to the Bureau of Labor Statistics for the CPI. Thanks to EPA's ENERGY STAR program, to Loudoun County and Prince William County, and to every county, state and city office whose records are cited in `docs/public-records.md`. Thanks to Meta and Apple for publishing each data center's electricity use.
