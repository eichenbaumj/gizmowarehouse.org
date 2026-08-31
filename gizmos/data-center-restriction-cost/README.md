# Pricing the Fear of Data Centers — source

Source materials for [the gizmo](../../src/content/data-center-restriction-cost.ts). Draft built 2026-08-08/09; live at gizmowarehouse.org/gizmo/data-center-restriction-cost.

## What's here

- `SCOPING.md` — the scoping memo: thesis, decision ledger (all four resolved with Joe), the claims-never-to-make list, precision notes from verification, build phases. Read it before editing the prose.
- `research/` — six verified research tracks (restriction landscape, fiscal benchmarks, blocked projects, policy menu, demand geography, methods critique), each with an adversarial verification block. ~48 load-bearing claims checked against primary sources. `research/displacement-audit-memo.md` is the 2026-08-19 verdict memo on the "blocked projects move" claim (two-axis taxonomy, pre-registered kill criteria, placebo arm, hostile read); its raw packets are `pipeline/raw/workflow_relocation_audit.json` and `pipeline/raw/workflow_followup_verdicts.json`.
- `pipeline/` — the data pipeline (Python stdlib only). `run_all.py` fetches Moratorium Nation + datacentertracker.org, merges the hand-curated state/tariff layers, geocodes, enforces QA gates, and writes `public/data/data-center-restriction-cost/*` plus the CSV download. `DECISIONS.md` logs every taxonomy judgment call — review with Joe before publish.
- `verify_claims.py` — the gate: locks the widget constants to `benchmarks.json`, enforces the prose MUST/MUST-NOT lists (attribution rules, vetoed-not-enacted, no national aggregates, no post-2036 projections), style budgets (em dashes, semicolons, AI tells), and outcome-tally-vs-prose consistency. Run it plus `npx tsc --noEmit` after any edit.

## Deployed pieces

- `src/content/data-center-restriction-cost.ts` — the piece
- `src/components/dcr/` + `src/config/dataCenterRestrictionCost.ts` — map + calculator embeds (`<dcr-map>`, `<dcr-town-calc>`)
- `public/data/data-center-restriction-cost/` — actions/outcomes/benchmarks JSON
- `public/assets/data-center-restriction-cost-{actions.csv,methodology.md}` — the download pills

## Before publish (not tonight)

1. Review `pipeline/DECISIONS.md` with Joe (taxonomy calls).
2. Sample-audit 25 datacentertracker rows against primary documents (`pipeline/raw/dct-spotcheck-sample.csv`).
3. OG card (`tools/generate-og-cards.py`), un-hide the entry, `npm run build`, push, Publish in Lovable, verify the live URL.
4. One visible-window eyeball of the map (hidden windows suspend rAF — a white canvas there is not a bug).
5. Quarterly-ish refresh intent: re-run `run_all.py`, update the snapshot date in `pipeline/config.py`, the as-of header, and re-run `verify_claims.py`.
6. **Outcome-trace registry (standing commitment, added 2026-08-19):** every refresh re-checks the trace's unresolved and dead rows (the 13 pending plus the 10 died) for status changes and late-appearing successor sites, against the audit's six kill criteria (`research/displacement-audit-memo.md` §pre-registered tests). Status changes are recorded in `pipeline/raw/workflow_traced_projects.json` with a DECISIONS.md entry, never silently overwritten. The trace edit runs `build_outcomes.py` standalone (never full `run_all.py` unless the actions snapshot is also being bumped).
