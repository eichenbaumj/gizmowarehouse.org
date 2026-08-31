# Medicaid Work Requirements — source

Source materials for [the gizmo](../../src/content/medicaid-work-requirements.ts).

A nationwide, county-and-grid-level map of who'll be subject to the new federal Medicaid work requirements that take effect December 31, 2026, under Section 71119 of the One Big Beautiful Bill Act (OBBBA), which adds §1902(xx) to the Medicaid Act. The audience is state Medicaid directors and their eligibility-and-enrollment deputies, with the implicit operational pitch: find and help these people **now**, before the deadline.

## Layout

```
gizmos/medicaid-work-requirements/
├── README.md           ← this file
├── METHODOLOGY.md      ← the load-bearing trust document; cite from the post
└── pipeline/           ← all data + tile generation lives here
    ├── config.py       ← central config (every policy param + burden weight)
    ├── 01_fetch_acs.py through 13_upload_r2.py
    ├── build.sh        ← orchestrator
    ├── requirements.txt
    ├── cors.json       ← R2 bucket CORS rule
    ├── raw/            ← gitignored source data
    └── output/         ← gitignored derived files
```

## Quick orientation

- **Effective date:** December 31, 2026. States must notify enrollees by September 30, 2026. HHS interim final rule (CMS-2454-IFC) issued June 1, 2026 (Federal Register June 3); figures here do not yet reflect it.
- **Target population:** Adults 19-64 enrolled through ACA Medicaid expansion (eligibility category VIII), excluding those categorically exempt under OBBBA.
- **Federal mandatory exemptions:** parents/caretakers of children ≤13, medically frail (blind, disabled, SUD, disabling mental disorder, serious/complex medical conditions), pregnant or postpartum, recent incarceration, compliance with SNAP/TANF work requirements.
- **State-discretion levers:** short-term hardship exceptions (case-by-case), high-unemployment hardship exception (counties with unemployment ≥8% or ≥1.5× national average — state must request).
- **Cannot be waived under Section 1115.**
- **National benchmark:** CBO scored work requirements alone at 5.2M coverage loss by 2034, 4.8M new uninsured, 18.5M subject to verification each year. Urban Institute HIPSM (March 2026) projects 3-7M coverage loss from the work requirement alone, rising to 4.9-10.1M in 2028 once OBBBA's six-month redeterminations are added (high-vs-low mitigation).
- **Non-expansion states** (10): AL, FL, GA (Pathways partial expansion is separate), KS, MS, SC, TN, TX, WI, WY. These render gray-hatched with explanatory click-card; an "Uninsured Adults" overlay surfaces their would-be-affected population.
- **Early implementers** (publicly committed): Nebraska (May 1, 2026 — already in effect), Montana (July 1, 2026), Iowa (December 1, 2026), Arkansas (July 1, 2026 soft, full Jan 2027).

## Build it

```bash
cd gizmos/medicaid-work-requirements/pipeline
./build.sh --sample-state PA   # ~90s local iteration
./build.sh                     # full nationwide, ~90 min
```

See METHODOLOGY.md for everything the build is actually doing.
