// social-capture.mjs — element screenshot for Reddit / social posts, from a
// running build (npm run build && npx vite preview --port 4173) or dev server.
//
//   node tools/social-capture.mjs <url-path> <css-selector> <out.png> [--wait ms] [--width px] [--base url] [--click "button text"]
//   python3 tools/social-letterbox.py <out.png>      # -> 1200x675 on white (Reddit's preview crop)
//
// Captures at 2x device scale. WebGL maps need preserveDrawingBuffer:true in
// their MapLibre constructor or they screenshot blank (DcrMap and
// NYCPropertyTaxMap have it; the Medicaid maps do not, capture their SVG
// charts instead).
import { chromium } from "playwright";

const [, , path, selector, out, ...rest] = process.argv;
if (!path || !selector || !out) {
  console.error('usage: node tools/social-capture.mjs <path> <selector> <out.png> [--wait ms] [--width px] [--base url] [--click "text"]');
  process.exit(2);
}
const opt = (k, d) => {
  const i = rest.indexOf(k);
  return i >= 0 ? rest[i + 1] : d;
};
const wait = Number(opt("--wait", 4000));
const width = Number(opt("--width", 1440));
const base = opt("--base", process.env.BASE_URL || "http://localhost:4173");
const click = opt("--click", null);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width, height: 1400 }, deviceScaleFactor: 2 });
await page.addStyleTag({ content: "body{background:#fff!important}" }).catch(() => {});
await page.goto(`${base}${path}`, { waitUntil: "networkidle" });
const el = page.locator(selector).first();
await el.waitFor({ state: "visible", timeout: 30000 });
await el.scrollIntoViewIfNeeded();
if (click) {
  await el.getByRole("button", { name: click }).first().click();
}
await page.waitForTimeout(wait);
await el.screenshot({ path: out, type: "png" });
const box = await el.boundingBox();
await browser.close();
console.log(`wrote ${out} (${Math.round(box.width)}x${Math.round(box.height)} css px, 2x)`);
