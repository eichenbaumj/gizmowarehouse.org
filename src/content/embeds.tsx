// Custom React components that gizmo markdown can embed inline.
//
// Usage (inside a gizmo's content/<slug>.ts markdown):
//   <nyc-tax-map />
//   <medicaid-map />
//   <medicaid-hero-flyover />
//   <medicaid-subject-profile />
//   <medicaid-divider />
//   <medicaid-find-your-state />
//
// The markdown pipeline (rehype-raw + react-markdown components prop in
// GizmoPage.tsx) maps the lowercase tag name to the component below. Tag
// names MUST be lowercase HTML-style (rehype-raw will lowercase them) and
// must NOT collide with real HTML elements.

import type { ComponentType } from "react";
import NYCPropertyTaxMap from "@/components/NYCPropertyTaxMap";
import MedicaidWorkRequirementsMap from "@/components/MedicaidWorkRequirementsMap";
import MountWhenNear from "@/components/MountWhenNear";
import MedicaidHeroFlyover from "@/components/MedicaidHeroFlyover";
import MedicaidSubjectProfile from "@/components/MedicaidSubjectProfile";
import MedicaidLossSankey from "@/components/MedicaidLossSankey";
import MedicaidDivider from "@/components/MedicaidDivider";
import MedicaidFindYourState from "@/components/MedicaidFindYourState";
import MedicaidMethodologyPanel from "@/components/MedicaidMethodologyPanel";
import MedicaidCaveatsPanel from "@/components/MedicaidCaveatsPanel";
import MedicaidCategoryOverlap from "@/components/MedicaidCategoryOverlap";
import MedicaidContents from "@/components/MedicaidContents";
import MedicaidExParteCapability from "@/components/MedicaidExParteCapability";
import CompGapMacro from "@/components/compgap/CompGapMacro";
import CompGapHero from "@/components/compgap/CompGapHero";
import CompGapEarnings from "@/components/compgap/CompGapEarnings";
import CompGapLadder from "@/components/compgap/CompGapLadder";
import CompGapEci from "@/components/compgap/CompGapEci";
import CompGapDomainExplorer from "@/components/compgap/CompGapDomainExplorer";
import CompGapCompression from "@/components/compgap/CompGapCompression";
import CompGapLocalityCard from "@/components/compgap/CompGapLocalityCard";
import GroceryDial from "@/components/grocery/GroceryDial";
import DcrMap from "@/components/dcr/DcrMap";
import DcrTownCalc from "@/components/dcr/DcrTownCalc";
import DcrFootprintBars from "@/components/dcr/DcrFootprintBars";

// Some embed components are intentionally unregistered: unregistering drops
// their source strings from the JS bundle while the .tsx files stay on disk;
// restoring one = re-add its import + registry line below. Registration
// gotcha: withAnchor doesn't forward props, so an embed driven by its own
// attributes must be registered directly, not wrapped.
const withAnchor = (id: string, Component: ComponentType): ComponentType =>
  function AnchoredEmbed() {
    return (
      <div id={id} className="scroll-mt-6">
        <Component />
      </div>
    );
  };

// The explore map is the heaviest thing on the page — a MapLibre/WebGL context
// that, alongside the hero map, overruns the iOS per-tab memory budget. On
// touch devices MountWhenNear defers mounting it until the reader scrolls near
// and unmounts it once well past, so its context + tiles aren't resident while
// the reader is still up in the hero. Desktop is a pure passthrough (mounts
// eagerly and never unmounts — identical to rendering the map directly).
const MedicaidMapLazy: ComponentType = () => (
  <MountWhenNear placeholderHeight={1400}>
    <MedicaidWorkRequirementsMap />
  </MountWhenNear>
);

// The restriction map is a MapLibre/WebGL context — same deferred-mount
// treatment as the medicaid explore map (see MedicaidMapLazy below).
const DcrMapLazy: ComponentType = () => (
  <MountWhenNear placeholderHeight={760}>
    <DcrMap />
  </MountWhenNear>
);

export const gizmoEmbeds: Record<string, ComponentType> = {
  "dcr-map": DcrMapLazy,
  "dcr-town-calc": DcrTownCalc,
  "dcr-footprint-bars": DcrFootprintBars,
  "nyc-tax-map": NYCPropertyTaxMap,
  "medicaid-contents": MedicaidContents,
  "medicaid-map": MedicaidMapLazy,
  "medicaid-hero-flyover": MedicaidHeroFlyover,
  "medicaid-subject-profile": MedicaidSubjectProfile,
  "medicaid-category-overlap": MedicaidCategoryOverlap,
  "medicaid-ex-parte-capability": MedicaidExParteCapability,
  "medicaid-loss-sankey": MedicaidLossSankey,
  "medicaid-divider": MedicaidDivider,
  "medicaid-find-your-state": MedicaidFindYourState,
  "medicaid-caveats-panel": MedicaidCaveatsPanel,
  "medicaid-methodology-panel": MedicaidMethodologyPanel,
  "compgap-macro": CompGapMacro,
  "compgap-hero": CompGapHero,
  "compgap-earnings": CompGapEarnings,
  "compgap-ladder": CompGapLadder,
  "compgap-eci": CompGapEci,
  "compgap-domain-explorer": CompGapDomainExplorer,
  "compgap-compression": CompGapCompression,
  "compgap-locality-card": CompGapLocalityCard,
  "grocery-dial": GroceryDial,
};
