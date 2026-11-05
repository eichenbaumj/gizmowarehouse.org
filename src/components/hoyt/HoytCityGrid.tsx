// The citywide grid of 0.33-mile cells, interactive (pan, zoom with ctrl+scroll, hover for name and count), as the sticky
// stage of the "city" scrolly. Steps: all | top20 (keeps the cells holding half) | improvers | precinct | dive. The teal three-shade ramp and the
// 65/25/10 calibration mirror multi-city-crime-explorer/src/components/CrimeExplorer/layers/palette.ts.
import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { cartoStyleUrl, cartoTransformRequest, CARTO_ATTRIBUTION } from "@/config/basemap";
import { CELL_ID, CLASS_STYLE, TIMES_SQUARE_CELL, type ImproversFile } from "@/config/hoytSchermerhorn";
import { loadHoyt, useHoytData, fmtInt } from "./hoytData";
import { useStage } from "./HoytScrolly";
import { HoytCaveatChip } from "./HoytChrome";

const RAMP = ["#88BECA", "#28889E", "#002D38"];
const OPAC = [0.6, 0.7, 0.8];
const OUTLINE = { color: "#88BECA", width: 0.6, opacity: 0.4 };
const LADDER = [2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 75, 100, 125, 150, 200, 250, 300, 400, 500, 750, 1000];
const CITY: [number, number] = [-73.93, 40.72];
const DOWNTOWN: [number, number] = [-73.9868, 40.6905];
const PRECINCT84: [number, number] = [-73.991, 40.6936];

function calibrate(counts: number[]): [number, number] {
  const occ = counts.filter((c) => c > 0).sort((a, b) => a - b);
  if (occ.length < 10) return [2, 3];
  const q = (f: number) => occ[Math.min(occ.length - 1, Math.floor(occ.length * f))];
  const snap = (v: number) => LADDER.reduce((best, x) => (Math.abs(x - v) < Math.abs(best - v) ? x : best), LADDER[0]);
  const t1 = snap(q(0.65)); let t2 = snap(q(0.9));
  if (t2 <= t1) t2 = LADDER[Math.min(LADDER.length - 1, LADDER.indexOf(t1) + 1)];
  return [t1, t2];
}

export function HoytCityGrid({ mode = "stage" }: { mode?: "stage" | "explore" }) {
  const explore = mode === "explore";
  const box = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const [ready, setReady] = useState(false);
  const [scale, setScale] = useState<[number, number]>([2, 3]);
  const [hover, setHover] = useState<{ name: string; count: number; rank: number } | null>(null);
  const [pinned, setPinned] = useState<{ name: string; count: number; rank: number; cell_id: string } | null>(null);
  const [zoomArmed, setZoomArmed] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(0);
  const { activeStep, reducedMotion } = useStage();
  const { data: improvers } = useHoytData<ImproversFile>("improvers");
  const gridRef = useRef<GeoJSON.FeatureCollection | null>(null);
  const firstSymbolRef = useRef<string | undefined>(undefined);
  const stagePointsRef = useRef<"idle" | "loading" | "ready">("idle");

  useEffect(() => {
    let cancelled = false;
    loadHoyt<GeoJSON.FeatureCollection>("grid").then((grid) => {
      if (cancelled || !box.current || mapRef.current) return;
      gridRef.current = grid;
      const counts = grid.features.map((f) => Number(f.properties?.count_2024_25 ?? 0));
      const sc = calibrate(counts);
      setScale(sc);
      const map = new maplibregl.Map({
        container: box.current, style: cartoStyleUrl("positron"), transformRequest: cartoTransformRequest, center: explore ? DOWNTOWN : CITY, zoom: explore ? 11.2 : 9.8,
        attributionControl: { compact: true, customAttribution: CARTO_ATTRIBUTION }, interactive: explore, dragRotate: false, pitchWithRotate: false, touchPitch: false,
        canvasContextAttributes: { preserveDrawingBuffer: true },
      } as any);
      mapRef.current = map;
      (window as any)[explore ? "__hoytCityExplore" : "__hoytCityGrid"] = map;
      if (explore) {
        map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
        map.scrollZoom.disable();
        const el = box.current;
        // Wheel zooms only while the pointer is over the map, so reading past it still scrolls the page.
        el.addEventListener("mouseenter", () => { map.scrollZoom.enable(); setZoomArmed(true); });
        el.addEventListener("mouseleave", () => { map.scrollZoom.disable(); setZoomArmed(false); });
        // Individual complaints appear once the reader is closer than the cell scale.
        let pointsLoaded = false;
        const base0: any = ["step", ["get", "count_2024_25"], 0, 1, OPAC[0], sc[0], OPAC[1], sc[1], OPAC[2]];
        const ensurePoints = () => {
          if (pointsLoaded || map.getZoom() < 13) return;
          pointsLoaded = true;
          loadHoyt<{ classes: string[]; p: [number, number, number][] }>("points_2024_25").then((pts) => {
            // NYPD rounds every complaint to a midblock or intersection, so identical coordinates stack. One
            // dot per point, sized by how many complaints sit on it, or 438 complaints look like 30 dots.
            const agg = new Map<string, { lon: number; lat: number; n: number; byCls: number[] }>();
            for (const [lon, lat, c] of pts.p) {
              const k = `${lon},${lat}`; let a = agg.get(k);
              if (!a) { a = { lon, lat, n: 0, byCls: new Array(pts.classes.length).fill(0) }; agg.set(k, a); }
              a.n += 1; a.byCls[c] += 1;
            }
            const features = [...agg.values()].sort((a, b) => b.n - a.n).map((a) => ({ type: "Feature", geometry: { type: "Point", coordinates: [a.lon, a.lat] },
              properties: { n: a.n, color: (CLASS_STYLE as any)[pts.classes[a.byCls.indexOf(Math.max(...a.byCls))]]?.color ?? "#3B3B3B" } }));
            if (map.getSource("hs-pts")) return;
            map.addSource("hs-pts", { type: "geojson", data: { type: "FeatureCollection", features } as any });
            const r = (k: number): any => ["*", k, ["sqrt", ["get", "n"]]];
            map.addLayer({ id: "hs-pts", type: "circle", source: "hs-pts", minzoom: 13.5, paint: {
              "circle-radius": ["interpolate", ["linear"], ["zoom"], 13.5, r(1.6), 15.5, r(3), 17, r(4.5)], "circle-color": ["get", "color"], "circle-opacity": 0.8,
              "circle-stroke-color": "#ffffff", "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 13.5, 0.5, 16, 1] } });
            map.addLayer({ id: "hs-pts-n", type: "symbol", source: "hs-pts", minzoom: 15, filter: [">=", ["get", "n"], 10], layout: {
              "text-field": ["to-string", ["get", "n"]], "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"], "text-size": 11, "text-allow-overlap": true },
              paint: { "text-color": "#ffffff", "text-halo-color": "rgba(0,0,0,0.35)", "text-halo-width": 0.8 } });
            // the cells step back as the dots take over
            const faded: any = ["interpolate", ["linear"], ["zoom"], 13, base0, 15.5, ["*", 0.25, base0]]; // zoom must be top-level
            map.setPaintProperty("hs-grid-fill", "fill-opacity", faded);
          }).catch(() => {});
        };
        map.on("moveend", ensurePoints);
        map.on("zoomend", () => setZoomLevel(Math.round(map.getZoom() * 10) / 10));
      }
      map.once("style.load", () => {
        const firstSymbol = (map.getStyle().layers ?? []).find((l) => l.type === "symbol")?.id;
        firstSymbolRef.current = firstSymbol;
        map.addSource("hs-grid", { type: "geojson", data: grid as any, promoteId: "cell_id" });
        map.addLayer({ id: "hs-grid-fill", type: "fill", source: "hs-grid", paint: {
          "fill-color": ["step", ["get", "count_2024_25"], "rgba(0,0,0,0)", 1, RAMP[0], sc[0], RAMP[1], sc[1], RAMP[2]],
          "fill-opacity": ["step", ["get", "count_2024_25"], 0, 1, OPAC[0], sc[0], OPAC[1], sc[1], OPAC[2]],
          "fill-opacity-transition": { duration: 500 } } }, firstSymbol);
        // Cell edges stay legible once the fill fades at street zoom: thicker and darker as you zoom in.
        map.addLayer({ id: "hs-grid-line", type: "line", source: "hs-grid", paint: {
          "line-color": ["interpolate", ["linear"], ["zoom"], 12, OUTLINE.color, 14, "#28889E"],
          "line-width": ["interpolate", ["linear"], ["zoom"], 11, OUTLINE.width, 13.5, 1.2, 16, 2.2],
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 11, OUTLINE.opacity, 13.5, 0.85] } }, firstSymbol);
        map.addLayer({ id: "hs-grid-focus", type: "line", source: "hs-grid", filter: ["in", ["get", "cell_id"], ["literal", [CELL_ID, TIMES_SQUARE_CELL]]], layout: { visibility: "none" }, paint: { "line-color": "#1F1FD6", "line-width": 2.5 } });
        if (!explore) {
          // Hand labels for the zoomed-in dive: the mall, the station, the courthouse. Streets come from the basemap.
          loadHoyt<GeoJSON.FeatureCollection>("labels").then((labels) => {
            if (map.getSource("hs-labels")) return;
            const keep = labels.features.filter((f) => f.properties?.status === "verified" && ["Fulton Mall", "Hoyt-Schermerhorn", "120 Schermerhorn: Criminal Court and Central Booking", "Albee Square"].includes(String(f.properties?.name)));
            map.addSource("hs-labels", { type: "geojson", data: { type: "FeatureCollection", features: keep } as any });
            map.addLayer({ id: "hs-labels", type: "symbol", source: "hs-labels", layout: { visibility: "none",
              "text-field": ["case", ["==", ["get", "kind"], "institution"], "Criminal Court and\nCentral Booking", ["get", "name"]],
              "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"], "text-size": 13, "text-anchor": "top", "text-offset": [0, 0.6], "text-allow-overlap": true },
              paint: { "text-color": "#1F1FD6", "text-halo-color": "#ffffff", "text-halo-width": 1.6 } });
          }).catch(() => {});
        }
        loadHoyt<GeoJSON.FeatureCollection>("precinct84").then((p84) => {
          if (map.getSource("hs-p84")) return;
          map.addSource("hs-p84", { type: "geojson", data: p84 as any });
          map.addLayer({ id: "hs-p84-line", type: "line", source: "hs-p84", layout: { visibility: "none" }, paint: { "line-color": "#1F1FD6", "line-width": 3, "line-dasharray": [2, 1.5] } });
          map.addLayer({ id: "hs-p84-fill", type: "fill", source: "hs-p84", layout: { visibility: "none" }, paint: { "fill-color": "#1F1FD6", "fill-opacity": 0.06 } });
        }).catch(() => {});
        map.on("mousemove", "hs-grid-fill", (e) => {
          const f = e.features?.[0]; if (!f) return;
          setHover({ name: String(f.properties?.name ?? f.properties?.cell_id), count: Number(f.properties?.count_2024_25 ?? 0), rank: Number(f.properties?.rank ?? 0) });
          map.getCanvas().style.cursor = "crosshair";
        });
        map.on("mouseleave", "hs-grid-fill", () => { setHover(null); map.getCanvas().style.cursor = ""; });
        if (explore) {
          map.on("click", "hs-grid-fill", (e) => {
            const f = e.features?.[0]; if (!f) return;
            setPinned({ cell_id: String(f.properties?.cell_id), name: String(f.properties?.name ?? f.properties?.cell_id), count: Number(f.properties?.count_2024_25 ?? 0), rank: Number(f.properties?.rank ?? 0) });
            map.setFilter("hs-grid-focus", ["in", ["get", "cell_id"], ["literal", [String(f.properties?.cell_id)]]]);
            map.setLayoutProperty("hs-grid-focus", "visibility", "visible");
          });
        }
        setReady(true);
      });
      const ro = new ResizeObserver(() => map.resize());
      ro.observe(box.current);
      (map as any)._ro = ro;
    });
    return () => { cancelled = true; (mapRef.current as any)?._ro?.disconnect(); markers.current.forEach((m) => m.remove()); mapRef.current?.remove(); mapRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current; if (!ready || !map || explore) return;
    const step = activeStep || "all";
    const thr = improvers?.concentration.threshold_count_half ?? Infinity;
    const base: any = ["step", ["get", "count_2024_25"], 0, 1, OPAC[0], scale[0], OPAC[1], scale[1], OPAC[2]];
    const inP84 = new Set((improvers?.precinct_84.cells ?? []).map((c) => c.cell_id));
    let opacity: any = base;
    if (step === "top20") opacity = ["case", ["<", ["get", "count_2024_25"], thr], 0.06, base];
    if (step === "precinct") opacity = ["case", ["in", ["get", "cell_id"], ["literal", [...inP84]]], base, 0.1];
    const dive = step === "dive";
    if (dive) opacity = ["case", ["==", ["get", "cell_id"], CELL_ID], 0.05, ["*", 0.3, base]];
    map.setPaintProperty("hs-grid-fill", "fill-opacity", opacity);
    map.setLayoutProperty("hs-grid-focus", "visibility", dive ? "visible" : "none");
    for (const id of ["hs-p84-line", "hs-p84-fill"]) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", step === "precinct" ? "visible" : "none");
    for (const id of ["hs-labels", "hs-pts-agg"]) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", dive ? "visible" : "none");
    const focus = gridRef.current?.features.find((x) => x.properties?.cell_id === CELL_ID);
    const ring = focus ? (focus.geometry as GeoJSON.Polygon).coordinates[0] : null;
    if (dive && ring) {
      // Fill the stage with the cell itself; streets label themselves at this zoom.
      const bounds: [[number, number], [number, number]] = [[ring[0][0], ring[0][1]], [ring[2][0], ring[2][1]]];
      map.fitBounds(bounds, { padding: { top: 70, bottom: 90, left: 40, right: 40 }, duration: reducedMotion ? 0 : 1600, essential: true } as any);
      if (stagePointsRef.current === "idle") {
        stagePointsRef.current = "loading";
        // One dot per police-rounded point, sized by how many 2024-25 complaints sit on it, so clusters read as clusters.
        loadHoyt<{ classes: string[]; p: [number, number, number][] }>("points_2024_25").then((pts) => {
          const [w, s0, e, n] = [ring[0][0], ring[0][1], ring[2][0], ring[2][1]]; const mx = (e - w) * 0.35, my = (n - s0) * 0.35;
          const agg = new Map<string, { lon: number; lat: number; n: number; byCls: number[]; inside: boolean }>();
          for (const [lon, lat, c] of pts.p) {
            if (lon < w - mx || lon > e + mx || lat < s0 - my || lat > n + my) continue;
            const k = `${lon},${lat}`; let a = agg.get(k);
            if (!a) { a = { lon, lat, n: 0, byCls: new Array(pts.classes.length).fill(0), inside: lon >= w && lon <= e && lat >= s0 && lat <= n }; agg.set(k, a); }
            a.n += 1; a.byCls[c] += 1;
          }
          const features = [...agg.values()].sort((a, b) => b.n - a.n).map((a) => ({ type: "Feature", geometry: { type: "Point", coordinates: [a.lon, a.lat] },
            properties: { n: a.n, inside: a.inside, color: (CLASS_STYLE as any)[pts.classes[a.byCls.indexOf(Math.max(...a.byCls))]]?.color ?? "#1F1FD6" } }));
          if (map.getSource("hs-pts-agg")) return;
          map.addSource("hs-pts-agg", { type: "geojson", data: { type: "FeatureCollection", features } as any });
          map.addLayer({ id: "hs-pts-agg", type: "circle", source: "hs-pts-agg", layout: { visibility: "visible" }, paint: {
            "circle-radius": ["interpolate", ["linear"], ["sqrt", ["get", "n"]], 1, 3.5, 3, 6, 6, 10, 10, 15],
            "circle-color": ["get", "color"], "circle-opacity": ["case", ["get", "inside"], 0.85, 0.3],
            "circle-stroke-color": "#ffffff", "circle-stroke-width": 1 } }, firstSymbolRef.current);
          stagePointsRef.current = "ready";
        }).catch(() => { stagePointsRef.current = "idle"; });
      }
    } else {
      const cam = step === "precinct" ? { center: PRECINCT84, zoom: 13.6 } : { center: CITY, zoom: 9.8 };
      if (reducedMotion) map.jumpTo(cam); else map.flyTo({ ...cam, duration: 1600, essential: true });
    }
    markers.current.forEach((m) => m.remove()); markers.current = [];
    const pill = (text: string, bg: string, lngLat: [number, number], anchor: "bottom" | "top" = "bottom") => {
      const el = document.createElement("div");
      el.style.cssText = `font-family:'Source Sans 3',sans-serif;font-size:12px;font-weight:700;color:#fff;background:${bg};padding:3px 8px;border-radius:999px;pointer-events:none;box-shadow:0 1px 4px rgba(0,0,0,.25);white-space:nowrap`;
      el.textContent = text;
      markers.current.push(new maplibregl.Marker({ element: el, anchor, offset: [0, anchor === "bottom" ? -4 : 4] }).setLngLat(lngLat).addTo(map));
    };
    const cellCenter = (cid: string): [number, number] | null => {
      const f = gridRef.current?.features.find((x) => x.properties?.cell_id === cid); if (!f) return null;
      const ring = (f.geometry as GeoJSON.Polygon).coordinates[0]; return [(ring[0][0] + ring[2][0]) / 2, (ring[0][1] + ring[2][1]) / 2];
    };
    if (step === "improvers" && improvers) {
      for (const d of improvers.biggest_declines.slice(0, 3)) { const c = cellCenter(d.cell_id); if (c) pill(`${d.name}: ${Math.round(d.change_pct)}%`, "#006878", c); }
    }
    if (step === "precinct" && improvers) {
      for (const c of improvers.precinct_84.cells) {
        if (c.change_pct == null) continue;
        pill(`${c.change_pct > 0 ? "+" : ""}${Math.round(c.change_pct)}%`, c.change_pct > 0 ? "#C93E20" : "#006878", [c.lon, c.lat], "top");
      }
    }
    if (step === "dive" && gridRef.current) {
      const f = gridRef.current.features.find((x) => x.properties?.cell_id === CELL_ID); const c = cellCenter(CELL_ID);
      if (f && c) { const ring = (f.geometry as GeoJSON.Polygon).coordinates[0]; pill(`#${f.properties?.rank} · ${fmtInt(Number(f.properties?.count_2024_25))} complaints, 2024 to 2025`, "#1F1FD6", [c[0], ring[2][1]]); }
    }
  }, [ready, activeStep, reducedMotion, scale, improvers, explore]);

  const legend = useMemo(() => [{ c: RAMP[0], l: `1 to ${scale[0] - 1}` }, { c: RAMP[1], l: `${scale[0]} to ${scale[1] - 1}` }, { c: RAMP[2], l: `${scale[1]} and up` }], [scale]);
  const conc = improvers?.concentration;
  const step = explore ? "explore" : (activeStep || "all");
  return (
    <div className={explore ? "relative h-[70vh] min-h-[420px] w-full overflow-hidden rounded-xl bg-vellum" : "absolute inset-0"}>
      <div ref={box} className="absolute inset-0" />
      {!ready && <div className="absolute inset-0 flex items-center justify-center font-sans text-sm text-steel">Loading the city…</div>}
      <div className="pointer-events-none absolute left-3 top-3 z-10 max-w-[min(92%,420px)] rounded-xl bg-white/95 px-3 py-2 shadow ring-1 ring-slate-200">
        <div className="font-sans text-[11px] font-semibold uppercase tracking-[0.09em] text-steel">Violent complaints, 2024 to 2025, per 0.33-mile cell</div>
        <div className="mt-1 flex gap-3 font-sans text-xs text-charcoal">{legend.map((x) => <span key={x.l}><span className="mr-1 inline-block h-3 w-3 rounded-sm align-middle" style={{ background: x.c }} />{x.l}</span>)}<span><span className="mr-1 inline-block h-3 w-3 rounded-sm border border-slate-300 align-middle" />none</span></div>
        {hover && <div className="mt-1 font-sans text-xs text-charcoal"><b>{hover.name}</b> · {fmtInt(hover.count)} complaints · #{hover.rank} of 2,854</div>}
        {!hover && explore && <div className="mt-1 font-sans text-[11px] text-steel">Hover a cell, click to pin it. Drag to pan, scroll to zoom{zoomLevel >= 13.5 ? "; each dot is a point police round complaints to, sized by how many sit on it and colored by the most common type" : "; zoom in to see where complaints sit"}.</div>}
        {explore && zoomLevel >= 13.5 && <div className="mt-1 flex flex-wrap gap-x-3 font-sans text-[11px] text-charcoal">{Object.entries(CLASS_STYLE).filter(([, v]) => v.drawn).map(([k, v]) => <span key={k}><span className="mr-1 inline-block h-2 w-2 rounded-full align-middle" style={{ background: v.color }} />{v.short}</span>)}</div>}
      </div>
      {explore && pinned && (
        <div className="absolute bottom-14 left-3 z-10 w-[min(92%,300px)] rounded-xl bg-white/95 px-3 py-2 shadow ring-1 ring-slate-200 font-sans text-sm text-charcoal">
          <div className="font-serif text-lg font-bold text-cobalt">{pinned.name}</div>
          <div>{fmtInt(pinned.count)} violent complaints, 2024 to 2025 · #{pinned.rank} of 2,854 cells</div>
          {pinned.cell_id === CELL_ID && <div className="mt-1 text-xs text-steel">This is the cell the piece is about.</div>}
          <button className="mt-1 text-xs font-semibold text-cobalt" onClick={() => { setPinned(null); mapRef.current?.setFilter("hs-grid-focus", ["in", ["get", "cell_id"], ["literal", [CELL_ID, TIMES_SQUARE_CELL]]]); }}>clear</button>
        </div>
      )}
      {step === "improvers" && improvers && (
        <div className="absolute bottom-14 left-3 z-10 max-w-[340px] rounded-xl bg-white/95 px-3 py-2 shadow ring-1 ring-slate-200 font-sans text-sm text-charcoal">
          Cells with the biggest declines, {improvers.year_early} to {improvers.year_late}, among cells with {improvers.min_early}+ violent complaints in {improvers.year_early}; offense codes that existed in {improvers.year_early}. Citywide: robbery {Math.round(improvers.city_change_by_family_pct.robbery.change_pct)}%, felony assault {improvers.city_change_by_family_pct.felony_assault.change_pct > 0 ? "+" : ""}{Math.round(improvers.city_change_by_family_pct.felony_assault.change_pct)}%.
        </div>
      )}
      {step === "precinct" && improvers && (
        <div className="absolute bottom-14 left-3 z-10 max-w-[340px] rounded-xl bg-white/95 px-3 py-2 shadow ring-1 ring-slate-200 font-sans text-sm text-charcoal">
          The 84th Precinct, cell by cell, {improvers.year_early} to {improvers.year_late}: {improvers.precinct_84.n_down} cells down, {improvers.precinct_84.n_up} up. The precinct as a whole: {improvers.precinct_84.change_pct != null && improvers.precinct_84.change_pct > 0 ? "+" : ""}{Math.round(improvers.precinct_84.change_pct ?? 0)}%.
        </div>
      )}
      {step === "top20" && conc && (
        <div className="absolute bottom-14 left-3 z-10 max-w-[320px] rounded-xl bg-white/95 px-3 py-2 shadow ring-1 ring-slate-200 font-sans text-sm text-charcoal">
          Half of the city's violent complaints sit in <b>{fmtInt(conc.cells_for_half)}</b> of its {fmtInt(conc.n_cells)} cells, about {Math.round(conc.cells_for_half_share_of_all * 100)}% of its land. The rest have faded.
        </div>
      )}
      {step === "dive" && (
        <div className="absolute bottom-14 left-3 z-10 max-w-[340px] rounded-xl bg-white/95 px-3 py-2 shadow ring-1 ring-slate-200 font-sans text-sm text-charcoal">
          Each dot is a point police round complaints to; bigger dots carry more of the cell's 2024 to 2025 violent complaints. Dots outside the cell are faded.
        </div>
      )}
      <HoytCaveatChip />
    </div>
  );
}

/** Standalone citywide grid map (not sticky, not scripted): drag, zoom controls, hover, click to pin. */
export function HoytCityExplore() {
  return (
    <div className="not-prose my-8" style={{ width: "min(100vw - 1.5rem, 80rem)", marginLeft: "calc(50% - min(100vw - 1.5rem, 80rem) / 2)" }}>
      <HoytCityGrid mode="explore" />
    </div>
  );
}
