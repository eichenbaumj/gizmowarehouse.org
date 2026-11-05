// One month on the block: a plain basemap at block scale, and as the reader scrolls through the
// section, days advance and every complaint appears at its hour and stays. Violent complaints are solid
// class-colored dots, larcenies and misdemeanor assaults small hollow grey dots. Coordinates are the
// NYPD-rounded points with a deterministic ~25 m jitter so stacked complaints can be told apart.
import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { cartoStyleUrl, cartoTransformRequest, CARTO_ATTRIBUTION } from "@/config/basemap";
import { CLASS_STYLE, CORE, MOBILE_STAGE_VH, type TimelapseFile } from "@/config/hoytSchermerhorn";
import { useScrollProgress } from "@/hooks/useScrollProgress";
import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";
import { loadHoyt, hourLabel, DOW } from "./hoytData";
import { HoytCaveatChip } from "./HoytChrome";
import { StageContext } from "./HoytScrolly";
import MountWhenNear from "@/components/MountWhenNear";
import { Children, isValidElement } from "react";

const JITTER_M = 22;
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

function toFC(d: TimelapseFile): GeoJSON.FeatureCollection {
  const dLat = JITTER_M / 111_000;
  return { type: "FeatureCollection", features: d.rows.map((r, i) => {
    const dLon = dLat / Math.cos((r.lat * Math.PI) / 180);
    const h = r.h ?? 12;
    return { type: "Feature", id: i, properties: { t: (r.d - 1) * 24 + h, kind: r.kind, violent: r.kind in CLASS_STYLE, zone: r.zone, d: r.d, h },
      geometry: { type: "Point", coordinates: [r.lon + r.jitter[0] * dLon, r.lat + r.jitter[1] * dLat] } };
  }) };
}

export function HoytTimelapse({ children }: { children?: ReactNode }) {
  const section = useRef<HTMLDivElement | null>(null);
  const progress = useScrollProgress(section);
  const reduced = usePrefersReducedMotion();
  const steps: string[] = [];
  Children.forEach(children, (c) => { if (isValidElement(c) && (c.props as any)?.step) steps.push(String((c.props as any).step)); });
  const activeIndex = Math.min(steps.length - 1, Math.floor(progress * steps.length));
  const ctx = { activeIndex, activeStep: steps[activeIndex] ?? "", steps, reducedMotion: reduced };
  // One card for the whole month. The card column is a tall runway so the month plays out over a few seconds
  // of scrolling (and back), with the card pinned mid-screen rather than four mid-scene pauses.
  const cards = Children.map(children, (c) => (isValidElement(c) && (c.props as any)?.step ? <div className="sticky top-6 pb-6">{c}</div> : c));
  return (
    <StageContext.Provider value={ctx}>
      <section ref={section} className="not-prose relative my-10" style={{ width: "min(100vw - 1.5rem, 100rem)", marginLeft: "calc(50% - min(100vw - 1.5rem, 100rem) / 2)" }}>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(0,1fr)_minmax(18rem,26rem)] md:gap-6">
          <div className="sticky top-6 z-[1] h-[var(--stage-h)] self-start md:h-[calc(100vh-3rem)]" style={{ "--stage-h": `${MOBILE_STAGE_VH}vh` } as CSSProperties}>
            <div className="relative h-full w-full overflow-hidden rounded-xl bg-vellum">
              <MountWhenNear placeholderHeight="100%"><TimelapseStage progress={reduced ? 1 : progress} /></MountWhenNear>
            </div>
          </div>
          <div className="min-h-[220vh] px-1 md:px-0">{cards}</div>
        </div>
      </section>
    </StageContext.Provider>
  );
}

function TimelapseStage({ progress }: { progress: number }) {
  const box = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [data, setData] = useState<TimelapseFile | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let cancelled = false;
    loadHoyt<TimelapseFile>("timelapse").then((d) => {
      if (cancelled || !box.current || mapRef.current) return;
      setData(d);
      const map = new maplibregl.Map({ container: box.current, style: cartoStyleUrl("positron"), transformRequest: cartoTransformRequest, center: [CORE[0] + 0.0008, CORE[1] + 0.0012], zoom: 16.1, interactive: false,
        attributionControl: { compact: true, customAttribution: CARTO_ATTRIBUTION }, canvasContextAttributes: { preserveDrawingBuffer: true } } as any);
      mapRef.current = map;
      (window as any).__hoytTimelapse = map;
      map.once("style.load", () => {
        map.addSource("hs-tl", { type: "geojson", data: toFC(d) as any });
        const colorExpr: any = ["match", ["get", "kind"], ...Object.entries(CLASS_STYLE).flatMap(([k, v]) => [k, v.color]), "#9AA0A6"];
        map.addLayer({ id: "hs-tl-minor", type: "circle", source: "hs-tl", filter: ["all", ["!", ["get", "violent"]], ["<=", ["get", "t"], -1]], paint: { "circle-radius": 4.5, "circle-color": "#B8BCC4", "circle-opacity": 0.95, "circle-stroke-color": "#4A5058", "circle-stroke-width": 1.4 } });
        map.addLayer({ id: "hs-tl-violent", type: "circle", source: "hs-tl", filter: ["all", ["get", "violent"], ["<=", ["get", "t"], -1]], paint: { "circle-radius": 7, "circle-color": colorExpr, "circle-opacity": 0.92, "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.5 } });
        setReady(true);
      });
      const ro = new ResizeObserver(() => map.resize()); ro.observe(box.current); (map as any)._ro = ro;
    });
    return () => { cancelled = true; (mapRef.current as any)?._ro?.disconnect(); mapRef.current?.remove(); mapRef.current = null; };
  }, []);
  const tMax = data ? data.days * 24 : 744;
  const t = Math.floor(progress * tMax);
  useEffect(() => {
    const map = mapRef.current; if (!ready || !map) return;
    map.setFilter("hs-tl-minor", ["all", ["!", ["get", "violent"]], ["<=", ["get", "t"], t]]);
    map.setFilter("hs-tl-violent", ["all", ["get", "violent"], ["<=", ["get", "t"], t]]);
  }, [ready, t]);
  const day = Math.min(data?.days ?? 31, Math.floor(t / 24) + 1);
  const hour = t % 24;
  const dow = data ? DOW[(data.first_dow + day - 1) % 7] : "";
  const shown = useMemo(() => data ? data.rows.filter((r) => (r.d - 1) * 24 + (r.h ?? 12) <= t) : [], [data, t]);
  const nViolent = shown.filter((r) => r.kind in CLASS_STYLE).length;
  const nMinor = shown.length - nViolent;
  return (
    <div className="absolute inset-0">
      <div ref={box} className="absolute inset-0" />
      {!ready && <div className="absolute inset-0 flex items-center justify-center font-sans text-sm text-steel">Loading the month…</div>}
      {data && (
        <div className="pointer-events-none absolute left-3 top-3 z-10 rounded-xl bg-white/95 px-3 py-2 shadow ring-1 ring-slate-200">
          <div className="font-sans text-[11px] font-semibold uppercase tracking-[0.09em] text-steel">{MONTHS[data.month - 1]} {data.year}, within 400 m of the station</div>
          <div className="font-serif text-2xl font-bold text-charcoal">{dow} the {day}{day === 1 || day === 21 || day === 31 ? "st" : day === 2 || day === 22 ? "nd" : day === 3 || day === 23 ? "rd" : "th"}, {hourLabel(hour)}</div>
          <div className="mt-1 font-sans text-xs text-charcoal"><b>{nViolent}</b> violent complaints so far · <b>{nMinor}</b> larcenies and misdemeanor assaults</div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 font-sans text-[11px] text-steel">
            {Object.entries(CLASS_STYLE).filter(([, v]) => v.drawn).map(([k, v]) => <span key={k}><span className="mr-1 inline-block h-2.5 w-2.5 rounded-full align-middle" style={{ background: v.color }} />{v.short}</span>)}
            <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-full border align-middle" style={{ background: "#B8BCC4", borderColor: "#4A5058" }} />larceny or misd. assault</span>
          </div>
        </div>
      )}
      <HoytCaveatChip />
    </div>
  );
}
