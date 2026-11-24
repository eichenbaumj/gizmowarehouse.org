# Row C's price deflator: what is already on file (looked up 2026-11-19, session 22)

A lookup in permitted code and frozen reports. It adopts nothing, fetches nothing and changes no file. The plan is a DRAFT, not frozen. No price was read.

Read for it: `pipeline/analysis/reconciliation_c.py`; `pipeline/instrument/fetch_instrument_inputs.py` and `pipeline/instrument/build_fiber_share.py` (the instrument's fetch and build code); `data/frozen/fetch_manifest_instrument.json`; `data/frozen/instrument_report.json` (its Table S3 check); `data/frozen/dc_construction_spending.csv`; `data/frozen/reconciliation_c_design.json` (its deflator line); `docs/gate1/bounded-read-row-c-2026-11-19.md`; `PREANALYSIS.md` (row C). A grep for CPI, deflator and the BLS series id over the files of `pipeline/analysis`, `pipeline/electricity`, `pipeline/instrument`, `pipeline/facilities` and `pipeline/tariffs` (by folder, not recursively, files named `availability*` skipped) found the series in the instrument code and in `reconciliation_c.py` only; `reconciliation_mu.py` mentions the CPI only to say that row M applies no deflator because a common one cancels from comparisons of logs. Nothing under `data/raw` was opened.

## Finding: a deflator series is already on file, and row C's code already names it

A correction to the question as put: `reconciliation_c.py` does take real 2024 prices from the caller and converts nothing, but it does name a series. Its docstring says the CPI-U annual-average series is on file as column `cpi_u` of `data/frozen/dc_construction_spending.csv`, and that the paper used this same series is "the agent's reading and is not established". Its function `cpi_factors_to_2024(table)` returns `cpi_u[2024] / cpi_u[year]` from that table and nothing else, and its design summary records `"deflator_on_file": "cpi_u in data/frozen/dc_construction_spending.csv; factors cpi_u[2024]/cpi_u[year]"` (`data/frozen/reconciliation_c_design.json`). The series is not among row C's adopted approximations (`OURS_APPROXIMATIONS` in the same module has no deflator entry), so no ruling has fixed it, as far as these files show.

| | |
|---|---|
| Series | BLS `CUUR0000SA0`, the CPI-U, annual average (BLS period M13), per `fetch_instrument_inputs.py`. The agent's knowledge, not stated in the code: the id denotes all items, U.S. city average, not seasonally adjusted, index base 1982-84 = 100. |
| Source | BLS public API v2, `https://api.bls.gov/publicAPI/v2/timeseries/data/CUUR0000SA0`, requested for 2006 to 2015 and 2016 to 2025 (`fetch_instrument_inputs.py`). |
| Raw file | `data/raw/bls/cpi_u_annual.json`, 428 bytes, sha256 `f95db6b8badcf675675b5fc1e0a73b2b93d45c0f0786563e6dd74f47f887bebb`, in the manifest fetched 2026-11-11T20:03:07Z. The manifest has no Last-Modified date and no BLS release date for it. Which years the raw file holds is not established (it was not opened); the code asks for 2006 to 2025. |
| Frozen copy | `data/frozen/dc_construction_spending.csv`, column `cpi_u`, years 2014 to 2025 (the years with complete Census spending). 2015: 237.017; 2024: 313.689; 2025: 321.943. |
| What it already does in the study | Puts the Census data center construction spending series in 2024 dollars (`build_fiber_share.py`: `real_2024_musd = nominal_musd * cpi[2024] / cpi_u`), the "current" spending series of row C and of C5. |
| Covers row C's price years? | Yes. Row C's panel is 2015 to 2024 (`reconciliation_c.YEARS`), all inside 2014 to 2025. |

## What the paper uses, as the row C bounded read records it

`docs/gate1/bounded-read-row-c-2026-11-19.md` records that the paper converts prices to real 2024 dollars "using the Consumer Price Index (CPI)" (section 2.1, p. 4; Table S2 notes, p. 30) and spending likewise "using the CPI" (S1.5, p. 33; Table S3 notes, p. 34), without naming the series (rows 2e and 7b). It proposed, as ours and weak, the CPI-U all items annual average on file for both.

## Evidence on whether the paper's CPI is this series

Our Census spending deflated with this series equals the paper's printed Table S3 at the paper's printed precision in every year from 2015 to 2023 (3.63, 5.39, 5.97, 8.66, 10.4, 11.2, 11.5, 13.5, 20.6 billion; `data/frozen/instrument_report.json`, `table_S3_check_real_2024_bn`; the 2024 gap, 34.8 against 31.1, is a revision of the nominal series, the factor being 1 in 2024). That is consistent with the paper deflating spending by the CPI-U all items annual average. It does not establish it: no other CPI variant is on file, so whether another would also match at three significant figures was not checked. And it concerns spending; that the paper used the same series for price rests on its using the same words for both. I am uncertain about this.

## Proposal (ours, not the paper's)

Row C's deflator for residential price: the CPI-U all items annual average on file, `cpi_u` in `data/frozen/dc_construction_spending.csv`, applied as `cpi_factors_to_2024` already computes it (price in year t times `cpi_u[2024] / cpi_u[t]`), labelled "ours; the paper says only 'the CPI'; our spending deflated by this series matches the paper's Table S3 to its printed precision in 2015 to 2023, which supports but does not establish that it is the paper's series". No new series is fetched.

Why it matters at all, the agent's reading: row C is in levels, not logs, so a national deflator does not cancel the way it does for row M's comparisons of logs. With state-by-year effects it rescales each year's prices by one factor, which changes the weight each year carries in the slope. The agent expects the differences between CPI variants over 2015 to 2024 to move the estimate little, but that is not computed here and I am uncertain about it.

Until Joe adopts it, the element stays open as the code has it: the caller supplies real 2024 prices, and the series it used must be stated with the result.
