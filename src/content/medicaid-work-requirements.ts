export default `
<medicaid-contents></medicaid-contents>

In America, about 70 million people get their healthcare from Medicaid. Starting on January 1st, 2027, 18.5 million of them will have to demonstrate work or qualifying-activity hours at application and on each renewal cycle to keep their healthcare.

If you are like most Gizmo Warehouse visitors, you get good, expensive healthcare in America, paid for by your W2 employer, or purchased on a marketplace. You renew your healthcare once a year and the renewal asks little of you. For the poorest Americans with health insurance, renewals will now run every six months, and each one asks them to prove they hit 80 hours of qualifying activity, or $580 in income, in a recent month.

In July 2025, Congress passed the **One Big Beautiful Bill Act** (pronounced colloquially, in my opinion, as O-BAH-BA). Section 71119 added a federal work requirement to Medicaid, codified at §1902(xx) of the Medicaid Act: adults ages 19–64 who got coverage through the Affordable Care Act's Medicaid expansion need to prove 80 hours of qualifying activity per month through work, school, job training, or community service (or earn $580 in a month — the federal minimum wage times 80 hours — which counts as an income-based alternative nationwide), or else document a categorical exemption. The requirement tracks the expansion-adult group, so it reaches the 40 states and DC that expanded, plus three non-expansion states (Wisconsin, Georgia, and Tennessee) that cover comparable adults through Section 1115 waivers, per CMS's June 2026 guidance.

The [Congressional Budget Office](https://www.cbo.gov/publication/61837) projects **18.5 million** people will be subject to the verification, and roughly **{national.cbo_loss_target_2034:M} will lose Medicaid coverage by 2034** from the work requirement alone. The [Urban Institute's HIPSM model](https://www.urban.org/research/publication/projected-reductions-medicaid-expansion-enrollment-under-obbbas-work) projects a comparable 3–7 million from the work requirement (rising to 4.9–10.1 million once OBBBA's six-month redeterminations are added), and the [Center on Budget and Policy Priorities (CBPP)](https://www.cbpp.org/research/health/medicaid-work-requirements-will-harm-low-paid-workers) estimates 9.7–14.4 million are at risk, with most of that group exposed if state implementation is poor. This piece contains a state-by-state, bottom-up analysis of coverage loss, which lands just above the CBO baseline. The band of estimates is the point. The difference between roughly 5 million and 10 million is what's preventable through good state operational design. About two-thirds of Medicaid adults ages 19–64 are working at least part-time (per KFF); most of the rest are caregivers, students, or have a qualifying medical condition. Most who lose coverage will still be eligible under the statute. They will lose it because they don't prove it through whatever verification system their state stands up by the December 31, 2026 implementation deadline.

State Medicaid directors have seven months to get ready. No two of them face the same version of this problem. The tour below shows why, and the six tools indexed up top break it down piece by piece.

<medicaid-hero-flyover></medicaid-hero-flyover>

<medicaid-divider></medicaid-divider>

## Pathways to compliance

*Tool 1 of 6. The 80-hour rule, who it lands on, and the two-thirds already working: the population the verification system has to clear.*

<medicaid-subject-profile></medicaid-subject-profile>

About two-thirds of Medicaid adults ages 19–64 are already working at least part-time (per KFF); most who aren't are caregivers, students, or have a qualifying medical condition. The question isn't whether they'd qualify substantively. It's whether they can prove it on the renewal cycle, through whatever verification system their state stands up between now and the deadline. That's where the projected coverage losses come from.

When CBO projects {national.cbo_loss_target_2034:M} coverage losses by 2034, they're not predicting that {national.cbo_loss_target_2034:M} people will fail to work 80 hours a month. They're predicting that {national.cbo_loss_target_2034:M} people will fall off Medicaid because something in the verification system fails them: a missed letter, a portal outage, a wrong address, a paystub that doesn't exist because last month's hours came from two different employers. The shorthand for this is **administrative churn**. The 30% baseline figure CBO uses comes from what happened in Arkansas in 2018 (about 18,000 adults — roughly 30% of those subject — lost coverage) and Georgia Pathways starting in 2023 (far lower enrollment than projected, over a longer baseline). When work requirements activate, a substantial share of subject enrollees lose coverage in the first year through paperwork failure, regardless of whether they were actually working enough hours.

<medicaid-divider></medicaid-divider>

## The automatic-verification pathways

*Tool 2 of 6. Every way to satisfy the rule maps to data a state could check on its own. How many of those automatic checks does each enrollee have?*

The point of the requirement isn't to make 18.5 million people upload paystubs every six months. It's to confirm, against data the state can already see, that they're working, caregiving, in school, medically frail, or otherwise covered. Most subjects qualify through more than one path; a working parent with a chronic condition has three. The enrollees most exposed are the ones with exactly one path: if that single check fails, no backstop catches them. The view below shows how those paths overlap across the subject pool.

<medicaid-category-overlap></medicaid-category-overlap>

The opportunity is large. Go back to the requirements breakdown: roughly two-thirds of the pool is already either working enough or sitting in a categorical exemption, and most of those statuses are, in principle, verifiable against data the state already holds (wage records for hours, the child's own Medicaid case for parents, claims and the health information exchange for medical frailty, the National Student Clearinghouse for students). A state that wires those feeds in before December 2026 can clear that two-thirds *ex parte*, without a single enrollee touching a portal. **Which feeds it prioritizes first decides how many people it keeps covered**, and the right order isn't the same everywhere. Medical frailty is the largest exemption category almost everywhere, but the share of low-income parents who are even *subject* to the rule runs from roughly 85% in Arkansas down to about a quarter in California, where most are covered outside expansion through the Section 1931 pathway. And American Indian / Alaska Native enrollees are a rounding error in most states but a top-three exempt group in Alaska, New Mexico, Oklahoma, Montana, and the Dakotas. The national figure is the wrong planning document for any individual state; your own profile is what matters.

Every Medicaid director will resolve the December 31 verification problem through some mix of two operational modes. **Ex parte verification** confirms hours and exemptions against administrative data the state already holds: Unemployment Insurance wage records, SNAP/TANF work-compliance logs, Medicaid claims, behavioral-health MCO enrollment, vital records, corrections data, child welfare records. **Paperwork burden** makes the enrollee re-prove what the state could have confirmed otherwise. Every state will do some of both, in different proportions, and how far each one gets toward ex parte is what the next tool scores.

<medicaid-divider></medicaid-divider>

## State ex parte verification capability

*Tool 3 of 6. Which states can actually auto-verify, scored on what they did during the unwinding rather than what they plan to do.*

What separates a state that clears most of its pool automatically from one that buries enrollees in paperwork is two things. The first is the readiness of its IT and data systems and the operations that run them: whether the eligibility system can reliably match a person to the right administrative record, how many duplicate or stale records muddy that match, and whether the state has the legal frameworks for data sharing and consent management that let it pull from other agencies at all. The second is the data sources: whether the state has integrated connections to the specific feeds an HR1 work-requirement check needs, not just the income feed an ordinary renewal already uses.

The score below leads with what states actually did during the 2023–2026 unwinding rather than what they plan to do, then layers in the breadth of their verification data sources and any documented history under a prior Section 1115 work requirement.

<medicaid-ex-parte-capability></medicaid-ex-parte-capability>

<medicaid-divider></medicaid-divider>

## Where the coverage losses come from

*Tool 4 of 6. A bottom-up count of who loses coverage, and why. The finding: most of them still qualify.*

The policy was framed around the expansion adults who aren't in any qualifying activity right now. The work requirement is designed to move them into compliance through work, school, or volunteering, and to ensure those with a documented exemption are properly identified. [CBO](https://www.cbo.gov/publication/61837) projects **5.2 million** will lose Medicaid by 2034; the [Urban Institute's HIPSM model](https://www.urban.org/research/publication/projected-reductions-medicaid-expansion-enrollment-under-obbbas-work) projects 3–7 million from the work requirement alone; [CBPP](https://www.cbpp.org/research/health/medicaid-work-requirements-will-harm-low-paid-workers) estimates 9.7–14.4 million at risk if state implementation lags. Our bottom-up model, built per-(state, subgroup) from subject pool × eligibility rate × failure rate and then summed and adjusted for the 6-month renewal cycle, lands at **5.42 million**, just above CBO's baseline. About 555,000 of that is genuine non-compliance: adults who stay out of any qualifying activity after the rule activates and don't claim an exemption. The other 4.9 million still qualify for Medicaid under the new rules. They lose coverage because the verification system fails to catch them. CBO assumes most of the at-risk-but-eligible will simply move into compliance; on the evidence from Arkansas and Georgia, that's the optimistic case, not the likely one.

<medicaid-loss-sankey></medicaid-loss-sankey>

### Compliant but can't prove it (~38%)

About 2.1 million people meet the OBBBA requirement through work, school, or volunteering, but can't document that compliance through the state portal. The data flips the popular narrative. Most of these people hold regular jobs (multiple part-time positions, variable retail and healthcare shifts, self-employment) whose hours are real but don't fit on a single pay stub. Gig-platform work is a small slice. Where verification fails, the binding constraint is the state's data infrastructure, not the kind of job someone holds.

The income alternative — $580 in a month, the federal minimum wage times 80 hours — applies nationwide, and it's the more useful test almost everywhere: income is already reported for Medicaid eligibility, so the state often has it on hand, while hours worked are not separately reported and have to be reconstructed from pay stubs or employer feeds. Where wages run well above the federal floor, 80 hours of work clears $580 easily, so the income test rarely binds there; it matters most for low-wage and variable-hour workers.

### Exempt but can't prove it (~51%)

About 2.8 million people are categorically exempt under OBBBA §1902(xx) but lose coverage anyway because their exemption can't be verified. Medical frailty is the largest piece, roughly a million people and the top category in nearly every state, because the "complex medical or behavioral-health condition" standard needs a recurring provider letter that claims data doesn't surface on its own. Caregiving is the next tier, parents of young children and, larger still, the people caring for a disabled adult, whose relationship no state eligibility system tracks cleanly. American Indian and Alaska Native enrollees are a rounding error in most states but a top-three category in Alaska, New Mexico, Oklahoma, Montana, and the Dakotas. Pregnancy has always permitted self-attestation in Medicaid, but the current CMS posture on self-attestation is murky; whether this important coverage group ends up exempt but unable to prove it will depend heavily on where the federal government lands on this question and how states implement.

### Genuinely not in any qualifying path (~10%)

The remaining ~555,000 people are not in any qualifying activity, not enrolled in school or volunteering, and not claiming a categorical exemption. These are the people the work requirement was designed to move into compliance through work, school, or volunteering. Whether they respond depends on the state's outreach, the timing of the December 2026 implementation, and the conditions of the local labor market.

<medicaid-divider></medicaid-divider>

## The map

*Tool 5 of 6. Where the procedural-disenrollment wave concentrates, from state down to the 1-mile grid, and how to read it.*

**The variables that meaningfully move the loss number sit before December 31, 2026**: ex parte data plumbing, cross-program data hookups, vendor configuration, the Q4 2026 enrollee comms plan, and a customer-support and navigation-assistance plan built around the workflows enrollees will actually have to use. Once the rule activates the operational story changes shape. Every procedural termination that hits in January 2027 represents a person the verification system has already failed; field outreach at that point is a recovery effort, not a way to prevent the loss in the first place.

Even in high-ex-parte states, some share of subjects will end up on the paperwork path. The **Compliance burden index** view of the map surfaces where that path is most likely to defeat eligible enrollees. It's a composite of three indicators that prior Section 1115 work-requirement implementations (Arkansas 2018, Georgia Pathways 2023–) showed predict procedural disenrollment: limited-English households, no broadband, and concentrated employment in seasonal, gig, construction, and hospitality sectors. Counties where the index runs above the national median are not necessarily counties where enrollees are less likely to meet the work requirement; they're counties where compliance is harder to verify.

**How to read this map.** This is a picture of where the procedural-disenrollment wave will concentrate, not a county-level outreach plan. The dense red counties show where the largest groups of enrollees will fall through the verification system; they don't show where a 2027 field campaign would do useful work, because by 2027 the verification system has already terminated those enrollees. A few patterns to look for: six states (California, New York, Pennsylvania, Illinois, Louisiana, and Michigan) carry roughly half of the absolute count. The highest per-capita rates run through Louisiana, Oregon, the District of Columbia, California, and New Mexico, where expansion reaches the largest share of working-age adults. Two regional clusters jump out even at the national view: the Arkansas–Louisiana Delta and Appalachian eastern Kentucky, where high subject-pool density meets weak state verification capability.

The map covers all 50 states + DC. Seven states render gray-hatched (Texas, Florida, Alabama, Mississippi, South Carolina, Kansas, Wyoming): they didn't expand and have no waiver population the requirement reaches, though they have working-age uninsured residents who would be in this picture if their state had expanded. Three non-expansion states are subject through Section 1115 waivers, per CMS's June 2026 list. Wisconsin shades in: its roughly 198,000 BadgerCare childless adults are newly subject, and modeled here. Georgia shades in too, but its Pathways enrollees already face a work requirement, so no net-new loss is modeled. Tennessee is on the list only through TennCare's 1115 parent/caretaker group (~17,700 adults covered to 100% FPL); since OBBBA exempts parents of a child under 14, almost none are actually subject, so we flag it (amber hatch) rather than model a loss. The default view is the county aggregate; toggle to the 1-mile grid for within-county hot spots once you've picked a state.

<medicaid-map></medicaid-map>

<medicaid-divider></medicaid-divider>

## Find your state

*Tool 6 of 6. A detailed operational brief for every state and DC: top counties, exemption mix, and a December-31 checklist.*

If you run a state Medicaid agency, the seven-month operational job is to maximize the number of people you can renew automatically: invest in ex parte data plumbing, cross-program data hookups (Medicaid claims, UI wage, SNAP/TANF, vital records, child welfare, DOC), vendor configuration, the Q4 2026 enrollee comms plan, customer-support staffing, and navigation assistance. Then make the manual processes as easy as possible for those who do have to self-attest or submit. The number to drive down isn't "people who lose coverage." It's "people who lose coverage and are still eligible." The brief below is built bottom-up by subgroup for your state.

<medicaid-find-your-state></medicaid-find-your-state>

<medicaid-divider></medicaid-divider>

## Caveats

<medicaid-caveats-panel></medicaid-caveats-panel>

<medicaid-divider></medicaid-divider>

## Methodology

<medicaid-methodology-panel></medicaid-methodology-panel>

If we got something wrong, please tell us: **joe@group17a.com**. Corrections will be credited in the next methodology refresh.

---

*Built by [17A](https://group17a.com). If it'd be useful to talk through any of this, drop a line.*
`;

// BLUF ("Bottom Line Up Front") — a <=250-word executive cut of the piece above,
// leading with the conclusion and reusing a lean three-embed subset (subject
// profile, loss Sankey, find-your-state; no maps). Rendered through the same
// pipeline as the default content; see GizmoPage + gizmoBlufContent.
export const bluf = `
## Bottom Line Up Front:

In July 2025, the One Big Beautiful Bill Act added a federal work requirement to Medicaid. Starting January 1, 2027, about 18.5 million adults covered through the ACA expansion (plus waiver-covered adults in three non-expansion states — Wisconsin, Georgia, and Tennessee) must prove 80 hours a month of work or qualifying activity (or $580 in income) at every six-month renewal, or lose their healthcare.

But "prove" takes many forms, some simple and easy to automate, others a costly seam in state eligibility systems. Our state-by-state model projects about 5.4 million people lose coverage by 2034, just above CBO's {national.cbo_loss_target_2034:M}. Yet roughly 4.9 million of them still qualify. They lose coverage because the verification system fails to catch them, not because they don't qualify.

<medicaid-subject-profile></medicaid-subject-profile>

About two-thirds of working-age Medicaid adults already work at least part-time; most of the rest are caregivers, students, or have a qualifying medical condition. When Arkansas tried this in 2018, about 95% of those who lost coverage were working enough or exemption-eligible. They just couldn't get the paperwork through.

<medicaid-category-overlap></medicaid-category-overlap>

Most qualify more than one way; the exposed have a single qualifying path, where one failed check leaves no backstop.

<medicaid-ex-parte-capability></medicaid-ex-parte-capability>

Whether a state clears people automatically or buries them in paperwork comes down to its data systems and the December 31, 2026 deadline.

<medicaid-loss-sankey></medicaid-loss-sankey>

The losses sort into three groups: compliant but unable to document it, exempt but unable to prove the exemption, and a small share, around 555,000, genuinely outside any qualifying activity. The paperwork failures are the overwhelming majority.

*[Read the full analysis](/gizmo/medicaid-work-requirements) · [Methodology](/gizmo/medicaid-work-requirements/methodology)*
`;
