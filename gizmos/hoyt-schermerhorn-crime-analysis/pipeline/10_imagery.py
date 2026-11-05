"""Stage 10: imagery manifest. For each planned photo, look for a recent Mapillary image near the stop
(Graph API; token MAPILLARY_TOKEN from the repo's .env.local). Mapillary imagery is CC BY-SA 4.0 and ships
with attribution. Without a token, or where coverage is thin, the entry is a placeholder with a shot brief.
Google Street View is never downloaded (Maps Platform ToS); each stop keeps an outbound link only."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

PHOTOS = [
    {"key": "arrive-fulton-east", "lat": 40.6901, "lon": -73.9858, "facing": 70, "caption": "Fulton Street looking east from Hoyt Street", "brief": "Weekday, about 4pm. Stand at the northeast corner of Fulton and Hoyt, face east down the mall. Long exposure so people ghost; storefronts and vendor tables sharp."},
    {"key": "courthouse-door", "lat": 40.6898, "lon": -73.9889, "facing": 350, "caption": "120 Schermerhorn Street, Criminal Court and Central Booking", "brief": "Wednesday, 10:30 to 11:30am. From the south sidewalk, the public door and the line. Handheld only. Never the sally port, transport, anyone in custody, or badge numbers. Not between 2:30 and 3:30pm (school next door)."},
    {"key": "macys-block", "lat": 40.6907, "lon": -73.9862, "facing": 20, "caption": "Fulton Street between Hoyt and Elm Place", "brief": "Weekday, about 1pm. The store doors from the sidewalk; count guards and locked cases through the glass for the field note."},
    {"key": "mid-mall", "lat": 40.6904, "lon": -73.9848, "facing": 70, "caption": "Fulton Street mid-mall, vendor tables", "brief": "Weekday, about 3pm. Tables and the crowd; keep still subjects small or from behind."},
    {"key": "albee-square", "lat": 40.6909, "lon": -73.9835, "facing": 40, "caption": "Albee Square and the City Point entrances", "brief": "Weekday, about 4pm. The plaza and escalators from public ground; no interiors."},
    {"key": "livingston", "lat": 40.6893, "lon": -73.9852, "facing": 90, "caption": "Livingston Street, one block south, same hour", "brief": "Same afternoon as the mall shots, within the hour. A quiet frame at the same exposure."},
    {"key": "hoyt-stairs", "lat": 40.6885, "lon": -73.9851, "facing": 180, "caption": "Hoyt-Schermerhorn station stairs", "brief": "Two frames: about 8:30am and about 10pm. Entrance and mezzanine only, handheld."},
    {"key": "dekalb-headhouse", "lat": 40.6906, "lon": -73.9814, "facing": 120, "caption": "DeKalb Avenue head house at Flatbush Avenue Extension", "brief": "Day and night pair. Photograph the space, never people living in it or their belongings."},
    {"key": "close-stairs", "lat": 40.6886, "lon": -73.9849, "facing": 0, "caption": "Back at the stairs", "brief": "Closing frame, late afternoon, looking up Hoyt toward Fulton."},
]
GRAPH = "https://graph.mapillary.com/images"


def token() -> str | None:
    t = os.environ.get("MAPILLARY_TOKEN")
    if t:
        return t
    env = config.REPO_ROOT / ".env.local"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("MAPILLARY_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"')
    return None


def best_image(tok: str, lat: float, lon: float, radius_deg: float = 0.0006) -> dict | None:
    bbox = f"{lon - radius_deg},{lat - radius_deg},{lon + radius_deg},{lat + radius_deg}"
    params = {"access_token": tok, "fields": "id,captured_at,compass_angle,thumb_2048_url,creator,is_pano,geometry", "bbox": bbox, "limit": 50}
    r = requests.get(GRAPH, params=params, timeout=60)
    if not r.ok:
        return None
    data = r.json().get("data", [])
    if not data:
        return None
    data.sort(key=lambda d: d.get("captured_at", 0), reverse=True)
    return data[0]


def main() -> None:
    tok = token()
    out = {"snapshot": config.SNAPSHOT_DATE, "token_present": bool(tok), "photos": []}
    assets = config.ASSETS_DIR
    commons_path = config.CROSSWALKS / "commons_photos.json"
    commons = json.loads(commons_path.read_text()) if commons_path.exists() else {}
    for p in PHOTOS:
        entry = {"key": p["key"], "status": "placeholder", "file": None, "caption": p["caption"], "captured_at": None, "facing_deg": p["facing"],
                 "attribution": None, "source_url": None, "brief": p["brief"], "lat": p["lat"], "lon": p["lon"],
                 "street_view_url": f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={p['lat']},{p['lon']}&heading={p['facing']}"}
        c = commons.get(p["key"])
        if c and (config.REPO_ROOT / c["file"].lstrip("/").replace("assets/", "public/assets/")).exists():
            entry.update({k: c[k] for k in ("status", "file", "caption", "captured_at", "facing_deg", "attribution", "source_url")})
            out["photos"].append(entry)
            continue
        if tok:
            img = best_image(tok, p["lat"], p["lon"])
            if img and img.get("thumb_2048_url"):
                try:
                    r = requests.get(img["thumb_2048_url"], timeout=60)
                    if r.ok:
                        fn = f"{config.ASSET_PREFIX}photo-{p['key']}.jpg"
                        (assets / fn).write_bytes(r.content)
                        entry.update({"status": "mapillary", "file": f"/assets/{fn}",
                                      "captured_at": time.strftime("%Y-%m-%d %H:%M", time.gmtime(img["captured_at"] / 1000)) if img.get("captured_at") else None,
                                      "facing_deg": img.get("compass_angle", p["facing"]),
                                      "attribution": f"Mapillary, {img.get('creator', {}).get('username', 'contributor')}, CC BY-SA 4.0",
                                      "source_url": f"https://www.mapillary.com/app/?pKey={img['id']}", "is_pano": img.get("is_pano", False)})
                except Exception as e:  # noqa: BLE001
                    entry["error"] = str(e)
            time.sleep(0.3)
        out["photos"].append(entry)
    (config.PUBLIC_DATA_DIR / "imagery.json").write_text(json.dumps(out, indent=1))
    n = sum(1 for p in out["photos"] if p["status"] == "mapillary"); nc = sum(1 for p in out["photos"] if p["status"] == "commons")
    print(f"stage 10 done: token {'present' if tok else 'ABSENT'}; {nc} from Wikimedia Commons, {n} from Mapillary, {len(PHOTOS) - n - nc} placeholders")


if __name__ == "__main__":
    main()
