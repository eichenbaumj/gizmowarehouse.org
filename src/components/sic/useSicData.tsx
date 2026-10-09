// Shared, module-cached loaders and card chrome for the self-insurance-cost embeds.
// One fetch per file per page load (the promise is cached), as in rhc/useRhcData.tsx.

import { useEffect, useState } from "react";
import { dataUrl } from "@/config/selfInsuranceCost";

type Name = Parameters<typeof dataUrl>[0];
const cache = new Map<Name, Promise<unknown>>();

function load<T>(name: Name): Promise<T> {
  if (!cache.has(name)) {
    cache.set(
      name,
      fetch(dataUrl(name)).then((r) => (r.ok ? (r.json() as Promise<T>) : Promise.reject(new Error("HTTP " + r.status)))),
    );
  }
  return cache.get(name) as Promise<T>;
}

export function useSicData<T>(name: Name): { data: T | null; err: string | null } {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    load<T>(name)
      .then((d) => live && setData(d))
      .catch((e) => live && setErr(String(e)));
    return () => {
      live = false;
    };
  }, [name]);
  return { data, err };
}

export function useIsNarrow(maxWidth = 480): boolean {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia(`(max-width: ${maxWidth}px)`);
    const on = () => setNarrow(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [maxWidth]);
  return narrow;
}

export const STEEL = "#6E6E6D";
export const GRID = "#E5E7EB";

export function SicCard({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`my-6 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 ${className ?? ""}`}>{children}</div>
  );
}
export function Eyebrow({ children }: { children: React.ReactNode }) {
  // explicit color: the page's prose styles paint headings cobalt, which an eyebrow should not be
  return (
    <div className="mb-1 font-sans text-[11px] font-semibold uppercase tracking-[0.09em]" style={{ color: STEEL }}>{children}</div>
  );
}
export function Sub({ children }: { children: React.ReactNode }) {
  return <p className="mb-3 mt-1 font-sans text-sm" style={{ color: STEEL }}>{children}</p>;
}
export function Loading({ h = 320 }: { h?: number }) {
  return <div className="my-6 animate-pulse rounded-2xl bg-vellum" style={{ height: h }} />;
}
export function Err({ msg }: { msg: string }) {
  return <div className="my-6 text-sm text-steel">Chart data unavailable ({msg}).</div>;
}
export const fmtMoney = (v: number, d = 0) => `$${v.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d })}`;
export const fmtPop = (v: number) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${Math.round(v / 1e3)}K` : `${Math.round(v)}`);
