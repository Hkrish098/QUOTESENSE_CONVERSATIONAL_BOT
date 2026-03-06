"""
transport_info.py — Google Maps transport connectivity for a given location.

Provides:
  get_transport_summary(lat, lng, api_key) → dict with:
    - nearby_metro   : list of metro station names within 2km
    - nearest_metro  : closest metro station + walking distance
    - majestic_km    : driving distance to Kempegowda Bus Terminal (Majestic)
    - majestic_time  : driving time to Majestic
    - transport_text : human-readable summary for the bot to show
"""

import os
import requests
from typing import Optional

# Kempegowda Bus Terminal (Majestic) — Bengaluru's central transit hub
MAJESTIC_LAT = 12.9767
MAJESTIC_LNG = 77.5713

GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")


def _nearby_metro_stations(lat: float, lng: float, api_key: str, radius_m: int = 2000) -> list[dict]:
    """
    Returns metro stations within radius_m metres using Google Places Nearby Search.
    Each entry: {"name": str, "distance_m": int}
    """
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lng}",
        "radius": radius_m,
        "keyword": "metro station",
        "key": api_key,
    }
    try:
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()
        stations = []
        for place in data.get("results", [])[:5]:
            loc = place["geometry"]["location"]
            # Rough distance in metres using bounding box
            dlat = abs(loc["lat"] - lat) * 111_000
            dlng = abs(loc["lng"] - lng) * 111_000 * 0.85
            dist = int((dlat**2 + dlng**2) ** 0.5)
            stations.append({"name": place["name"], "distance_m": dist})
        # Sort by distance
        stations.sort(key=lambda x: x["distance_m"])
        return stations
    except Exception as e:
        print(f"⚠️ Metro lookup failed: {e}")
        return []


def _distance_matrix(
    origin_lat: float, origin_lng: float,
    dest_lat: float, dest_lng: float,
    api_key: str,
    mode: str = "driving",
) -> dict:
    """
    Returns {"distance_km": float, "duration_min": int} via Google Distance Matrix.
    """
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins":      f"{origin_lat},{origin_lng}",
        "destinations": f"{dest_lat},{dest_lng}",
        "mode":         mode,
        "key":          api_key,
    }
    try:
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()
        element = data["rows"][0]["elements"][0]
        if element["status"] != "OK":
            return {}
        return {
            "distance_km": round(element["distance"]["value"] / 1000, 1),
            "duration_min": round(element["duration"]["value"] / 60),
        }
    except Exception as e:
        print(f"⚠️ Distance matrix failed: {e}")
        return {}


def get_transport_summary(lat: float, lng: float, api_key: str = "") -> dict:
    """
    Returns transport connectivity info for a given lat/lng.

    Returns dict:
      nearby_metro   : list[dict]  (name, distance_m)
      nearest_metro  : str | None
      majestic_km    : float | None
      majestic_min   : int | None
      transport_text : str  (ready for display)
    """
    key = api_key or GOOGLE_API_KEY
    if not key:
        return {"transport_text": ""}

    result = {
        "nearby_metro":  [],
        "nearest_metro": None,
        "majestic_km":   None,
        "majestic_min":  None,
        "transport_text": "",
    }

    # Metro stations
    stations = _nearby_metro_stations(lat, lng, key)
    result["nearby_metro"] = stations
    if stations:
        closest = stations[0]
        walk_min = round(closest["distance_m"] / 80)   # ~80 m/min walking
        result["nearest_metro"] = closest["name"]
        metro_line = f"🚇 **Nearest Metro:** {closest['name']} (~{walk_min} min walk)"
    else:
        metro_line = "🚇 **Metro:** No metro station within 2 km"

    # Distance to Majestic
    majestic = _distance_matrix(lat, lng, MAJESTIC_LAT, MAJESTIC_LNG, key)
    if majestic:
        result["majestic_km"]  = majestic["distance_km"]
        result["majestic_min"] = majestic["duration_min"]
        majestic_line = (
            f"🚌 **To Majestic (KSRTC Hub):** "
            f"{majestic['distance_km']} km · ~{majestic['duration_min']} min drive"
        )
    else:
        majestic_line = ""

    lines = [metro_line]
    if majestic_line:
        lines.append(majestic_line)

    result["transport_text"] = "\n".join(lines)
    return result


def format_transport_for_area(area_name: str, lat: float, lng: float, api_key: str = "") -> str:
    """
    Returns a formatted transport block for display in listings or midpoint message.
    """
    info = get_transport_summary(lat, lng, api_key)
    if not info.get("transport_text"):
        return ""
    return f"\n\n🗺️ **Transport Connectivity — {area_name}:**\n{info['transport_text']}"