# data-center-utility-bills

## What this is

This folder holds the code, the frozen inputs and the result records for a study I ran on one question. When a utility takes on a lot of data center load, does it go on to charge its residential customers more than it otherwise would have? Everything here is built from public data. What the study found, in plain language, is in the write-up on gizmowarehouse.org.

The design in brief. A utility counts as a "host" from the first year its data center load reaches 2% of its 2009 to 2011 retail sales. The study looks at hosts that crossed that line in 2011 to 2022. Each host is compared with ten matched utilities in the same wholesale market region. A market region is the wholesale power market a utility buys in, such as PJM or MISO. The method is a stacked event study. Each host and its ten matches form their own before-and-after comparison, from six years before the crossing to three years after, and the comparisons are stacked and estimated together. Prices come from EIA Form 861, the federal government's yearly survey of every electric utility, for 2001 to 2025. Data center load comes from an inventory of 2,244 sites built from three public sources and checked by hand where it mattered most.

I posted what I would want if I were trying to reproduce this study or build on it.

## What is here

- `PREANALYSIS.md` is the pre-analysis plan. It fixes the question, the design, the checks and the wording of the headline before any outcome was read.
- `pipeline/electricity/` fetches EIA Form 861 and builds the panel of utilities by state by year. It also fetches degree days and state fuel mix, assigns market regions, and sums merged utilities into one unit (`succession.csv`).
- `pipeline/facilities/` fetches the data center sources and builds the inventory. Hand-verification records are in `pipeline/facilities/verified/`. Leads that were not yet verified are in `pipeline/facilities/leads/`.
- `pipeline/instrument/` rebuilds two public inputs (FCC fiber blocks and Census data center construction spending) for one row that compares this study with a published paper.
- `pipeline/analysis/` holds the matched design, the power simulation, the estimation code, every run the plan lists and the code that wrote the result records.
- `pipeline/tariffs/` picks the sample for a tariff check from load and sales only.
- `tests/` holds the unit tests. Most of them run on invented data. `tests/fixtures/` holds two small made-up data files.
- `data/frozen/` holds the inputs and intermediate outputs that the plan and the write-up cite, plus three fetch manifests that record each download's URL, size and SHA-256 hash. `data/frozen/superseded/` keeps an earlier run that the final design replaced, with a note saying so.
- `data/results/session28_uc/` holds the machine-written records of the one run on outcomes.
- `docs/prior-work.md` and `docs/prior-work-detail.md` record the earlier studies I read and what each one estimated.
- `docs/claims.md` checks public quotes, blocked projects and polls against primary sources.
- `docs/public-records.md` lists the government record sources tried for dating large sites and what each gave.
- `docs/tariff-check.md` describes the tariff check.
- `docs/gate1/` holds 32 specification and findings documents the code refers to. The code names more documents in that folder than are here. The rest are working records and stay private. One of them, `stored-file-hashes-at-the-freeze-2026-11-20.txt`, lists the SHA-256 hash of each stored file at the freeze.

## How to rebuild it from public data

### Environment

The study ran on Python 3.13.5. Create a virtual environment with Python 3.13, activate it and install the pinned packages.

```
python3.13 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Run every command from this folder. The project's convention is `python3 -I`, which runs Python in isolated mode so that nothing from the working directory or the user's environment gets onto the import path. With the virtual environment active, `python3` is the environment's interpreter.

One package matters more than the others. The Callaway and Sant'Anna estimator, a second estimator run beside the main one, needs `diff-diff` at exactly version 4.0.0. The code refuses that run if a different version is installed.

### Fetch

Each script downloads into `data/raw/`, which is not in this repository. `DATA_SOURCES.md` says what each source is and where it comes from.

```
python3 -I pipeline/electricity/fetch_eia861.py
python3 -I pipeline/electricity/fetch_fuel_mix.py
python3 -I pipeline/electricity/fetch_degree_days.py
python3 -I pipeline/facilities/fetch_facilities.py
python3 -I pipeline/facilities/fetch_territories.py
python3 -I pipeline/instrument/fetch_instrument_inputs.py
```

`fetch_fuel_mix.py` and `fetch_degree_days.py` also write their outputs straight into `data/frozen/`, so they overwrite the shipped copies. The FCC requests in `fetch_instrument_inputs.py` are slow. The script retries and resumes.

Sources change after the fact. PUDL, the OpenStreetMap query and the Business Insider file are live. A fresh download may not match the hashes in `data/frozen/fetch_manifest_*.json`.

### Build

These steps rebuild the electricity panel, the inventory and the matched design. They write to `data/interim/` and `data/frozen/`. `build_panel.py` also computes residential prices and writes them under `data/blind/`, apart from the quantities. The steps after it work from load and sales only. If you have this folder under git, `git diff data/frozen` afterward shows what your rebuild changed against what I froze.

```
python3 -I pipeline/electricity/build_panel.py
python3 -I pipeline/electricity/market_zones.py
python3 -I pipeline/facilities/apply_verified.py
python3 -I pipeline/facilities/build_inventory.py
python3 -I pipeline/facilities/dating_report.py
python3 -I pipeline/facilities/dating_sensitivity.py
python3 -I pipeline/facilities/buildout.py
python3 -I pipeline/facilities/treatment_bounds.py
python3 -I pipeline/analysis/design.py
python3 -I pipeline/instrument/build_fiber_share.py
```

`market_zones.py` needs the territory map from `fetch_territories.py`. `treatment_bounds.py` must run after `build_inventory.py`, `dating_sensitivity.py` and `buildout.py`. `design.py` must run after `treatment_bounds.py`.

Two inputs to `build_inventory.py` do not come from any fetch script here. Both are explained under "What is not included".

Many other modules write single files under `data/frozen/`. Each says in its own docstring what it reads, what it writes and what must run first. I have not written out one complete order for them here.

### Tests

The command below runs the suite as the project ran it. It leaves out nine test files that exercise a parked audit path and the panel builder. The project's own rules kept those nine out of its suite runs, and I have not run them in a clean copy either.

```
python3 -I -m pytest -q -p no:cacheprovider tests/ \
  --ignore=tests/test_adapter_against_evaluator.py --ignore=tests/test_adapter_evaluator.py \
  --ignore=tests/test_adapter_toy_cases.py --ignore=tests/test_availability.py \
  --ignore=tests/test_availability_adapter.py --ignore=tests/test_availability_run_check.py \
  --ignore=tests/test_availability_runs.py --ignore=tests/test_availability_screen_run.py \
  --ignore=tests/test_panel.py
```

What to expect. On 2026-11-22 I ran these 105 test files in a clean copy holding exactly the files published here, with no data fetched or rebuilt. Of 3,106 tests, 3,090 passed, 8 were skipped, 1 is marked as an expected failure, and 7 did not pass. The run took about 13 minutes. All 7 need something this repository does not hold.

- 5 tests in `tests/test_pass_c_exact_s18.py` need the rebuilt inventory under `data/interim/`.
- 1 test in `tests/test_pool_restrictions.py` compares text against the private decisions log.
- 1 test in `tests/test_condition4_peaks_invented.py` compares text against a private handover note.

The 8 skipped tests say in their skip messages that the panel or the inventory has not been built.

### The run on outcomes, and its gate

The outcome is the residential price. The code keeps prices out of reach until the plan is frozen. Every read of an outcome after the freeze goes through one function, `load_outcomes_after_the_freeze` in `pipeline/analysis/run_outcomes.py`. It refuses to read unless all of these hold:

- a file named `GATE1_SIGNED` exists in this folder
- the environment variable `DCUB_OUTCOME_RUN_AUTHORIZED` is set to `1` for that process
- git shows that `PREANALYSIS.md` is committed with no uncommitted change, and that the freeze commit `ea426c4` is an ancestor of the current commit

`pipeline/analysis/execute_outcomes.py` runs the entries in the plan's order. Rows U and C come first. They are the two rows that set this study's setup beside published papers. They are comparisons only, and the code gives no verdict on whether a paper reproduces. The inventory check against sales comes next, then the rest. The script writes one JSON record per run, a manifest and a plain-text report into the folder you name. The script also refuses to start unless `diff-diff` 4.0.0 imports and git shows no uncommitted change under `pipeline/`, `tests/` or `PREANALYSIS.md`. Run with no arguments, it prints what it would do and does nothing. The run that made the records here was this command, with the gate file in place and the variable set for that process only.

```
python3 -I pipeline/analysis/execute_outcomes.py --inputs-are research_data_after_the_freeze --output-dir <new folder> --through remaining
```

A copy of this folder without the private repository's history will not pass the third check, because the freeze commit is not in it. The function refuses with a message saying why, and nothing is read. To estimate on your own rebuild, `run_outcomes.run_all(inputs, outcomes)` takes the assembled inputs (`assemble_inputs.assemble`) and an outcome frame you pass in. Its docstring describes what it expects. The run also needs inputs that a public rebuild cannot make as shipped. They are listed under "What is not included".

## Where the results are

`data/results/session28_uc/` holds the machine-written output of the one run on outcomes. `manifest.json` lists every record in the order it was written. `report.txt` is the plain-text report written alongside. The 59 numbered JSON files are the run records. The code that wrote them (`pipeline/analysis/execute_outcomes.py`) gives every record its provenance. That covers the freeze commit, the commit of the code that ran, the Python and library versions and a hash of the outcome file as it was read. No outcome value goes into the provenance.

Start with `report.txt`. Every record carries a field named `estimated` that says whether the entry produced a number. Three entries did not, and their records say why. The records by number:

- `0001` and `0004` are checks made at the moment the outcome file was read.
- `0002` and `0003` are the two rows that set this study beside published papers (rows U and C in the plan).
- `0005` checks the inventory's data center load against each utility's reported sales.
- `0006` to `0009` are the main estimate on four sets of utilities. `0006_main_headline_set` is the set the write-up leads with, the utilities whose data centers I could verify best. `0009_main_every_cohort_utility` is every utility that crossed the 2% line in 2011 to 2022 and could be analyzed. `0007` and `0008` are two other sets the plan defines, the ten-year set and the headline set plus the utilities left unsettled.
- `0010` is the plan's timing run and `0011` weights utilities by their customers.
- `0012` to `0014` are the other outcomes. They are electricity use per customer, the bill per customer and the count of residential customers.
- `0015` to `0021` are the plan's "second number", an estimate per point of data center load share, with its sensitivity runs.
- `0022` to `0026` change which utilities may serve as comparisons.
- `0027` to `0029` assume data centers started later than recorded, by one, three and five years.
- `0030` and `0031` are the second estimator (Callaway and Sant'Anna) and the check of whether the two estimators agree.
- `0032` to `0039` change one design choice at a time. They cover a longer horizon, future hosts as comparisons, comparisons from the same state, thresholds of 1% and 5%, two fuel-mix variants and a size-band run.
- `0040` to `0048` are the extra analyses the plan labels E1 to E7.
- `0049` to `0052` are the plan's four conditions. They are load share, investor ownership, retail choice and past utilization.
- `0053` to `0056` drop one market region, one state, Virginia, or the five highest-load utilities at a time.
- `0057` to `0059` are the tariff check, the regional layer and exploratory work. None of the three was estimated.

`PREANALYSIS.md` defines every entry by the same name.

The write-up on gizmowarehouse.org says what the results mean. These files are the record it rests on.

## What is not included, and why

- `docs/DECISIONS.md`, the project's private decisions log. Code comments cite its entries by number, for example "D-49". Those numbers point into that log. Where a comment and the plan differ, the frozen plan governs. Five modules read the log, and the parts that read it will not run without it. `pipeline/analysis/pool_restrictions.py --check` compares its text against the log. The other four look up an authorizing entry in the log and stop when they cannot find it. They are `pipeline/analysis/run_availability_screen.py`, `pipeline/electricity/audit_availability.py`, `pipeline/electricity/preserve_availability.py` and `pipeline/electricity/write_usable_flag.py`.
- The working handover notes, outside reviews, the research notes under `docs/research/` and the other files under `docs/gate1/`.
- A planned water-bill study. It was scoped and closed because not enough historical water rates could be found. Its code, documents and data are left out.
- `data/raw/`, `data/interim/` and `data/blind/`. The fetch scripts rebuild most of `data/raw/`, and the build scripts rebuild most of the other two. The items below are the gaps. The Business Insider file has no stated license, so I do not redistribute it.
- The cache of Census geocoder results for Epoch AI street addresses. It lives in `data/raw/`. `build_inventory.py` does not call the geocoder and stops if an address is missing from the cache, so a fresh rebuild needs that cache rebuilt first.
- EPRI's state totals of data center electricity use (`data/raw/epri/epri_state_dashboard.json`). `build_inventory.py` scales permit-based load in each state to these totals. No script here fetches the file.
- The usable flag on the quantities file (`res_price_usable`). The outcome run reads it to decide which utility-years have a usable price. `build_panel.py` does not write it. `write_usable_flag.py` does, and that script reads the private log and runs under a macOS sandbox profile. So a public rebuild does not produce the flag as shipped.

Some tests need the rebuilt data or the private documents. The test status above says which.

## The plan and its freeze

I wrote the plan before any outcome was read and froze it in the project's own git history. The plan is internally frozen and not externally preregistered. Three commits mark it. The freeze commit is `ea426c4`. The approved specification is `ed3a2ff`. The execution commit, the code that ran on the outcomes, is `2e4196f`. These ids belong to the private repository where the work was done. This public copy does not carry that history, so you cannot check them out here. The plan file itself records the freeze, and the code writes into each result record the commits it ran under.

## Who did the work

I built this with Claude, Anthropic's AI model, over more than thirty working sessions. Claude wrote the code, did the bulk of the research legwork and ran the tests. I set the question, made the calls and read the results. The mistakes are mine.

## License and reuse

Two files at the top of this repository set the terms. `LICENSE` puts the code under the MIT License. `LICENSE-CONTENT` puts the write-ups, the documents and the data files the pipelines produce under Creative Commons Attribution 4.0.

The data sources keep their own terms. `DATA_SOURCES.md` lists them and credits each one.
