export const STATE_NAMES: Record<string, string> = {
  AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California", CO: "Colorado", CT: "Connecticut",
  DE: "Delaware", DC: "District of Columbia", FL: "Florida", GA: "Georgia", HI: "Hawaii", ID: "Idaho", IL: "Illinois",
  IN: "Indiana", IA: "Iowa", KS: "Kansas", KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland",
  MA: "Massachusetts", MI: "Michigan", MN: "Minnesota", MS: "Mississippi", MO: "Missouri", MT: "Montana",
  NE: "Nebraska", NV: "Nevada", NH: "New Hampshire", NJ: "New Jersey", NM: "New Mexico", NY: "New York",
  NC: "North Carolina", ND: "North Dakota", OH: "Ohio", OK: "Oklahoma", OR: "Oregon", PA: "Pennsylvania",
  RI: "Rhode Island", SC: "South Carolina", SD: "South Dakota", TN: "Tennessee", TX: "Texas", UT: "Utah",
  VT: "Vermont", VA: "Virginia", WA: "Washington", WV: "West Virginia", WI: "Wisconsin", WY: "Wyoming",
};

export function slugify(s: string): string {
  return s
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function stateSlug(abbr: string): string {
  return slugify(STATE_NAMES[abbr] ?? abbr);
}

export const n0 = (v: number): string => Math.round(v).toLocaleString("en-US");
export const n1 = (v: number): string => v.toLocaleString("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
export const pct = (v: number, d = 1): string => `${(v * 100).toFixed(d)}%`;
export const pctPts = (v: number, d = 0): string => {
  const t = v.toFixed(d);
  if (/^-?0(\.0+)?$/.test(t)) return `0${d ? "." + "0".repeat(d) : ""}%`; // never "-0%"
  return `${v > 0 ? "+" : ""}${t}%`;
};
export const usd = (v: number): string => `$${n0(v)}`;

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
/** "2026-07-16" -> "July 16, 2026"; "2026-07" -> "July 2026". */
export function longDate(iso: string): string {
  const m = iso.match(/^(\d{4})-(\d{2})(?:-(\d{2}))?/);
  if (!m) return iso;
  const [, y, mo, d] = m;
  return d ? `${MONTHS[Number(mo) - 1]} ${Number(d)}, ${y}` : `${MONTHS[Number(mo) - 1]} ${y}`;
}

/** Oxford-comma list: ["a","b","c"] -> "a, b, and c". */
export function listJoin(items: string[]): string {
  if (items.length <= 1) return items.join("");
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n0(n)} ${n === 1 ? one : many}`;
}

/** Make slugs unique within a set by suffixing -2, -3 ... */
export function uniqueSlugs<T>(items: T[], key: (t: T) => string): Map<T, string> {
  const seen = new Map<string, number>();
  const out = new Map<T, string>();
  for (const it of items) {
    const base = key(it) || "item";
    const n = (seen.get(base) ?? 0) + 1;
    seen.set(base, n);
    out.set(it, n === 1 ? base : `${base}-${n}`);
  }
  return out;
}

/** "a"/"an" for the next word. */
export function article(word: string): string {
  return /^[aeiou]/i.test(word) ? `an ${word}` : `a ${word}`;
}
