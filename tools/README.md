# tools/

Generic gizmo-warehouse infrastructure — anything that's about *running the warehouse* rather than building a specific gizmo.

## Adding a new gizmo

```bash
python tools/new-gizmo.py
```

It prompts for slug, title, categories, summary, and optional links, then writes:

- `gizmos/<slug>/README.md` — empty stub for source materials
- `src/content/<slug>.ts` — empty markdown content file
- An `import` line + map entry in `src/content/index.ts`
- A metadata object appended to the `gizmos` array in `src/data/gizmos.ts`

Then write the markdown in `src/content/<slug>.ts`, drop any served files (PDFs, images, downloads) in `public/assets/`, and `npm run dev` to preview at <http://localhost:8080>.

## Deploy

Push to `main` on GitHub. Lovable syncs the push and builds it, but production only changes when you click **Publish → Publish changes** in the Lovable editor. Verify on the live URL, then run `npm run seo:ping` (IndexNow) so Bing and the engines that share the protocol fetch the changed pages.

## SEO

Everything a page's `<head>` needs comes from one place, [`src/lib/seo.ts`](../src/lib/seo.ts): titles (`seoTitle` is the search-facing `<title>`; `title` stays the H1, the card, and og:title), descriptions, canonical, OG image, and JSON-LD. Pages call `usePageMeta(...)` at runtime with the same object the prerenderer bakes at build time, so the two views agree.

`npm run build` does, in order: `check:basemap` → `derive-data` (CSV/geojson → the JSON the data pages read) → `generate-sitemap` (`public/sitemap.xml` with lastmod from git, `public/llms.txt`, `src/data/lastmod.json`) → `vite build` → `build:static` (an SSR bundle of the app with the interactive embeds swapped for [`src/content/embeds.static.tsx`](../src/content/embeds.static.tsx)) → `prerender` (one full-body HTML file per route in `dist/`, plus `404.html` and alias stubs). Crawlers that skip JavaScript get the whole page; the browser mounts React on top and replaces it.

Routes live in [`src/lib/routes.ts`](../src/lib/routes.ts) (sitemap + prerender) and [`src/AppRoutes.tsx`](../src/AppRoutes.tsx) (the router); `test/routes.test.ts` keeps them in step. Programmatic data pages (one per state, county, city, jurisdiction) are declared in [`src/data/dataPages/`](../src/data/dataPages/): a `DatasetSpec` names its files and a pure `build`; every sentence is a template filled from the data, and `test/data-pages.test.ts` asserts the numbers equal the source rows.

OG cards: `python3 tools/generate-og-cards.py` makes a card for any gizmo without one (reads `gizmos.ts`; pass slugs to regenerate). `npm test` fails if a live gizmo has no card.

IndexNow: `npm run seo:ping` after a Publish (default cap 200 URLs; `-- /path` for specific pages). The key file in `public/` is public by design. `public/robots.txt` allows everything and points at the sitemap.

The traffic plan, Search Console baseline, weekly loop, and the ad kit are in `gizmos/_seo/` (private, never mirrored).

## Domains

- **Public URL:** `https://gizmowarehouse.org`. Lovable serves the project; DNS is on Cloudflare. `www.gizmowarehouse.org` redirects to apex. The `*.lovable.app` URL still works as a fallback. Full setup, verification commands, and failure modes in [`HOSTING_SITE.md`](HOSTING_SITE.md).
- **Asset hosting:** files larger than Lovable's ~25 MB cap (PMTiles, big GeoJSON, downloadable artifacts) live at `https://data.gizmowarehouse.org/<gizmo-slug>/...` on Cloudflare R2. Setup pattern in [`HOSTING_DATA.md`](HOSTING_DATA.md).

## Brand

The 17A brand system is the source of truth for colors, fonts, and visual style: Cobalt Blue `#1F1FD6`, Carolina Blue `#21A8E0`, Charcoal `#3B3B3B`. Source Serif 4 for headings; Source Sans 3 for body. Loaded from Google Fonts in `index.html`. PDF build scripts load local TTFs from a `BRAND_ROOT` env var pointing at the brand-assets directory.

## Adding a new category

`new-gizmo.py` only offers the existing categories. To add a new one:

1. Add it to the `Category` type in `src/data/gizmos.ts` and to `ALL_CATEGORIES`.
2. Add a Tailwind color mapping in `src/components/CategoryBadge.tsx`.

Only do this when there's real content for it — empty buckets dilute the home page.
