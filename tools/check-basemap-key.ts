// Build gate for CARTO basemap hygiene. Runs first in `npm run build`.
//
// Rules, all scoped to <repo>/src:
//   1. The CARTO host (cartocdn.com) may appear only in src/config/basemap.ts.
//      Everything else goes through cartoRasterTiles / cartoStyleUrl.
//   2. The key literal may appear only in src/config/basemap.ts.
//   3. Every file that calls `new maplibregl.Map(` must wire
//      `transformRequest: cartoTransformRequest` (same-file check).
//
// Why: the key was patched into two configs on 2026-08-26, then a third config
// was created in September by copy-pasting keyless URLs from a pre-fix source.
// That gizmo shipped watermarked for weeks. Centralize + gate, so the next
// copy-paste fails the build instead of the live site.

import { readdirSync, readFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { CARTO_BASEMAP_KEY } from "../src/config/basemap";

const ROOT = process.cwd();
const ALLOWED = "src/config/basemap.ts";
const SCAN_EXT = /\.(ts|tsx|js|jsx|mjs|css|html|md)$/;

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const NEEDLES = [
  {
    re: /cartocdn\.com/i,
    label: "CARTO host outside src/config/basemap.ts (use cartoRasterTiles / cartoStyleUrl)",
  },
  {
    re: new RegExp(escapeRe(CARTO_BASEMAP_KEY)),
    label: "inline CARTO key (import from src/config/basemap.ts)",
  },
];

function* walk(dir: string): Generator<string> {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.test(entry.name)) yield p;
  }
}

const hits: string[] = [];
for (const file of walk(join(ROOT, "src"))) {
  const rel = relative(ROOT, file).split(sep).join("/");
  if (rel === ALLOWED) continue;
  const text = readFileSync(file, "utf8");
  text.split("\n").forEach((line, i) => {
    for (const n of NEEDLES) {
      if (n.re.test(line)) hits.push(`${rel}:${i + 1}: ${n.label}`);
    }
  });
  if (/new maplibregl\.Map\(/.test(text) && !text.includes("cartoTransformRequest")) {
    hits.push(`${rel}: new maplibregl.Map without transformRequest: cartoTransformRequest`);
  }
}

if (hits.length) {
  console.error(`[check-basemap-key] ${hits.length} problem(s):\n  ${hits.join("\n  ")}`);
  process.exit(1);
}
console.log("[check-basemap-key] OK");
