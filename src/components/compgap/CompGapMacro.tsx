// CompGapMacro — back-compat wrapper. The macro block was split into four
// embeds (hero+Sankey, earnings, ladder, ECI) so the narrative can be layered
// between charts; the content now uses those directly. This wrapper renders them
// in sequence for anything still referencing <compgap-macro>.

import CompGapHero from "./CompGapHero";
import CompGapEarnings from "./CompGapEarnings";
import CompGapLadder from "./CompGapLadder";
import CompGapEci from "./CompGapEci";

export default function CompGapMacro() {
  return (
    <>
      <CompGapHero />
      <CompGapEarnings />
      <CompGapLadder />
      <CompGapEci />
    </>
  );
}
