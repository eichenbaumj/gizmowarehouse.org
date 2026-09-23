// Renders every public route through the same entry the build uses and
// checks a crawler would actually get the page: an <h1>, real paragraphs,
// the interpolated numbers, and the static embed stand-ins.
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { renderRoute } from "../src/entry-static";
import { publicRoutes } from "../src/lib/routes";
import { gizmoEmbeds as liveEmbeds } from "../src/content/embeds";
import { gizmoContent } from "../src/content";

const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

function ctxFor(urls?: string[]) {
  const out: Record<string, unknown> = {};
  for (const u of urls ?? []) out[u] = JSON.parse(readFileSync(`public${u}`, "utf8"));
  return out;
}

describe("static render", () => {
  it("registers a static stand-in for every live embed (alias swaps ./embeds for ./embeds.static in tests)", () => {
    // Under the test alias, `liveEmbeds` IS the static registry; compare against the tag names used in content.
    const used = new Set<string>();
    for (const md of Object.values(gizmoContent)) for (const m of md.matchAll(/<([a-z]+(?:-[a-z]+)+)\s*\/?>/g)) used.add(m[1]);
    for (const tag of used) expect(Object.keys(liveEmbeds), `no static stand-in for <${tag}>`).toContain(tag);
  });

  it.each(publicRoutes().map((r) => [r.path, r]))("%s renders a real page", (_p, r) => {
    const html = renderRoute((r as any).path, ctxFor((r as any).dataContextUrls));
    expect(html).toMatch(/<h1[^>]*>/);
    expect(text(html).length).toBeGreaterThan(300);
    expect(html).toContain("Gizmo Warehouse"); // layout header present
  });

  it("gizmo pages carry their prose, related links, and no unresolved tokens", () => {
    for (const r of publicRoutes().filter((x) => x.gizmo && x.path === `/gizmo/${x.gizmo.slug}`)) {
      const html = renderRoute(r.path, ctxFor(r.dataContextUrls));
      expect((html.match(/<p[ >]/g) ?? []).length).toBeGreaterThan(2);
      expect(html).toContain("More from the warehouse");
      if (r.dataContextUrls?.length) expect(html).not.toMatch(/\{[a-zA-Z0-9_.]+(?::[a-zA-Z%]+)?\}/);
    }
  });

  it("medicaid and data-center pages expose the state tables to crawlers", () => {
    const med = renderRoute("/gizmo/medicaid-work-requirements", ctxFor(["/data/medicaid-state-summary.json"]));
    expect(med).toContain('data-static-embed="medicaid-map"');
    expect(med).toContain("<td>Texas</td>");
    const dcr = renderRoute("/gizmo/data-center-restriction-cost");
    expect(dcr).toContain('data-static-embed="dcr-map"');
    expect(dcr).toContain('data-static-embed="dcr-town-calc"');
  });

  it("unknown routes render the 404 page", () => {
    expect(renderRoute("/nope/nothing")).toMatch(/This page doesn(?:'|&#x27;)t exist/);
  });
});
