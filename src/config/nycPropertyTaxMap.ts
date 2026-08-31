// Configuration for the NYC Property Tax interactive map (v2).
//
// Two-source architecture:
//   - NTA aggregates (262 polygons, ~few MB GeoJSON in /public/data/) for low-zoom
//   - Parcels (~860k polygons, ~150-250 MB PMTiles on R2) for high-zoom
//
// Zoom crossfade z=11..13 fades NTAs out and parcels in, mirroring the
// national-poverty-explorer pattern. Initial paint at z=11 is fast (262
// features) instead of slow (856k parcels rendered globally).
//
// Data is hosted on Cloudflare R2 (bucket: gizmo-warehouse-data) and served
// through the custom domain `data.gizmowarehouse.org`. We DO NOT use the bucket's
// `pub-*.r2.dev` URL because OpenDNS / Cisco Umbrella / Quad9 / many corporate
// DNS resolvers selectively block individual `*.r2.dev` hostnames as suspected
// abuse vectors, returning a self-signed block-page cert that browsers reject
// (net::ERR_CERT_AUTHORITY_INVALID). The custom domain on a Joe-owned zone
// dodges that classification entirely. Pattern documented in tools/HOSTING_DATA.md.

export const NYC_TAX_MAP_CONFIG = {
  // Citywide centerpoint (lower Manhattan / midtown junction). At zoom 11
  // the NTA layer paints all 5 boros in <1s.
  // Default view: Lower Manhattan + Brooklyn waterfront at zoom 12. Drops
  // the user into a zoom level where parcel-by-parcel variation is already
  // visible — the city-scale view at zoom 11 reads as a uniform mass.
  center: [-74.005, 40.7] as [number, number],
  zoom: 12,
  minZoom: 9,
  maxZoom: 17,
  bounds: [
    [-74.27, 40.49],
    [-73.68, 40.92],
  ] as [[number, number], [number, number]],

  // Sources hosted on Cloudflare R2 (bucket gizmo-warehouse-data), served via
  // the custom domain data.gizmowarehouse.org. See header comment for why.
  // Bump ?v= on the pmtiles whenever the citywide rebuild runs (immutable
  // cache header on R2 keeps stale tiles otherwise).
  ntaGeoJsonUrl: "https://data.gizmowarehouse.org/nyc-property-tax/nta-aggregates.geojson",
  parcelsPmtilesUrl: "https://data.gizmowarehouse.org/nyc-property-tax/parcels.pmtiles?v=7",
  parcelsSourceLayer: "parcels",
  parcelsManifestUrl: null as string | null,
  statsUrl: "https://data.gizmowarehouse.org/nyc-property-tax/stats.json",
  classMediansUrl: "https://data.gizmowarehouse.org/nyc-property-tax/class-medians.json",

  // Layer visibility / opacity by zoom. Crossfade z=11..13 fades NTA out
  // as parcels fade in.
  ntaOpacityStops: [9, 0.85, 10, 0.85, 11, 0.55, 12, 0.0] as number[],
  parcelOpacityStops: [11, 0.0, 12, 0.65, 13, 0.85, 15, 0.85] as number[],
  ntaMaxZoom: 12, // hide NTAs above this
  parcelMinZoom: 11, // show parcels at this and above

  // Render modes. Five total. Each maps a property to a fill color and
  // describes the legend label, unit, and color stops. Default = $/sqft
  // (the clearest story per Joe's first-look review).
  modes: {
    tax_per_sqft: {
      label: "Tax per square foot",
      property: "tax_per_sqft",
      ntaProperty: "median_tax_per_sqft",
      legendUnit: "$/sqft/yr",
      // Sequential single-hue: pale → deep cobalt as $/sqft rises.
      // Brooklyn brownstones land in the $1-$3 range; Class 4 commercial
      // is $10-$30; Manhattan office can be $40+.
      stops: [
        [0, "#F2F2F2"],
        [2, "#D6E4F2"],
        [5, "#7B9BE0"],
        [10, "#1F1FD6"],
        [25, "#0A0A8A"],
      ] as [number, string][],
      // Tighter stops for NTA-aggregate rendering at low zoom — NTA medians
      // cluster in $1-$8 range, so the parcel-scale stops would wash out.
      ntaStops: [
        [0, "#F2F2F2"],
        [1, "#D6E4F2"],
        [3, "#7B9BE0"],
        [6, "#1F1FD6"],
        [12, "#0A0A8A"],
      ] as [number, string][],
    },
    market_value: {
      label: "DOF market value",
      property: "market_value",
      ntaProperty: "median_market_value",
      legendUnit: "USD",
      stops: [
        [0, "#F2F2F2"],
        [500_000, "#D6E4F2"],
        [2_000_000, "#7B9BE0"],
        [10_000_000, "#1F1FD6"],
        [50_000_000, "#0A0A8A"],
      ] as [number, string][],
      ntaStops: [
        [0, "#F2F2F2"],
        [300_000, "#D6E4F2"],
        [1_000_000, "#7B9BE0"],
        [3_000_000, "#1F1FD6"],
        [10_000_000, "#0A0A8A"],
      ] as [number, string][],
    },
    etr_vs_citywide: {
      label: "Tax rate vs NYC median",
      property: "etr",            // raw ETR; client computes vs citywide median
      ntaProperty: "median_etr",
      legendUnit: "× median",
      // Diverging cobalt ↔ amber. Below the citywide median = under-paying
      // (cool); above = over-paying (warm).
      stops: [
        [-0.7, "#1F1FD6"],
        [-0.3, "#7B9BE0"],
        [-0.1, "#D6E4F2"],
        [0.0, "#F2F2F2"],
        [0.1, "#F2D9A8"],
        [0.4, "#E69138"],
        [1.0, "#B45309"],
      ] as [number, string][],
      // Tighter diverging stops for NTA-aggregate rendering — NTA-median
      // ETRs cluster in a narrower band than parcel-level ETRs, so the
      // parcel-scale stops leave most NTAs in the pale center.
      ntaStops: [
        [-0.5, "#1F1FD6"],
        [-0.25, "#7B9BE0"],
        [-0.10, "#D6E4F2"],
        [0.0, "#F2F2F2"],
        [0.10, "#F2D9A8"],
        [0.25, "#E69138"],
        [0.50, "#B45309"],
      ] as [number, string][],
      // For this mode: paint expression is `(etr / citywide_median - 1)`.
      diverging: "citywide" as const,
    },
    etr_vs_class: {
      label: "Tax rate vs similar buildings",
      property: "etr",
      ntaProperty: null,           // NTA aggregate isn't class-stratified
      legendUnit: "× class median",
      stops: [
        [-0.7, "#1F1FD6"],
        [-0.3, "#7B9BE0"],
        [-0.1, "#D6E4F2"],
        [0.0, "#F2F2F2"],
        [0.1, "#F2D9A8"],
        [0.4, "#E69138"],
        [1.0, "#B45309"],
      ] as [number, string][],
      // Paint expression: `(etr / class_median[tax_class] - 1)`.
      diverging: "class" as const,
    },
    abatement: {
      label: "Abatement intensity",
      property: "exempt_fraction",
      ntaProperty: "median_exempt_fraction",
      legendUnit: "% exempt",
      // Sequential, distinct from the cobalt/amber ETR ramps to avoid
      // visual collision. Pale neutral → deep teal as exemption climbs.
      stops: [
        [0, "#F2F2F2"],
        [0.1, "#A7D9CE"],
        [0.3, "#5BB1A1"],
        [0.6, "#1F8579"],
        [0.95, "#0A4A40"],
      ] as [number, string][],
      ntaStops: [
        [0, "#F2F2F2"],
        [0.05, "#A7D9CE"],
        [0.15, "#5BB1A1"],
        [0.30, "#1F8579"],
        [0.60, "#0A4A40"],
      ] as [number, string][],
    },
  } as const,

  defaultMode: "tax_per_sqft" as const,

  // Hide flagged parcels by default.
  hideFlags: ["no_pvad_match", "no_market_value"] as string[],
};

export type NycTaxMapMode = keyof typeof NYC_TAX_MAP_CONFIG.modes;
