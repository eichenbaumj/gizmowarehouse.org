// Single source of truth for page-level SEO: titles, descriptions, canonical
// URLs, social images, and JSON-LD. Used at runtime (usePageMeta in the
// pages) AND at build time (tools/prerender.ts bakes the same values into the
// static HTML), so the crawler view and the browser view never drift.
//
// Two titles per gizmo, on purpose:
//   - `title`     is Joe's headline. It is the H1, the card, and og:title
//                 (what a human sees when the link is shared).
//   - `seoTitle`  (optional) is the search-facing <title> + JSON-LD headline.
//                 It says what the page is about in the words people type.
//                 Falls back to `title`.
import type { Gizmo } from "../data/gizmos";
import type { DataPage } from "../data/dataPages/types";
import lastmod from "../data/lastmod.json";

export const SITE_URL = "https://gizmowarehouse.org";
export const SITE_NAME = "Gizmo Warehouse";
export const SITE_TAGLINE = "Shareable tools, analyses, and work products from Joe Eichenbaum at 17A.";
export const DEFAULT_OG_IMAGE = `${SITE_URL}/og/default.png`;
export const OG_IMAGE_SIZE = { width: 1200, height: 630 };

export const AUTHOR = {
  "@type": "Person",
  name: "Joe Eichenbaum",
  url: "https://www.17a.co",
  affiliation: { "@type": "Organization", name: "17A", url: "https://www.17a.co" },
} as const;

export const PUBLISHER = {
  "@type": "Organization",
  name: "Gizmo Warehouse",
  url: SITE_URL,
  logo: { "@type": "ImageObject", url: `${SITE_URL}/favicon.png` },
} as const;

/** Everything a page's <head> needs. Both runtime and build time consume this. */
export interface PageSeo {
  /** <title> and JSON-LD headline. */
  title: string;
  /** og:title / twitter:title. Defaults to `title`. */
  socialTitle?: string;
  description: string;
  canonical: string;
  /** Defaults to DEFAULT_OG_IMAGE. */
  ogImage?: string;
  /** Defaults to "website". */
  ogType?: "website" | "article";
  /** ISO date; used for article:published_time + JSON-LD. */
  datePublished?: string;
  dateModified?: string;
  noindex?: boolean;
  jsonLd?: object | object[];
}

export function gizmoUrl(g: Pick<Gizmo, "slug">): string {
  return `${SITE_URL}/gizmo/${g.slug}`;
}

export function gizmoOgImage(g: Pick<Gizmo, "slug">): string {
  return `${SITE_URL}/og/${g.slug}.png`;
}

export function gizmoSearchTitle(g: Pick<Gizmo, "title" | "seoTitle">): string {
  return g.seoTitle || g.title;
}

export function gizmoDescription(g: Pick<Gizmo, "summary" | "metaDescription">): string {
  return g.metaDescription || g.summary;
}

/** "2026-09" → "2026-09-01"; already-full dates pass through. */
export function isoDate(d: string): string {
  return /^\d{4}-\d{2}$/.test(d) ? `${d}-01` : d;
}

/** Last content change for a gizmo (from src/data/lastmod.json, written by tools/generate-sitemap.ts). */
export function gizmoLastmod(g: Pick<Gizmo, "slug" | "date">): string {
  const v = (lastmod as Record<string, string>)[g.slug];
  return v ? v.slice(0, 10) : isoDate(g.date);
}

export function breadcrumbJsonLd(items: { name: string; url: string }[]): object {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((it, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: it.name,
      item: it.url,
    })),
  };
}

export function gizmoSeo(g: Gizmo): PageSeo {
  const url = gizmoUrl(g);
  const description = gizmoDescription(g);
  const datePublished = isoDate(g.date);
  const dateModified = gizmoLastmod(g);
  const ogImage = gizmoOgImage(g);
  return {
    title: `${gizmoSearchTitle(g)} | ${SITE_NAME}`,
    socialTitle: g.title,
    description,
    canonical: url,
    ogImage,
    ogType: "article",
    datePublished,
    dateModified,
    noindex: !!g.hidden,
    jsonLd: [
      {
        "@context": "https://schema.org",
        "@type": "Article",
        headline: gizmoSearchTitle(g),
        alternativeHeadline: g.seoTitle ? g.title : undefined,
        description,
        image: [ogImage],
        datePublished,
        dateModified,
        url,
        mainEntityOfPage: { "@type": "WebPage", "@id": url },
        author: AUTHOR,
        publisher: PUBLISHER,
        keywords: g.categories.join(", "),
        isAccessibleForFree: true,
      },
      breadcrumbJsonLd([
        { name: SITE_NAME, url: `${SITE_URL}/` },
        { name: g.title, url },
      ]),
    ],
  };
}

export function homeSeo(): PageSeo {
  return {
    title: `${SITE_NAME} | 17A`,
    description: SITE_TAGLINE,
    canonical: `${SITE_URL}/`,
    ogImage: DEFAULT_OG_IMAGE,
    ogType: "website",
    jsonLd: [
      {
        "@context": "https://schema.org",
        "@type": "WebSite",
        name: SITE_NAME,
        url: SITE_URL,
        description: SITE_TAGLINE,
        publisher: PUBLISHER,
      },
      {
        "@context": "https://schema.org",
        "@type": "Organization",
        name: "17A",
        url: "https://www.17a.co",
        founder: { "@type": "Person", name: "Joe Eichenbaum" },
      },
    ],
  };
}

export function notFoundSeo(): PageSeo {
  return {
    title: `Not Found | ${SITE_NAME}`,
    description: "That page doesn't exist. Head back to the Gizmo Warehouse to browse everything that does.",
    canonical: `${SITE_URL}/`,
    ogImage: DEFAULT_OG_IMAGE,
    ogType: "website",
    noindex: true,
  };
}

/** Related gizmos: most shared categories first, then newest. Never hidden, never self. */
export function relatedGizmos(g: Gizmo, all: Gizmo[], n = 3): Gizmo[] {
  const mine = new Set(g.categories);
  return all
    .filter((o) => o.slug !== g.slug && !o.hidden)
    .map((o) => ({ o, shared: o.categories.filter((c) => mine.has(c)).length }))
    .sort((a, b) => b.shared - a.shared || (a.o.date < b.o.date ? 1 : a.o.date > b.o.date ? -1 : 0))
    .slice(0, n)
    .map((x) => x.o);
}

/** SEO for a programmatic data page (src/data/dataPages). */
export function dataPageSeo(p: DataPage, parent?: Pick<Gizmo, "slug" | "date">): PageSeo {
  const url = `${SITE_URL}${p.path}`;
  const ogImage = `${SITE_URL}/og/${p.parentSlug}.png`;
  const datePublished = parent ? isoDate(parent.date) : p.snapshot;
  return {
    title: `${p.seoTitle || p.title} | ${SITE_NAME}`,
    socialTitle: p.title,
    description: p.description,
    canonical: url,
    ogImage,
    ogType: "article",
    datePublished,
    dateModified: p.snapshot,
    jsonLd: [
      {
        "@context": "https://schema.org",
        "@type": p.isHub ? "CollectionPage" : "Article",
        headline: p.seoTitle || p.title,
        alternativeHeadline: p.seoTitle ? p.title : undefined,
        description: p.description,
        image: [ogImage],
        datePublished,
        dateModified: p.snapshot,
        url,
        mainEntityOfPage: { "@type": "WebPage", "@id": url },
        author: AUTHOR,
        publisher: PUBLISHER,
        isPartOf: { "@type": "WebPage", "@id": `${SITE_URL}/gizmo/${p.parentSlug}` },
        isAccessibleForFree: true,
      },
      breadcrumbJsonLd(p.crumbs.map((c) => ({ name: c.name, url: `${SITE_URL}${c.path}` }))),
    ],
  };
}
