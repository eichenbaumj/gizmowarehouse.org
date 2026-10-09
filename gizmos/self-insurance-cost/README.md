# The Price of Insuring Yourself — source

Source materials and the full reproducible pipeline for [the gizmo](../../src/content/self-insurance-cost.ts). Status: FULL FIRST DRAFT built 2026-10-08 (pipeline green, gates green, charts verified in the dev server at desktop and phone width). Not live; embeds not registered; awaiting Joe's review and his Publish OK. Argument (after Joe's review): the bill is the same (matched ratio 1.03, range 0.51 to 1.79), police exposure sets the level (1.43 per 10 points), and self-insurance buys a swing twice as large (0.54 vs 0.27 year-to-year) that lands on small police-heavy governments; see SCOPING.md for the three pre-registered sentences and `pipeline/DECISIONS.md` for every coding call.

The question: do governments that carry their own liability risk (self-insure) spend more on claims and insurance than governments of similar size and type that buy coverage from a public-entity risk pool or a commercial insurer? Every New York local government files the same two lines with the State Comptroller, premiums paid and judgments paid, so New York is where the test runs. The federal National Transit Database supplies the national picture for transit agencies.

All of this code is public (this folder ships to the public mirror, `eichenbaumj/gizmowarehouse.org`, once the post is live) and the post links back here.

## What's here

- `SCOPING.md` — thesis, the pre-registered primary specification (written before any model ran), the three result shapes and the sentence for each, the intervention menu drafted per result shape, the claims-never-to-make list, precision notes, decision ledger with Joe.
- `METHODOLOGY.md` — the reader-facing method note (also shipped as the methodology download).
- `research/` — the empirical design memo, the pools-vs-self-insurance primer, the 1985–86 liability crisis, Vallejo 2018, literature notes (Schwartz 2016, Rappaport 2017, Clark 2026, Governing 2016, Chicago COFA 2019), tort-cap notes, and the hostile methods read.
- `crosswalks/` — the hand-labeled treatment file (`ny_treatment_labels.csv`: one row per entity with the structure read from its audited financial statements, the document URL, page, and a verbatim quote), the ACFR worklist, transit labels, state tort caps. These ship with the gizmo; they are the auditable part.
- `pipeline/` — numbered stages 01–10, `config.py` (every constant with its source), `fetchers.py`, `run_all.py` (orchestrator + hard QA gates + report), `DECISIONS.md` (dated ledger of every coding call), `requirements.txt`. `raw/` and `output/` are gitignored and reproducible.
- `verify_claims.py` — the gate that locks the prose, the config literals, and the pipeline outputs to each other (pins, co-location of numbers with their framing, banned phrases, the no-MTA rule, style budgets, download files).

## Reproduce

```bash
cd gizmos/self-insurance-cost/pipeline
python3 -m pip install -r requirements.txt
python3 run_all.py            # fetch NY Comptroller + NTD data, build panels, models, exports
python3 run_all.py --check    # re-validate without rebuilding
python3 ../verify_claims.py   # prose/config/data lock
```

Stage inputs and outputs are listed at the top of each stage file. The only step that is not scripted is reading the GASB 10 risk-management note in each audited statement; those readings are recorded row by row in `crosswalks/ny_treatment_labels.csv` with the quote that justifies each label.

## Data sources

- NY State Comptroller, Financial Data for Local Governments (account-level, 1995–2026): https://wwe1.osc.state.ny.us/localgov/findata/financial-data-for-local-governments.cfm
- FTA National Transit Database via the DOT open-data portal: Operating Expenses by Type (`j5uj-anzx`), Service by Mode (`wwdp-t4re`)
- Audited financial statements (GASB Statement 10 risk-management notes) of the labeled entities, cited row by row in `crosswalks/`
- NY DFS examination report on NYMIR (2020); Matthiesen Wickert & Lehrer 50-state municipal liability chart (2/14/22); Schwartz, 63 UCLA L. Rev. 1144 (2016); Rappaport, 130 Harv. L. Rev. 1539 (2017); Clark, "Municipal Liability Insurance as Police Oversight" (working paper, 2026)

## Deployed pieces (when live)

- `src/content/self-insurance-cost.ts` — the piece
- `src/components/sic/` + `src/config/selfInsuranceCost.ts` — the embeds
- `public/data/self-insurance-cost/` — the JSON the embeds read
- `public/assets/self-insurance-cost-{ny-panel,ntd-panel,treatment-labels}.csv`, `-methodology.md` — the download pills

## Before publish

1. `python3 pipeline/run_all.py` green; every `[REVIEW]` in `pipeline/DECISIONS.md` resolved with Joe.
2. `python3 verify_claims.py`, `npm run typecheck`, `npm test`, `npm run build` green.
3. OG card, `PUBLISH_CHECKLIST.md` fields, mirror stanza paths, sitemap.
4. Joe's explicit OK in chat, then `python tools/new-gizmo.py --publish self-insurance-cost`, push, Publish in Lovable, verify the live URL, `npm run seo:ping`.
