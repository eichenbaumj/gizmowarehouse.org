// The one place that knows about CARTO basemaps.
//
// CARTO key-enforces its free basemaps (raster since 2026-08-26, vector
// announced). Keyless raster tiles come back with an "API KEY REQUIRED"
// watermark. The key below is CARTO's free public basemaps key, meant to sit
// in client code; the same key runs across the 17A / CPAL map fleet.
//
// Two layers of protection:
//   1. URL builders bake the key into raster tile templates and style URLs.
//   2. cartoTransformRequest, passed to every `new maplibregl.Map`, keys any
//      *.basemaps.cartocdn.com request MapLibre makes. That matters for hosted
//      vector styles: a ?key= on style.json does NOT propagate to the TileJSON,
//      .mvt tiles, sprite, and glyph requests the style fans out to (verified
//      2026-09-21: style.json is byte-identical keyed vs keyless).
//
// tools/check-basemap-key.ts fails the build if the CARTO host or the key
// literal appear anywhere else under src/, or if a MapLibre constructor skips
// the transform. Keep this module side-effect-free with a type-only maplibre
// import: the guard loads it in node.

import type { RequestTransformFunction } from "maplibre-gl";

export const CARTO_BASEMAP_KEY = "cb1_271o_1_f779989250ccc009272193f4";

export const CARTO_ATTRIBUTION =
  '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>';

export type CartoRasterVariant =
  | "voyager"
  | "voyager_nolabels"
  | "voyager_only_labels"
  | "light_all"
  | "light_nolabels"
  | "light_only_labels"
  | "dark_all"
  | "dark_nolabels"
  | "dark_only_labels";

export type CartoGlStyle = "voyager" | "positron" | "dark-matter";

const CARTO_HOST = "basemaps.cartocdn.com";

/** Append the key as ?key= (or &key=) unless a key= parameter is already present. */
export function withCartoKey(url: string): string {
  if (/[?&]key=/.test(url)) return url;
  return `${url}${url.includes("?") ? "&" : "?"}key=${CARTO_BASEMAP_KEY}`;
}

/** Four-subdomain raster tile templates for a MapLibre raster source. */
export function cartoRasterTiles(variant: CartoRasterVariant): string[] {
  return ["a", "b", "c", "d"].map((s) =>
    withCartoKey(`https://${s}.${CARTO_HOST}/rastertiles/${variant}/{z}/{x}/{y}.png`),
  );
}

/**
 * Hosted vector style URL. The key here is cosmetic today (CARTO serves the
 * same JSON either way); cartoTransformRequest is what keys the child requests.
 */
export function cartoStyleUrl(style: CartoGlStyle): string {
  return withCartoKey(`https://${CARTO_HOST}/gl/${style}-gl-style/style.json`);
}

function isCartoHost(url: string): boolean {
  // Anchored to absolute http(s) so pmtiles://…, relative /data/… paths, and
  // anything else fall through untouched. String ops only: `new URL` throws on
  // relative input and re-serializes glyph URLs that carry raw spaces/commas.
  const m = /^https?:\/\/([^/?#]+)/i.exec(url);
  if (!m) return false;
  const host = m[1].toLowerCase();
  return host === CARTO_HOST || host.endsWith(`.${CARTO_HOST}`);
}

/**
 * MapLibre `transformRequest`: keys every CARTO basemap request (style JSON,
 * TileJSON, tiles, sprite, glyphs) and passes every other request through
 * unchanged. Returning undefined is MapLibre's documented "no change".
 */
export const cartoTransformRequest: RequestTransformFunction = (url) => {
  if (!isCartoHost(url)) return undefined;
  const keyed = withCartoKey(url);
  return keyed === url ? undefined : { url: keyed };
};
