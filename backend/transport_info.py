"""
transport_info.py — Transport connectivity for Bengaluru rental search.

Metro lookup uses a curated list of ONLY operational Namma Metro stations
(verified March 2026). This replaces Google Places API for metro lookup
because Places API returns:
  - Bus stops tagged as "metro station"
  - Under-construction stations (e.g. "Metro Station- in progress")
  - Incorrect station names

Distance to Majestic still uses Google Distance Matrix API (driving).
Reverse geocoding still uses Google Geocoding API.

Walk time display:
  ≤ 1.5 km  → "~X min walk"
  1.5–5 km  → "X.X km (auto-rickshaw recommended)"
  > 5 km    → metro not shown / "No metro station nearby"
"""

import os
import math
import requests
from typing import Optional

GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# Kempegowda Bus Terminal (Majestic) — Bengaluru's central KSRTC hub
MAJESTIC_LAT = 12.9767
MAJESTIC_LNG = 77.5713

# ─────────────────────────────────────────────────────────────────────────────
# Curated Namma Metro station database — OPERATIONAL only, March 2026
# Format: (station_name, line_colour, latitude, longitude)
#
# Sources: BMRCL official route map + field-verified coordinates
# ─────────────────────────────────────────────────────────────────────────────
NAMMA_METRO_STATIONS: list[tuple[str, str, float, float]] = [

    # ── PURPLE LINE (East–West) ───────────────────────────────────────────────
    # East end: Whitefield (Kadugodi) ↔ West end: Challaghatta
    ("Whitefield (Kadugodi)",  "Purple", 12.9698, 77.7503),
    ("Hopefarm Channasandra",  "Purple", 12.9742, 77.7392),
    ("Sri Sathya Sai Hospital","Purple", 12.9762, 77.7104),
    ("Nallurhalli",            "Purple", 12.9762, 77.6982),
    ("Kundalahalli",           "Purple", 12.9755, 77.6893),
    ("Brookefield",            "Purple", 12.9745, 77.6805),
    ("ITPL",                   "Purple", 12.9735, 77.6718),
    ("Doddanekundi",           "Purple", 12.9725, 77.6618),
    ("AECS Layout",            "Purple", 12.9715, 77.6512),
    ("KR Puram",               "Purple", 12.9920, 77.6963),
    ("Benniganahalli",         "Purple", 12.9880, 77.6832),
    ("Hoodi",                  "Purple", 12.9832, 77.6722),
    ("Garudacharpalya",        "Purple", 12.9795, 77.6618),
    ("Tin Factory",            "Purple", 12.9765, 77.6512),
    ("Indiranagar",            "Purple", 12.9780, 77.6408),
    ("Halasuru",               "Purple", 12.9780, 77.6285),
    ("Trinity",                "Purple", 12.9740, 77.6195),
    ("MG Road",                "Purple", 12.9745, 77.6083),
    ("Cubbon Park",            "Purple", 12.9765, 77.5975),
    ("Vidhana Soudha",         "Purple", 12.9792, 77.5908),
    ("Sir M Visvesvaraya",     "Purple", 12.9792, 77.5808),
    ("Majestic",               "Purple", 12.9767, 77.5713),
    ("City Railway Station",   "Purple", 12.9780, 77.5638),
    ("Magadi Road",            "Purple", 12.9740, 77.5545),
    ("Hosahalli",              "Purple", 12.9680, 77.5435),
    ("Vijayanagar",            "Purple", 12.9632, 77.5340),
    ("Attiguppe",              "Purple", 12.9588, 77.5265),
    ("Deepanjali Nagar",       "Purple", 12.9542, 77.5198),
    ("Mysore Road",            "Purple", 12.9502, 77.5120),
    ("Pantharapalya",          "Purple", 12.9462, 77.5058),
    ("Nayandahalli",           "Purple", 12.9388, 77.5025),
    ("Rajarajeshwari Nagar",   "Purple", 12.9228, 77.4985),
    ("Jnanabharathi",          "Purple", 12.9168, 77.4952),
    ("Pattanagere",            "Purple", 12.9075, 77.4918),
    ("Kengeri Bus Terminal",   "Purple", 12.9008, 77.4882),
    ("Kengeri",                "Purple", 12.8988, 77.4848),
    ("Challaghatta",           "Purple", 12.8948, 77.4782),

    # ── GREEN LINE (North–South) ──────────────────────────────────────────────
    # South end: Silk Institute / Gottigere ↔ North end: Nagasandra / Nagawara
    ("Silk Institute",         "Green",  12.8928, 77.5823),
    ("Yelachenahalli",         "Green",  12.9002, 77.5823),
    ("Konanakunte Cross",      "Green",  12.9075, 77.5838),
    ("Doddakallasandra",       "Green",  12.9142, 77.5858),
    ("Vajarahalli",            "Green",  12.9195, 77.5878),
    ("Talaghattapura",         "Green",  12.9248, 77.5898),
    ("Banashankari",           "Green",  12.9268, 77.5638),
    ("Jayadeva Hospital",      "Green",  12.9302, 77.5912),
    ("RV Road",                "Green",  12.9348, 77.5938),
    ("South End Circle",       "Green",  12.9395, 77.5912),
    ("Lalbagh",                "Green",  12.9488, 77.5845),
    ("National College",       "Green",  12.9535, 77.5818),
    ("KR Market",              "Green",  12.9635, 77.5762),
    ("Chamrajpet",             "Green",  12.9668, 77.5738),
    ("Majestic",               "Green",  12.9767, 77.5713),
    ("Chickpete",              "Green",  12.9712, 77.5745),
    ("City Market",            "Green",  12.9678, 77.5762),
    ("Mahalakshmi",            "Green",  12.9788, 77.5662),
    ("Sandal Soap Factory",    "Green",  12.9838, 77.5628),
    ("Jalahalli",              "Green",  13.0238, 77.5538),
    ("Peenya Industry",        "Green",  13.0312, 77.5388),
    ("Peenya",                 "Green",  13.0338, 77.5298),
    ("Goraguntepalya",         "Green",  13.0282, 77.5228),
    ("Yeshwanthpur",           "Green",  13.0248, 77.5328),
    ("Dasarahalli",            "Green",  13.0412, 77.5138),
    ("Nagasandra",             "Green",  13.0488, 77.5228),
    ("Nagawara",               "Green",  13.0412, 77.6098),
    ("Gottigere",              "Green",  12.8612, 77.5968),
    ("Hulimavu",               "Green",  12.8788, 77.5932),
    ("JP Nagar",               "Green",  12.8962, 77.5882),
    ("Jayanagar",              "Green",  12.9262, 77.5918),
    # Phase 2A Green Line South extension (operational 2024)
    ("Bommasandra",            "Green",  12.8118, 77.6988),
    ("Hebbagodi",              "Green",  12.8208, 77.6938),
    ("Electronics City",       "Green",  12.8312, 77.6778),
    ("Hongasandra",            "Green",  12.8658, 77.6182),
    ("Begur Road",             "Green",  12.8758, 77.6082),
    ("Hosa Road",              "Green",  12.8888, 77.5968),
]

MAX_METRO_RADIUS_KM = 5.0   # Don't show metro beyond this distance


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Straight-line distance in metres between two lat/lng points."""
    dlat = (lat2 - lat1) * 111_000
    dlng = (lng2 - lng1) * 111_000 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dlat**2 + dlng**2)


def nearest_metro(lat: float, lng: float) -> Optional[dict]:
    """
    Returns the nearest operational Namma Metro station within 5 km.
    Result: {name, line, distance_km, display} or None if nothing within 5 km.
    """
    best_dist = float("inf")
    best      = None

    for name, line, slat, slng in NAMMA_METRO_STATIONS:
        dist_m = _haversine_m(lat, lng, slat, slng)
        if dist_m < best_dist:
            best_dist = dist_m
            best      = (name, line, dist_m)

    if best is None or best[2] > MAX_METRO_RADIUS_KM * 1000:
        return None

    name, line, dist_m = best
    dist_km = round(dist_m / 1000, 1)

    if dist_km <= 1.5:
        walk_min  = round(dist_m / 80)   # 80 m/min walking pace
        access    = f"~{walk_min} min walk"
    else:
        access    = f"{dist_km} km — auto-rickshaw recommended"

    return {
        "name":        name,
        "line":        line,
        "distance_km": dist_km,
        "display":     f"Metro: {name} ({line} Line) — {access}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Google APIs — distance to Majestic + reverse geocoding
# ─────────────────────────────────────────────────────────────────────────────

def _distance_to_majestic(lat: float, lng: float, api_key: str) -> dict:
    """Driving distance and time to Kempegowda Bus Terminal (Majestic)."""
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/distancematrix/json",
            params={
                "origins":      f"{lat},{lng}",
                "destinations": f"{MAJESTIC_LAT},{MAJESTIC_LNG}",
                "mode":         "driving",
                "key":          api_key,
            },
            timeout=5,
        )
        element = resp.json()["rows"][0]["elements"][0]
        if element["status"] != "OK":
            return {}
        return {
            "distance_km": round(element["distance"]["value"] / 1000, 1),
            "duration_min": round(element["duration"]["value"] / 60),
        }
    except Exception as e:
        print(f"⚠️ Distance Matrix failed: {e}")
        return {}


def reverse_geocode_area(lat: float, lng: float, api_key: str = "") -> str:
    """Returns a short readable area name for a lat/lng via Google Geocoding."""
    key = api_key or GOOGLE_API_KEY
    if not key:
        return "the midpoint area"
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"latlng": f"{lat},{lng}", "key": key},
            timeout=5,
        )
        results = resp.json().get("results", [])
        if not results:
            return "the midpoint area"
        priority = ["sublocality_level_1", "sublocality_level_2", "neighborhood", "locality"]
        name_map = {}
        for comp in results[0].get("address_components", []):
            for t in comp["types"]:
                if t in priority and t not in name_map:
                    name_map[t] = comp["long_name"]
        for p in priority:
            if p in name_map:
                return name_map[p]
        return results[0].get("formatted_address", "").split(",")[0].strip() or "the midpoint area"
    except Exception as e:
        print(f"⚠️ Reverse geocode failed: {e}")
        return "the midpoint area"


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_transport_summary(lat: float, lng: float, api_key: str = "") -> dict:
    """
    Returns transport info for a lat/lng.
    Keys: metro (dict|None), majestic_km, majestic_min, transport_text
    """
    key = api_key or GOOGLE_API_KEY

    metro  = nearest_metro(lat, lng)
    result = {
        "metro":        metro,
        "majestic_km":  None,
        "majestic_min": None,
        "transport_text": "",
    }

    lines = []
    if metro:
        lines.append(metro["display"])
    else:
        lines.append("Metro: No operational station within 5 km")

    if key:
        majestic = _distance_to_majestic(lat, lng, key)
        if majestic:
            result["majestic_km"]  = majestic["distance_km"]
            result["majestic_min"] = majestic["duration_min"]
            lines.append(
                f"Majestic (KSRTC Hub): {majestic['distance_km']} km"
                f" — ~{majestic['duration_min']} min drive"
            )

    result["transport_text"] = "\n".join(lines)
    return result


def format_transport_for_area(area_name: str, lat: float, lng: float, api_key: str = "") -> str:
    """Formatted transport block for display in chat."""
    info = get_transport_summary(lat, lng, api_key)
    if not info.get("transport_text"):
        return ""
    return f"\nTransport ({area_name}):\n{info['transport_text']}"