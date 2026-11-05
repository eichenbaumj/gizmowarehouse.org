// Module-cached loaders for the hoyt-schermerhorn-crime-analysis data files (one fetch per file per
// page load), plus the kill-switch helper the components use before drawing a claim.
import { useEffect, useState } from "react";
import { dataUrl, type DqFile, type HoytDataName } from "@/config/hoytSchermerhorn";

const cache = new Map<HoytDataName, Promise<unknown>>();

export function loadHoyt<T>(name: HoytDataName): Promise<T> {
  if (!cache.has(name)) {
    cache.set(
      name,
      fetch(dataUrl(name)).then((r) => (r.ok ? (r.json() as Promise<T>) : Promise.reject(new Error(`HTTP ${r.status} for ${name}`)))),
    );
  }
  return cache.get(name) as Promise<T>;
}

export function useHoytData<T>(name: HoytDataName): { data: T | null; err: string | null } {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    loadHoyt<T>(name)
      .then((d) => live && setData(d))
      .catch((e) => live && setErr(String(e)));
    return () => {
      live = false;
    };
  }, [name]);
  return { data, err };
}

/** A claim may be drawn only if the pipeline marked it publishable. Unknown claim = not ok. */
export function claimOk(dq: DqFile | null, id: string): boolean {
  return !!dq?.claims?.[id]?.publishable;
}

export const fmtInt = (n: number) => Math.round(n).toLocaleString("en-US");
export const fmtPct0 = (x: number) => `${Math.round(x * 100)}%`;
export const HOURS = Array.from({ length: 24 }, (_, i) => i);
export const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
export function hourLabel(h: number): string {
  if (h === 0) return "12am";
  if (h === 12) return "12pm";
  return h < 12 ? `${h}am` : `${h - 12}pm`;
}
