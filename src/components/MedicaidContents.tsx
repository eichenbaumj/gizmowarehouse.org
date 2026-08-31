// MedicaidContents — "What do we have here": a highly-visual table of contents.
//
// Six tiles that double as a visual index of the piece's standalone assets. Each
// tile shows a mini-glyph of what it is and smooth-scrolls to that section's H2
// anchor (slugs produced by GizmoPage's headingSlug). Sits at the very top of the
// gizmo, before the opening prose — a reader gets "what kind of thing this is"
// before reading a word.

const COBALT = "#1F1FD6";
const COBALT_LIGHT = "#7B9BE0";
const CAROLINA = "#21A8E0";
const TEAL = "#0EA5A4";
const VIOLET = "#8B5CF6";
const SLATE = "#94A3B8";

// ---- Mini-glyphs (each ~44x44) -------------------------------------------

function GlyphRequirements() {
  // Stacked 1/3-1/3-1/3 bar: already compliant / exempt / residual.
  return (
    <svg viewBox="0 0 44 44" className="h-11 w-11" aria-hidden>
      <rect x="6" y="9" width="32" height="7.5" rx="2" fill={COBALT} />
      <rect x="6" y="18.5" width="32" height="7.5" rx="2" fill={CAROLINA} />
      <rect x="6" y="28" width="32" height="7.5" rx="2" fill={SLATE} />
    </svg>
  );
}

function GlyphPathways() {
  // Four overlapping category circles (Work / Parent / Med-frail / Student).
  return (
    <svg viewBox="0 0 44 44" className="h-11 w-11" aria-hidden>
      <circle cx="17" cy="18" r="9" fill={COBALT} fillOpacity="0.75" />
      <circle cx="27" cy="18" r="9" fill={TEAL} fillOpacity="0.7" />
      <circle cx="17" cy="27" r="9" fill={CAROLINA} fillOpacity="0.7" />
      <circle cx="27" cy="27" r="9" fill={VIOLET} fillOpacity="0.65" />
    </svg>
  );
}

function GlyphExParte() {
  // Mini tile cartogram — a grid of small squares in graded blues.
  const shades = [COBALT, CAROLINA, COBALT_LIGHT, "#0A0A8A", CAROLINA, COBALT_LIGHT,
    "#E69138", COBALT, CAROLINA, COBALT_LIGHT, COBALT, CAROLINA];
  return (
    <svg viewBox="0 0 44 44" className="h-11 w-11" aria-hidden>
      {shades.map((c, i) => {
        const col = i % 4, row = Math.floor(i / 4);
        return <rect key={i} x={6 + col * 9} y={9 + row * 9} width="7.5" height="7.5" rx="1.5" fill={c} />;
      })}
    </svg>
  );
}

function GlyphLoss() {
  // One source band splitting into three flows (sankey-ish).
  return (
    <svg viewBox="0 0 44 44" className="h-11 w-11" aria-hidden>
      <rect x="5" y="14" width="6" height="16" rx="2" fill={COBALT} />
      <path d="M11 16 C 22 16, 24 11, 37 11 L37 16 C 26 16, 24 20, 11 20 Z" fill={COBALT} fillOpacity="0.55" />
      <path d="M11 21 C 22 21, 24 21, 37 21 L37 26 C 26 26, 24 26, 11 25 Z" fill={CAROLINA} fillOpacity="0.6" />
      <path d="M11 26 C 22 27, 24 32, 37 33 L37 37 C 26 37, 22 30, 11 29 Z" fill={SLATE} fillOpacity="0.6" />
    </svg>
  );
}

function GlyphBrief() {
  // Document with a location pin — a per-state brief.
  return (
    <svg viewBox="0 0 44 44" className="h-11 w-11" aria-hidden>
      <rect x="10" y="7" width="20" height="28" rx="2.5" fill="#fff" stroke={COBALT} strokeWidth="2" />
      <line x1="14" y1="14" x2="26" y2="14" stroke={COBALT_LIGHT} strokeWidth="2" strokeLinecap="round" />
      <line x1="14" y1="19" x2="26" y2="19" stroke={COBALT_LIGHT} strokeWidth="2" strokeLinecap="round" />
      <line x1="14" y1="24" x2="22" y2="24" stroke={COBALT_LIGHT} strokeWidth="2" strokeLinecap="round" />
      <path d="M31 22 a5 5 0 1 1 -0.01 0 Z" fill={CAROLINA} />
      <path d="M31 22 l0 9 l-3.5 -5 Z" fill={CAROLINA} />
      <circle cx="31" cy="26.5" r="1.7" fill="#fff" />
    </svg>
  );
}

interface Tile {
  n: number;
  title: string;
  desc: string;
  anchor: string;
  glyph?: () => JSX.Element;
  img?: string;
  note?: string;
}

const TILES: Tile[] = [
  { n: 1, title: "Complying / Exempt / At Risk", desc: "Who's already meeting the rule, who's exempt, and who's at risk.", anchor: "pathways-to-compliance", glyph: GlyphRequirements },
  { n: 2, title: "Automatic Verification Pathways", desc: "Prioritizing the most important ways each state can verify clients ex parte, without paperwork.", anchor: "the-automatic-verification-pathways", glyph: GlyphPathways },
  { n: 3, title: "Ex Parte Capability", desc: "How well states are likely to do at automatic verifications, scored on observed auto-renewals and breadth of data sources.", anchor: "state-ex-parte-verification-capability", glyph: GlyphExParte },
  { n: 4, title: "Coverage Loss", desc: "Where the projected 5.4M losses come from, subgroup by subgroup.", anchor: "where-the-coverage-losses-come-from", glyph: GlyphLoss },
  { n: 5, title: "Everything on a Map", desc: "Where the disenrollment wave concentrates, down to the 1-mile grid.", anchor: "the-map", img: "/assets/medicaid-national-map.png", note: "a compliance-burden index that flags where the paperwork, not the work, will defeat eligible people: limited English, no broadband, seasonal jobs." },
  { n: 6, title: "Find Your State", desc: "A detailed operational brief for every state and DC.", anchor: "find-your-state", glyph: GlyphBrief },
];

function scrollTo(anchor: string) {
  const el = document.getElementById(anchor);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    history.replaceState(null, "", `#${anchor}`);
  }
}

export default function MedicaidContents() {
  return (
    <div
      className="not-prose my-8"
      style={{
        width: "min(100vw - 1.5rem, 80rem)",
        marginLeft: "calc(50% - min(50vw - 0.75rem, 40rem))",
        marginRight: "calc(50% - min(50vw - 0.75rem, 40rem))",
      }}
    >
      <div className="mb-1 font-sans text-[11px] font-bold uppercase tracking-[0.18em] text-carolina">
        What do we have here?
      </div>
      <p className="mb-5 font-serif text-[1.15rem] leading-snug text-charcoal">
        Six tools for the 41 states who have 7 months before the deadline. Each answers
        a different question. Jump to any one.
      </p>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {TILES.map((t) => (
          <a
            key={t.anchor}
            href={`#${t.anchor}`}
            onClick={(e) => { e.preventDefault(); scrollTo(t.anchor); }}
            className="group flex items-start gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-carolina/60 hover:shadow-md"
          >
            <div className="flex-none">
              {t.img ? (
                <img
                  src={t.img}
                  alt="US county map of work-requirement subject counts"
                  className="h-11 w-16 rounded-md bg-white object-contain ring-1 ring-slate-200"
                />
              ) : (
                t.glyph && <t.glyph />
              )}
            </div>
            <div className="min-w-0">
              <div className="font-sans text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
                {t.n} / 6
              </div>
              <div className="mt-0.5 font-serif text-[1.02rem] font-semibold leading-tight text-cobalt group-hover:text-cobalt/80">
                {t.title}
              </div>
              <p className="mt-1 text-[0.85rem] leading-snug text-slate-600">
                {t.desc}
              </p>
              {t.note && (
                <p className="mt-1.5 text-[0.78rem] leading-snug text-slate-500">
                  <span className="font-semibold text-carolina">New: </span>
                  {t.note}
                </p>
              )}
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}
