import { describe, expect, it } from "vitest";
import { existsSync } from "node:fs";
import { gizmos } from "../src/data/gizmos";
import { gizmoDescription, gizmoSearchTitle, gizmoSeo, relatedGizmos } from "../src/lib/seo";

const live = gizmos.filter((g) => !g.hidden);

describe("gizmo SEO fields", () => {
  it.each(live.map((g) => [g.slug, g]))("%s has a social card in public/og", (_slug, g) => {
    expect(existsSync(`public/og/${(g as any).slug}.png`)).toBe(true);
  });
  it("the default card exists", () => {
    expect(existsSync("public/og/default.png")).toBe(true);
  });
  it.each(live.map((g) => [g.slug, g]))("%s description is a search snippet, not an essay", (_slug, g) => {
    const d = gizmoDescription(g as any);
    expect(d.length).toBeGreaterThanOrEqual(60);
    expect(d.length).toBeLessThanOrEqual(170);
  });
  it.each(live.map((g) => [g.slug, g]))("%s search title fits a result", (_slug, g) => {
    const t = gizmoSearchTitle(g as any);
    expect(t.length).toBeLessThanOrEqual(90);
  });
  it.each(live.filter((g) => g.metaDescription || g.seoTitle).map((g) => [g.slug, g]))("%s new copy has no em dashes", (_slug, g) => {
    expect(`${(g as any).seoTitle ?? ""} ${(g as any).metaDescription ?? ""}`).not.toMatch(/—/);
  });
  it("Article JSON-LD carries dates, image, author, publisher", () => {
    for (const g of live) {
      const seo = gizmoSeo(g);
      const [article, crumbs] = seo.jsonLd as any[];
      expect(article["@type"]).toBe("Article");
      expect(article.datePublished).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(article.dateModified).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(article.image[0]).toContain(`/og/${g.slug}.png`);
      expect(article.author.name).toBe("Joe Eichenbaum");
      expect(article.publisher.name).toBe("Gizmo Warehouse");
      expect(crumbs["@type"]).toBe("BreadcrumbList");
      expect(seo.socialTitle).toBe(g.title);
      expect(seo.title).toContain(gizmoSearchTitle(g));
    }
  });
  it("related gizmos never include self or hidden, and prefer shared categories", () => {
    for (const g of live) {
      const rel = relatedGizmos(g, gizmos);
      expect(rel.length).toBeGreaterThan(0);
      expect(rel.some((r) => r.slug === g.slug)).toBe(false);
      expect(rel.some((r) => r.hidden)).toBe(false);
    }
    const medicaid = live.find((g) => g.slug === "medicaid-work-requirements")!;
    expect(relatedGizmos(medicaid, gizmos)[0].categories.some((c) => medicaid.categories.includes(c))).toBe(true);
  });
});
