// Derived data files for the programmatic data pages (src/data/dataPages/).
// Generated from committed sources; run as the first build step so they can't
// drift, and commit the outputs so the mirror and hosted builds have them.
//
//   public/data/data-center-restriction-cost/actions-rows.json
//       <- public/assets/data-center-restriction-cost-actions.csv (the download)
//   public/data/medicaid-counties-table.json
//       <- public/data/medicaid-counties.geojson (properties only; no geometry)
import { readFileSync, writeFileSync } from "node:fs";

function parseCsv(text: string): Record<string, string>[] {
  const lines = text.split(/\r?\n/).filter((l) => l.length && !l.startsWith("#"));
  const parseLine = (line: string): string[] => {
    const out: string[] = [];
    let cur = "";
    let q = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (q) {
        if (ch === '"' && line[i + 1] === '"') {
          cur += '"';
          i++;
        } else if (ch === '"') q = false;
        else cur += ch;
      } else if (ch === '"') q = true;
      else if (ch === ",") {
        out.push(cur);
        cur = "";
      } else cur += ch;
    }
    out.push(cur);
    return out;
  };
  // Re-join rows whose quoted fields span lines.
  const rows: string[][] = [];
  let buf = "";
  for (const line of lines) {
    buf = buf ? `${buf}\n${line}` : line;
    const quotes = (buf.match(/"/g) ?? []).length;
    if (quotes % 2 === 0) {
      rows.push(parseLine(buf));
      buf = "";
    }
  }
  const head = rows[0];
  return rows.slice(1).map((r) => Object.fromEntries(head.map((h, i) => [h, r[i] ?? ""])));
}

const csv = readFileSync("public/assets/data-center-restriction-cost-actions.csv", "utf8");
const rows = parseCsv(csv).map((r) => ({
  id: r.id, dataset: r.dataset, level: r.level, state: r.state, state_fips: r.state_fips, jurisdiction: r.jurisdiction,
  jurisdiction_type: r.jurisdiction_type, action_type: r.action_type, class: r.class, status: r.status, date: r.date,
  mw_threshold: r.mw_threshold, county_fips: r.county_fips, county_name: r.county_name, county_wide: r.county_wide,
  summary: r.summary, source_name: r.source_name, source_url: r.source_url, note: r.note,
}));
writeFileSync("public/data/data-center-restriction-cost/actions-rows.json", JSON.stringify(rows));
console.log(`[derive-data] ${rows.length} action rows -> public/data/data-center-restriction-cost/actions-rows.json`);

const gj = JSON.parse(readFileSync("public/data/medicaid-counties.geojson", "utf8")) as { features: { properties: Record<string, unknown> }[] };
const counties = gj.features.map((f) => {
  const p = f.properties;
  return {
    GEOID: p.GEOID, state_fips: p.state_fips, state_abbr: p.state_abbr, county_name: p.county_name, pov_pct: p.pov_pct,
    subject_count_strict: p.subject_count_strict, loss_exposure_strict: p.loss_exposure_strict, subject_rate: p.subject_rate,
    uninsured_below_138pct: p.uninsured_below_138pct, expansion: p.expansion,
    total_pop: p.total_pop, working_age_pop: p.working_age_pop,
  };
});
writeFileSync("public/data/medicaid-counties-table.json", JSON.stringify(counties));
console.log(`[derive-data] ${counties.length} county rows -> public/data/medicaid-counties-table.json`);
