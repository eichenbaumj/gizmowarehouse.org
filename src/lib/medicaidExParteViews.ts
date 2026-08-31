// Shared ex parte cartogram view definitions, kept in a non-component module so
// the component files that use them (MedicaidLossSankey's ExParteCartogram and
// the standalone MedicaidExParteCapability section) stay Fast-Refresh-clean —
// a .tsx component file exporting a runtime value const breaks React HMR.

export type CartogramView = "composite" | "observed_ex_parte" | "data_sources";

export const CARTOGRAM_VIEW_LABELS: Record<CartogramView, string> = {
  composite: "Composite",
  observed_ex_parte: "Observed ex parte",
  data_sources: "Data sources",
};
