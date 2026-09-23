// Registry of programmatic data-page sets. Add a DatasetSpec here and the
// routes, sitemap, prerender, and the /gizmo/<slug>/* renderer all pick it up.
import { dataPoints, type DataPage, type DatasetSpec } from "./types";
import { dcrSpec } from "./dcr";
import { medicaidSpec } from "./medicaid";
import { compgapSpec } from "./compgap";

export type { DataPage, DataSection, DataTable, Cell, DatasetSpec } from "./types";
export { dataPoints } from "./types";

export const DATASETS: DatasetSpec[] = [dcrSpec, medicaidSpec, compgapSpec];

export function datasetForSlug(slug: string): DatasetSpec | undefined {
  return DATASETS.find((d) => d.parentSlug === slug);
}

/** Build a dataset's pages, dropping any below the thin-content floor. Returns the kept pages and the dropped paths. */
export function buildDataset(spec: DatasetSpec, files: Record<string, unknown>): { pages: DataPage[]; dropped: string[] } {
  const all = spec.build(files);
  const pages: DataPage[] = [];
  const dropped: string[] = [];
  const seen = new Set<string>();
  for (const p of all) {
    if (seen.has(p.path)) throw new Error(`[dataPages] duplicate path ${p.path}`);
    seen.add(p.path);
    if (!p.isHub && dataPoints(p) < spec.minCells) dropped.push(p.path);
    else pages.push(p);
  }
  return { pages, dropped };
}

/** All datasets' pages from a combined files map (keys are public URLs). Datasets whose files are missing are skipped. */
export function buildAllDataPages(files: Record<string, unknown>): { pages: DataPage[]; dropped: string[] } {
  const pages: DataPage[] = [];
  const dropped: string[] = [];
  for (const spec of DATASETS) {
    if (!spec.files.every((f) => f in files)) continue;
    const r = buildDataset(spec, files);
    pages.push(...r.pages);
    dropped.push(...r.dropped);
  }
  return { pages, dropped };
}
