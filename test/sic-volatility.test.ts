// Locks the swing exhibit (<sic-volatility>) to the pipeline: what the chart draws and says must equal what
// stage 07 computed, and no visible string may slip into jargon or a police gradient the data do not show.
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { CLASS_NAME, summarize, swingCopy, swingRows, type ClassKey } from "../src/components/sic/sicVolatilityModel";

const ents = JSON.parse(readFileSync("public/data/self-insurance-cost/ny_entities.json", "utf8"));
const models = JSON.parse(readFileSync("public/data/self-insurance-cost/models.json", "utf8"));
const vol = models.ny.volatility;
const { drawn, leftOut } = swingRows(ents.rows);
const S = summarize(drawn);

describe("swing exhibit", () => {
  it("draws the same governments stage 07 counted, class by class", () => {
    for (const k of Object.keys(CLASS_NAME) as ClassKey[]) {
      expect(S[k].self.n).toBe(vol.by_class[k].n_self);
      expect(S[k].covered.n).toBe(vol.by_class[k].n_covered);
    }
    expect(S.all.self.n).toBe(vol.n_self);
    expect(S.all.covered.n).toBe(vol.n_covered);
  });

  it("matches the typical worst year and swing stage 07 published", () => {
    expect(Math.abs((S.all.self.ratio ?? 0) - vol.max_over_mean_self)).toBeLessThan(0.01);
    expect(Math.abs((S.all.covered.ratio ?? 0) - vol.max_over_mean_covered)).toBeLessThan(0.01);
    expect(Math.abs((S.all.self.swing ?? 0) - vol.yoy_cv_self)).toBeLessThan(0.002);
    expect(Math.abs((S.all.covered.swing ?? 0) - vol.yoy_cv_covered)).toBeLessThan(0.002);
  });

  it("leaves out exactly the governments with a negative year", () => {
    expect(leftOut.map((q) => q.name).sort()).toEqual(vol.left_out.map((q: { entity_name: string }) => q.entity_name).sort());
    for (const r of drawn) {
      const s: (number | null)[] = ents.series[r.muni];
      expect(s.every((v) => v != null && v >= 0)).toBe(true);
      const vals = s as number[];
      const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
      expect(Math.abs(Math.max(...vals) / mean - r.ratio)).toBeLessThan(0.01);
    }
  });

  it("keeps the two swing estimates close enough to round together", () => {
    const h = (v: number) => Math.round(v * 2) / 2;
    expect(Math.abs(h(vol.matched_ratio) - h(vol.controlled_ratio))).toBeLessThanOrEqual(0.5);
  });

  it("writes copy in plain words", () => {
    const { sub, foot } = swingCopy(drawn, leftOut, vol);
    for (const t of [sub, foot]) {
      expect(t).not.toMatch(/—|median|\bCV\b|coefficient|standard deviation|police/i);
    }
    expect(foot).toContain(leftOut.length ? "is left out because its recorded cost fell below zero" : "Tap or hover");
  });
});
