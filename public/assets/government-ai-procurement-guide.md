# Buying AI for a Government Agency

A short practical guide for senior staff and procurement officers. Built for May 2026.

The companion post at [gizmowarehouse.org/gizmo/microsoft-copilot](https://gizmowarehouse.org/gizmo/microsoft-copilot) makes the case that Microsoft 365 Copilot is the AI tool most government employees currently have, but Copilot is a vastly inferior product to widely adopted tools in the private sector. This is the practical guide for getting your agency onto the AI tools that actually work.

---

## 1. Set up the vendor meetings this week

Don't wait for a seed team or a procurement plan to start the conversation. Email Anthropic and OpenAI sales today. Microsoft can't be made to compete with vendors you haven't talked to.

Three calls to schedule:

- **Anthropic (Claude Enterprise / Claude for Government)** &mdash; via [anthropic.com/contact-sales](https://www.anthropic.com/contact-sales). Ask for: pricing at your seat count, FedRAMP authorization status, dedicated-tenant or government cloud availability, zero-data-retention terms, sample 60-day pilot structure.
- **OpenAI (ChatGPT Enterprise / OpenAI for Government)** &mdash; via [openai.com/enterprise](https://openai.com/enterprise) or your existing federal/SLG contact. Same questions.
- **Microsoft (your existing account team)** &mdash; tell them you're running a comparison this cycle and you want them in it. Most account teams will respond well to a fair-fight framing.

Realistic timeline: Microsoft's account team can move in days (the relationship and contracting plumbing already exist). OpenAI's enterprise / public-sector function is mature; expect a few weeks to a written proposal. Anthropic is currently demand-overwhelmed and may take 4&ndash;8 weeks to respond to cold inbound; start that conversation first, in parallel with the others. Don't let any single vendor's pace stall the comparison.

## 2. Stand up an AI seed team

A deliberate cross-section of your agency, given enterprise Claude or ChatGPT Enterprise seats for 90 days. The goal is not to "evaluate AI." It is to build the internal expertise you need to procure well.

| Cohort | Big agency (~20 people) | Smaller agency (~10 people) | Profile |
|---|---|---|---|
| Senior leaders | 5 | 2&ndash;3 | CIO, budget director, department heads, chief of staff. People who have never used a frontier AI tool. |
| Mid-career operators | 10 | 5 | Senior analysts, in-house attorneys, planners, communications, program managers. The people who write everything. |
| Newer staff | 5 | 2&ndash;3 | Recent hires, eager experimenters, no preconceptions. |

Table: Seed-team composition by agency size.

Same ratio either way: roughly 25% leaders, 50% mid-career, 25% newer. After 90 days, ask each person to share their three most useful workflows in writing. Aggregate them. That document is what you take into procurement.

## 3. Run a head-to-head on five real workflows

Microsoft will quote you a Copilot price. Make them earn it against an alternative on workflows that match your agency's actual work. Five tests, scored 1&ndash;5 by the seed team:

| Workflow | What to test | What to score |
|---|---|---|
| Memo drafting | Draft a 5-page memo from a scoping note and three reference docs. | Time to first usable draft; factual accuracy; voice match; revisions needed before signoff. |
| Long-document summary | Summarize a 200-page environmental review or RFP response into a one-page executive memo. | Coverage of key findings; hallucinations; usable in this form by a department head? |
| Recurring report | Build the next instance of an existing monthly report (operations, performance, finance) from raw data plus the prior month's version. | Accuracy of numbers; format consistency; manual rework needed. |
| Email and meeting prep | Triage a busy morning's inbox and produce briefing notes for three afternoon meetings. | Quality of triage; usefulness of notes; refusals on benign content. |
| Document search | "Find me everything in our SharePoint about X and tell me the contradictions." | Whether the tool can actually access agency content without manual file attachment. |

Table: Five workflows for the head-to-head pilot.

Score Copilot, ChatGPT Enterprise, and Claude Enterprise on each. Total score wins the line item.

## 4. Vendor-comparison questions

Send these to every vendor you're considering. Score yes / no / qualified.

- **FedRAMP authorization level** (Moderate or High) and current ATO date.
- **Government Community Cloud (GCC) / GCC High availability**, and feature parity with the commercial tier. (Microsoft 365 Copilot features routinely lag in GCC by 6+ months. Anthropic and OpenAI run dedicated-tenant or government cloud offerings of their own; ask about feature parity there too.)
- **Default data retention** for prompts and outputs. Can it be set to zero?
- **Will the vendor train on your tenant data?** Get the answer in writing.
- **Underlying model class** (named frontier model) and update cadence.
- **Agentic capability**: can it take multi-step actions across tools, or just chat?
- **Audit log access** for compliance and FOIA-response workflows.
- **Per-seat pricing** at your volume, with cancellation terms in writing.

## 5. Sample EA-renewal language

For your CIO or procurement officer to send to Microsoft. The point is to make the AI line a competitive line, not a default amendment, while keeping the M365 relationship intact.

> Thanks for sending the renewal proposal. We're staying on M365 as our productivity platform; no change there. We do want to be more deliberate about how we evaluate the AI add-on this cycle.
>
> We're planning a 60-day internal pilot comparing Microsoft 365 Copilot against ChatGPT Enterprise and Claude Enterprise on three real workflows our staff runs regularly. We'd appreciate Microsoft's help structuring it fairly: shared workflow definitions, a small group of seats on each platform, an agreed scoring rubric. We'll commit to the AI line item once we've seen the comparison.
>
> Happy to schedule a working session to walk through what we have in mind.

## 6. What to skip

- **Multi-vendor RFPs with 200-question security matrices** before you have any internal users. You don't yet know what to ask.
- **Big-bang agency-wide deployments.** Seed team first, agency-wide later.
- **"AI strategy" decks from the major consulting firms.** You don't need a strategy yet. You need real users on real tools, doing real work.

---

If you want to talk through how this would map to your specific agency: joe@group17a.com.
