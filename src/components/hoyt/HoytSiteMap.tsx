// A small figure-ground map of the cell and its surroundings, drawn from the building footprints the pipeline
// already ships: the cell outline, the 400 m circle around the station, and the archetype sites,
// numbered. Pure SVG, no WebGL, so it can sit inside every ledger card and in the static render.
// focus = a stop id to highlight (the ledger minimap) or "all" (the index map after the month).
import { useEffect, useState } from "react";
import { CELL_BOUNDS, CELL_ID, COBALT, CORE, SITES, STEEL, type StopsFile } from "@/config/hoytSchermerhorn";
import { loadHoyt, useHoytData } from "./hoytData";
import { Card, Eyebrow } from "./HoytChrome";

const BBOX = { west: -73.9925, east: -73.9805, south: 40.6865, north: 40.6935 };
const M_PER_DEG_LAT = 111_320; const M_PER_DEG_LON = 111_320 * Math.cos((40.69 * Math.PI) / 180);
let footprintsCache: GeoJSON.FeatureCollection | null = null;

function useFootprints(): GeoJSON.FeatureCollection | null {
  const [fp, setFp] = useState<GeoJSON.FeatureCollection | null>(footprintsCache);
  useEffect(() => { if (fp) return; loadHoyt<GeoJSON.FeatureCollection>("footprints").then((f) => { footprintsCache = f; setFp(f); }).catch(() => {}); }, [fp]);
  return fp;
}

export function HoytSiteMap({ focus = "all", size = "index" }: { focus?: string; size?: "index" | "mini" }) {
  const fp = useFootprints();
  const { data: stops } = useHoytData<StopsFile>("stops");
  const W = size === "mini" ? 260 : 760; const H = Math.round(W * ((BBOX.north - BBOX.south) * M_PER_DEG_LAT) / ((BBOX.east - BBOX.west) * M_PER_DEG_LON));
  const x = (lon: number) => ((lon - BBOX.west) / (BBOX.east - BBOX.west)) * W;
  const y = (lat: number) => ((BBOX.north - lat) / (BBOX.north - BBOX.south)) * H;
  const ring = (coords: number[][]) => coords.map(([lon, lat], i) => `${i ? "L" : "M"}${x(lon).toFixed(1)},${y(lat).toFixed(1)}`).join("") + "Z";
  const paths: string[] = [];
  for (const f of fp?.features ?? []) {
    const g = f.geometry as GeoJSON.Polygon | GeoJSON.MultiPolygon;
    const polys = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
    for (const poly of polys) paths.push(poly.map(ring).join(""));
  }
  const sites = SITES.map((s) => ({ ...s, stop: stops?.stops.find((t) => t.id === s.id) })).filter((s) => s.stop);
  const r400 = (400 / M_PER_DEG_LON / (BBOX.east - BBOX.west)) * W;
  const mini = size === "mini";
  const svg = (
    <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" role="img" aria-label={`Map of the cell and the ${sites.length} sites`}>
      <rect width={W} height={H} fill="#F6F7F8" />
      <path d={paths.join(" ")} fill="#DCDFE3" stroke="#ffffff" strokeWidth={0.4} />
      <circle cx={x(CORE[0])} cy={y(CORE[1])} r={r400} fill="none" stroke={STEEL} strokeWidth={mini ? 0.8 : 1} strokeDasharray="4 3" opacity={0.6} />
      <rect x={x(CELL_BOUNDS.west)} y={y(CELL_BOUNDS.north)} width={x(CELL_BOUNDS.east) - x(CELL_BOUNDS.west)} height={y(CELL_BOUNDS.south) - y(CELL_BOUNDS.north)} fill={COBALT} fillOpacity={0.05} stroke={COBALT} strokeWidth={mini ? 1.5 : 2.5} />
      {!mini && <text x={x(CELL_BOUNDS.west) + 8} y={y(CELL_BOUNDS.north) + 18} fontSize={13} fontFamily="Source Sans 3" fontWeight={700} fill={COBALT}>cell {CELL_ID}</text>}
      {!mini && <text x={x(CORE[0]) + r400 * 0.72} y={y(CORE[1]) + r400 * 0.72} fontSize={12} fontFamily="Source Sans 3" fill={STEEL}>400 m</text>}
      {sites.map((s) => {
        const on = focus === "all" || focus === s.id; const cx = x(s.stop!.lon), cy = y(s.stop!.lat); const R = mini ? (on ? 9 : 6) : 13;
        return (
          <g key={s.id}>
            {focus === s.id && <circle cx={cx} cy={cy} r={R + 7} fill="none" stroke={COBALT} strokeWidth={2} opacity={0.5} />}
            <circle cx={cx} cy={cy} r={R} fill={on ? COBALT : "#ffffff"} stroke={on ? "#ffffff" : STEEL} strokeWidth={1.5} />
            <text x={cx} y={cy + (mini ? 3.5 : 5)} fontSize={mini ? 10 : 14} fontFamily="Source Sans 3" fontWeight={700} textAnchor="middle" fill={on ? "#ffffff" : STEEL}>{s.n}</text>
            {!mini && <text x={cx + R + 6} y={cy + 5} fontSize={13} fontFamily="Source Sans 3" fontWeight={600} fill="#3B3B3B" stroke="#F6F7F8" strokeWidth={3} paintOrder="stroke">{s.name}</text>}
          </g>
        );
      })}
    </svg>
  );
  if (mini) return <div className="overflow-hidden rounded-lg ring-1 ring-slate-200">{svg}</div>;
  return (
    <Card className="not-prose my-8">
      <Eyebrow>The sites</Eyebrow>
      {svg}
      <div className="mt-2 font-sans text-xs text-steel">Blue square: the map cell. Dashed circle: 400 meters from the Hoyt-Schermerhorn station, the area the site figures below cover. Building footprints from NYC Open Data.</div>
    </Card>
  );
}
