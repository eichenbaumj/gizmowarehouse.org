import whitepaper from "./reducing-violence-whitepaper";
import fakebook from "./fakebook-maker";
import claudeUsage from "./claude-code-usage";
import groceryMath from "./nyc-public-grocery-math";
import groceryMath30 from "./nyc-public-grocery-new-math";
import nycPropertyTax from "./nyc-property-tax-map";
import microsoftCopilot from "./microsoft-copilot";
import medicaidWorkRequirements, { bluf as medicaidBluf } from "./medicaid-work-requirements";
import publicPrivateCompensation, { bluf as compgapBluf } from "./public-private-compensation-comparison";
import dataCenterRestrictionCost from "./data-center-restriction-cost";
import gospelOfClaudeCode from "./gospel-of-claude-code";

export const gizmoContent: Record<string, string> = {
  "data-center-restriction-cost": dataCenterRestrictionCost,
  "nyc-public-grocery-new-math": groceryMath30,
  "public-private-compensation-comparison": publicPrivateCompensation,
  "reducing-violence-whitepaper": whitepaper,
  "fakebook-maker": fakebook,
  "claude-code-usage": claudeUsage,
  "nyc-public-grocery-math": groceryMath,
  "nyc-property-tax-map": nycPropertyTax,
  "microsoft-copilot": microsoftCopilot,
  "medicaid-work-requirements": medicaidWorkRequirements,
  "gospel-of-claude-code": gospelOfClaudeCode,
};

// Optional short-form ("BLUF") variants, keyed by the same slug. A gizmo has a
// BLUF view iff it appears here; GizmoPage shows the read-mode toggle only then.
// Add an entry to give another gizmo an executive cut — no other wiring needed.
export const gizmoBlufContent: Record<string, string> = {
  "public-private-compensation-comparison": compgapBluf,
  "medicaid-work-requirements": medicaidBluf,
};
