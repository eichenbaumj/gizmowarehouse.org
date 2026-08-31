"""The footprint block: where data centers actually run, per state.

Source: EPRI, Powering Intelligence 2026 — the State-Level Data Center Power
Data dashboard (powering-intelligence.epri.com/dashboard/), which publishes
per-state nominal capacity (GW), peak load (GW), and annual energy (TWh) for
2021-2024 historical plus low/medium/high scenarios to 2030, and offers the
data for download. The extracted dataset is cached at
raw/epri_state_dashboard.json. The map uses 2024 historical annual energy as
"footprint today" and the 2030 MEDIUM scenario as the labeled projection.

Known gap: EPRI's dashboard covers the 50 states (no District of Columbia);
DC carries nulls and the QA gate expects exactly that.
"""

from __future__ import annotations

import json

import config
import geocode as geomod

SUM_TOLERANCE = 0.03  # states must sum to EPRI's own US row within 3%


def _state_centroids():
    doc = json.loads(config.US_STATES_GEOJSON.read_text())
    out = {}
    for f in doc["features"]:
        latlon = geomod._ring_average(f["geometry"])
        if latlon:
            out[f["properties"]["STATEFP"]] = latlon
    return out


def build_footprint(abbr_to_fips):
    if not config.EPRI_RAW_JSON.exists():
        return None, "raw/epri_state_dashboard.json missing — footprint block skipped"
    doc = json.loads(config.EPRI_RAW_JSON.read_text())
    rows = doc["rows"]
    h24 = {r["state"]: r for r in rows if r["scenario"] == "hist" and r["year"] == 2024}
    med30 = {r["state"]: r for r in rows if r["scenario"] == "medium" and r["year"] == 2030}

    us24 = h24.get("US", {}).get("annual_TWh")
    state_sum = sum(r["annual_TWh"] for s, r in h24.items() if s != "US")
    if us24 and abs(state_sum - us24) / us24 > SUM_TOLERANCE:
        return None, f"EPRI state sum {state_sum:.1f} TWh vs US row {us24:.1f} — outside tolerance"

    centroids = _state_centroids()
    states = {}
    for abbr, fips in abbr_to_fips.items():
        h = h24.get(abbr)
        m = med30.get(abbr)
        lat, lon = centroids.get(fips, (None, None))
        states[fips] = {
            "abbr": abbr,
            "twh_2024": round(h["annual_TWh"], 2) if h else None,
            "gw_2024_nominal": round(h["nominal_GW"], 2) if h else None,
            "twh_2030_medium": round(m["annual_TWh"], 1) if m else None,
            "lat": lat,
            "lon": lon,
        }
    block = {
        "source": "EPRI, Powering Intelligence 2026 (state-level dashboard)",
        "source_url": "https://powering-intelligence.epri.com/dashboard/",
        "year": 2024,
        "projection": "2030, EPRI medium scenario",
        "us_twh_2024": us24,
        "us_twh_2030_medium": round(med30.get("US", {}).get("annual_TWh", 0), 1) or None,
        "states": states,
    }
    return block, None
