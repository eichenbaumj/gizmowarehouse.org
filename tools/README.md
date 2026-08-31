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

Push to `main` on GitHub. Lovable watches the repo and auto-deploys; no separate build/deploy step is needed from this repo.

## SEO

Per-route `<title>` / `description` / `canonical` / `og:*` tags are set in JS via [`src/lib/usePageMeta.ts`](../src/lib/usePageMeta.ts). The pre-JS HTML in [`index.html`](../index.html) holds the homepage-level fallback for crawlers that don't run JS.

[`generate-sitemap.ts`](generate-sitemap.ts) reads `src/data/gizmos.ts` and writes `public/sitemap.xml`. It runs automatically as part of `npm run build`, so new gizmos get a sitemap entry on the next deploy without any manual step. To regenerate ad-hoc: `npm run generate-sitemap`.

`public/robots.txt` allows everything and points crawlers at the sitemap.

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
