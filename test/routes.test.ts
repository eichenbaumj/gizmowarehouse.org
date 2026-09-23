import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { ALL_CATEGORIES, categoryFromSlug, categorySlug, gizmos } from "../src/data/gizmos";
import { METHODOLOGY_ROUTES, publicRoutes } from "../src/lib/routes";

const appRoutes = readFileSync("src/AppRoutes.tsx", "utf8");

describe("route registry", () => {
  it("lists every live gizmo and nothing hidden", () => {
    const paths = new Set(publicRoutes().map((r) => r.path));
    for (const g of gizmos) {
      expect(paths.has(`/gizmo/${g.slug}`)).toBe(!g.hidden);
    }
  });
  it("methodology routes exist in AppRoutes.tsx", () => {
    for (const m of METHODOLOGY_ROUTES) expect(appRoutes).toContain(`path="${m.path}"`);
  });
  it("category slugs round-trip and the route exists", () => {
    expect(appRoutes).toContain('path="/category/:category"');
    for (const c of ALL_CATEGORIES) expect(categoryFromSlug(categorySlug(c))).toBe(c);
  });
  it("has no duplicate paths", () => {
    const paths = publicRoutes().map((r) => r.path);
    expect(new Set(paths).size).toBe(paths.length);
  });
});

describe("generated files", () => {
  const sitemap = readFileSync("public/sitemap.xml", "utf8");
  const llms = readFileSync("public/llms.txt", "utf8");
  it("sitemap has every public route with a lastmod", () => {
    for (const r of publicRoutes()) {
      expect(sitemap).toContain(`<loc>https://gizmowarehouse.org${r.path}</loc><lastmod>`);
    }
    expect(sitemap).not.toMatch(/claude-code-usage/);
  });
  it("llms.txt lists every live gizmo and no hidden one", () => {
    for (const g of gizmos) expect(llms.includes(`/gizmo/${g.slug})`)).toBe(!g.hidden);
  });
  it("robots.txt points at the sitemap", () => {
    expect(readFileSync("public/robots.txt", "utf8")).toContain("Sitemap: https://gizmowarehouse.org/sitemap.xml");
  });
});
