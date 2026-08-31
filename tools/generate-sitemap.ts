import { writeFileSync } from "node:fs";
import { gizmos } from "../src/data/gizmos";

const SITE_URL = "https://gizmowarehouse.org";

const urls = [`${SITE_URL}/`, ...gizmos.filter((g) => !g.hidden).map((g) => `${SITE_URL}/gizmo/${g.slug}`)];

const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.map((u) => `  <url><loc>${u}</loc></url>`).join("\n")}
</urlset>
`;

writeFileSync("public/sitemap.xml", xml);
console.log(`Generated public/sitemap.xml with ${urls.length} URLs`);
