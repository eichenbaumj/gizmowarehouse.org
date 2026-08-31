# Stage 1 go/no-go — RESULT: NO-GO for assessor-PAY → regressivity (causal)

Date: 2026-06-25. New York State, municipal assessing units, 2006–2025.

## What we built (all real, reproducible from `pipeline/raw/`)
- **Outcome:** NY ORPTS assessment-equity survey — Residential Coefficient of Dispersion
  (COD), PRD, Market-Value Ratio, by municipality × Survey Year, 2004–2025. ~600 munis
  report COD/yr; 989 munis ever; 768 with ≥5 yrs.
- **Treatment:** NY OSC AUD account **A13551 "Assessment / Personal Services"** —
  assessment-office payroll isolated per municipality × year, 1995–2025.
- **Crosswalk:** name+county join, 955/961 munis matched (99.4%).
- **Instrument:** shift-share = base-period (CBP 1998) county finance+real-estate
  employment share × national Financial-Activities wage shock (FRED CES5500000003).
- **Controls:** FHFA county HPI growth + 3-yr volatility (the boom confound).
- Analysis frame: `pipeline/output/ny_analysis_frame.parquet` — N≈8,967 muni-years,
  740 munis, 53 counties.

## Key estimates (dCOD / d log assessment pay)
| spec | estimate | t |
|---|---|---|
| raw cross-section, no FE | −1.60 | −5.4 |
| + county FE | −0.70 | −2.6 |
| + muni & year FE (within) | **−0.010** | −0.03 |
| within, also: PRD | +0.0005 | 0.19 |
| within, also: Market-Value Ratio | −0.56 | −0.48 |
| within, also: \|MVR−100\| | +0.49 | 0.42 |
| **first-stage F (instrument → pay)** | — | **≈2.2** |

## Verdict
Two independent failures: (1) **weak instrument** — local appraisal/finance wage
pressure does not move town assessment budgets (F≈2), because NY assessor pay is set on
sticky local schedules, disconnected from the private market; (2) **null within-muni
effect** — once size/wealth are absorbed, assessment pay has zero relationship with any
assessment-quality measure. The −1.6 raw gradient is entirely between-municipality
confounding (bigger/richer towns spend more AND assess better).

## Substantive lesson (the useful part)
Public assessment **pay** is not the binding margin. Assessment quality is driven by the
**reassessment decision** (lumpy, often state-subsidized), not the assessor's salary
flow — and public pay is so administratively compressed that a wage-shift instrument has
no first stage. This caution likely generalizes to the accountant/revenue-collector
fallbacks (same sticky-public-pay problem).

## Forks (pending Joe's decision)
1. **Repoint same data at the reassessment-policy natural experiment** (NY's elimination
   of state reassessment aid ~2010; CAP consolidation) → causal effect of assessment
   *effort/state aid* on regressivity. Keeps all data; changes lever pay→policy. Needs
   policy-timeline verification.
2. **National ASPEP-023 → FAC audit-quality** shift-share — expect the same weak-instrument
   wall; low-medium hope.
3. **Descriptive paper** — magnitude/incidence of regressivity + the confounded gradient,
   no causal claim. Lower ambition.
4. **Walk away from the paper**; fold the honest negative + compression finding into the
   existing comp-gap gizmo.
