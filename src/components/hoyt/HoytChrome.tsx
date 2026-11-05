// Small shared pieces: the visible prose slot, the caveat chip, card chrome, photo frame, downloads.
import type { ReactNode } from "react";
import { DATA_BUNDLE, DOWNLOADS, STEEL, type Photo } from "@/config/hoytSchermerhorn";

export function Eyebrow({ children }: { children: ReactNode }) {
  return <div className="mb-1 font-sans text-[11px] font-semibold uppercase tracking-[0.09em]" style={{ color: STEEL }}>{children}</div>;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 ${className}`}>{children}</div>;
}

/** The prose slot Joe fills. Visible in the draft; the static stand-in renders a plain paragraph. */
export function HoytDraft({ id, words, children }: { id?: string; words?: string | number; children?: ReactNode }) {
  return (
    <div className="not-prose my-4 rounded-lg border-2 border-dashed border-amber-400 bg-amber-50/70 px-4 py-3 text-[15px] leading-relaxed text-amber-950">
      <div className="mb-1 font-sans text-[11px] font-semibold uppercase tracking-[0.09em] text-amber-700">
        Draft slot {id ?? ""}{words ? ` · Joe writes, about ${words} words` : " · Joe writes"}
      </div>
      <div className="italic text-amber-900/80">{children}</div>
    </div>
  );
}

export function HoytCaveatChip({ expanded = false }: { expanded?: boolean }) {
  return (
    <div className="pointer-events-auto absolute bottom-3 left-3 z-10 max-w-[260px] rounded-full bg-white/95 px-3 py-1.5 font-sans text-[11px] font-semibold text-charcoal shadow ring-1 ring-slate-200" title="NYPD places each complaint at a rounded midblock or intersection point. Nothing under 3 incidents is drawn. Station counts sit on the station.">
      Police-rounded locations, not addresses
      {expanded && <div className="mt-1 font-normal text-steel">Nothing under 3 incidents drawn. Station counts sit on the station.</div>}
    </div>
  );
}

export function HoytPhotoFrame({ photo, bleed = false }: { photo: Photo | null; bleed?: boolean }) {
  const cls = bleed ? "not-prose my-8 -mx-4 sm:-mx-8" : "not-prose my-6";
  if (photo && photo.file && photo.status !== "placeholder") {
    return (
      <figure className={cls}>
        <img src={photo.file} alt={photo.caption} className="w-full rounded-md object-cover" loading="lazy" />
        <figcaption className="mt-2 font-sans text-sm text-steel">
          {photo.caption}{photo.captured_at ? ` · ${photo.captured_at}` : ""}{photo.attribution ? ` · ${photo.attribution}` : ""}
          {photo.source_url && <> · <a href={photo.source_url} className="underline" target="_blank" rel="noreferrer">source</a></>}
        </figcaption>
      </figure>
    );
  }
  return (
    <figure className={cls}>
      <div className="flex aspect-[3/2] w-full flex-col justify-between rounded-md border border-dashed border-slate-300 bg-vellum p-5">
        <div className="font-sans text-[11px] font-semibold uppercase tracking-[0.09em] text-steel">Photo placeholder</div>
        <div>
          <div className="font-serif text-xl text-charcoal">{photo?.caption ?? "Planned photo"}</div>
          <div className="mt-2 max-w-prose font-sans text-sm text-steel">{photo?.brief ?? "Shot brief pending."}</div>
        </div>
        <div className="font-sans text-xs text-steel">Caption will carry the capture date and time.{photo?.street_view_url && <> <a className="underline" href={photo.street_view_url} target="_blank" rel="noreferrer">Scout this corner in Street View</a></>}</div>
      </div>
    </figure>
  );
}

export function HoytDownloads() {
  return (
    <Card className="not-prose my-8">
      <Eyebrow>Data</Eyebrow>
      <a className="inline-block rounded-md bg-cobalt px-4 py-2 font-sans text-[15px] font-semibold text-white hover:opacity-90" href={DATA_BUNDLE.url}>{DATA_BUNDLE.label}</a>
      <div className="mt-3 font-sans text-xs text-steel">Or each file on its own:</div>
      <ul className="mt-1 space-y-2">
        {DOWNLOADS.map((d) => (
          <li key={d.url}>
            <a className="font-sans text-[15px] font-semibold text-cobalt hover:underline" href={d.url}>{d.label}</a>
          </li>
        ))}
      </ul>
      <p className="mt-3 font-sans text-xs text-steel">NYPD Complaint Data, Historic and Year-To-Date, via NYC Open Data. Victim and suspect demographic columns are not included. Coordinates are as NYPD publishes them: rounded to a midblock or intersection.</p>
    </Card>
  );
}
