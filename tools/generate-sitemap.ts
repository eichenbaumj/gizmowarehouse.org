// Writes public/sitemap.xml, public/llms.txt, and src/data/lastmod.json from
// the route registry (src/lib/routes.ts). Runs first in `npm run build`.
//
// lastmod comes from `git log -1` on each route's source files. When git is
// unavailable (some hosted builds), the committed src/data/lastmod.json is
// kept as-is, so commit that file whenever it changes.
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { gizmos } from "../src/data/gizmos";
import { publicRoutes, absoluteUrl } from "../src/lib/routes";
import { gizmoDescription, isoDate, SITE_TAGLINE } from "../src/lib/seo";
import { loadDataFiles } from "./lib/loadDataFiles";
import { buildAllDataPages } from "../src/data/dataPages";

const LASTMOD_PATH = "src/data/lastmod.json";

const gitCache = new Map<string, string | null>();
function gitLastmod(files: string[]): string | null {
  const key = files.join("\0");
  if (gitCache.has(key)) return gitCache.get(key)!;
  const v = gitLastmodRaw(files);
  gitCache.set(key, v);
  return v;
}
function gitLastmodRaw(files: string[]): string | null {
  try {
    const out = execFileSync("git", ["log", "-1", "--format=%cI", "--", ...files], { encoding: "utf8" }).trim();
    return out ? out.slice(0, 10) : null;
  } catch {
    return null;
  }
}

const previous: Record<string, string> = existsSync(LASTMOD_PATH) ? JSON.parse(readFileSync(LASTMOD_PATH, "utf8")) : {};
const next: Record<string, string> = {};
let gitOk = true;

const dataFiles = loadDataFiles();
const { dropped } = buildAllDataPages(dataFiles);
if (dropped.length) console.warn(`[sitemap] ${dropped.length} data page(s) below the thin-content floor, excluded:\n  ${dropped.join("\n  ")}`);
const routes = publicRoutes(dataFiles);
const entries = routes.map((r) => {
  const key = r.path === "/" ? "/" : r.path;
  let lastmod = gitLastmod(r.sources);
  if (lastmod === null) {
    gitOk = false;
    lastmod = previous[key] ?? (r.fallbackDate ? isoDate(r.fallbackDate) : new Date().toISOString().slice(0, 10));
  }
  if (!r.dataPage) next[key] = lastmod; // data pages date from their snapshot; keep lastmod.json small
  if (r.gizmo && r.path === `/gizmo/${r.gizmo.slug}`) next[r.gizmo.slug] = lastmod; // slug key for src/lib/seo.ts
  return { loc: absoluteUrl(r.path), lastmod, priority: r.priority };
});

const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${entries
  .map((e) => `  <url><loc>${e.loc}</loc><lastmod>${e.lastmod}</lastmod><priority>${e.priority.toFixed(1)}</priority></url>`)
  .join("\n")}
</urlset>
`;
writeFileSync("public/sitemap.xml", xml);

// llms.txt: the same inventory for LLM crawlers, generated so it can't drift.
const live = gizmos.filter((g) => !g.hidden);
const llms = `# Gizmo Warehouse

> ${SITE_TAGLINE} A running collection of things built that aren't covered by an NDA.

Joe is a partner at 17A, a consulting firm serving state and local government. Most of his work is confidential; this site is where the shareable residue lives: tools, write-ups, and analyses across public safety, city and state government, healthcare policy, music, and AI.

## Pages

- [Home](/): Browse all gizmos, filterable by category.
${routes
  .filter((r) => r.path.startsWith("/category/"))
  .map((r) => `- [${r.path.replace("/category/", "").replace(/-/g, " ")}](${r.path}): Category index.`)
  .join("\n")}

## Gizmos

${live
  .map((g) => {
    const extra = (g.links ?? [])
      .filter((l) => /^https?:/.test(l.url))
      .map((l) => `${l.label}: ${l.url}`)
      .join("; ");
    return `- [${g.title}](/gizmo/${g.slug}) (${g.date}): ${gizmoDescription(g)}${extra ? ` ${extra}` : ""}`;
  })
  .join("\n")}

## Data pages

One page per state, county, city, or jurisdiction, generated from the datasets behind the pieces above:
${routes
  .filter((r) => r.dataPage?.isHub)
  .map((r) => `- [${r.dataPage!.title}](${r.path}): ${r.dataPage!.description}`)
  .join("\n")}

## Methodology

${routes
  .filter((r) => r.path.endsWith("/methodology"))
  .map((r) => `- [${r.gizmo?.title} methodology](${r.path})`)
  .join("\n")}
`;
writeFileSync("public/llms.txt", llms);

const changed = JSON.stringify(next) !== JSON.stringify(previous);
if (gitOk || !existsSync(LASTMOD_PATH)) writeFileSync(LASTMOD_PATH, JSON.stringify(next, null, 2) + "\n");
console.log(
  `[sitemap] ${entries.length} URLs -> public/sitemap.xml; llms.txt ${live.length} gizmos; lastmod ${gitOk ? "from git" : "KEPT (git unavailable)"}${changed && gitOk ? " (updated, commit src/data/lastmod.json)" : ""}`
);
