"""
main.py — FastAPI chat endpoint for Tatva Bengaluru Rental Bot.

Fixes in this version:
  [1] Dashboard — no border box, plain emoji list, NEVER shows BHK for PG persona.
  [2] _strip_llm_dashboard — catches PG-specific headers:
      "✨ Your Tatva PG Selections", "👦/👧 Gender Preference:" lines.
  [3] PG DB query — uses `preferred_tenants` and `has_gym`/`food_included` columns.
  [4] Extractor — for PG, size_bhk is NEVER written directly (only via Sharing mirror).
  [5] _repair_session_from_history — PG: never writes size_bhk directly.
"""

import os
import json
import re
import traceback
from typing import Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from groq import Groq
from supabase import create_client, Client, ClientOptions

from prompts import get_system_prompt, get_pg_system_prompt
from ai_tools import get_extraction_prompt, amenity_explicitly_mentioned
from schemas import RentalExtractionMonitor
from recommender import get_smart_suggestions
from geospatial import get_coordinates
from transport_info import format_transport_for_area, get_transport_summary, reverse_geocode_area
from utils import safe_int, coerce_bool

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://quotesense-conversational-bot.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY"),
    options=ClientOptions(postgrest_client_timeout=60),
)
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

user_sessions: Dict[str, dict] = {}

BOOL_AMENITY_FIELDS = frozenset({
    "two_wheeler_parking", "four_wheeler_parking",
    "gym_nearby", "food_included", "has_wifi", "has_washing_machine",
})
INT_AMENITY_FIELDS = frozenset({"bath", "balcony"})

# ─────────────────────────────────────────────────────────────────────────────
# PG Hub Registry — GROUND TRUTH from database.
# Keys = normalised location names (must match DB `location` column exactly).
# Values = list of `nearby_hub` values that exist in the DB for that location.
# Used to: (1) show users real options, (2) validate extracted hub names,
#           (3) skip the nearby_hub filter if user gave a non-matching name.
# ─────────────────────────────────────────────────────────────────────────────
PG_LOCATION_HUBS: dict[str, list[str]] = {
    "BTM Layout":             ["BTM 2nd Stage", "IIM Bangalore", "Silk Board", "Udupi Garden"],
    "Bellandur":              ["Central Mall", "Eco World", "Embassy Tech Village", "RMZ Ecospace"],
    "Electronic City Phase 1":["IIIT Bangalore", "Infosys Campus", "PES University (EC Campus)", "Wipro Gate 1"],
    "Electronic City Phase 2":["Biocon", "Tata Consultancy Services", "Tech Mahindra"],
    "HSR Layout":             ["27th Main Road", "HSR BDA Complex", "NIFT Bangalore", "Oxford College"],
    "Hebbal":                 ["Columbia Asia Hospital", "Hebbal Flyover", "Manyata Tech Park"],
    "Indiranagar":            ["100ft Road", "CMH Road", "ESI Hospital", "Toit Brewery"],
    "Jayanagar":              ["Jain University", "Jayanagar 4th Block", "RV Road"],
    "Koramangala":            ["Christ University", "Jyoti Nivas College", "Koramangala 80ft Road", "St. Johns Hospital"],
    "Marathahalli":           ["Innovative Multiplex", "Kalamandir", "Prestige Tech Park"],
    "Mathikere":              ["IISc Bangalore", "MS Ramaiah Institute", "Yeshwanthpur Metro"],
    "Nagavara":               ["Elements Mall", "Lumbini Gardens", "Manyata Tech Park"],
    "Rajajinagar":            ["Iskcon Temple", "Orion Mall", "World Trade Center"],
    "Sarjapur Road":          ["Decathlon Sarjapur", "RGA Tech Park", "Wipro Sarjapur"],
    "Whitefield":             ["GR Tech Park", "ITPL", "MVJ College", "Sigma Soft Tech Park"],
}

# Flat set of ALL valid hub names (for fast lookup)
ALL_PG_HUBS: frozenset[str] = frozenset(
    hub for hubs in PG_LOCATION_HUBS.values() for hub in hubs
)


def _get_pg_hubs_for_location(location: str) -> list[str]:
    """Returns known nearby_hub options for a given PG location. Case-insensitive."""
    loc_lower = location.strip().lower()
    for key, hubs in PG_LOCATION_HUBS.items():
        if key.lower() == loc_lower or loc_lower in key.lower():
            return hubs
    return []


def _validate_pg_hub(hub_name: str, location: str = "") -> str | None:
    """
    Returns the exact DB hub name if hub_name matches a known hub (exact or partial),
    otherwise returns None.
    Optionally restricts to hubs available in a specific location.
    """
    if not hub_name:
        return None
    hub_lower = hub_name.strip().lower()
    # First try exact match in all hubs
    for known in ALL_PG_HUBS:
        if known.lower() == hub_lower:
            return known
    # Partial match — hub_lower is a substring of a known hub (e.g. "80ft road" → "Koramangala 80ft Road")
    for known in ALL_PG_HUBS:
        if hub_lower in known.lower() or known.lower() in hub_lower:
            # If location given, restrict to that location's hubs
            if location:
                loc_hubs = _get_pg_hubs_for_location(location)
                if known in loc_hubs:
                    return known
            else:
                return known
    return None



# ─────────────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    user_id: str
    message: str


def _empty_session() -> dict:
    return {
        "location": "", "rent_price_inr_per_month": 0, "property_type": None,
        "persona": None, "size_bhk": 0, "total_sqft": 0, "furnishing": "",
        "marital_status": "", "family_hubs": [], "structure": "",
        "Sharing": 0, "gender_preference": "", "nearby_hub": "",
        "pg_hub_state": None,   # None | "offered" | "confirmed"
        "bath": 0, "balcony": 0,
        "two_wheeler_parking": False, "four_wheeler_parking": False,
        "gym_nearby": False, "food_included": False,
        "has_wifi": False, "has_washing_machine": False,
        "history": [],
        # Midpoint state machine
        "midpoint_state": None,      # None | "offered" | "confirmed"
        "midpoint_lat": None,
        "midpoint_lng": None,
        "midpoint_area": "",         # reverse-geocoded area name
        "family_coords_cache": [],   # [{name, lat, lng}, ...]
    }


def _detect_persona(msg: str) -> Optional[str]:
    lower = msg.lower()
    if any(k in lower for k in ("pg", "hostel", "colive", "co-living", "paying guest")):
        return "pg"
    if any(k in lower for k in ("home", "apartment", "family", "house", "villa", "flat", "bhk")):
        return "home"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# FIX [1]: Dashboard — no border, plain list, BHK hidden for PG persona
# ─────────────────────────────────────────────────────────────────────────────
def _build_dashboard(session: dict) -> str:
    """Server-side requirements dashboard. Clean numbered list, minimal emoji."""
    persona = session.get("persona")
    lines = []
    n = 1

    if session.get("location"):
        lines.append(f"  {n}. Location       : {session['location']}")
        n += 1

    if persona == "pg":
        sharing = safe_int(session.get("Sharing"), 0)
        if sharing > 0:
            label = {1: "Single", 2: "Double", 3: "Triple", 4: "Four"}.get(sharing, str(sharing))
            lines.append(f"  {n}. Sharing        : {label}")
            n += 1
        if session.get("gender_preference"):
            lines.append(f"  {n}. Type           : {session['gender_preference']} PG")
            n += 1
    else:
        bhk = safe_int(session.get("size_bhk"), 0)
        if bhk > 0:
            lines.append(f"  {n}. BHK            : {bhk} BHK")
            n += 1

    budget = safe_int(session.get("rent_price_inr_per_month"), 0)
    if budget > 0:
        lines.append(f"  {n}. Budget         : ₹{budget:,}/month")
        n += 1

    if persona != "pg":
        sqft = safe_int(session.get("total_sqft"), 0)
        if sqft > 0:
            lines.append(f"  {n}. Area           : {sqft} sqft")
            n += 1
        if session.get("furnishing"):
            lines.append(f"  {n}. Furnishing     : {session['furnishing']}")
            n += 1
        if session.get("marital_status"):
            lines.append(f"  {n}. Status         : {session['marital_status']}")
            n += 1
        hubs = session.get("family_hubs", [])
        if hubs:
            lines.append(f"  {n}. Work Hubs      : {', '.join(hubs)}")
            n += 1
        if safe_int(session.get("bath"), 0) > 0:
            lines.append(f"  {n}. Bathrooms      : {session['bath']}")
            n += 1
        if safe_int(session.get("balcony"), 0) > 0:
            lines.append(f"  {n}. Balcony        : Yes")
            n += 1

    if persona == "pg" and session.get("nearby_hub"):
        lines.append(f"  {n}. Near           : {session['nearby_hub']}")
        n += 1

    amenities = []
    if session.get("two_wheeler_parking"):   amenities.append("Bike Parking")
    if session.get("four_wheeler_parking"):  amenities.append("Car Parking")
    if session.get("gym_nearby"):            amenities.append("Gym Nearby")
    if session.get("food_included"):         amenities.append("Food Included")
    if session.get("has_washing_machine"):   amenities.append("Washing Machine")
    if amenities:
        lines.append(f"  {n}. Amenities      : {', '.join(amenities)}")

    if not lines:
        return ""

    return "— Your Search Criteria —\n" + "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# JSON parser
# ─────────────────────────────────────────────────────────────────────────────
def _strip_comments(s: str) -> str:
    return re.sub(r"\s*//[^\n\"]*", "", s)


def _parse_json_from_text(text: str) -> dict:
    if not text:
        return {}
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*",     "", text)
    text = text.strip()
    for candidate in [text, _strip_comments(text)]:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        for candidate in [match.group(0), _strip_comments(match.group(0))]:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# FIX [2]: Strip ALL LLM-generated dashboard variants (Home AND PG)
# ─────────────────────────────────────────────────────────────────────────────
def _strip_llm_dashboard(text: str) -> str:
    # Strip block headers (home dashboard, PG dashboard, any box)
    text = re.sub(
        r"(?:###\s*(?:STATUS DASHBOARD|📋[^\n]*)|╔═[^\n]*╗|✨\s*Your Tatva PG Selections[^\n]*)[\s\S]*?(?:╚[^\n]*╝\n?|(?=\n\n[A-Z])|\Z)",
        "", text, flags=re.IGNORECASE,
    ).strip()

    # Strip standalone "✨ Your Tatva PG Selections:" line (no block following)
    text = re.sub(r"✨\s*Your Tatva PG Selections[^\n]*\n?", "", text, flags=re.IGNORECASE).strip()

    # Strip inline emoji-label lines (home and PG variants)
    text = re.sub(
        r"(?:📍|🛏️|💰|📐|🛋️|👫|🏢|🚿|🌿|✅|🤝|🚻|🏍️|🚗|💪|🍱|📶|🫧|👦|👧|🏫)[^\n]*\n?",
        "", text,
    ).strip()

    # Collapse blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Merge extracted data into session
# ─────────────────────────────────────────────────────────────────────────────
def _merge_extracted_into_session(raw: dict, session: dict, current_msg: str) -> None:
    persona = session.get("persona")

    # 1. family_hubs
    family_hubs_raw = raw.pop("family_hubs", None)
    if family_hubs_raw:
        hubs_list = (
            family_hubs_raw if isinstance(family_hubs_raw, list)
            else [h.strip() for h in str(family_hubs_raw).split(",")]
        )
        for hub in hubs_list:
            hub = hub.strip()
            if hub and hub.lower() not in ("null", "none", "n/a", ""):
                if hub not in session["family_hubs"]:
                    session["family_hubs"].append(hub)

    # 2. Bool amenity fields — hallucination guard
    for field in list(BOOL_AMENITY_FIELDS):
        if field not in raw:
            continue
        val = raw.pop(field)
        coerced = coerce_bool(val)
        if coerced is True:
            if amenity_explicitly_mentioned(field, current_msg):
                session[field] = True
        elif coerced is False:
            session[field] = False

    # 3. Int amenity fields
    for field in list(INT_AMENITY_FIELDS):
        if field not in raw:
            continue
        val = raw.pop(field)
        parsed = safe_int(val, default=0)
        if parsed > 0:
            session[field] = parsed

    # FIX [4]: For PG, forcibly remove size_bhk from raw before Pydantic
    # so it can NEVER be written directly — only via Sharing mirror below.
    if persona == "pg":
        raw.pop("size_bhk", None)

    # 4. Pydantic validation
    try:
        validated = RentalExtractionMonitor(**raw).model_dump(exclude_none=True)
    except ValidationError as exc:
        print(f"\n⚠️  PYDANTIC WARNING:\n{exc}\n")
        validated = {k: v for k, v in raw.items() if v is not None}
    except Exception:
        traceback.print_exc()
        validated = {}

    # 5. Merge
    for key, val in validated.items():
        if val is None:
            continue
        if key == "size_bhk":
            # Only write size_bhk for Home persona
            if persona != "pg":
                session["size_bhk"] = val
        elif key == "Sharing":
            if persona == "pg":
                # Guard: only accept Sharing when user explicitly stated a type.
                # Prevents SLM inferring "single" from "I am looking for a pg".
                _sharing_kw = [
                    "single", "double", "triple", "four sharing", "quad",
                    "1 sharing", "2 sharing", "3 sharing", "4 sharing",
                    "1-sharing", "2-sharing", "3-sharing",
                    "single sharing", "double sharing", "triple sharing",
                ]
                if any(kw in current_msg.lower() for kw in _sharing_kw):
                    session["Sharing"] = val
                    session["size_bhk"] = val  # mirror for DB query only
        elif key == "marital_status":
            # Guard: only write marital_status if user explicitly stated it.
            # Prevents SLM inferring "Single" from "I want to rent a house".
            _married_kw = ["married", "wife", "husband", "spouse", "partner", "couple"]
            _single_kw  = ["single", "bachelor", "alone", "solo", "by myself", "just me"]
            msg_lower   = current_msg.lower()
            if any(kw in msg_lower for kw in _married_kw + _single_kw):
                session["marital_status"] = val
        elif key == "location":
            # Guard: once family_hubs are confirmed (2+ entries), lock the location.
            # Prevents extractor overwriting location with midpoint area names.
            if len(session.get("family_hubs", [])) < 2:
                session["location"] = val
        elif key == "nearby_hub":
            # Guard: only store hub if it matches a real DB value
            validated_hub = _validate_pg_hub(str(val), session.get("location", ""))
            if validated_hub:
                session["nearby_hub"] = validated_hub
            # else: discard — don't store free-text that won't match DB
        elif key in session:
            session[key] = val
        else:
            session[key] = val


# ─────────────────────────────────────────────────────────────────────────────
# History fallback repair
# ─────────────────────────────────────────────────────────────────────────────
def _repair_session_from_history(session: dict) -> None:
    persona = session.get("persona")
    history = session.get("history", [])
    user_msgs = [e["content"] for e in history if e.get("role") == "user"][-6:]
    combined = " ".join(user_msgs).lower()

    # Budget
    if not session.get("rent_price_inr_per_month"):
        budget_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:k\b|thousand|lakh|lakhs)", combined)
        if budget_match:
            parsed = safe_int(budget_match.group(0).strip())
            if parsed > 0:
                session["rent_price_inr_per_month"] = parsed
        else:
            # plain number like "10000"
            plain = re.search(r"\b(\d{4,6})\b", combined)
            if plain:
                parsed = safe_int(plain.group(1))
                if parsed > 1000:
                    session["rent_price_inr_per_month"] = parsed

    if persona == "pg":
        # Gender
        if not session.get("gender_preference"):
            if any(w in combined for w in ("boys", "male", "gents", "boys pg")):
                session["gender_preference"] = "Boys"
            elif any(w in combined for w in ("girls", "female", "ladies", "girls pg")):
                session["gender_preference"] = "Girls"
            elif any(w in combined for w in ("unisex", "any gender", "mixed")):
                session["gender_preference"] = "Unisex"

        # Sharing — FIX [5]: for PG, set Sharing AND mirror to size_bhk
        if not session.get("Sharing"):
            # Only match EXPLICIT sharing type phrases — NOT "for myself" / "alone"
            # (those just mean the person is searching solo, not that they want single-sharing)
            if any(w in combined for w in ("single sharing", "1 sharing", "1-sharing", "single room")):
                session["Sharing"] = 1
                session["size_bhk"] = 1
            elif any(w in combined for w in ("double sharing", "double room", "2 sharing", "2-sharing")):
                session["Sharing"] = 2
                session["size_bhk"] = 2
            elif any(w in combined for w in ("triple sharing", "triple room", "3 sharing", "3-sharing")):
                session["Sharing"] = 3
                session["size_bhk"] = 3
            elif any(w in combined for w in ("four sharing", "4 sharing", "4-sharing", "quad sharing")):
                session["Sharing"] = 4
                session["size_bhk"] = 4

        # Food
        if not session.get("food_included"):
            if any(w in combined for w in ("food", "meals", "mess", "tiffin", "food included")):
                session["food_included"] = True

        # Gym
        if not session.get("gym_nearby"):
            if any(w in combined for w in ("gym", "fitness", "workout")):
                session["gym_nearby"] = True

    if persona == "home":
        if not session.get("size_bhk"):
            bhk_match = re.search(r"(\d)\s*bhk", combined)
            if bhk_match:
                session["size_bhk"] = int(bhk_match.group(1))

        if not session.get("marital_status"):
            if any(w in combined for w in ("wife", "husband", "married", "spouse", "partner", "family")):
                session["marital_status"] = "Married"
            elif any(w in combined for w in ("single", "alone", "bachelor", "solo")):
                session["marital_status"] = "Single"

    # Location (both)
    if not session.get("location"):
        from location_areas import normalise_area
        loc_match = re.search(
            r"\b(?:at|in|near|around)\s+([A-Za-z][A-Za-z\s]{2,25}?)(?:\s*[,\.\!]|\s*$)",
            " ".join(user_msgs), re.IGNORECASE,
        )
        if loc_match:
            raw_loc = loc_match.group(1).strip()
            normalised = normalise_area(raw_loc)
            if normalised:
                session["location"] = normalised


# ─────────────────────────────────────────────────────────────────────────────
# Midpoint area choice helpers
# ─────────────────────────────────────────────────────────────────────────────

def _hub_matches(hub_name: str, user_msg_lower: str) -> bool:
    """Robust hub name matcher — handles abbreviations, typos, partial names."""
    from location_areas import normalise_area
    hub_lower = hub_name.lower()
    if hub_lower in user_msg_lower:
        return True
    skip = {"the", "and", "near", "area", "road", "main", "cross", "phase", "layout", "city"}
    hub_words = [w for w in hub_lower.split() if len(w) >= 3 and w not in skip]
    msg_words  = set(user_msg_lower.split())
    if any(w in msg_words for w in hub_words):
        return True
    for word in user_msg_lower.split():
        if len(word) >= 3:
            try:
                normalised = normalise_area(word).lower()
                if normalised == hub_lower or hub_lower.startswith(normalised):
                    return True
            except Exception:
                pass
    return False


def _detect_area_choice(msg: str, session: dict) -> str:
    """
    Detects which area option the user chose from the midpoint menu.
    Returns: "midpoint" | "hub_0" | "hub_1" | "hub_2" | "all"

    Order of priority:
      1. Numbered option (2, 3...) or hub name match → hub_N
      2. "all"/"both" keywords or last option number → all
      3. "1"/"first"/midpoint name/"midpoint" → midpoint
      4. Fallback → midpoint
    """
    import re as _re
    lower = msg.strip().lower()
    family_coords = session.get("family_coords_cache", [])
    midpoint_area = (session.get("midpoint_area") or "").lower()

    # 1. Hub check FIRST (highest priority — prevents "all" in "marathahalli" false-positive)
    for i, c in enumerate(family_coords[:3]):
        num = str(i + 2)
        if lower.strip() in (num, f"{num}.", f"option {num}"):
            return f"hub_{i}"
        if _hub_matches(c["name"], lower):
            return f"hub_{i}"

    # 2. "all"/"both" or last numbered option
    last_num = str(len(family_coords) + 2)
    if lower.strip() in (last_num, f"{last_num}.", f"option {last_num}"):
        return "all"
    all_kw = ["show all", "all areas", "all three", "every area", "both areas"]
    if any(k in lower for k in all_kw) or _re.search(r"\ball\b|\bboth\b|\bevery\b", lower):
        return "all"

    # 3. Midpoint
    if lower.strip() in ("1", "1.", "first", "option 1", "midpoint") or \
       (midpoint_area and midpoint_area in lower) or "midpoint" in lower:
        return "midpoint"

    return "midpoint"



def _resolve_search_areas(choice: str, session: dict, family_coords: list) -> list[dict]:
    """
    Converts a choice string into a list of area dicts for DB querying.
    Each dict: {type: "midpoint"|"hub", name, label, lat, lng}
    """
    midpoint_lat  = session.get("midpoint_lat")
    midpoint_lng  = session.get("midpoint_lng")
    midpoint_area = session.get("midpoint_area", "Midpoint Area")

    midpoint_entry = {
        "type": "midpoint", "name": midpoint_area,
        "label": f"{midpoint_area} (Midpoint ⭐)",
        "lat": midpoint_lat, "lng": midpoint_lng,
    }

    if choice == "midpoint":
        return [midpoint_entry]

    if choice == "all":
        areas = [midpoint_entry]
        for c in family_coords:
            areas.append({
                "type": "hub", "name": c["name"],
                "label": c["name"],
                "lat": c["lat"], "lng": c["lng"],
            })
        return areas

    # hub_0, hub_1, hub_2
    try:
        idx = int(choice.split("_")[1])
        c = family_coords[idx]
        return [{
            "type": "hub", "name": c["name"],
            "label": c["name"],
            "lat": c["lat"], "lng": c["lng"],
        }]
    except (IndexError, ValueError):
        return [midpoint_entry]


# ─────────────────────────────────────────────────────────────────────────────
# Session title + action buttons
# ─────────────────────────────────────────────────────────────────────────────

def _generate_session_title(session: dict) -> str:
    """
    Auto-generates a sidebar session title like the Tatva.Build app.
    Examples:
      "1 BHK in Koramangala — ₹20k"
      "Double Sharing Boys PG · HSR Layout"
      "3 BHK Married · Whitefield–Marathahalli midpoint"
    """
    persona = session.get("persona")
    parts   = []

    if persona == "pg":
        sharing = safe_int(session.get("Sharing"), 0)
        gender  = session.get("gender_preference", "")
        label   = {1: "Single", 2: "Double", 3: "Triple", 4: "Four"}.get(sharing, "")
        if label and gender:
            parts.append(f"{label} Sharing {gender} PG")
        elif label:
            parts.append(f"{label} Sharing PG")
        else:
            parts.append("PG")
    else:
        bhk = safe_int(session.get("size_bhk"), 0)
        if bhk:
            parts.append(f"{bhk} BHK")
        else:
            parts.append("Home")

    # Location / midpoint
    midpoint_area = session.get("midpoint_area", "")
    hubs          = session.get("family_hubs", [])
    location      = session.get("location", "")

    if midpoint_area and len(hubs) >= 2:
        hub_short = "–".join(h.split()[0] for h in hubs[:2])
        parts.append(f"near {midpoint_area} ({hub_short} midpoint)")
    elif location:
        parts.append(f"in {location}")

    # Budget
    budget = safe_int(session.get("rent_price_inr_per_month"), 0)
    if budget:
        if budget >= 100_000:
            b_str = f"₹{budget//100000}L"
        elif budget >= 1000:
            b_str = f"₹{budget//1000}k"
        else:
            b_str = f"₹{budget}"
        parts.append(b_str)

    return " · ".join(parts) if parts else "New Search"


def _build_actions(status: str, session: dict) -> list[dict]:
    """
    Returns a list of action button definitions for the frontend to render.
    Each button: {id, label, style}   style: "primary" | "secondary" | "ghost"

    Status values:
      "complete"        → listings shown
      "midpoint_choice" → midpoint menu shown
      "incomplete"      → still collecting info
    """
    persona = session.get("persona")
    actions = []

    if status == "complete":
        actions += [
            {"id": "refine_search", "label": "Refine Search",   "style": "secondary"},
            {"id": "change_area",   "label": "Change Area",     "style": "secondary"},
            {"id": "new_search",    "label": "New Search",      "style": "ghost"},
        ]
        if len(session.get("family_hubs", [])) >= 2:
            actions.insert(0, {
                "id": "show_other_areas", "label": "Try Other Areas", "style": "primary"
            })

    elif status == "midpoint_choice":
        hubs = session.get("family_hubs", [])
        actions.append({"id": "choose_midpoint", "label": "Midpoint (Recommended)", "style": "primary"})
        for i, hub in enumerate(hubs[:3]):
            actions.append({
                "id": f"choose_hub_{i}",
                "label": f"Near {hub}",
                "style": "secondary",
            })
        actions.append({"id": "choose_all", "label": "Show All Areas", "style": "ghost"})

    elif status == "incomplete":
        # Only show if user seems close to done (has location + budget)
        has_basics = (
            session.get("rent_price_inr_per_month", 0) > 0 and
            (session.get("location") or len(session.get("family_hubs", [])) >= 1)
        )
        if has_basics:
            actions.append({"id": "show_me", "label": "Show Listings", "style": "primary"})

    return actions


# ─────────────────────────────────────────────────────────────────────────────
# Chat endpoint
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/chat")
async def chat_handler(request: ChatRequest):
    u_id = request.user_id
    msg  = request.message

    greetings = {"hi", "hello", "hii", "hey", "reset", "start"}
    is_greeting = (msg.lower().strip() in greetings) or (
        any(g in msg.lower() for g in greetings) and len(msg.split()) <= 3
    )

    if is_greeting or u_id not in user_sessions:
        user_sessions[u_id] = _empty_session()
        if is_greeting:
            return JSONResponse(content={
                "response": (
                    "Hey there! 👋 I'm **Tatva**, your Bengaluru Rental Expert! 🏠✨\n\n"
                    "Let's find you the perfect place — fast! 🚀\n\n"
                    "Are you hunting for a **Home/Apartment** for your family, "
                    "or a **PG/Co-living** spot for yourself?"
                ),
                "status": "incomplete",
                "data": user_sessions[u_id],
            })

    session = user_sessions[u_id]

    # Detect persona BEFORE extractor runs
    if not session.get("persona"):
        session["persona"] = _detect_persona(msg)

    try:
        # ══════════════════════════════════════════════════════════════════
        # BRAIN 1 — SLM Extractor
        # ══════════════════════════════════════════════════════════════════
        extraction_messages = [
            {"role": "system", "content": get_extraction_prompt(session)}
        ]
        for entry in session["history"][-4:]:
            if isinstance(entry, dict) and entry.get("role") in ("user", "assistant"):
                extraction_messages.append(entry)
        extraction_messages.append({"role": "user", "content": msg})

        try:
            extract_completion = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=extraction_messages,
                temperature=0,
                max_tokens=400,
            )
            raw_text = extract_completion.choices[0].message.content or ""
            raw_extracted = _parse_json_from_text(raw_text)
            if raw_extracted:
                _merge_extracted_into_session(raw_extracted, session, msg)
        except Exception:
            print("\n⚠️  EXTRACTOR ERROR (non-fatal):")
            traceback.print_exc()

        # History fallback
        _repair_session_from_history(session)

        # ══════════════════════════════════════════════════════════════════
        # BRAIN 2 — LLM Consultant
        # ══════════════════════════════════════════════════════════════════
        hubs = session.get("family_hubs", [])
        known_summary = ", ".join(
            f"{k}: {v}" for k, v in session.items()
            if v not in (0, "", None, [], False) and k != "history"
        )

        persona = session.get("persona")

        system_prompt_fn = (
            get_pg_system_prompt if session.get("persona") == "pg" else get_system_prompt
        )
        system_msg = system_prompt_fn(session, [])
        system_msg += f"\n\n### GROUND TRUTH — DO NOT RE-ASK:\n{known_summary}"

        # For PG: inject the actual available nearby_hubs for the confirmed location
        if persona == "pg" and session.get("location"):
            pg_hubs = _get_pg_hubs_for_location(session["location"])
            if pg_hubs and not session.get("nearby_hub"):
                hub_list = ", ".join(f"\"{h}\"" for h in pg_hubs)
                system_msg += (
                    f"\n\n### PG HUB OPTIONS FOR {session['location'].upper()} (use these EXACT names):"
                    f"\n{hub_list}"
                    f"\nWhen asking about nearby landmark/office/college, present ONLY these options."
                    f" Do NOT accept or store any other hub name the user mentions."
                    f" Format as: 'Which is closest to you — {', '.join(pg_hubs[:3])}?'"
                )
            elif session.get("nearby_hub"):
                system_msg += (
                    f"\n\n### PG HUB CONFIRMED: {session['nearby_hub']}"
                    f"\nDo NOT ask about nearby hub again."
                )

        if len(hubs) >= 2:
            system_msg += (
                f"\n\n### MIDPOINT ADVISOR: Family commutes to {', '.join(hubs)}."
                f" Recommend the midpoint. Don't prioritise stated location."
            )

        system_msg += (
            "\n\n### OUTPUT RULES (STRICT):"
            "\n1. No emojis. Plain text only."
            "\n2. Do NOT print any requirements list, dashboard, or header of any kind."
            "\n3. Start directly with the conversational message — no preamble."
            "\n4. Ask EXACTLY 2 questions per reply (follow the phase strategy)."
            "\n5. No filler phrases: 'Love it!', 'Awesome!', 'Great choice!' are banned."
            "\n6. When ready to show listings, say exactly: \"Ready to search? Say show me.\""
        )

        consultant_messages = [{"role": "system", "content": system_msg}]
        for entry in session["history"][-4:]:
            if isinstance(entry, dict) and entry.get("role") in ("user", "assistant"):
                consultant_messages.append(entry)
        consultant_messages.append({"role": "user", "content": msg})

        try:
            chat_completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=consultant_messages,
            )
        except Exception:
            traceback.print_exc()
            return JSONResponse(content={
                "response": "Checking my database but things are a bit slow right now. Try again in 5 seconds! ⏳",
                "status": "incomplete", "data": session,
            })

        bot_reply = chat_completion.choices[0].message.content
        bot_reply = _strip_llm_dashboard(bot_reply)
        dashboard = _build_dashboard(session)
        if dashboard:
            bot_reply = f"{dashboard}\n\n{bot_reply}"

        # ══════════════════════════════════════════════════════════════════
        # SEARCH TRIGGER — explicit user command only
        # ══════════════════════════════════════════════════════════════════
        persona = session.get("persona")
        target_table = "PG_Listings" if persona == "pg" else "properties"

        if persona == "pg":
            essentials = ["Sharing", "gender_preference", "location"]  # budget optional for PG
        else:
            essentials = ["rent_price_inr_per_month", "size_bhk"]
            if len(hubs) < 2:
                essentials.append("location")

        has_enough_data = all(
            session.get(k) not in (0, "", None, []) for k in essentials
        )
        user_wants_show = bool(
            re.search(r"\b(show|list|search|find|ok show|show me)\b", msg.lower())
        ) or session.get("midpoint_state") in ("offered", "confirmed")  # user replying to/after midpoint menu

        if user_wants_show and has_enough_data:
            query = supabase.table(target_table).select("*")

            # ── PG-specific DB filters ─────────────────────────────────────
            if persona == "pg":
                # Sharing count (stored as size_bhk in PG table)
                sharing_count = safe_int(session.get("Sharing") or session.get("size_bhk"), 1)
                query = query.eq("size_bhk", sharing_count)

                # Gender — PG table uses 'preferred_tenants'
                gender = session.get("gender_preference", "")
                if gender:
                    # Unisex PGs should show for everyone; gender-specific PGs filter strictly
                    if gender != "Unisex":
                        query = query.in_("preferred_tenants", [gender, "Unisex"])

                # Budget
                budget = safe_int(session.get("rent_price_inr_per_month"), 0)
                if budget > 0:
                    query = query.lte("rent_price_inr_per_month", budget)

                # Location
                if session.get("location"):
                    query = query.ilike("location", f"%{session['location']}%")

                # Optional amenity filters
                if session.get("food_included"):
                    query = query.eq("food_included", True)
                if session.get("gym_nearby"):
                    query = query.eq("has_gym", True)

                # Nearby hub — only apply if it's a validated DB value
                hub = session.get("nearby_hub", "")
                if hub and hub in ALL_PG_HUBS:
                    query = query.eq("nearby_hub", hub)

            # ── Home-specific DB filters ───────────────────────────────────
            else:
                # Geocode hubs (use cache if already done)
                family_coords = session.get("family_coords_cache") or []
                if not family_coords:
                    for hub in hubs:
                        try:
                            c = get_coordinates(hub)
                            if c and c.get("lat") and c.get("lng"):
                                family_coords.append({"name": hub, **c})
                        except Exception:
                            print(f"⚠️ Geocoding failed: {hub}")
                    session["family_coords_cache"] = family_coords

                # ── MIDPOINT STATE: "confirmed" → user wants a different area ─
                # Re-detect area choice and search directly (skip the menu).
                if session.get("midpoint_state") == "confirmed":
                    session["midpoint_state"] = "offered"  # allow re-resolution

                # ── MIDPOINT STATE: "offered" → user is choosing area ──────
                if session.get("midpoint_state") == "offered":
                    choice = _detect_area_choice(msg, session)
                    areas_to_search = _resolve_search_areas(choice, session, family_coords)

                    all_results = []
                    transport_blocks = []
                    rec_text = ""

                    for area in areas_to_search:
                        area_query = supabase.table(target_table).select("*")
                        if area["type"] == "midpoint":
                            lat, lng = area["lat"], area["lng"]
                            area_query = (
                                area_query
                                .gte("latitude",  lat - 0.04).lte("latitude",  lat + 0.04)
                                .gte("longitude", lng - 0.04).lte("longitude", lng + 0.04)
                            )
                        else:
                            area_query = area_query.ilike("location", f"%{area['name']}%")

                        raw_size = session.get("size_bhk")
                        search_size = safe_int(raw_size) if raw_size and raw_size != 0 else 1
                        area_query = area_query.eq("size_bhk", search_size)

                        budget = safe_int(session.get("rent_price_inr_per_month"), 0)
                        if budget > 0:
                            area_query = area_query.lte("rent_price_inr_per_month", budget)

                        try:
                            r = area_query.limit(10).execute()
                            all_results.extend(r.data or [])
                        except Exception:
                            traceback.print_exc()

                        # Transport info for each chosen area
                        if GOOGLE_API_KEY and area.get("lat") and area.get("lng"):
                            t = format_transport_for_area(area["label"], area["lat"], area["lng"], GOOGLE_API_KEY)
                            if t:
                                transport_blocks.append(t)

                    session["midpoint_state"] = "confirmed"
                    res_data = all_results

                    if areas_to_search:
                        area_labels = ", ".join(a["label"] for a in areas_to_search)
                        rec_text = f"\n\nSearching near: {area_labels}"
                    transport_text = "\n".join(transport_blocks)

                    # Fall through to shared format + return below
                    # (set using_midpoint so we skip the ilike fallback)
                    using_midpoint = True
                    recommendation_text = rec_text

                # ── MIDPOINT STATE: None → first "show me", calculate midpoint ─
                elif len(family_coords) >= 2:
                    midpoint_lat = sum(c["lat"] for c in family_coords) / len(family_coords)
                    midpoint_lng = sum(c["lng"] for c in family_coords) / len(family_coords)
                    hub_names    = " and ".join(c["name"] for c in family_coords)

                    # Reverse-geocode midpoint to a readable area name
                    midpoint_area = (
                        reverse_geocode_area(midpoint_lat, midpoint_lng, GOOGLE_API_KEY)
                        if GOOGLE_API_KEY else "the midpoint area"
                    )

                    # Transport info for midpoint
                    transport_info = {}
                    transport_text = ""
                    if GOOGLE_API_KEY:
                        transport_info = get_transport_summary(midpoint_lat, midpoint_lng, GOOGLE_API_KEY)
                        transport_text = transport_info.get("transport_text", "")

                    # Store midpoint in session for next turn
                    session["midpoint_state"]      = "offered"
                    session["midpoint_lat"]         = midpoint_lat
                    session["midpoint_lng"]         = midpoint_lng
                    session["midpoint_area"]        = midpoint_area
                    session["family_coords_cache"]  = family_coords

                    # Build the option menu
                    hub_options = []
                    role_labels = ["your", "partner's", "hub 3's"]
                    for _i, _c in enumerate(family_coords[:3]):
                        _role = role_labels[_i] if _i < len(role_labels) else ""
                        hub_options.append(f"  {_i+2}. Near {_c['name']} ({_role} office)")
                    hub_options = "\n".join(hub_options)
                    transport_lines = f"\n  {transport_text.strip()}" if transport_text else ""

                    all_opt_num = len(family_coords) + 2
                    midpoint_msg = (
                        f"{dashboard}\n\n"
                        f"**Commute Midpoint Calculated**\n\n"
                        f"  Midpoint area : {midpoint_area}\n"
                        f"  Between       : {hub_names}"
                        f"{transport_lines}\n\n"
                        f"Where would you like to search?\n\n"
                        f"  1. {midpoint_area} (midpoint — recommended)\n"
                        f"{hub_options}\n"
                        f"  {all_opt_num}. Show listings from all areas\n\n"
                        "Reply with the number or area name."
                    )
                    session["history"] += [
                        {"role": "user",      "content": msg},
                        {"role": "assistant", "content": midpoint_msg},
                    ]
                    return JSONResponse(content={
                        "response":      midpoint_msg,
                        "status":        "midpoint_choice",
                        "actions":       _build_actions("midpoint_choice", session),
                        "session_title": _generate_session_title(session),
                        "data":          session,
                    })

                else:
                    # Single hub or no hubs — direct location search
                    using_midpoint = False
                    recommendation_text = ""
                    transport_text = ""
                    res_data = None  # will be fetched below

                    if session.get("location"):
                        query = query.ilike("location", f"%{session['location']}%")
                    elif family_coords:
                        query = query.ilike("location", f"%{family_coords[0]['name']}%")

                    raw_size = session.get("size_bhk")
                    search_size = safe_int(raw_size) if raw_size and raw_size != 0 else 1
                    query = query.eq("size_bhk", search_size)

                    budget = safe_int(session.get("rent_price_inr_per_month"), 0)
                    if budget > 0:
                        query = query.lte("rent_price_inr_per_month", budget)

                        # ── Execute (skip if state machine already fetched res_data) ──
            if persona != "pg" and session.get("midpoint_state") == "confirmed":
                pass  # res_data already populated by state machine above
            else:
                try:
                    result   = query.limit(15).execute()
                    res_data = result.data
                except Exception as db_err:
                    traceback.print_exc()
                    return JSONResponse(status_code=500, content={
                        "response": "Database connection error. Please try again.",
                        "status": "error", "debug": str(db_err),
                    })

            if not res_data:
                try:
                    fallback_msg = get_smart_suggestions(session, supabase)
                except Exception:
                    traceback.print_exc()
                    fallback_msg = (
                        "Hmm, no exact matches right now 🤔 "
                        "Want to bump the budget a little or try a nearby area?"
                    )
                session["history"] += [
                    {"role": "user",      "content": msg},
                    {"role": "assistant", "content": fallback_msg},
                ]
                reply = f"{dashboard}\n\n{fallback_msg}" if dashboard else fallback_msg
                return JSONResponse(content={"response": reply, "status": "incomplete", "data": session})

            formatted = []
            for item in res_data:
                rent = safe_int(item.get("rent_price_inr_per_month"))
                sqft = safe_int(item.get("total_sqft"))
                if rent == 0:
                    continue
                item["formatted_rent"] = f"₹{rent:,}"
                item["display_sqft"]   = f"{sqft} sqft" if sqft > 0 else "Area not specified"
                formatted.append(item)

            rec_text = recommendation_text if persona != "pg" else ""
            t_text   = transport_text      if persona != "pg" else ""

            final_msg = (
                f"{dashboard}\n\n"
                f"Found {len(formatted)} properties matching your criteria."
                f"{rec_text}{t_text}"
            )
            session_title = _generate_session_title(session)
            return JSONResponse(content={
                "response":      final_msg,
                "status":        "complete",
                "properties":    formatted,
                "actions":       _build_actions("complete", session),
                "session_title": session_title,
                "data":          session,
            })

        elif user_wants_show and not has_enough_data:
            missing = [k for k in essentials if session.get(k) in (0, "", None, [])]
            friendly = {
                "rent_price_inr_per_month": "your budget 💰",
                "Sharing": "sharing type (single/double/triple) 🤝",
                "gender_preference": "Boys/Girls/Unisex preference 🚻",
                "size_bhk": "BHK size 🛏️",
                "location": "preferred area 📍",
            }
            missing_str = " and ".join(friendly.get(k, k) for k in missing)
            reply = f"{dashboard}\n\nAlmost there! 🙌 Just tell me **{missing_str}** and we're ready to go!"
            session["history"] += [
                {"role": "user",      "content": msg},
                {"role": "assistant", "content": reply},
            ]
            return JSONResponse(content={
                "response": reply,
                "status":   "incomplete",
                "actions":  _build_actions("incomplete", session),
                "data":     session,
            })

        # Normal conversational turn
        session["history"] += [
            {"role": "user",      "content": msg},
            {"role": "assistant", "content": bot_reply},
        ]
        return JSONResponse(content={
            "response":      bot_reply,
            "status":        "incomplete",
            "actions":       _build_actions("incomplete", session),
            "session_title": _generate_session_title(session),
            "data":          session,
        })

    except Exception:
        print("\n💥 FATAL UNHANDLED ERROR:")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={
            "response": "Oops! A backend hiccup — please try again! 🔄",
            "status": "error",
        })