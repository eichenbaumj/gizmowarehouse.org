// Fails the build if any unpublished gizmo slug appears in the production bundle. Unpublished = a
// directory under gizmos/ or a file under src/content/ whose slug is not in src/data/gizmos.ts.
// Generic by construction: no slug literals here.
import { existsSync, readdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { join } from "node:path";

const root = process.cwd();
const gizmosTs = readFileSync(join(root, "src/data/gizmos.ts"), "utf8");
const published = new Set([...gizmosTs.matchAll(/slug:\s*"([a-z0-9-]+)"/g)].map((m) => m[1]));
const candidates = new Set<string>();
for (const d of readdirSync(join(root, "gizmos"))) {
  if (!d.startsWith("_") && d !== "README.md" && statSync(join(root, "gizmos", d)).isDirectory()) candidates.add(d);
}
for (const f of readdirSync(join(root, "src/content"))) {
  const m = f.match(/^([a-z0-9-]+)\.ts$/);
  if (m && m[1] !== "index") candidates.add(m[1]);
}
const drafts = [...candidates].filter((s) => !published.has(s));
const assets = join(root, "dist", "assets");
let files: string[] = [];
try {
  files = readdirSync(assets).filter((f) => f.endsWith(".js") || f.endsWith(".css"));
} catch {
  console.log("check-draft-leak: no dist/assets yet, nothing to check");
  process.exit(0);
}
const hits: string[] = [];
for (const f of files) {
  const txt = readFileSync(join(assets, f), "utf8");
  for (const s of drafts) {
    if (txt.includes(s)) hits.push(`${f}: ${s}`);
  }
}
if (hits.length) {
  console.error("check-draft-leak: unpublished slug found in the bundle:\n  " + hits.join("\n  "));
  process.exit(1);
}
// A draft's data and downloads live under public/ so the dev server can serve them, and Vite copies
// public/ into dist verbatim. Strip them from the production tree so an unpublished gizmo's files are
// never reachable on the live site before its Publish.
const removed: string[] = [];
for (const s of drafts) {
  const dataDir = join(root, "dist", "data", s);
  if (existsSync(dataDir)) { rmSync(dataDir, { recursive: true, force: true }); removed.push(`data/${s}/`); }
  for (const f of files.length ? readdirSync(assets) : []) {
    if (f.startsWith(`${s}-`)) { rmSync(join(assets, f), { force: true }); removed.push(`assets/${f}`); }
  }
  const og = join(root, "dist", "og", `${s}.png`);
  if (existsSync(og)) { rmSync(og, { force: true }); removed.push(`og/${s}.png`); }
}
console.log(`check-draft-leak: ${drafts.length} draft slug(s) screened against ${files.length} bundle files, none found` + (removed.length ? `; removed ${removed.length} draft public file(s) from dist: ${removed.join(", ")}` : ""));
