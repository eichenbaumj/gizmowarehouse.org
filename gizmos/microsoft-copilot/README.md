# How to Save the Government from Microsoft Copilot — source

Source materials and methodology notes for [the gizmo](../../src/content/microsoft-copilot.ts).

## What's in this folder

- `README.md` — research notes, source list, fact-check log, future-update triggers
- `pdf-template.html` — pandoc HTML template (cover band, body slot, page scaffold)
- `pdf-styles.css` — 17A brand stylesheet (fonts, page rules, type scale, tables, blockquote)
- `build-procurement-pdf.sh` — regenerates `public/assets/government-ai-procurement-guide.pdf` from its markdown source. Pass `--html-only` to skip the PDF step and just produce `preview.html` for browser iteration.
- `preview.html` *(gitignored)* — intermediate HTML output for browser preview before the WeasyPrint pass

The published artifacts live elsewhere:

- [`src/content/microsoft-copilot.ts`](../../src/content/microsoft-copilot.ts) — the post markdown
- [`public/assets/government-ai-procurement-guide.md`](../../public/assets/government-ai-procurement-guide.md) — the procurement checklist (markdown source)
- [`public/assets/government-ai-procurement-guide.pdf`](../../public/assets/government-ai-procurement-guide.pdf) — same content rendered to a 17A-branded PDF

## Research summary

Three parallel research passes were run during planning. The findings that ended up load-bearing in the post:

### 1. Copilot's underlying model (premise that needed correcting)

The original outline assumed Copilot was running an outdated model. **That is not correct as of May 2026.** Microsoft 365 Copilot now runs on GPT-5.4 Thinking (default since March 2026, with GPT-5.3 Instant as the lighter tier), and in January 2026 Microsoft added Claude Opus 4.5 and 4.7 as selectable models inside Copilot Studio, the Researcher agent, and Excel Agent Mode. The Researcher agent uses two models in parallel: GPT for initial research, Claude for review/critique.

This forced the central reframe: the argument is not that the model is bad. The argument is that Copilot has access to frontier intelligence and still ships a poor product around it.

### 2. Quality and reception evidence

- **Recon Analytics (via perspectives.plus)**: 70% of users initially preferred Copilot because of Office integration; only 8% kept that preference after trying alternatives. Market share among paid AI subscribers fell from 18.8% (July 2025) to 11.5% (January 2026).
- **Tessl head-to-head**: when Copilot is deployed alongside ChatGPT in the same enterprise, 76% of employees pick ChatGPT and 18% pick Copilot.
- **Gartner (August 2024, still cited)**: 72% of pilot users struggle to integrate Copilot into daily routines; 57% report engagement decline.
- **Microsoft FY26 Q3 (April 2026)**: 20M paid M365 Copilot seats (3.3% of 450M commercial M365 base). CEO claimed engagement parity with Outlook; weekly query growth 20% QoQ.
- **The Register (March 2026)**: Microsoft paused automatic Copilot deployment after admin backlash on opt-out model.
- **Documented failure modes**, aggregated from G2, Capterra, r/sysadmin: SharePoint/OneDrive content access failures unless manually attached; silent failures on Teams meeting note generation; instruction forgetting across sessions; refusals on benign content.
- **Nadella quote**: reportedly called some Copilot integrations "almost unusable" internally (Latitude.so).

### 3. Private-sector enterprise AI adoption

- **Anthropic revenue trajectory**: Jan 2024 $87M → Dec 2024 $1B → Dec 2025 $9B → Feb 2026 $14B → April 2026 $30B annualized run rate. ~80x in 16 months. Enterprise-driven (PYMNTS, VentureBeat).
- **Customer base**: 8 of the Fortune 10 are Claude customers; 1,000+ companies at $1M+/year ACV; 70% of Fortune 100 use Claude.
- **Named customers**: Bridgewater (50–70% research-cycle compression), Goldman Sachs (founding partner in May 2026 $1.5B Anthropic enterprise JV), Citi, Visa, AIG, Accenture (30,000 trained), Cognizant, McKinsey, TELUS (57,000 employees on Claude via internal Fuel iX platform), Deloitte (470,000 globally), Zapier.
- **OpenAI ChatGPT Enterprise**: 1.5M seats across 150,000+ companies; 7M total workplace seats. Enterprise revenue is now ~40% of total OpenAI revenue.
- **Coding**: Claude Code holds 54% of AI coding market; 46% of multi-tool developers name it "most loved" (vs Cursor 19%, GitHub Copilot 9%). Claude Code revenue ~$2.5B annualized run rate.

### 4. SLG procurement and pilots

- **Microsoft public-sector market share**: ~85% (CCIA / Omdia 2021 study, still cited).
- **Pricing**: M365 Copilot is $30/user/month, sold as add-on to existing M365 license. No new procurement event required at EA amendment.
- **GSA OneGov agreement (September 2025)**: 12 months of free Copilot for federal G5 customers, ~$3B in projected savings, flowing down to state/local through delegation.
- **Pennsylvania pilot (counter-evidence to "Copilot default is inevitable")**: PA partnered with OpenAI on ChatGPT Enterprise in 2024 (175 employees, 14 agencies, 12 months). Reported 95-min/day average time savings on admin tasks, 85%+ positive experience. PA later added Copilot alongside ChatGPT, not as a replacement.
- **Seattle**: Conducted 500-employee Copilot pilot 2024–25 with positive initial survey (2.5 hrs/wk savings). New mayor halted citywide rollout in March 2026.
- **NASCIO 2025 State CIO Survey**: 82% of CIO-org employees use generative AI in daily work (up from 53% prior year). AI governance ranked #1 priority for 2026. Specific Copilot adoption rates not broken out.
- **California Executive Order N-12-23 (2023)**: directed procurement guidelines for GenAI. CA has not announced a statewide Copilot mandate; departments are using the California Software License Program for "Copilot readiness services" without committing to Copilot endpoint.

## Counter-evidence weighed and acknowledged

- Pennsylvania and Seattle both show SLGs actively shopping alternatives or pausing rollouts. The Copilot default is not deterministic. The post is therefore framed as "structural vulnerability" rather than "inevitable capture."
- Some private-sector enterprises (notably in financial services and tech, ~64% of Fortune 500 by some surveys) do have active Copilot deployments — adoption is not zero in private sector. The head-to-head 76%/18% number is the right anchor because it isolates the choice from the lock-in.
- The 8% retention figure is from Recon Analytics, a single firm. Could not find independent corroboration in published material before May 2026; flagging as "single-source but credible" and pairing it with the Tessl head-to-head and the Gartner integration-difficulty number to triangulate.

## Sources used in the post

| Claim | Source |
|---|---|
| Microsoft holds 85% of U.S. public-sector productivity software | [CCIA / Omdia](https://ccianet.org/news/2021/09/new-study-shows-microsoft-holds-85-market-share-in-u-s-public-sector-productivity-software/) |
| GSA OneGov 12-month free Copilot, September 2025 | [GSA](https://www.gsa.gov/about-gsa/newsroom/news-releases/multibillion-dollar-gsa-onegov-agreement-with-microsoft-brings-steep-discounts-09022025) |
| 70% / 8% retention; 18.8% → 11.5% market share; Claude inside Copilot Studio | [perspectives.plus](https://www.perspectives.plus/p/microsoft-ai-numbers-good-bad-ugly) |
| 76% / 18% Copilot vs ChatGPT head-to-head | [tessl.io](https://tessl.io/blog/developers-love-claude-code-but-microsofts-copilot-has-enterprise-edge) |
| Nadella "almost unusable" quote | [latitude.so](https://latitude.so/blog/microsoft-copilot-ai-performance-reliability-issues) |
| Anthropic $30B run rate, April 2026 | [PYMNTS](https://www.pymnts.com/artificial-intelligence-2/2026/anthropic-hits-30-billion-run-rate-as-enterprise-demand-accelerates/) |
| 8 of Fortune 10 are Claude customers; 1,000+ at $1M+ ACV | [getpanto.ai](https://www.getpanto.ai/blog/anthropic-ai-statistics) |
| OpenAI ChatGPT Enterprise 1.5M seats / 150k+ companies | [getpanto.ai](https://www.getpanto.ai/blog/openai-statistics) |
| Accenture trains 30,000 professionals on Claude | [Anthropic](https://www.anthropic.com/news/anthropic-accenture-partnership) |

## Update triggers

If any of the following changes, the post needs revisiting:

- **Microsoft updates Copilot's backing model** (recheck quarterly). The "frontier model, broken wrapper" reframe depends on the model staying frontier-class.
- **Microsoft ships a meaningful Copilot product overhaul** (a "Copilot 2" reset, a major UX redesign). The whole post may need a revisit.
- **A NASCIO or StateScoop survey publishes Copilot-specific SLG adoption rates.** Swap that into the procurement-physics section.
- **Anthropic / OpenAI revenue figures move materially.** Refresh the contrast numbers.
- **An independent retention study contradicts the 8% Recon Analytics figure.** Re-anchor section 3.
