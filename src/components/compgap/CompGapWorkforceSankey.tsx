// CompGapWorkforceSankey — what government workers actually do. A two-column
// inline-SVG Sankey: Federal / State / Local on the left, occupation groups on
// the right, flows sized by employment (ACS, employed residents 25-64). Built by
// hand (no D3) to match the gizmo's aesthetic, like MedicaidLossSankey.
//
// Data: /data/compgap/workforce_composition.json (pipeline stage 07). The "Other
// roles" node rolls up the small service tail so the chart stays readable; every
// named group Joe cares about (teachers, police/fire, military, lawyers) is its
// own flow.

import { useEffect, useMemo, useState } from "react";
import MethodologyInfo from "@/components/MethodologyInfo";

const LEVEL_COLOR: Record<string, string> = {
  federal: "#1F1FD6",   // cobalt
  state: "#21A8E0",     // carolina
  local: "#C99A2E",     // gold
};
const LEVEL_LABEL: Record<string, string> = {
  federal: "Federal", state: "State", local: "Local",
};

// Hover tooltips (native <title>) explaining what each node contains.
const LEVEL_DESC: Record<string, string> = {
  federal: "Federal civilian employees plus active-duty military, ages 25–64 (ACS).",
  state: "State government employees, ages 25–64 (ACS).",
  local: "Local government — counties, cities, and school districts — ages 25–64 (ACS).",
};
const WORKGROUP_DESC: Record<string, string> = {
  education: "K-12 and college teachers, instructors, librarians, and teaching assistants (SOC 25).",
  admin: "Clerks, secretaries, administrative specialists, and postal workers (SOC 43).",
  protective: "Police, firefighters, corrections officers, and detectives (SOC 33).",
  management: "Managers, directors, administrators, and executives (SOC 11).",
  healthcare: "Physicians, nurses, pharmacists, therapists, and other clinicians (SOC 29).",
  social: "Social workers, counselors, clergy, and other community-service workers (SOC 21).",
  business_ops: "HR, management analysts, buyers, and other business-operations roles (SOC 13).",
  science: "Life, physical, and social scientists, plus mathematical occupations (SOC 19, 15-2).",
  transportation: "Bus and transit operators, drivers, and material-moving workers (SOC 53).",
  tech: "Software developers, IT and systems administration, data, and cybersecurity (SOC 15-1).",
  building_grounds: "Custodians, groundskeepers, and building-maintenance workers (SOC 37).",
  healthcare_support: "Aides, orderlies, and other healthcare-support workers (SOC 31).",
  military: "All uniformed personnel aged 25–64 (~0.85M). The full active-duty force is about 1.3M counting all ages (DoD); the rest are mostly under 25.",
  finance: "Accountants, auditors, financial analysts, and examiners (SOC 13-2).",
  engineering: "Civil, mechanical, electrical, and other engineers, plus architects (SOC 17).",
  legal: "Lawyers, judges, paralegals, and legal-support workers (SOC 23).",
  __other__: "Food service, production, arts & media, personal care, sales, and farming.",
};

interface Flow { govlevel: string; workgroup: string; employed_m: number; share_of_level_pct: number }
interface WG { key: string; label: string; total_m: number }
interface Data {
  levels: string[];
  level_totals_m: Record<string, number>;
  ces_level_totals_m: Record<string, number>;
  acs_vs_ces_note: string;
  workgroups: WG[];
  matrix: Flow[];
}

// Keep the long service tail as one labeled rollup so the chart reads cleanly.
const ROLLUP = new Set(["production", "food", "arts_media", "personal_care", "sales", "farming"]);
const ROLLUP_KEY = "__other__";

const W = 720;
const PXM = 30;            // pixels per million workers
const NODE_W = 13;
const NODE_GAP = 7;
const TOP = 8;
const LEFT_X = 150;        // left node bar x
const RIGHT_X = W - 196;   // right node bar x

export default function CompGapWorkforceSankey() {
  const [data, setData] = useState<Data | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);

  useEffect(() => {
    fetch("/data/compgap/workforce_composition.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  const layout = useMemo(() => {
    if (!data) return null;
    const levels = data.levels;

    // roll the tail into one node
    const rollupTotal = data.workgroups
      .filter((w) => ROLLUP.has(w.key))
      .reduce((s, w) => s + w.total_m, 0);
    const named = data.workgroups.filter((w) => !ROLLUP.has(w.key));
    const wgs: WG[] = [...named];
    if (rollupTotal > 0) wgs.push({ key: ROLLUP_KEY, label: "Other roles", total_m: rollupTotal });
    wgs.sort((a, b) => b.total_m - a.total_m);

    const remap = (k: string) => (ROLLUP.has(k) ? ROLLUP_KEY : k);
    const flows = data.matrix.map((f) => ({ ...f, workgroup: remap(f.workgroup) }));

    // left nodes (levels), stacked
    const leftNodes: Record<string, { y: number; h: number }> = {};
    let y = TOP;
    for (const lv of levels) {
      const h = data.level_totals_m[lv] * PXM;
      leftNodes[lv] = { y, h };
      y += h + NODE_GAP;
    }
    const leftBottom = y - NODE_GAP;

    // right nodes (workgroups), stacked
    const rightNodes: Record<string, { y: number; h: number; label: string }> = {};
    y = TOP;
    for (const w of wgs) {
      const h = w.total_m * PXM;
      rightNodes[w.key] = { y, h, label: w.label };
      y += h + NODE_GAP;
    }
    const rightBottom = y - NODE_GAP;
    const height = Math.max(leftBottom, rightBottom) + 6;

    // assign flow slots: within each left node order by right display order;
    // within each right node order by level order.
    const leftOff: Record<string, number> = {};
    const rightOff: Record<string, number> = {};
    levels.forEach((lv) => (leftOff[lv] = 0));
    wgs.forEach((w) => (rightOff[w.key] = 0));

    const bands: { id: string; level: string; wg: string; d: string; v: number; label: string }[] = [];
    for (const lv of levels) {
      // sum per workgroup for this level, then iterate in right display order
      for (const w of wgs) {
        const v = flows
          .filter((f) => f.govlevel === lv && f.workgroup === w.key)
          .reduce((s, f) => s + f.employed_m, 0);
        if (v <= 0) continue;
        const sH = v * PXM;
        const sy = leftNodes[lv].y + leftOff[lv]; leftOff[lv] += sH;
        const ty = rightNodes[w.key].y + rightOff[w.key]; rightOff[w.key] += sH;
        const x0 = LEFT_X + NODE_W, x1 = RIGHT_X, xm = (x0 + x1) / 2;
        const d = [
          `M${x0},${sy}`,
          `C${xm},${sy} ${xm},${ty} ${x1},${ty}`,
          `L${x1},${ty + sH}`,
          `C${xm},${ty + sH} ${xm},${sy + sH} ${x0},${sy + sH}`,
          "Z",
        ].join(" ");
        bands.push({ id: `${lv}-${w.key}`, level: lv, wg: w.key, d, v, label: rightNodes[w.key].label });
      }
    }
    return { levels, wgs, leftNodes, rightNodes, bands, height };
  }, [data]);

  if (err) return <div className="my-4 text-sm text-steel">Workforce chart unavailable ({err}).</div>;
  if (!data || !layout) return <div className="my-4 h-8 animate-pulse rounded bg-vellum" />;

  const { levels, leftNodes, rightNodes, wgs, bands, height } = layout;
  const fmtM = (m: number) => `${m.toFixed(m < 1 ? 2 : 1)}M`;

  return (
    <div className="mt-5">
      <div className="mb-1 flex items-center gap-2">
        <h5 className="font-serif text-[15px] font-semibold text-cobalt">What government workers do</h5>
        <MethodologyInfo id="compgap.workforce" variant="icon" />
      </div>
      <p className="mb-2 text-[12px] leading-relaxed text-charcoal/70">
        Occupation mix of the government workforce, by level. Teaching is the single
        biggest thing government does; the federal side is the only place active-duty
        military and the largest white-collar concentrations show up.
      </p>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${height}`} width="100%" style={{ minWidth: 560 }}
          role="img" aria-label="Sankey of government employment by level and occupation">
          {/* flows */}
          {bands.map((b) => {
            const active = hover === b.level || hover === b.wg || hover === null;
            return (
              <path key={b.id} d={b.d} fill={LEVEL_COLOR[b.level]}
                opacity={active ? 0.42 : 0.08}
                onMouseEnter={() => setHover(b.wg)} onMouseLeave={() => setHover(null)}>
                <title>{`${LEVEL_LABEL[b.level]} · ${b.label}: ${fmtM(b.v)}`}</title>
              </path>
            );
          })}
          {/* left nodes */}
          {levels.map((lv) => {
            const n = leftNodes[lv];
            return (
              <g key={lv} onMouseEnter={() => setHover(lv)} onMouseLeave={() => setHover(null)}>
                <title>{`${LEVEL_LABEL[lv]} — ${fmtM(data.level_totals_m[lv])}. ${LEVEL_DESC[lv] ?? ""}`}</title>
                <rect x={LEFT_X} y={n.y} width={NODE_W} height={n.h} fill={LEVEL_COLOR[lv]} rx={2} />
                <text x={LEFT_X - 8} y={n.y + n.h / 2 - 4} textAnchor="end"
                  className="fill-charcoal" fontSize={13} fontWeight={600}>{LEVEL_LABEL[lv]}</text>
                <text x={LEFT_X - 8} y={n.y + n.h / 2 + 10} textAnchor="end"
                  className="fill-charcoal/55" fontSize={11}>{fmtM(data.level_totals_m[lv])}</text>
              </g>
            );
          })}
          {/* right nodes */}
          {wgs.map((w) => {
            const n = rightNodes[w.key];
            if (!n) return null;
            return (
              <g key={w.key} onMouseEnter={() => setHover(w.key)} onMouseLeave={() => setHover(null)}>
                <title>{`${n.label} — ${fmtM(w.total_m)}. ${WORKGROUP_DESC[w.key] ?? ""}`}</title>
                <rect x={RIGHT_X} y={n.y} width={NODE_W} height={n.h} fill="#6E6E6D" rx={2} />
                <text x={RIGHT_X + NODE_W + 6} y={n.y + n.h / 2 + 3.5}
                  className="fill-charcoal" fontSize={11}>
                  {n.label} <tspan className="fill-charcoal/50">{fmtM(w.total_m)}</tspan>
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-charcoal/55">
        Same ACS basis as the stat strip (employed residents 25–64), so the totals line up:
        federal {fmtM(data.level_totals_m.federal)}, state {fmtM(data.level_totals_m.state)},
        local {fmtM(data.level_totals_m.local)}. &ldquo;Teachers &amp; instructors&rdquo; is the
        full educational-instruction group (K-12 plus public-college faculty, special-ed,
        librarians, and aides) across all three levels; active-duty military shows up only on the
        federal side.
      </p>
    </div>
  );
}
