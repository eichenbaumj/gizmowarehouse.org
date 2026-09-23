// IndexNow: tell Bing (and the engines that share the protocol: DuckDuckGo,
// Yandex, Naver, Seznam) which URLs changed. Google ignores it; the sitemap's
// lastmod covers Google. Run AFTER clicking Publish in Lovable, since the
// engines fetch the URLs immediately:
//
//   npm run seo:ping                 # every URL in public/sitemap.xml
//   npm run seo:ping -- /gizmo/foo   # specific paths
//   npm run seo:ping -- --limit 200  # cap the batch (default 200/day: a
//                                    # 1,000-URL spike from a small site
//                                    # reads as spam)
//
// The key is a random 32-hex string served back at /<key>.txt (public/), which
// is how the protocol proves the host is ours. It is not a secret.
import { readFileSync, readdirSync } from "node:fs";
import { SITE_URL } from "../src/lib/seo";

const ENDPOINT = "https://api.indexnow.org/indexnow";
const HOST = new URL(SITE_URL).host;

function findKey(): string {
  const f = readdirSync("public").find((n) => /^[a-f0-9]{32}\.txt$/.test(n));
  if (!f) throw new Error("No IndexNow key file in public/ (expected <32 hex>.txt)");
  return f.replace(/\.txt$/, "");
}

function sitemapUrls(): string[] {
  const xml = readFileSync("public/sitemap.xml", "utf8");
  return [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
}

async function main() {
  const args = process.argv.slice(2);
  let limit = 200;
  const paths: string[] = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--limit") limit = Number(args[++i]);
    else paths.push(args[i]);
  }
  const key = findKey();
  const urls = (paths.length ? paths.map((p) => (p.startsWith("http") ? p : `${SITE_URL}${p}`)) : sitemapUrls()).slice(0, limit);
  if (urls.length === 0) {
    console.log("[indexnow] nothing to send");
    return;
  }
  const body = { host: HOST, key, keyLocation: `${SITE_URL}/${key}.txt`, urlList: [...new Set(urls)] };
  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: { "content-type": "application/json; charset=utf-8" },
    body: JSON.stringify(body),
  });
  console.log(`[indexnow] HTTP ${res.status} for ${body.urlList.length} url(s)${res.status === 200 || res.status === 202 ? "" : ": " + (await res.text())}`);
  if (res.status !== 200 && res.status !== 202) process.exit(1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
