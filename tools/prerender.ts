/**
 * Postbuild: emit per-route index.html files for each gizmo so social
 * crawlers (LinkedIn, Slack, iMessage, Facebook, Twitter, Discord,
 * WhatsApp) see per-page <meta og:*> tags. Those crawlers don't execute
 * JS, so the runtime usePageMeta tags don't reach them — we have to bake
 * the tags into static HTML at build time.
 *
 * The body is identical to dist/index.html (the SPA bundle), so React
 * still hydrates and routing still works. We only rewrite the <head>.
 */
import fs from "node:fs";
import path from "node:path";
import { gizmos } from "../src/data/gizmos";

const SITE_URL = "https://gizmowarehouse.org";
const DIST = path.resolve("dist");
const SHELL = path.join(DIST, "index.html");

function escapeAttr(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function rewriteHead(shell: string, opts: {
  title: string;
  description: string;
  canonical: string;
  ogType: string;
  ogImage?: string;
}): string {
  let html = shell;

  // <title>
  html = html.replace(/<title>[^<]*<\/title>/, `<title>${escapeAttr(opts.title)}</title>`);

  // Helpers to replace meta by attribute=value
  const replaceMeta = (attr: "name" | "property", key: string, content: string) => {
    const re = new RegExp(`<meta\\s+${attr}="${key}"[^>]*>`, "i");
    const tag = `<meta ${attr}="${key}" content="${escapeAttr(content)}">`;
    if (re.test(html)) html = html.replace(re, tag);
    else html = html.replace("</head>", `  ${tag}\n</head>`);
  };
  const replaceLink = (rel: string, href: string) => {
    const re = new RegExp(`<link\\s+rel="${rel}"[^>]*>`, "i");
    const tag = `<link rel="${rel}" href="${escapeAttr(href)}">`;
    if (re.test(html)) html = html.replace(re, tag);
    else html = html.replace("</head>", `  ${tag}\n</head>`);
  };

  replaceMeta("name", "description", opts.description);
  replaceLink("canonical", opts.canonical);
  replaceMeta("property", "og:title", opts.title);
  replaceMeta("property", "og:description", opts.description);
  replaceMeta("property", "og:url", opts.canonical);
  replaceMeta("property", "og:type", opts.ogType);
  replaceMeta("name", "twitter:title", opts.title);
  replaceMeta("name", "twitter:description", opts.description);
  if (opts.ogImage) {
    replaceMeta("property", "og:image", opts.ogImage);
    replaceMeta("name", "twitter:image", opts.ogImage);
  }

  return html;
}

function main() {
  if (!fs.existsSync(SHELL)) {
    console.error(`[prerender] missing ${SHELL} — did vite build run?`);
    process.exit(1);
  }
  const shell = fs.readFileSync(SHELL, "utf8");

  let count = 0;
  for (const g of gizmos) {
    if (g.hidden) continue; // unlisted: no per-route social-preview HTML
    const ogPath = path.join("public", "og", `${g.slug}.png`);
    const hasOg = fs.existsSync(ogPath);
    const ogImage = hasOg ? `${SITE_URL}/og/${g.slug}.png` : undefined;

    const html = rewriteHead(shell, {
      title: `${g.title} | Gizmo Warehouse`,
      description: g.metaDescription || g.summary,
      canonical: `${SITE_URL}/gizmo/${g.slug}`,
      ogType: "article",
      ogImage,
    });

    const outDir = path.join(DIST, "gizmo", g.slug);
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(path.join(outDir, "index.html"), html);
    count += 1;
    console.log(`[prerender] /gizmo/${g.slug}${hasOg ? "  (+og:image)" : ""}`);
  }
  console.log(`[prerender] wrote ${count} route(s)`);
}

main();