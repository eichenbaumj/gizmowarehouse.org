import { type ImageryFile } from "@/config/hoytSchermerhorn";
import { useHoytData } from "./hoytData";
import { HoytPhotoFrame } from "./HoytChrome";

export function HoytPhoto({ photo, bleed }: { photo?: string; bleed?: boolean | string }) {
  const { data } = useHoytData<ImageryFile>("imagery");
  const p = data?.photos.find((x) => x.key === photo) ?? null;
  return <HoytPhotoFrame photo={p ?? (photo ? { key: photo, status: "placeholder", file: null, caption: photo, captured_at: null, facing_deg: null, attribution: null, source_url: null, brief: "Shot brief pending.", lat: 0, lon: 0, street_view_url: "" } : null)} bleed={bleed !== undefined && bleed !== false} />;
}
