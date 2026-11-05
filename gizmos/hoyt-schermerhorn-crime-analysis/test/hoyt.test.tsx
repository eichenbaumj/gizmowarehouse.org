// Gizmo-local tests (vite test.include covers gizmos/*/test). They run against the real exported data in
// public/data/<slug>/ and skip, with a reason, when the pipeline has not exported yet.
import { statSync, existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import content from "@/content/hoyt-schermerhorn-crime-analysis";
import { hoytEmbeds } from "@/components/hoyt/hoytEmbeds";
import { CITY_STEPS, CLASS_ORDER, HOYT_SLUG } from "@/config/hoytSchermerhorn";
import { interpolateTokens } from "@/lib/interpolateTokens";

const DATA = join(process.cwd(), "public", "data", HOYT_SLUG);
const has = existsSync(join(DATA, "context.json")) && existsSync(join(DATA, "timelapse.json"));
const read = (n: string) => JSON.parse(readFileSync(join(DATA, n), "utf8"));
const tags = [...content.matchAll(/<hs-([a-z-]+)/g)].map((m) => `hs-${m[1]}`);

describe("content and registries", () => {
  it("every hs-* tag in the content has a live component", () => {
    for (const t of new Set(tags)) expect(hoytEmbeds[t], t).toBeTruthy();
  });
  it("every hs-* tag has a static stand-in", async () => {
    if (!has) return;
    const { hoytEmbedsStatic } = await import("@/components/hoyt/hoyt.static");
    for (const t of new Set(tags)) expect(hoytEmbedsStatic[t], t).toBeTruthy();
  });
  it("every city step names a CITY_STEPS entry", () => {
    const section = content.split('<hs-scrolly stage="city"')[1]?.split("</hs-scrolly>")[0] ?? "";
    const steps = [...section.matchAll(/<hs-step step="([a-z0-9-]+)"/g)].map((m) => m[1]);
    expect(steps.length).toBeGreaterThan(0);
    for (const s of steps) expect((CITY_STEPS as readonly string[]).includes(s), s).toBe(true);
  });
  it("no em dashes in shipped prose", () => {
    expect(content.includes("—")).toBe(false);
  });
  it("static render keeps the prose and has no unresolved tokens", async () => {
    if (!has) return;
    const { hoytEmbedsStatic } = await import("@/components/hoyt/hoyt.static");
    const ctx = read("context.json");
    const md = interpolateTokens(content, ctx);
    const html = renderToStaticMarkup(createElement(ReactMarkdown as any, { remarkPlugins: [remarkGfm], rehypePlugins: [rehypeRaw], components: hoytEmbedsStatic }, md));
    expect(html.length).toBeGreaterThan(3000);
    expect((html.match(/<p>/g) ?? []).length).toBeGreaterThan(10);
    expect(/\{[a-z_]+\.[a-z_0-9.]+(:[a-z%0_]+)?\}/.test(html)).toBe(false);
  });
});

describe("exported data is internally consistent", () => {
  it.skipIf(!has)("zone sums equal the ribbon core totals per year", () => {
    const zones = read("zones.json"); const ribbon = read("ribbon.json");
    const core = ribbon.geos.core400;
    core.years.forEach((y: string, i: number) => {
      const z = ["street_stores", "courthouse", "transit"].reduce((a, k) => a + CLASS_ORDER.reduce((b, c) => b + (zones.by_zone_year_class[k][y]?.[c] ?? 0), 0), 0);
      expect(z, y).toBe(core.all[i]);
    });
  });
  it.skipIf(!has)("ladder ranks are 2, 5, 15 and each step drops at least two places", () => {
    const l = read("ladder.json");
    expect([l.primary.all.rank, l.primary.no_officer.rank, l.primary.no_officer_no_retail.rank]).toEqual([2, 5, 15]);
    // the courthouse point alone is 172 of 438; without it the cell still sits in the top one percent
    expect(l.primary.no_courthouse.count).toBe(l.primary.all.count - 172);
    expect(l.primary.no_courthouse.rank).toBeGreaterThan(l.primary.all.rank);
    expect(l.primary.no_courthouse.rank).toBeLessThanOrEqual(Math.ceil(l.n_cells * 0.01));
    const ctx = read("context.json"); expect(ctx.cell.rank_no_courthouse).toBe(l.primary.no_courthouse.rank);
    expect(l.ladder_ok).toBe(true);
  });
  it.skipIf(!has)("grid per-resident rate and rank agree with density.json for this cell", () => {
    const g = read("grid.geojson"); const d = read("density.json");
    const me = g.features.find((f: any) => f.properties.cell_id === "40_42").properties;
    expect(me.rank_res).toBe(d.ranks.residents.rank);
    expect(me.rate_res).toBeCloseTo(d.ranks.residents.rate_per_1000_per_year, 1);
    expect(g.n_cells_rate_res).toBe(d.ranks.residents.n_cells);
    expect(g.features.filter((f: any) => f.properties.rate_res != null).length).toBe(g.n_cells_rate_res);
  });
  it.skipIf(!has)("density ranks exist and the count rank matches the ladder", () => {
    const d = read("density.json"); const l = read("ladder.json");
    expect(d.count_rank).toBe(l.primary.all.rank);
    for (const k of ["residents", "jobs", "residents_plus_jobs"]) expect(d.ranks[k].rank, k).toBeGreaterThan(0);
  });
  it.skipIf(!has)("citywide change by family brackets the total, on both bases", () => {
    const i = read("improvers.json");
    for (const [fam, tot] of [[i.city_change_by_family_pct, i.city.change_pct], [i.city_change_by_family_pct_raw, i.city.change_pct_raw]] as const) {
      const vals = [fam.robbery.change_pct, fam.felony_assault.change_pct, fam.homicide.change_pct];
      expect(tot).toBeGreaterThan(Math.min(...vals)); expect(tot).toBeLessThan(Math.max(...vals));
    }
  });
  it.skipIf(!has)("the stable-code basis removes codes, never adds them", () => {
    const i = read("improvers.json");
    expect(i.city.late).toBeLessThan(i.city.late_raw);
    expect(i.city.early_raw - i.city.early).toBeLessThan(10); // a handful of mis-dated rows at most: the codes did not exist in 2006
    expect(i.city_change_by_family_pct.felony_assault.change_pct).toBeLessThan(i.city_change_by_family_pct_raw.felony_assault.change_pct);
    expect(i.strangulation_2025).toBeGreaterThan(1000);
  });
  it.skipIf(!has)("named declines are single-year figures that also clear the windowed guard", () => {
    const i = read("improvers.json");
    for (const r of i.biggest_declines) {
      expect(r.early).toBeGreaterThanOrEqual(i.min_early);
      expect(r.change_pct).toBeCloseTo((r.late / r.early - 1) * 100, 0);
      expect(r.change_pct_windowed).toBeLessThanOrEqual(i.guard.decline_pct);
    }
    expect(i.biggest_declines[2].change_pct).toBeLessThanOrEqual(-60);
  });
  it("the data bundle zip holds the README and all four CSVs", async () => {
    const zipPath = join(__dirname, "../../../public/assets/hoyt-schermerhorn-crime-analysis-data.zip");
    if (!existsSync(zipPath)) return;
    const { execSync } = await import("node:child_process");
    const listing = execSync(`unzip -l "${zipPath}"`).toString();
    for (const f of ["README.md", "core-incidents.csv", "yearly-series.csv", "cell-ranking.csv", "dq-audit.csv"]) expect(listing, f).toContain(f);
    const readme = execSync(`unzip -p "${zipPath}" hoyt-schermerhorn-crime-analysis-data/README.md`).toString();
    expect(readme).toContain("A **complaint** is a crime reported to or recorded by the police");
    expect(readme).not.toContain("\u2014");
    expect(statSync(zipPath).size).toBeLessThan(25_000_000);
  });
  it.skipIf(!has)("concentration facts are coherent", () => {
    const c = read("improvers.json").concentration;
    expect(c.top20pct_share).toBeGreaterThan(0.5);
    expect(c.cells_for_half).toBeLessThan(c.top20pct_cells);
    expect(c.cells_for_20pct).toBeLessThan(c.cells_for_half);
    expect(c.cells_for_20pct_share_of_all).toBeCloseTo(c.cells_for_20pct / c.n_cells, 3);
    expect(c.threshold_count_half).toBeGreaterThanOrEqual(c.threshold_count_top20pct);
  });
  it.skipIf(!has)("the time-lapse month sums match its counts and every dot has a day and kind", () => {
    const t = read("timelapse.json");
    const violent = t.rows.filter((r: any) => CLASS_ORDER.includes(r.kind)).length;
    expect(violent).toBe(t.counts.violent);
    for (const r of t.rows) { expect(r.d).toBeGreaterThanOrEqual(1); expect(r.d).toBeLessThanOrEqual(t.days); expect(typeof r.kind).toBe("string"); }
  });
  it.skipIf(!has)("sankey flows sum to the total on both sides", () => {
    const s = read("sankey.json");
    const sum = s.flows.reduce((a: number, f: any) => a + f.n, 0);
    expect(sum).toBe(s.total);
    expect(s.places.reduce((a: number, p: any) => a + p.n, 0)).toBe(s.total);
  });
  it.skipIf(!has)("precinct polygons carry the same change figures as the summary", () => {
    const fc = read("precincts.geojson"); const p = read("precincts_1990.json");
    expect(fc.features.length).toBeGreaterThanOrEqual(76);
    const by = new Map(p.summary.map((r: any) => [r.precinct, r]));
    for (const f of fc.features) {
      const r: any = by.get(f.properties.precinct);
      if (r) expect(f.properties.change_pct, `precinct ${f.properties.precinct}`).toBe(r.change_pct);
    }
    const p84 = fc.features.find((f: any) => f.properties.precinct === 84);
    expect(p84.properties.change_pct).toBeLessThan(-70);
  });
  it.skipIf(!has)("precinct table covers at least 70 precincts and the 84th is present", () => {
    const p = read("precincts_1990.json");
    expect(p.n_precincts).toBeGreaterThanOrEqual(70);
    expect(p.precincts["84"].Robbery["1990"]).toBe(1908);
  });
  it.skipIf(!has)("clock shares sum to one and the core night share is below the city's", () => {
    const c = read("clock.json");
    for (const k of Object.keys(c.hour_share)) expect(Math.abs(c.hour_share[k].reduce((a: number, b: number) => a + b, 0) - 1)).toBeLessThan(0.01);
    expect(c.night.core400.share).toBeLessThan(c.night.city.share);
  });
  it.skipIf(!has)("dq has no failed gates and context matches headlines", () => {
    const dq = read("dq.json"); const ctx = read("context.json");
    expect(dq.summary.gates_failed).toBe(0);
    expect(ctx.cell.rank_all).toBe(dq.claims.claim_7.primary.value);
  });
  it.skipIf(!has)("every photo key in the content exists in imagery.json", () => {
    const keys = new Set(read("imagery.json").photos.map((p: any) => p.key));
    for (const m of content.matchAll(/<hs-photo photo="([a-z-]+)"/g)) expect(keys.has(m[1]), m[1]).toBe(true);
  });
});
