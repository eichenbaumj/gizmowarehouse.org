// Every NYPD precinct as a choropleth of its change in violent crime (murder + robbery + felony assault),
// 1990 to 2025. Hover for the name and change; click to pin the precinct's numbers under the map. The
// 84th is outlined. Precincts created after 1990 have no change figure and draw in grey.
import { useEffect, useRef, useState, type CSSProperties } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { cartoStyleUrl, cartoTransformRequest } from "@/config/basemap";
import { COBALT, STEEL, type PrecinctsFile } from "@/config/hoytSchermerhorn";
import { loadHoyt, useHoytData, fmtInt } from "./hoytData";
import { Card, Eyebrow } from "./HoytChrome";

type Row = PrecinctsFile["summary"][number] & { borough?: string; neighborhoods?: string };
const ordinal = (n: number) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][Math.min(n % 10, 4)] ?? "th"}`;
const place = (r: { neighborhoods?: string | null; precinct: number }) => (r.neighborhoods ?? "").split(";")[0].trim() || `${ordinal(r.precinct)} Precinct`;

// Decline bands, deepest first. Same teal family as the city grid so the two maps read as one system.
export const BANDS: { max: number; color: string; label: string }[] = [
  { max: -80, color: "#002D38", label: "down 80% or more" },
  { max: -60, color: "#135F70", label: "down 60 to 80%" },
  { max: -40, color: "#28889E", label: "down 40 to 60%" },
  { max: -20, color: "#88BECA", label: "down 20 to 40%" },
  { max: Infinity, color: "#F3D9CC", label: "down less than 20%, or flat" },
];
const NO_DATA = "#E5E7EB";
const CITY_BOUNDS: [[number, number], [number, number]] = [[-74.26, 40.49], [-73.70, 40.92]];

export function HoytPrecinctMap() {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const { data } = useHoytData<PrecinctsFile>("precincts_1990");
  const [picked, setPicked] = useState<number | null>(null);
  const [hover, setHover] = useState<{ precinct: number; name: string; change: number | null; x: number; y: number } | null>(null);
  const rows = ((data?.summary ?? []) as Row[]);
  const sel = picked != null ? rows.find((r) => r.precinct === picked) ?? null : null;

  useEffect(() => {
    if (!box.current || mapRef.current) return;
    let cancelled = false;
    loadHoyt<GeoJSON.FeatureCollection>("precincts").then((fc) => {
      if (cancelled || !box.current || mapRef.current) return;
      const map = new maplibregl.Map({
        container: box.current, style: cartoStyleUrl("positron"), transformRequest: cartoTransformRequest, bounds: CITY_BOUNDS, fitBoundsOptions: { padding: 12 },
        attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false, touchPitch: false,
        cooperativeGestures: true, canvasContextAttributes: { preserveDrawingBuffer: true },
      } as any);
      mapRef.current = map;
      (window as any).__hoytPrecinctMap = map;
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.on("load", () => {
        map.addSource("hs-pct", { type: "geojson", data: fc as any, promoteId: "precinct" });
        const step: any = ["step", ["get", "change_pct"], BANDS[0].color];
        for (let i = 1; i < BANDS.length; i++) step.push(BANDS[i - 1].max, BANDS[i].color);
        const color: any = ["case", ["==", ["typeof", ["get", "change_pct"]], "number"], step, NO_DATA];
        map.addLayer({ id: "hs-pct-fill", type: "fill", source: "hs-pct", paint: { "fill-color": color, "fill-opacity": ["case", ["boolean", ["feature-state", "hover"], false], 1, 0.82] } });
        map.addLayer({ id: "hs-pct-line", type: "line", source: "hs-pct", paint: { "line-color": "#ffffff", "line-width": 0.8 } });
        map.addLayer({ id: "hs-pct-84", type: "line", source: "hs-pct", filter: ["==", ["get", "precinct"], 84], paint: { "line-color": COBALT, "line-width": 2.5 } });
        map.addLayer({ id: "hs-pct-pick", type: "line", source: "hs-pct", filter: ["==", ["get", "precinct"], -1], paint: { "line-color": "#3B3B3B", "line-width": 2.5 } });
        let hovered: number | null = null;
        map.on("mousemove", "hs-pct-fill", (e) => {
          const f = e.features?.[0]; if (!f) return;
          const id = Number(f.properties?.precinct);
          if (hovered != null && hovered !== id) map.setFeatureState({ source: "hs-pct", id: hovered }, { hover: false });
          map.setFeatureState({ source: "hs-pct", id }, { hover: true }); hovered = id;
          map.getCanvas().style.cursor = "pointer";
          setHover({ precinct: id, name: place(f.properties as any), change: typeof f.properties?.change_pct === "number" ? f.properties.change_pct : null, x: e.point.x, y: e.point.y });
        });
        map.on("mouseleave", "hs-pct-fill", () => {
          if (hovered != null) map.setFeatureState({ source: "hs-pct", id: hovered }, { hover: false });
          hovered = null; map.getCanvas().style.cursor = ""; setHover(null);
        });
        map.on("click", "hs-pct-fill", (e) => {
          const id = Number(e.features?.[0]?.properties?.precinct);
          setPicked((p) => (p === id ? null : id));
        });
      });
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const map = mapRef.current; if (!map || !map.getLayer("hs-pct-pick")) return;
    map.setFilter("hs-pct-pick", ["==", ["get", "precinct"], picked ?? -1]);
  }, [picked]);

  return (
    <Card className="not-prose my-8">
      <Eyebrow>Change in murder plus robbery plus felony assault, by precinct, 1990 to 2025</Eyebrow>
      <div className="relative h-[420px] w-full overflow-hidden rounded-xl bg-vellum md:h-[560px]">
        <div ref={box} className="absolute inset-0" />
        {hover && (
          <div className="pointer-events-none absolute z-10 rounded-md bg-white/95 px-2 py-1 font-sans text-xs text-charcoal shadow ring-1 ring-slate-200" style={{ left: hover.x + 12, top: hover.y + 12 } as CSSProperties}>
            <span className="font-semibold">{hover.name}</span> <span style={{ color: STEEL }}>{ordinal(hover.precinct)} Pct</span>
            {hover.change != null ? <span> · {Math.round(hover.change)}%</span> : <span style={{ color: STEEL }}> · created after 1990</span>}
          </div>
        )}
        <div className="absolute bottom-3 left-3 z-10 rounded-xl bg-white/95 px-3 py-2 shadow ring-1 ring-slate-200 font-sans text-xs text-charcoal">
          {BANDS.map((b) => <div key={b.label} className="flex items-center gap-2"><span className="inline-block h-3 w-3 rounded-sm" style={{ background: b.color }} /> {b.label}</div>)}
          <div className="flex items-center gap-2"><span className="inline-block h-3 w-3 rounded-sm" style={{ background: NO_DATA }} /> created after 1990</div>
          <div className="mt-1 flex items-center gap-2"><span className="inline-block h-0 w-3 border-t-2" style={{ borderColor: COBALT }} /> the 84th</div>
        </div>
      </div>
      <div className="mt-2 min-h-[2.5rem] font-sans text-sm text-charcoal">
        {sel ? (
          <div className="flex flex-wrap items-baseline gap-x-2 rounded-md bg-vellum px-3 py-1.5">
            <span className="font-serif text-base font-bold text-cobalt">{place(sel)}</span>
            <span className="text-xs text-steel">{sel.borough}, {ordinal(sel.precinct)} Precinct</span>
            {sel.change_pct != null ? (
              <span>{fmtInt(sel.violent_1990)} in 1990, {fmtInt(sel.violent_2025)} in 2025 ({Math.round(sel.change_pct)}%). Robbery {Math.round(sel.robbery_change_pct ?? 0)}%, felony assault {sel.fel_assault_change_pct != null && sel.fel_assault_change_pct > 0 ? "+" : ""}{Math.round(sel.fel_assault_change_pct ?? 0)}%, murders {sel.murder_1990} to {sel.murder_2025}.</span>
            ) : <span>Created after 1990, so no comparison.</span>}
            <button className="text-xs font-semibold text-cobalt" onClick={() => setPicked(null)}>clear</button>
          </div>
        ) : <div className="px-1 text-xs text-steel">Hover a precinct for its change; click to pin its numbers. Hold Ctrl (or ⌘) and scroll to zoom. The 84th is outlined in blue.</div>}
      </div>
      <div className="mt-2 font-sans text-xs text-steel">Murder, robbery and felony assault, NYPD CompStat historical tables. {rows.filter((r) => r.change_pct != null).length} precincts have a 1990 line; the 33rd, 116th and 121st were created after 1990. Neighborhood names are approximate.</div>
    </Card>
  );
}
