# The Price of Insuring Yourself: source

Source materials and the full reproducible pipeline for [The Price of Insuring Yourself](https://gizmowarehouse.org/gizmo/self-insurance-cost) on gizmowarehouse.org. The piece asks whether New York local governments that carry their own liability spend more on lawsuits and liability insurance than governments of the same type and size that buy coverage from a risk pool or an insurer. Every number on the page comes out of the code in this folder.

## What's here

- `crosswalks/ny_treatment_labels.csv`: one row per government, with the liability arrangement read from the risk-management note (GASB Statement 10) in its audited financial statements, the document URL, the page, and a verbatim quote. The readings were done with AI help and checked by hand; the per-batch readings it is compiled from are in `crosswalks/ny_label_readings/`.
- `crosswalks/ny_line_coding.csv`: what each self-insurance-fund line, excess-insurance line, and internal premium charge pays (liability, or workers' compensation and health), read from the same statements with a quote and page per line. Only lines that pay liability count toward the outcome, and internal charges are not counted twice.
- `crosswalks/ntd_treatment_labels.csv`: the same labels for the largest directly operated transit agencies; `ny_pool_rosters.csv` (the NYMIR subscriber list, July 2026); `ny_switcher_verification.csv` (the premium-line breaks checked against statements, almost all accounting recodings); `state_tort_caps.csv`.
- `pipeline/`: numbered stages 01 to 10, `config.py` (every account code, threshold, and constant with its reason), `fetchers.py`, and `run_all.py` (orchestrator plus hard QA gates). `raw/` and `output/` are rebuilt by the pipeline and are not committed.
- `verify_claims.py`: the gate that locks the page's prose, the chart config, and the pipeline outputs to each other. It recomputes the numbers the prose states, checks the wording that depends on them, and fails on banned phrasing.

## Reproduce

```bash
cd gizmos/self-insurance-cost/pipeline
python3 -m pip install -r requirements.txt
python3 run_all.py            # fetch Comptroller + NTD data, build panels, models, exports (stage 07 takes a while)
python3 run_all.py --check    # re-validate existing outputs
python3 ../verify_claims.py   # prose/config/data lock
```

The only step that is not scripted is reading each government's risk-management note; those readings are the CSVs in `crosswalks/`, each row carrying the quote that justifies it, so a reader can check any label against its source.

## Data sources

- NY State Comptroller, Financial Data for Local Governments (account-level files, 1995 to 2026): https://wwe1.osc.state.ny.us/localgov/findata/financial-data-for-local-governments.cfm
- Federal Transit Administration, National Transit Database, via the DOT open-data portal: Operating Expenses by Type (`j5uj-anzx`), Service by Mode (`wwdp-t4re`)
- Audited financial statements of each labeled government (Federal Audit Clearinghouse and government websites), cited row by row in `crosswalks/`
- NY DFS examination report on NYMIR (as of December 31, 2020); Matthiesen, Wickert & Lehrer 50-state municipal liability chart (February 2022); Schwartz, 63 UCLA L. Rev. 1144 (2016); Rappaport, 130 Harv. L. Rev. 1539 (2017); Clark, "Municipal Liability Insurance as Police Oversight" (working paper, April 2026)

## Questions or corrections

joe@group17a.com
