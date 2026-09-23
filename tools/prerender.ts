/**
 * Postbuild: one static HTML file per public route, with the FULL page body
 * rendered (not just the <head>), so every crawler that skips JavaScript
 * (Bing, LLM crawlers, social scrapers, Google's first indexing pass) reads
 * the whole piece. React then mounts on top with createRoot().render() and
 * replaces the static tree with the live app.
 *
 * Inputs:  dist/index.html (the vite SPA shell), dist-static/entry-static.js
 *          (the SSR bundle from `npm run build:static`), src/lib/routes.ts.
 * Outputs: dist/<route>/index.html for every route, dist/index.html for "/",
 *          dist/404.html (noindex), and meta-refresh stubs for ALIAS_ROUTES.
 *
 * The <head> is rewritten from the same src/lib/seo.ts helpers the pages use
 * at runtime, so the static and live views agree tag for tag.
 */
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { dataPageSeo, gizmoSeo, homeSeo, notFoundSeo, OG_IMAGE_SIZE, SITE_NAME, SITE_URL, DEFAULT_OG_IMAGE, breadcrumbJsonLd, type PageSeo } from "../src/lib/seo";
import { ALIAS_ROUTES, publicRoutes, type PublicRoute } from "../src/lib/routes";
import { categoryFromSlug } from "../src/data/gizmos";
import { loadDataFiles } from "./lib/loadDataFiles";
import { CATEGORY_BLURBS } from "../src/lib/categories";

const DIST = path.resolve("dist");
const SHELL = path.join(DIST, "index.html");
const STATIC_BUNDLE = path.resolve("dist-static/entry-static.js");

function escapeAttr(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function stripManagedHead(shell: string): string {
  // Drop every tag we manage so a route never inherits a stale one from the shell.
  return shell
    .replace(/\s*<meta\s+(?:name|property)="(?:description|robots|og:[^"]+|twitter:[^"]+|article:[^"]+)"[^>]*>/gi, "")
    .replace(/\s*<link\s+rel="canonical"[^>]*>/gi, "")
    .replace(/\s*<script type="application\/ld\+json" id="page-jsonld">[\s\S]*?<\/script>/gi, "");
}

function buildHead(seo: PageSeo): string {
  const ogImage = seo.ogImage || DEFAULT_OG_IMAGE;
  const ogType = seo.ogType || "website";
  const social = seo.socialTitle || seo.title;
  const tags: string[] = [
    `<meta name="description" content="${escapeAttr(seo.description)}">`,
    `<meta name="robots" content="${seo.noindex ? "noindex, follow" : "index, follow, max-image-preview:large"}">`,
    `<link rel="canonical" href="${escapeAttr(seo.canonical)}">`,
    `<meta property="og:site_name" content="${SITE_NAME}">`,
    `<meta property="og:type" content="${ogType}">`,
    `<meta property="og:url" content="${escapeAttr(seo.canonical)}">`,
    `<meta property="og:title" content="${escapeAttr(social)}">`,
    `<meta property="og:description" content="${escapeAttr(seo.description)}">`,
    `<meta property="og:image" content="${escapeAttr(ogImage)}">`,
    `<meta property="og:image:width" content="${OG_IMAGE_SIZE.width}">`,
    `<meta property="og:image:height" content="${OG_IMAGE_SIZE.height}">`,
    `<meta property="og:image:alt" content="${escapeAttr(social)}">`,
    `<meta name="twitter:card" content="summary_large_image">`,
    `<meta name="twitter:title" content="${escapeAttr(social)}">`,
    `<meta name="twitter:description" content="${escapeAttr(seo.description)}">`,
    `<meta name="twitter:image" content="${escapeAttr(ogImage)}">`,
  ];
  if (ogType === "article" && seo.datePublished) {
    tags.push(`<meta property="article:published_time" content="${seo.datePublished}">`);
    if (seo.dateModified) tags.push(`<meta property="article:modified_time" content="${seo.dateModified}">`);
    tags.push(`<meta property="article:author" content="Joe Eichenbaum">`);
  }
  if (seo.jsonLd) {
    // "</" inside JSON would close the script tag early.
    tags.push(`<script type="application/ld+json" id="page-jsonld">${JSON.stringify(seo.jsonLd).replace(/<\//g, "<\\/")}</script>`);
  }
  return tags.map((t) => `    ${t}`).join("\n");
}

function assemble(shell: string, seo: PageSeo, body: string): string {
  let html = stripManagedHead(shell);
  html = html.replace(/<title>[^<]*<\/title>/, `<title>${escapeAttr(seo.title)}</title>\n${buildHead(seo)}`);
  const root = html.match(/<div id="root"><\/div>/);
  if (!root) throw new Error("[prerender] shell has no empty <div id=\"root\"></div>");
  return html.replace(root[0], `<div id="root" data-static="1">${body}</div>`);
}

function write(routePath: string, html: string) {
  const outDir = routePath === "/" ? DIST : path.join(DIST, routePath.replace(/^\//, ""));
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, "index.html"), html);
}

function loadDataContexts(r: PublicRoute): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const url of r.dataContextUrls ?? []) {
    const file = path.join("public", url);
    if (!fs.existsSync(file)) {
      console.warn(`[prerender] data context missing: ${file}`);
      continue;
    }
    out[url] = JSON.parse(fs.readFileSync(file, "utf8"));
  }
  return out;
}

function seoForRoute(r: PublicRoute): PageSeo {
  if (r.path === "/") return homeSeo();
  if (r.dataPage) return dataPageSeo(r.dataPage, r.gizmo);
  if (r.gizmo && r.path === `/gizmo/${r.gizmo.slug}`) return gizmoSeo(r.gizmo);
  if (r.gizmo && r.path.endsWith("/methodology")) {
    const url = `${SITE_URL}${r.path}`;
    return {
      title: `Methodology: ${r.gizmo.seoTitle || r.gizmo.title} | ${SITE_NAME}`,
      socialTitle: `Methodology: ${r.gizmo.title}`,
      description: `Sources, model choices, and caveats behind "${r.gizmo.title}" by Joe Eichenbaum at 17A.`,
      canonical: url,
      ogImage: `${SITE_URL}/og/${r.gizmo.slug}.png`,
      ogType: "article",
      datePublished: r.gizmo.date.length === 7 ? `${r.gizmo.date}-01` : r.gizmo.date,
      jsonLd: breadcrumbJsonLd([
        { name: SITE_NAME, url: `${SITE_URL}/` },
        { name: r.gizmo.title, url: `${SITE_URL}/gizmo/${r.gizmo.slug}` },
        { name: "Methodology", url },
      ]),
    };
  }
  if (r.path.startsWith("/category/")) {
    const cat = categoryFromSlug(r.path.replace("/category/", ""));
    const url = `${SITE_URL}${r.path}`;
    return {
      title: `${cat} | ${SITE_NAME}`,
      description: `${cat ? CATEGORY_BLURBS[cat] : ""} Gizmos from Joe Eichenbaum at 17A.`.trim(),
      canonical: url,
      ogType: "website",
      jsonLd: breadcrumbJsonLd([
        { name: SITE_NAME, url: `${SITE_URL}/` },
        { name: cat ?? "", url },
      ]),
    };
  }
  throw new Error(`[prerender] no SEO mapping for ${r.path}`);
}

async function main() {
  if (!fs.existsSync(SHELL)) {
    console.error(`[prerender] missing ${SHELL}: did vite build run?`);
    process.exit(1);
  }
  if (!fs.existsSync(STATIC_BUNDLE)) {
    console.error(`[prerender] missing ${STATIC_BUNDLE}: run npm run build:static first`);
    process.exit(1);
  }
  const shell = fs.readFileSync(SHELL, "utf8");
  const { renderRoute } = (await import(pathToFileURL(STATIC_BUNDLE).href)) as { renderRoute: (url: string, ctx?: Record<string, unknown>) => string };

  let count = 0;
  const problems: string[] = [];
  const dataFiles = loadDataFiles();
  const routes = publicRoutes(dataFiles);
  const quiet = routes.length > 60; // one line per route is noise at 1,000+ pages
  for (const r of routes) {
    const body = renderRoute(r.path, r.dataPage ? dataFiles : loadDataContexts(r));
    const seo = seoForRoute(r);
    if (!seo.ogImage) seo.ogImage = DEFAULT_OG_IMAGE;
    if (seo.ogImage.startsWith(`${SITE_URL}/og/`)) {
      const local = path.join("public", seo.ogImage.slice(SITE_URL.length));
      if (!fs.existsSync(local)) {
        problems.push(`${r.path}: og image missing (${local}); using default`);
        seo.ogImage = DEFAULT_OG_IMAGE;
      }
    }
    const textLen = body.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").length;
    if (textLen < 200) problems.push(`${r.path}: static body is only ${textLen} chars of text`);
    write(r.path, assemble(shell, seo, body));
    count += 1;
    if (!quiet || !r.dataPage) console.log(`[prerender] ${r.path}  (${textLen.toLocaleString()} chars)`);
  }
  const dataCount = routes.filter((r) => r.dataPage).length;
  if (dataCount) console.log(`[prerender] ${dataCount} data pages across ${new Set(routes.filter((r) => r.dataPage).map((r) => r.gizmo?.slug)).size} gizmos`);

  // 404: noindex, canonical home. Served by hosts that honor 404.html; harmless otherwise.
  const nf = notFoundSeo();
  fs.writeFileSync(path.join(DIST, "404.html"), assemble(shell, nf, renderRoute("/__not_found__")));

  // Old URLs: a static page that canonicalizes and refreshes to the new one.
  for (const a of ALIAS_ROUTES) {
    const target = `${SITE_URL}${a.to}`;
    const html = assemble(shell, { title: `Moved | ${SITE_NAME}`, description: `This page moved to ${target}.`, canonical: target, noindex: true }, `<p>This page has moved to <a href="${a.to}">${target}</a>.</p>`)
      .replace("</head>", `    <meta http-equiv="refresh" content="0;url=${a.to}">\n  </head>`);
    write(a.from, html);
    console.log(`[prerender] ${a.from} -> ${a.to} (alias)`);
  }

  console.log(`[prerender] wrote ${count} route(s) + 404.html + ${ALIAS_ROUTES.length} alias(es)`);
  if (problems.length) {
    console.error(`[prerender] ${problems.length} problem(s):\n  ${problems.join("\n  ")}`);
    process.exit(1);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
