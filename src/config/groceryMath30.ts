// Single source of truth for the grocery dial (<grocery-dial />) and the
// July 2026 update's headline numbers.
//
// gizmos/nyc-public-grocery-math/verify_claims.py parses the GROCERY_MODEL
// literal below and asserts every constant matches build_model.py, so the web
// dial and the downloadable xlsx cannot drift. Keep values as plain numeric
// literals on single lines — the verify gate reads them by regex.

export const GROCERY_MODEL = {
  stores: 5,
  avgSqft: 13800, // RFP-consistent: (15,000 App. D Bronx + 3 × 15,000 App. E selling space + 9,000 La Marqueta) ÷ 5
  cogsPct: 0.72, // FMI 2024 industry average, % of gross at market prices
  laborPct: 0.12, // % of gross, NYC prevailing-wage central case
  opexPct: 0.09, // utilities, shrink, insurance, tech — ex rent (city-owned)
  operatorFee: 400000, // $/store/yr, private operator
  capexTotal: 70000000, // announced capital budget, five stores
  years: 10,
  discountRate: 0.04, // municipal borrowing rate — the present-value frame for leverage
  basketDiscount: 0.3, // announced July 27, 2026: 30% off the core basket
  basketShare: 0.6, // core basket's share of store sales
  promisedSavingsMonthly: 90, // City Hall projection, $/shopper/month
  defaultRevPerSqft: 1019, // FMI 2025 industry average ($19.59/wk × 52) — demand-consistent central for a 30%-off store
  defaultBlend: 0.18, // = basketDiscount × basketShare
  defaultPersonsPerHH: 2.48, // Census QuickFacts 2020–2024: NYC average household size
  aprilRevPerSqft: 500, // the April model's quiet-small-format central
  aprilDiscount: 0.1, // the April model's central-case discount assumption
} as const;

export interface DialResult {
  grossPerStore: number; // $/yr, market-value throughput
  contribution: number; // per $1 of gross sales
  resultPerStore: number; // operating result, $/yr (negative = loss)
  subsidyPerYear: number; // five stores, $/yr (negative = the stores profit)
  envelope: number; // ten-year public bill, nominal: capex + years × subsidy
  transferPerYear: number; // discount dollars reaching shoppers, five stores
  savingsPerYear: number; // the promised full deal, $/household/yr
  households: number; // households receiving the full deal
  people: number; // households × persons per household
  benefitTenYear: number; // nominal: transferPerYear × years
  envelopePV: number; // capex + subsidy × annuity factor — the envelope in today's dollars
  benefitPV: number; // transfer × annuity factor — the benefit in today's dollars
  leverage: number; // benefitPV ÷ envelopePV: food benefit per public dollar, in today's dollars
}

export function computeDial(
  revPerSqft: number,
  blend: number,
  personsPerHH: number,
): DialResult {
  const m = GROCERY_MODEL;
  const grossPerStore = m.avgSqft * revPerSqft;
  const contribution = 1 - blend - (m.cogsPct + m.laborPct + m.opexPct);
  const resultPerStore = grossPerStore * contribution - m.operatorFee;
  const subsidyPerYear = -m.stores * resultPerStore;
  const envelope = m.capexTotal + m.years * subsidyPerYear;
  const transferPerYear = m.stores * grossPerStore * blend;
  const savingsPerYear = 12 * m.promisedSavingsMonthly;
  const households = transferPerYear / savingsPerYear;
  const people = households * personsPerHH;
  const benefitTenYear = transferPerYear * m.years;
  // The bill stays nominal (the sum of checks the city writes); leverage reads in
  // today's dollars — both ten-year flows discounted at the muni rate.
  const annuityFactor = (1 - Math.pow(1 + m.discountRate, -m.years)) / m.discountRate;
  const envelopePV = m.capexTotal + subsidyPerYear * annuityFactor;
  const benefitPV = transferPerYear * annuityFactor;
  const leverage = envelopePV > 0 ? benefitPV / envelopePV : Infinity;
  return {
    grossPerStore,
    contribution,
    resultPerStore,
    subsidyPerYear,
    envelope,
    transferPerYear,
    savingsPerYear,
    households,
    people,
    benefitTenYear,
    envelopePV,
    benefitPV,
    leverage,
  };
}
