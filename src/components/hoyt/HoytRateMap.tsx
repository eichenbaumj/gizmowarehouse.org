// The whole city by violent complaints per 1,000 residents per year (2024 to 2025), cells with at least
// 500 residents. A different picture from the count map: this is where living next to it is most common.
// Hover a cell for its rate and rank; this piece's cell is outlined. Ctrl/Cmd + scroll zooms.
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { cartoStyleUrl, cartoTransformRequest, CARTO_ATTRIBUTION } from "@/config/basemap";
import { CELL_ID, COBALT, STEEL } from "@/config/hoytSchermerhorn";
import { loadHoyt, fmtInt } from "./hoytData";
import { Card, Eyebrow } from "./HoytChrome";

const RAMP = ["#D2E6EB", "#88BECA", "#28889E", "#135F70", "#002D38"];
const NO_DATA = "#EEF0F2";
const CITY_BOUNDS: [[number, number], [number, number]] = [[-74.26, 40.49], [-73.70, 40.92]];
type GridFC = GeoJSON.FeatureCollection & { n_cells_rate_res?: number; min_residents?: number };

function quantile(sorted: number[], q: number): number { return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * q))]; }

export function HoytRateMap() {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [grid, setGrid] = useState<GridFC | null>(null);
  const [hover, setHover] = useState<{ name: string; rate: number | null; rank: number | null; residents: number; x: number; y: number } | null>(null);
  // Breaks at the median, 75th, 90th and 97th percentiles of eligible cells, so the top band is the top few percent.
  const breaks = useMemo(() => {
    if (!grid) return null;
    const r = grid.features.map((f) => f.properties?.rate_res).filter((v): v is number => typeof v === "number").sort((a, b) => a - b);
    return [quantile(r, 0.5), quantile(r, 0.75), quantile(r, 0.9), quantile(r, 0.97)];
  }, [grid]);
  const me = grid?.features.find((f) => f.properties?.cell_id === CELL_ID)?.properties;

  useEffect(() => {
    if (!box.current || mapRef.current) return;
    let cancelled = false;
    loadHoyt<GridFC>("grid").then((g) => {
      if (cancelled || !box.current || mapRef.current) return;
      setGrid(g);
      const r = g.features.map((f) => f.properties?.rate_res).filter((v): v is number => typeof v === "number").sort((a, b) => a - b);
      const br = [quantile(r, 0.5), quantile(r, 0.75), quantile(r, 0.9), quantile(r, 0.97)];
      const map = new maplibregl.Map({
        container: box.current, style: cartoStyleUrl("positron"), transformRequest: cartoTransformRequest, bounds: CITY_BOUNDS, fitBoundsOptions: { padding: 12 },
        attributionControl: { compact: true, customAttribution: CARTO_ATTRIBUTION }, dragRotate: false, pitchWithRotate: false, touchPitch: false,
        cooperativeGestures: true, canvasContextAttributes: { preserveDrawingBuffer: true },
      } as any);
      mapRef.current = map;
      (window as any).__hoytRateMap = map;
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.on("load", () => {
        const firstSymbol = (map.getStyle().layers ?? []).find((l) => l.type === "symbol")?.id;
        map.addSource("hs-rate", { type: "geojson", data: g as any, promoteId: "cell_id" });
        const color: any = ["case", ["==", ["typeof", ["get", "rate_res"]], "number"],
          ["step", ["get", "rate_res"], RAMP[0], br[0], RAMP[1], br[1], RAMP[2], br[2], RAMP[3], br[3], RAMP[4]], NO_DATA];
        map.addLayer({ id: "hs-rate-fill", type: "fill", source: "hs-rate", paint: { "fill-color": color, "fill-opacity": ["case", ["==", ["typeof", ["get", "rate_res"]], "number"], 0.85, 0.5] } }, firstSymbol);
        map.addLayer({ id: "hs-rate-line", type: "line", source: "hs-rate", paint: { "line-color": "#ffffff", "line-width": 0.4, "line-opacity": 0.6 } }, firstSymbol);
        map.addLayer({ id: "hs-rate-me", type: "line", source: "hs-rate", filter: ["==", ["get", "cell_id"], CELL_ID], paint: { "line-color": COBALT, "line-width": 3 } });
        map.on("mousemove", "hs-rate-fill", (e) => {
          const f = e.features?.[0]; if (!f) return;
          map.getCanvas().style.cursor = "crosshair";
          setHover({ name: String(f.properties?.name ?? f.properties?.cell_id), rate: typeof f.properties?.rate_res === "number" ? f.properties.rate_res : null,
            rank: typeof f.properties?.rank_res === "number" ? f.properties.rank_res : null, residents: Number(f.properties?.residents ?? 0), x: e.point.x, y: e.point.y });
        });
        map.on("mouseleave", "hs-rate-fill", () => { map.getCanvas().style.cursor = ""; setHover(null); });
      });
    });
    return () => { cancelled = true; };
  }, []);

  const nEl = grid?.n_cells_rate_res ?? 0; const minPop = grid?.min_residents ?? 500;
  const fmtRate = (v: number) => (v < 10 ? v.toFixed(1) : Math.round(v).toString());
  return (
    <Card className="not-prose my-8">
      <Eyebrow>Violent complaints per 1,000 residents per year, 2024 to 2025, cells with {minPop}+ residents</Eyebrow>
      <div className="relative h-[420px] w-full overflow-hidden rounded-xl bg-vellum md:h-[560px]">
        <div ref={box} className="absolute inset-0" />
        {hover && (
          <div className="pointer-events-none absolute z-10 rounded-md bg-white/95 px-2 py-1 font-sans text-xs text-charcoal shadow ring-1 ring-slate-200" style={{ left: hover.x + 12, top: hover.y + 12 } as CSSProperties}>
            <span className="font-semibold">{hover.name}</span>
            {hover.rate != null ? <span> · {fmtRate(hover.rate)} per 1,000 a year · #{hover.rank} of {fmtInt(nEl)}</span> : <span style={{ color: STEEL }}> · under {minPop} residents ({fmtInt(hover.residents)})</span>}
          </div>
        )}
        {breaks && (
          <div className="absolute bottom-3 left-3 z-10 rounded-xl bg-white/95 px-3 py-2 shadow ring-1 ring-slate-200 font-sans text-xs text-charcoal">
            <div className="mb-1 font-semibold">Per 1,000 residents a year</div>
            {[`under ${fmtRate(breaks[0])}`, `${fmtRate(breaks[0])} to ${fmtRate(breaks[1])}`, `${fmtRate(breaks[1])} to ${fmtRate(breaks[2])}`, `${fmtRate(breaks[2])} to ${fmtRate(breaks[3])}`, `${fmtRate(breaks[3])} and up (top 3%)`].map((l, i) => (
              <div key={l} className="flex items-center gap-2"><span className="inline-block h-3 w-3 rounded-sm" style={{ background: RAMP[i] }} /> {l}</div>
            ))}
            <div className="flex items-center gap-2"><span className="inline-block h-3 w-3 rounded-sm" style={{ background: NO_DATA }} /> under {minPop} residents</div>
            <div className="mt-1 flex items-center gap-2"><span className="inline-block h-0 w-3 border-t-2" style={{ borderColor: COBALT }} /> this piece's cell</div>
          </div>
        )}
      </div>
      <div className="mt-2 font-sans text-sm text-charcoal">
        {me && typeof me.rate_res === "number" ? <>Outlined: <b>{fmtRate(me.rate_res)}</b> violent complaints per 1,000 residents a year, <b>#{me.rank_res}</b> of {fmtInt(nEl)} cells with {minPop}+ residents. Hover any cell; hold Ctrl (or ⌘) and scroll to zoom.</> : <>Hover any cell; hold Ctrl (or ⌘) and scroll to zoom.</>}
      </div>
      <div className="mt-1 font-sans text-xs text-steel">Residents from the 2020 Census by block, apportioned to cells. Cells under {minPop} residents are left grey so empty commercial land cannot post a rate.</div>
    </Card>
  );
}
