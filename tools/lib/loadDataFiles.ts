// Reads every file the data-page datasets need from public/, keyed by URL.
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { DATASETS } from "../../src/data/dataPages";

export function loadDataFiles(): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const spec of DATASETS) {
    for (const url of spec.files) {
      const file = path.join("public", url);
      if (!existsSync(file)) {
        console.warn(`[dataPages] ${spec.id}: missing ${file} (run npm run derive-data?)`);
        continue;
      }
      out[url] = JSON.parse(readFileSync(file, "utf8"));
    }
  }
  return out;
}
