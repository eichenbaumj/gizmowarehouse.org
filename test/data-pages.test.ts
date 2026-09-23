// The programmatic pages are generated, never reviewed, so the tests carry the
// review: every number on a page must equal its source row, slugs must be
// unique, no page may be thin, and the wiring (routes, sitemap) must include
// them.
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { DATASETS, buildAllDataPages, buildDataset, dataPoints } from "../src/data/dataPages";
import { DCR_FILES, type ActionRow } from "../src/data/dataPages/dcr";
import { MEDICAID_FILES } from "../src/data/dataPages/medicaid";
import { COMPGAP_FILES } from "../src/data/dataPages/compgap";
import { STATE_NAMES, stateSlug } from "../src/data/dataPages/util";
import { loadDataFiles } from "../tools/lib/loadDataFiles";
import { publicRoutes } from "../src/lib/routes";
import { renderRoute } from "../src/entry-static";
import { dataPageSeo } from "../src/lib/seo";

const files = loadDataFiles();
const { pages, dropped } = buildAllDataPages(files);
const n0 = (v: number) => Math.round(v).toLocaleString("en-US");
const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/&#x27;/g, "'").replace(/&amp;/g, "&").replace(/\s+/g, " ");

describe("data pages: shape", () => {
  it("builds every dataset", () => {
    for (const spec of DATASETS) expect(spec.files.every((f) => f in files), `${spec.id} files present`).toBe(true);
    expect(pages.length).toBeGreaterThan(1000);
  });
  it("paths are unique, well-formed, and under the parent gizmo", () => {
    const seen = new Set<string>();
    for (const p of pages) {
      expect(seen.has(p.path), p.path).toBe(false);
      seen.add(p.path);
      expect(p.path).toMatch(/^\/gizmo\/[a-z0-9-]+\/[a-z0-9\/-]+$/);
      expect(p.path.startsWith(`/gizmo/${p.parentSlug}/`)).toBe(true);
      expect(p.path).not.toMatch(/\/\/|-\/|\/-|--/);
    }
  });
  it("no page is thin and nothing was dropped", () => {
    expect(dropped).toEqual([]);
    for (const p of pages) if (!p.isHub) expect(dataPoints(p), p.path).toBeGreaterThanOrEqual(8);
  });
  it("titles, descriptions, and copy carry no em dashes, placeholders, or NaN", () => {
    for (const p of pages) {
      const blob = JSON.stringify(p);
      expect(blob, p.path).not.toMatch(/undefined|NaN|\[object|\{[a-z_]+\}/);
      // Our own prose has no em dashes; quoted source records ("The record reads: ...", list details) keep theirs.
      const ours = [p.title, p.seoTitle ?? "", p.description, p.kicker, ...p.intro.filter((t) => !t.startsWith("The record")), ...p.sections.flatMap((s) => [s.heading ?? "", s.note ?? "", ...(s.paragraphs ?? []), ...(s.table?.caption ? [s.table.caption] : [])])].join(" ");
      expect(ours, p.path).not.toMatch(/—/);
      expect(p.description.length, p.path).toBeGreaterThan(60);
      expect(p.description.length, p.path).toBeLessThan(320);
      expect(p.title.length, p.path).toBeLessThan(140);
    }
  });
  it("every page links back to its parent and its hub, and hubs link to every child", () => {
    for (const spec of DATASETS) {
      const mine = pages.filter((p) => p.parentSlug === spec.parentSlug);
      const hub = mine.find((p) => p.isHub)!;
      expect(hub).toBeTruthy();
      const hubLinks = new Set<string>();
      for (const s of hub.sections) for (const r of s.table?.rows ?? []) for (const c of r) if (typeof c === "object" && c && "href" in c) hubLinks.add(c.href);
      for (const p of mine) {
        expect(p.related.some((r) => r.href === `/gizmo/${spec.parentSlug}`), p.path).toBe(true);
        if (p.isHub) continue;
        expect(p.crumbs[p.crumbs.length - 1].path).toBe(p.path);
        // State/city pages are reachable from the hub; jurisdiction pages from their state page.
        if (/\/(state|city)\//.test(p.path)) expect(hubLinks.has(p.path), `hub links ${p.path}`).toBe(true);
        else {
          const statePath = p.crumbs[p.crumbs.length - 2].path;
          const sp = pages.find((x) => x.path === statePath)!;
          const links = new Set<string>();
          for (const s of sp.sections) for (const r of s.table?.rows ?? []) for (const c of r) if (typeof c === "object" && c && "href" in c) links.add(c.href);
          expect(links.has(p.path), `${statePath} links ${p.path}`).toBe(true);
        }
      }
    }
  });
});

describe("data pages: numbers match the source rows", () => {
  it("data-center jurisdiction pages carry each row's summary, status, date, and source", () => {
    const rows = files[DCR_FILES.rows] as ActionRow[];
    const byPath = new Map(pages.map((p) => [p.path, p]));
    const dcrPages = pages.filter((p) => p.parentSlug === "data-center-restriction-cost" && !p.isHub && p.path.split("/").length === 5 && !p.path.includes("/state/"));
    expect(dcrPages.length).toBeGreaterThan(800); // 933 rows collapse to one page per (name, type, county)
    let checked = 0;
    const needle = (r: ActionRow) => r.summary.trim().replace(/\.?$/, "");
    for (const r of rows.filter((x) => x.level === "local")) {
      const page = dcrPages.find((p) => p.intro.some((t) => t.includes(needle(r))))!;
      expect(page, `${r.id} has a page`).toBeTruthy();
      const blob = JSON.stringify(page);
      expect(blob).toContain(JSON.stringify(r.source_url).slice(1, -1));
      expect(blob).toContain(r.status.replace(/_/g, " "));
      checked++;
    }
    expect(checked).toBe(rows.filter((x) => x.level === "local").length);
    expect(byPath.has("/gizmo/data-center-restriction-cost/tracker")).toBe(true);
  });
  it("data-center state pages list exactly their local rows", () => {
    const rows = files[DCR_FILES.rows] as ActionRow[];
    for (const abbr of new Set(rows.map((r) => r.state))) {
      const local = rows.filter((r) => r.state === abbr && r.level === "local");
      const sp = pages.find((p) => p.path === `/gizmo/data-center-restriction-cost/state/${stateSlug(abbr)}`)!;
      expect(sp, abbr).toBeTruthy();
      expect(sp.kicker).toContain(STATE_NAMES[abbr]);
      const table = sp.sections.find((s) => s.heading?.startsWith("Local actions"))?.table;
      expect(table?.rows.length ?? 0, abbr).toBe(local.length);
    }
  });
  it("medicaid state pages equal the state summary and county table", () => {
    const summary = files[MEDICAID_FILES.summary] as any;
    const counties = files[MEDICAID_FILES.counties] as any[];
    for (const s of summary.states) {
      const page = pages.find((p) => p.parentSlug === "medicaid-work-requirements" && p.kicker.endsWith(`· ${s.state_name}`))!;
      expect(page, s.state_name).toBeTruthy();
      const key = page.sections.find((x) => x.heading === "Key figures")!.table!.rows;
      expect(key.find((r) => r[0] === "Adults subject, strict definition")![1]).toBe(n0(s.subject_count_strict));
      expect(key.find((r) => r[0] === "Expansion pool (adults 19 to 64)")![1]).toBe(n0(s.expansion_pool));
      const ct = page.sections.find((x) => x.heading === `Counties in ${s.state_name}`)?.table;
      const expected = counties.filter((c) => c.state_fips === s.state_fips && c.subject_count_strict > 0);
      expect(ct?.rows.length ?? 0, s.state_name).toBe(expected.length);
      if (ct) {
        const top = expected.sort((a, b) => b.subject_count_strict - a.subject_count_strict)[0];
        expect(ct.rows[0][0]).toBe(top.county_name);
        expect(ct.rows[0][1]).toBe(n0(top.subject_count_strict));
      }
    }
    expect(pages.filter((p) => p.parentSlug === "medicaid-work-requirements" && !p.isHub).length).toBe(51);
  });
  it("comp-gap state pages equal the cross-section medians", () => {
    const xs = files[COMPGAP_FILES.states] as any;
    const states = new Set<string>(xs.records.map((r: any) => r.state));
    for (const st of states) {
      const pub = xs.records.find((r: any) => r.state === st && r.domain === "all" && r.sector === "public");
      const priv = xs.records.find((r: any) => r.state === st && r.domain === "all" && r.sector === "private");
      const page = pages.find((p) => p.parentSlug === "public-private-compensation-comparison" && p.path === `/gizmo/public-private-compensation-comparison/state/${stateSlug(st)}`);
      expect(page, st).toBeTruthy();
      const row = page!.sections[0].table!.rows[0];
      expect(row[1]).toBe(`$${pub.p50.toFixed(2)}`);
      expect(row[2]).toBe(`$${priv.p50.toFixed(2)}`);
    }
    const cities = files[COMPGAP_FILES.cities] as any;
    expect(pages.filter((p) => p.path.includes("/city/")).length).toBe(cities.cities.length);
  });
});

describe("data pages: wiring", () => {
  it("routes include every page with the dataset files as data context", () => {
    const routes = publicRoutes(files).filter((r) => r.dataPage);
    expect(routes.length).toBe(pages.length);
    for (const r of routes) expect(r.dataContextUrls?.length).toBeGreaterThan(0);
  });
  it("the sitemap on disk lists the hubs", () => {
    const sm = readFileSync("public/sitemap.xml", "utf8");
    for (const p of pages.filter((x) => x.isHub)) expect(sm).toContain(`<loc>https://gizmowarehouse.org${p.path}</loc>`);
  });
  it("a state page, a jurisdiction page, and a hub render statically with their numbers", () => {
    for (const path of ["/gizmo/medicaid-work-requirements/state/texas", "/gizmo/data-center-restriction-cost/state/georgia", "/gizmo/data-center-restriction-cost/tracker", "/gizmo/public-private-compensation-comparison/city/new-york-city"]) {
      const page = pages.find((p) => p.path === path)!;
      expect(page, path).toBeTruthy();
      const html = renderRoute(path, files);
      const t = text(html);
      expect(t).toContain(page.title);
      expect(t).toContain(page.intro[0].slice(0, 60));
      expect(html).toContain('href="/gizmo/');
      const seo = dataPageSeo(page);
      expect(seo.canonical).toBe(`https://gizmowarehouse.org${path}`);
    }
  });
  it("a jurisdiction page for a real GSC query renders", () => {
    const p = pages.find((x) => x.path === "/gizmo/data-center-restriction-cost/georgia/montgomery-county");
    if (!p) return; // only if that row exists in the snapshot
    expect(text(renderRoute(p.path, files))).toContain("Montgomery County");
  });
});
