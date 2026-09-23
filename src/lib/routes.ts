// Every public, indexable route on the site, in one list. Consumed by
// tools/generate-sitemap.ts (sitemap.xml + llms.txt) and tools/prerender.ts
// (one static HTML file per route). When you add a route to src/AppRoutes.tsx
// that should be crawled, add it here too; test/routes.test.ts checks the two
// agree.
import { ALL_CATEGORIES, categorySlug, gizmos, type Gizmo } from "../data/gizmos";
import { SITE_URL } from "./seo";
import { buildAllDataPages, DATASETS } from "../data/dataPages";
import type { DataPage } from "../data/dataPages/types";

export interface PublicRoute {
  /** Path starting with "/". */
  path: string;
  /** Files whose git history dates the route (for sitemap lastmod). */
  sources: string[];
  /** The gizmo this route belongs to, if any. */
  gizmo?: Gizmo;
  /** Fallback lastmod (YYYY-MM or YYYY-MM-DD) when git can't date the sources. */
  fallbackDate?: string;
  /** sitemap <priority> hint. */
  priority: number;
  /** Optional data files (public/ paths) the page interpolates; passed to the static render. */
  dataContextUrls?: string[];
  /** Set for programmatic data pages. */
  dataPage?: DataPage;
}

export const METHODOLOGY_ROUTES: { slug: string; path: string; source: string }[] = [
  {
    slug: "medicaid-work-requirements",
    path: "/gizmo/medicaid-work-requirements/methodology",
    source: "gizmos/medicaid-work-requirements/METHODOLOGY.md",
  },
  {
    slug: "public-private-compensation-comparison",
    path: "/gizmo/public-private-compensation-comparison/methodology",
    source: "gizmos/public-private-compensation-comparison/APPENDIX.md",
  },
];

/** Old URLs that must keep resolving. Prerendered as meta-refresh + canonical to the target. */
export const ALIAS_ROUTES: { from: string; to: string }[] = [
  { from: "/gizmo/nyc-public-grocery-math-30", to: "/gizmo/nyc-public-grocery-new-math" },
];

/**
 * @param dataFiles the data-page datasets' files keyed by URL (tools load them
 *   from public/ with tools/lib/loadDataFiles.ts). Omit to list only the
 *   hand-written routes.
 */
export function publicRoutes(dataFiles?: Record<string, unknown>): PublicRoute[] {
  const live = gizmos.filter((g) => !g.hidden);
  const routes: PublicRoute[] = [
    { path: "/", sources: ["src/data/gizmos.ts", "src/pages/Home.tsx"], priority: 1.0 },
  ];
  for (const g of live) {
    routes.push({
      path: `/gizmo/${g.slug}`,
      sources: [`src/content/${g.slug}.ts`],
      gizmo: g,
      fallbackDate: g.date,
      priority: 0.8,
      dataContextUrls: g.dataContextUrl ? [g.dataContextUrl] : undefined,
    });
  }
  for (const m of METHODOLOGY_ROUTES) {
    const g = live.find((x) => x.slug === m.slug);
    if (!g) continue;
    routes.push({ path: m.path, sources: [m.source], gizmo: g, fallbackDate: g.date, priority: 0.4 });
  }
  for (const c of ALL_CATEGORIES) {
    if (!live.some((g) => g.categories.includes(c))) continue; // no empty buckets
    routes.push({ path: `/category/${categorySlug(c)}`, sources: ["src/data/gizmos.ts"], priority: 0.5 });
  }
  if (dataFiles) {
    const { pages } = buildAllDataPages(dataFiles);
    for (const p of pages) {
      const g = live.find((x) => x.slug === p.parentSlug);
      if (!g) continue; // parent unpublished: its data pages stay off the site
      const spec = DATASETS.find((d) => d.parentSlug === p.parentSlug)!;
      routes.push({
        path: p.path,
        sources: spec.files.map((f) => `public${f}`),
        gizmo: g,
        fallbackDate: p.snapshot,
        priority: p.isHub ? 0.7 : 0.6,
        dataContextUrls: spec.files,
        dataPage: p,
      });
    }
  }
  return routes;
}

export function absoluteUrl(path: string): string {
  return `${SITE_URL}${path}`;
}
