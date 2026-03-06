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
from transport_info import format_transport_for_area
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
class ChatRequest(BaseModel):
    user_id: str
    message: str


def _empty_session() -> dict:
    return {
        "location": "", "rent_price_inr_per_month": 0, "property_type": None,
        "persona": None, "size_bhk": 0, "total_sqft": 0, "furnishing": "",
        "marital_status": "", "family_hubs": [], "structure": "",
        "Sharing": 0, "gender_preference": "", "nearby_hub": "",
        "bath": 0, "balcony": 0,
        "two_wheeler_parking": False, "four_wheeler_parking": False,
        "gym_nearby": False, "food_included": False,
        "has_wifi": False, "has_washing_machine": False,
        "history": [],
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
    persona = session.get("persona")
    lines = []

    if session.get("location"):
        lines.append(f"📍 Location: {session['location']}")

    # FIX [1]: For PG, NEVER show BHK — show Sharing only.
    #          For Home, NEVER show Sharing — show BHK only.
    if persona == "pg":
        sharing = safe_int(session.get("Sharing"), 0)
        if sharing > 0:
            label = {1: "Single", 2: "Double", 3: "Triple", 4: "Four"}.get(sharing, f"{sharing}")
            lines.append(f"🤝 Sharing: {label} Sharing")
        if session.get("gender_preference"):
            lines.append(f"🚻 Gender: {session['gender_preference']} PG")
    else:
        bhk = safe_int(session.get("size_bhk"), 0)
        if bhk > 0:
            lines.append(f"🛏️  BHK: {bhk} BHK")

    budget = safe_int(session.get("rent_price_inr_per_month"), 0)
    if budget > 0:
        lines.append(f"💰 Budget: ₹{budget:,}/month")

    if persona != "pg":
        sqft = safe_int(session.get("total_sqft"), 0)
        if sqft > 0:
            lines.append(f"📐 Area: {sqft} sqft")

        if session.get("furnishing"):
            lines.append(f"🛋️  Furnishing: {session['furnishing']}")

        if session.get("marital_status"):
            lines.append(f"👫 Status: {session['marital_status']}")

        hubs = session.get("family_hubs", [])
        if hubs:
            lines.append(f"🏢 Work/School Hubs: {', '.join(hubs)}")

        if safe_int(session.get("bath"), 0) > 0:
            lines.append(f"🚿 Bathrooms: {session['bath']}")

        if safe_int(session.get("balcony"), 0) > 0:
            lines.append(f"🌿 Balconies: {session['balcony']}")

    # PG-specific info
    if persona == "pg" and session.get("nearby_hub"):
        lines.append(f"🏫 Near: {session['nearby_hub']}")

    # Amenities (relevant to both)
    amenity_icons = []
    if session.get("two_wheeler_parking"):   amenity_icons.append("🏍️ Bike Parking")
    if session.get("four_wheeler_parking"):  amenity_icons.append("🚗 Car Parking")
    if session.get("gym_nearby"):            amenity_icons.append("💪 Gym")
    if session.get("food_included"):         amenity_icons.append("🍱 Food Included")
    if session.get("has_washing_machine"):   amenity_icons.append("🫧 Washing Machine")
    if amenity_icons:
        lines.append(f"✅ Amenities: {', '.join(amenity_icons)}")

    if not lines:
        return ""

    return "📋 Your Requirements So Far:\n" + "\n".join(f"  {l}" for l in lines)


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
        elif key == "nearby_hub":
            session["nearby_hub"] = val
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

        system_prompt_fn = (
            get_pg_system_prompt if session.get("persona") == "pg" else get_system_prompt
        )
        system_msg = system_prompt_fn(session, [])
        system_msg += f"\n\n### GROUND TRUTH — DO NOT RE-ASK:\n{known_summary}"

        if len(hubs) >= 2:
            system_msg += (
                f"\n\n### MIDPOINT ADVISOR: Family commutes to {', '.join(hubs)}."
                f" Recommend the midpoint. Don't prioritise stated location."
            )

        system_msg += (
            "\n\n### OUTPUT RULES (STRICT):"
            "\n1. Do NOT print any requirements list, dashboard, or header."
            "\n2. Do NOT print 'Your Tatva PG Selections' or any similar header."
            "\n3. Start directly with the conversational message."
            "\n4. Ask EXACTLY 2 questions bundled in one reply (follow the phase strategy)."
            "\n5. When ready to show listings, say: 'Ready to see your matches? Just say show me! 🏠🔥'"
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
            essentials = ["rent_price_inr_per_month", "Sharing", "gender_preference"]
        else:
            essentials = ["rent_price_inr_per_month", "size_bhk"]
            if len(hubs) < 2:
                essentials.append("location")

        has_enough_data = all(
            session.get(k) not in (0, "", None, []) for k in essentials
        )
        user_wants_show = bool(
            re.search(r"\b(show|list|search|find|ok show|show me)\b", msg.lower())
        )

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

                # Nearby hub
                if session.get("nearby_hub"):
                    query = query.ilike("nearby_hub", f"%{session['nearby_hub']}%")

            # ── Home-specific DB filters ───────────────────────────────────
            else:
                family_coords = []
                for hub in hubs:
                    try:
                        c = get_coordinates(hub)
                        if c and c.get("lat") and c.get("lng"):
                            family_coords.append({"name": hub, **c})
                    except Exception:
                        print(f"⚠️ Geocoding failed: {hub}")

                using_midpoint = False
                midpoint_lat = midpoint_lng = None
                recommendation_text = ""
                transport_text = ""

                if len(family_coords) >= 2:
                    try:
                        midpoint_lat = sum(c["lat"] for c in family_coords) / len(family_coords)
                        midpoint_lng = sum(c["lng"] for c in family_coords) / len(family_coords)
                        hub_names = ", ".join(c["name"] for c in family_coords)
                        query = (
                            query
                            .gte("latitude",  midpoint_lat - 0.04).lte("latitude",  midpoint_lat + 0.04)
                            .gte("longitude", midpoint_lng - 0.04).lte("longitude", midpoint_lng + 0.04)
                        )
                        recommendation_text = (
                            f"\n\n💡 **Tatva Midpoint Choice:**\n"
                            f"Optimal midpoint between **{hub_names}** — "
                            f"saves everyone daily commute time and transport cost! 🚀"
                        )
                        using_midpoint = True
                        if GOOGLE_API_KEY:
                            transport_text = format_transport_for_area(
                                "Midpoint Area", midpoint_lat, midpoint_lng, GOOGLE_API_KEY
                            )
                    except Exception:
                        traceback.print_exc()

                if not using_midpoint and session.get("location"):
                    query = query.ilike("location", f"%{session['location']}%")

                raw_size = session.get("size_bhk")
                search_size = safe_int(raw_size) if raw_size and raw_size != 0 else 1
                query = query.eq("size_bhk", search_size)

                budget = safe_int(session.get("rent_price_inr_per_month"), 0)
                if budget > 0:
                    query = query.lte("rent_price_inr_per_month", budget)

            # ── Execute ────────────────────────────────────────────────────
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
                f"🎉 Found **{len(formatted)} matches** for you!"
                f"{rec_text}{t_text}"
            )
            return JSONResponse(content={
                "response":   final_msg,
                "status":     "complete",
                "properties": formatted,
                "data":       session,
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
            return JSONResponse(content={"response": reply, "status": "incomplete", "data": session})

        # Normal conversational turn
        session["history"] += [
            {"role": "user",      "content": msg},
            {"role": "assistant", "content": bot_reply},
        ]
        return JSONResponse(content={"response": bot_reply, "status": "incomplete", "data": session})

    except Exception:
        print("\n💥 FATAL UNHANDLED ERROR:")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={
            "response": "Oops! A backend hiccup — please try again! 🔄",
            "status": "error",
        })