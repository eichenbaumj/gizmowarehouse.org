# NYC Public Grocery Math — source

Build scripts and source records for [the April piece](../../src/content/nyc-public-grocery-math.ts) and [the July 2026 update](../../src/content/nyc-public-grocery-new-math.ts). This folder is the standing model of record for the NYC public grocery store plan — it gets revisited each time the administration announces implementation specifics (next checkpoints: RFP Q&A postings Aug 14 / Sep 21 2026, operator selection early 2027, store openings).

- `build_model.py` → writes `public/assets/nyc-public-grocery-model.xlsx` (the downloadable financial model; the July 2026 Update tab carries the announced-plan scenarios in the RFP-consistent frame — 13,800 selling sqft, FMI-2025 $1,019/sqft, leverage in today's dollars at the 4% municipal rate)
- `build_charts.py` → writes all five charts: the April pair (`grocery-capex-benchmark.png`, `grocery-leverage-comparison.png`) and the July 2026 set (`grocery-30-leverage.png`, `grocery-30-envelope.png`, `grocery-30-reach.png`)
- `verify_claims.py` → the pre-publish gate: independently re-derives every headline number and checks it against the workbook (LibreOffice-evaluated), both pieces' displayed literals, the chart data arrays (numerically), `src/config/groceryMath30.ts` AND the dial's rendered copy in `GroceryDial.tsx`, plus a build-fingerprint freshness check (the workbook must have been built from the current `build_model.py`)
- `IMPLEMENTATION_LEDGER_2026-08.md` → every official document and quote on the rollout, sourced and dated, conflicts flagged; append to it on future updates
- `research/vision_plan.pdf` (+ extracted `.txt`) → the July 27, 2026 "N.Y.C. Groceries: A Recipe for Affordability" vision plan
- `research/rfp/NYC-Groceries-Operators-RFP.pdf` (+ extracted `.txt`) → the 44-page operator RFP (obtained August 2, 2026), the operative procurement document: footprints (Appendices D–E), Core Basket categories (Appendix C), Affordability Payment structure (pp. 6–7, 20)
- `research/audit_2026-08/` → the August 2026 adversarial pass: decision ledger, canonical numbers, merged findings (43 verification agents + 9 blind refuters), evidence cache
- `research/economist-review_2026-08/` → the economist-review round (critique from an economist reader, relayed secondhand, Aug 6): RESPONSE_MEMO.md (point-by-point reply + questions for the follow-up conversation), RESEARCH_NOTES.md (5-agent sweep: site tenure, BCA conventions, asset lives, rent comps, real rates). Decisions in the audit ledger, D-22/D-23

Run from the repo root:

```bash
python3 gizmos/nyc-public-grocery-math/build_model.py
python3 gizmos/nyc-public-grocery-math/build_charts.py
python3 gizmos/nyc-public-grocery-math/verify_claims.py
```

Dependencies: `openpyxl`, `matplotlib`, `numpy`; `verify_claims.py` additionally needs LibreOffice (`soffice`) on PATH for formula evaluation, and `build_charts.py` uses the Source Serif 4 / Source Sans 3 TTFs in `tools/.fonts-cache/` (fetched by `tools/generate-og-cards.py` on first run).

Gotchas:

- **All five PNGs regenerate on every `build_charts.py` run** — including the April pair, whose byte-freeze was retired in August 2026 when their data was corrected in place (see `research/audit_2026-08/DECISION_LEDGER.md`, D-13). Expect all five to show as changed after a run; that is now correct behavior.
- Every assumption in the model is a yellow cell with a sourced comment. The Assumptions tab keeps the April central case (10% discount) so the April piece's per-store P&L still matches the file; the announced plan lives on the July 2026 Update tab. Three April-era assumptions (school-meals cost basis, FRESH cost/benefit sourcing, SNAP household count) were corrected in August 2026 in BOTH pieces — the April piece's banner discloses this.
- The gate's word cap splits the piece at the first `<details` tag — the methodology appendix and Sources block are exempt by design; body prose is not.
