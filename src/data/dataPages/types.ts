// Programmatic "data pages": one indexable page per state, county, city, or
// jurisdiction, generated from the same public/data files the interactive
// pieces read. Every sentence is a template filled from the data (no prose to
// review), and test/data-pages.test.ts checks the numbers on each page equal
// the source rows.
//
// A DatasetSpec declares which files it needs and a pure `build` that turns
// them into pages. The browser (src/pages/DataPage.tsx) fetches the files and
// builds on demand; the tools (sitemap, prerender) read the files from disk
// and build the same pages. Nothing here may touch the DOM or fs.

export type Cell = string | number | { text: string; href: string };

export interface DataTable {
  head: string[];
  rows: Cell[][];
  caption?: string;
}

export interface DataSection {
  heading?: string;
  paragraphs?: string[];
  table?: DataTable;
  list?: { text: string; href?: string; detail?: string }[];
  /** Small-print line under the section. */
  note?: string;
}

export interface DataPage {
  /** Site path, e.g. "/gizmo/data-center-restriction-cost/state/georgia". */
  path: string;
  /** The gizmo this page belongs to. */
  parentSlug: string;
  /** H1. */
  title: string;
  /** <title> and JSON-LD headline; defaults to title. */
  seoTitle?: string;
  description: string;
  /** Small line above the H1 ("Data center restrictions · Georgia"). */
  kicker: string;
  intro: string[];
  sections: DataSection[];
  /** Breadcrumb trail, ending in this page. */
  crumbs: { name: string; path: string }[];
  /** ISO date of the data snapshot this page reflects. */
  snapshot: string;
  sources: { name: string; href: string }[];
  /** Sibling/parent links rendered at the bottom. */
  related: { text: string; href: string }[];
  /** True for the dataset's index page. */
  isHub?: boolean;
}

export interface DatasetSpec {
  id: string;
  parentSlug: string;
  /** public/ paths (as URLs) this dataset reads. */
  files: string[];
  /** Pure: files keyed by URL -> pages. Must be deterministic. */
  build: (files: Record<string, unknown>) => DataPage[];
  /** Minimum "data points" a page must carry; thinner pages are dropped (thin-content guard). */
  minCells: number;
}

/** Count the numbers and links on a page, the thin-content yardstick. */
export function dataPoints(p: DataPage): number {
  let n = 0;
  for (const s of p.sections) {
    if (s.table) n += s.table.rows.reduce((a, r) => a + r.length, 0);
    if (s.list) n += s.list.length;
    for (const para of s.paragraphs ?? []) n += (para.match(/\d[\d,.]*/g) ?? []).length;
  }
  for (const para of p.intro) n += (para.match(/\d[\d,.]*/g) ?? []).length;
  return n;
}
