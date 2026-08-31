// Simple {tokenName} substitution in markdown content. Used by GizmoPage to
// inject values from a gizmo's baked data context into the prose without
// hardcoding the figures.
//
// Tokens use the form {tokenName} or {tokenName:format} where format is one
// of: "M" (millions, 1 decimal), "K" (thousands, no decimal), "%" (percent),
// "n" (raw integer with thousands separators), or "raw" (no formatting).
// Default format when omitted is "n".
//
// Lookup path: nested keys via dot notation. `{national.subject_count_strict:M}`
// resolves to `context.national.subject_count_strict` formatted as "18.5M".

export type TokenContext = Record<string, any>;

const TOKEN_RE = /\{([a-zA-Z0-9_.]+)(?::([a-zA-Z%]+))?\}/g;

function lookup(ctx: TokenContext, path: string): any {
  return path.split(".").reduce<any>((acc, key) => {
    if (acc == null) return undefined;
    return acc[key];
  }, ctx);
}

function formatValue(value: any, format: string): string {
  if (value == null) return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) {
    return String(value);
  }
  switch (format) {
    case "M":
      return (n / 1_000_000).toFixed(n < 10_000_000 ? 1 : 0) + " million";
    case "M_compact":
      return (n / 1_000_000).toFixed(1) + "M";
    case "K":
      return Math.round(n / 1000).toLocaleString("en-US") + "K";
    case "%":
      return (n * 100).toFixed(1) + "%";
    case "%0":
      return Math.round(n * 100) + "%";
    case "raw":
      return String(value);
    case "n":
    default:
      return Math.round(n).toLocaleString("en-US");
  }
}

export function interpolateTokens(markdown: string, ctx: TokenContext | null | undefined): string {
  if (!ctx) return markdown;
  return markdown.replace(TOKEN_RE, (full, path, fmt) => {
    const v = lookup(ctx, path);
    if (v === undefined) return full; // leave unresolved tokens alone
    return formatValue(v, fmt ?? "n");
  });
}
