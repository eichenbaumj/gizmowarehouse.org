export default `
<img src="/assets/enterprise-ai-meme.jpg" alt='Three-headed dragon meme labeled "Enterprise AI": Claude and ChatGPT drawn as fierce dragons, Copilot as the goofy cartoon dragon with its tongue out' style="max-width: 420px; width: 100%; display: block; margin: 0 auto;" />

Most government employees who have AI on their work computer have **Microsoft 365 Copilot**. It's a bad product, unlocking little to negative value for the agencies running it. Agencies that ignored Copilot and bought ChatGPT or Claude instead are getting noticeably more done with the same staff: junior analysts producing first drafts that look like senior staff wrote them, 200-page environmental reviews compressed into board memos before lunch, a research assistant at every desk who answers at 11pm.

There's a structural reason for the gap. The fix is within reach this procurement cycle.

## Why this is happening

The procurement physics get you most of the way:

- **Microsoft holds about 85% of U.S. public-sector productivity software** ([CCIA / Omdia](https://ccianet.org/news/2021/09/new-study-shows-microsoft-holds-85-market-share-in-u-s-public-sector-productivity-software/)). Almost every agency runs M365, and most run on the GCC tenant.
- **Copilot is a $30 per-user-per-month add-on** to that existing license. Adding it is a single-line amendment at EA renewal: no new procurement, no fresh security review, no separate contract.
- **GSA's September 2025 OneGov agreement** [gives federal G5 customers 12 months of free Copilot](https://www.gsa.gov/about-gsa/newsroom/news-releases/multibillion-dollar-gsa-onegov-agreement-with-microsoft-brings-steep-discounts-09022025), and that's now flowing down to state and local through delegation.

CIOs are being asked to "do AI," and are offered a frictionless way to satisfy that mandate without touching procurement, security, or the lawyers. I don't blame them for taking the offer!

## Copilot is dramatically worse than out-of-the-box OpenAI or Anthropic

The cleanest test is head-to-head. Where Copilot and ChatGPT are deployed alongside each other in the same enterprise, **76% of employees pick ChatGPT and 18% pick Copilot** ([Recon Analytics, Feb 2026](https://www.reconanalytics.com/ai-choice-2026-why-licenses-dont-equal-adoption/)). Microsoft's share of paid AI subscribers fell from 18.8% to 11.5% in the six months between July 2025 and January 2026. When workers have Copilot, ChatGPT, and Gemini all available, only **8% pick Copilot** as their preferred tool &mdash; same direction as the 76/18 head-to-head. Satya Nadella reportedly called some Copilot integrations "almost unusable" internally ([latitude.so](https://latitude.so/blog/microsoft-copilot-ai-performance-reliability-issues)).

Caveat: these figures are paid-subscriber and private-sector. Nobody publishes a clean breakdown for state and local government specifically. If you have better SLG data, I'd love to see it.

This is not a model problem. Copilot runs GPT-5.4 Thinking, and in January 2026 Microsoft itself added Claude Opus 4.5 and 4.7 as selectable models inside Copilot Studio &mdash; a tacit acknowledgement that GPT alone in their wrapper wasn't producing what users needed. The intelligence is there. The wrapper around it is the failure point: the M365 integration layer, the agent orchestration, the policy layer that refuses benign requests citing safety.

## Meanwhile, in the private sector

- **Anthropic hit a $30B annualized revenue run rate in April 2026**, up from ~$1B at end of 2024 ([PYMNTS](https://www.pymnts.com/artificial-intelligence-2/2026/anthropic-hits-30-billion-run-rate-as-enterprise-demand-accelerates/)).
- **8 of the Fortune 10 are Claude customers; 1,000+ companies spend $1M+/year with Anthropic** ([getpanto.ai](https://www.getpanto.ai/blog/anthropic-ai-statistics)).
- **OpenAI ChatGPT Enterprise**: ~1.5M seats across 150,000+ companies ([getpanto.ai](https://www.getpanto.ai/blog/openai-statistics)).

[TELUS](https://www.anthropic.com/customers/telus), a Canadian telco, gave all 57,000 of its employees access to Claude through Fuel iX, an internal platform they built.

Where customers can choose, they're choosing. Where they can't, they're getting Copilot.

## What governments can do right now

**Stand up a 20-person AI seed team next month.** Not a bureaucratic pilot. A deliberate distribution of enterprise Claude or ChatGPT seats: 5 senior leaders who have never touched a frontier AI tool (the CIO, the budget director, two department heads, the chief of staff), 10 mid-career operators (analysts, attorneys, planners, communications, the program managers who write everything), and 5 newer staff. The point isn't to "evaluate AI." It's to build a small group of internal users who can describe to procurement what good looks like before the next EA renewal lands.

**Don't add Copilot to your next M365 renewal until it earns it.** Ask Microsoft for a head-to-head pilot against ChatGPT Enterprise or Claude Enterprise on three real workflows your agency runs: summarizing a long RFP response, preparing a research brief from a stack of source documents, building a recurring monthly report from raw data. If Copilot wins, buy it. If it loses, the renewal is the moment of maximum negotiating leverage you'll have all year. If you're an agency leader and your CIO hasn't done this, ask why; procurement runs on requests.

**Use the procurement checklist** &mdash; [PDF](/assets/government-ai-procurement-guide.pdf) or [markdown](/assets/government-ai-procurement-guide.md). Seed-team composition, head-to-head workflow tests with rubrics, vendor-comparison questions, sample EA-renewal language. The artifact you can hand your procurement office on a Monday morning.

## Bottom Line

M365 is a great franchise, and Copilot will probably get good. The problem is that government is the one customer base where Microsoft doesn't have to make it good first. Every other major customer can switch; government can't, easily, and Microsoft is pricing and shipping accordingly. The fix is for government to behave like every other large customer: buy on the merits, run the head-to-head, hold the renewal line until the product earns it. I'd happily buy Copilot the day it does.

If you want to talk through how this would map to your specific agency, joe@group17a.com.

<details>
<summary>Sources</summary>

- [CCIA: Microsoft holds 85% market share in U.S. public sector productivity software](https://ccianet.org/news/2021/09/new-study-shows-microsoft-holds-85-market-share-in-u-s-public-sector-productivity-software/) (Omdia study)
- [GSA OneGov agreement with Microsoft, September 2025](https://www.gsa.gov/about-gsa/newsroom/news-releases/multibillion-dollar-gsa-onegov-agreement-with-microsoft-brings-steep-discounts-09022025)
- [Perspectives Plus: Microsoft AI numbers (Recon Analytics retention data, 8% / 11.5% market share, Claude inside Copilot Studio)](https://www.perspectives.plus/p/microsoft-ai-numbers-good-bad-ugly)
- [Recon Analytics: AI Choice 2026 — 76% / 18% Copilot vs ChatGPT head-to-head](https://www.reconanalytics.com/ai-choice-2026-why-licenses-dont-equal-adoption/)
- [Latitude.so: Nadella "almost unusable" quote on Copilot integrations](https://latitude.so/blog/microsoft-copilot-ai-performance-reliability-issues)
- [PYMNTS: Anthropic hits $30B run rate, enterprise-driven](https://www.pymnts.com/artificial-intelligence-2/2026/anthropic-hits-30-billion-run-rate-as-enterprise-demand-accelerates/)
- [Panto AI: Anthropic statistics (Fortune 10 customers, $1M+ ACV count)](https://www.getpanto.ai/blog/anthropic-ai-statistics)
- [Panto AI: OpenAI statistics (ChatGPT Enterprise seats)](https://www.getpanto.ai/blog/openai-statistics)
- [Anthropic customer story: TELUS](https://www.anthropic.com/customers/telus)

</details>
`;
