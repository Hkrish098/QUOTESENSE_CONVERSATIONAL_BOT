import os
import json
import re
import pandas as pd
from groq import Groq
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List
from dotenv import load_dotenv
from supabase import create_client, Client,ClientOptions
from prompts import get_system_prompt
from recommender import get_smart_suggestions # Import the new engine
from geospatial import get_coordinates
import time

load_dotenv()
app = FastAPI()
# --- CONFIGURATION ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

options = ClientOptions(
    postgrest_client_timeout=60, # This is the correct way to set 30s timeout
    headers={'X-Client-Info': 'tatva-ai-backend'}
)

supabase: Client = create_client(
    os.getenv("SUPABASE_URL"), 
    os.getenv("SUPABASE_KEY"),
    options=options
)

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# We keep this for AI extraction compatibility
MODEL_FEATURES = [
    'location', 'size_bhk', 'total_sqft', 'rent_price_inr_per_month', 
    'furnishing', 'bath', 'balcony', 'property_type', 'building_age', 
    'four_wheeler_parking', 'two_wheeler_parking', 'pets_allowed', 
    'dietary_preference', 'swimming_pool', 'gym_nearby',
    'marital_status', 'family_hubs' # AI will extract these into the session
]

user_sessions: Dict[str, dict] = {}

class ChatRequest(BaseModel):
    user_id: str
    message: str

def safe_int(val, default=0):
    if val is None: return default
    try:
        # Convert to string, take part before decimal, remove commas
        # "31250.0" -> "31250"
        str_val = str(val).split('.')[0].replace(',', '')
        nums = re.findall(r'\d+', str_val)
        return int(nums[-1]) if nums else default
    except:
        return default

@app.post("/chat")
async def chat_handler(request: ChatRequest):
    u_id, msg = request.user_id, request.message
    
    # --- 1. SESSION RESET & INITIALIZATION ---
    greetings = ["hi", "hello", "hii", "hey", "reset", "start over"]
    is_greeting = msg.lower().strip() in greetings and len(msg.split()) == 1
    
    if is_greeting or u_id not in user_sessions:
        user_sessions[u_id] = {feat: 0 if feat != 'location' else "" for feat in MODEL_FEATURES}
        user_sessions[u_id].update({"history": [], "property_type": "Apartment"})

    session = user_sessions[u_id]

    try:
        # --- 2. AI EXTRACTION ---
        system_msg = get_system_prompt(session, MODEL_FEATURES)
        history_slice = [] if is_greeting else session["history"][-8:]
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system_msg}, *history_slice, {"role": "user", "content": msg}],
            response_format={"type": "json_object"}
        )
        
        res = json.loads(completion.choices[0].message.content)
        extracted = res.get("extracted_data", {})
        bot_reply = res.get("reply", "")
        ai_intent = res.get("intent", "ask_more")

        # Update Session State
        for key, val in extracted.items():
            if val not in [0, None, "", False]:
                if key in ['size_bhk', 'total_sqft', 'rent_price_inr_per_month']:
                    session[key] = safe_int(val)
                else:
                    session[key] = val

       # --- 3. TRIGGER LOGIC (The Secure Gate) ---
        # 1. Define mandatory essentials for a valid search
        essentials = ['location', 'size_bhk', 'rent_price_inr_per_month','marital_status', 'family_hubs']
        has_all_data = all(session.get(k) not in [0, "", None, []] for k in essentials)
        
        # 2. Strict Regex for User Commands
        # This ensures words like "yes" or "ok" don't trigger unless a search verb is used
        force_pattern = r"\b(show|list|search|fetch|find|proceed|see matches)\b"
        user_wants_listings = re.search(force_pattern, msg.lower())

        # 3. Decision Matrix
        # Trigger ONLY IF: (AI says ready OR User forced it) AND we have the core data.
        should_trigger = (ai_intent == "show_listings" or has_all_data) and user_wants_listings

        # --- 4. SEARCH & FALLBACK BLOCK (STABILIZED WITH RETRY) ---
        if should_trigger:
            query = supabase.table("properties").select("*")
            
            # --- PHASE 1: GEOSPATIAL FILTERS ---
            family_coords = []
            if session.get('family_hubs'):
                for hub in session['family_hubs']:
                    try:
                        c = get_coordinates(hub)
                        if c: family_coords.append(c)
                    except: continue

            if len(family_coords) >= 2:
                # FAMILY MODE: Center-point search (FASTEST)
                avg_lat = sum(c['lat'] for c in family_coords) / len(family_coords)
                avg_lng = sum(c['lng'] for c in family_coords) / len(family_coords)
                buffer = 0.04 
                query = query.gte("latitude", avg_lat - buffer).lte("latitude", avg_lat + buffer)
                query = query.gte("longitude", avg_lng - buffer).lte("longitude", avg_lng + buffer)
                print(f"👨‍👩‍👧‍👦 Family Center-Point Search: {avg_lat}, {avg_lng}")

            elif len(family_coords) == 1:
                # SOLO MODE: 2km radius
                lat, lng = family_coords[0]['lat'], family_coords[0]['lng']
                buffer = 0.015
                query = query.gte("latitude", lat - buffer).lte("latitude", lat + buffer)
                query = query.gte("longitude", lng - buffer).lte("longitude", lng + buffer)
                print("👤 Solo Radius Search")

            else:
                # TEXT MODE: ilike search
                query = query.ilike("location", f"%{session.get('location')}%")
                print("📍 Text Search")

            # --- PHASE 2: ATTRIBUTE FILTERS ---
            query = query.eq("size_bhk", safe_int(session.get('size_bhk', 0)))
            
            budget = safe_int(session.get('rent_price_inr_per_month', 0))
            if budget > 0:
                query = query.lte("rent_price_inr_per_month", int(budget + 5000))

            if "independent" in str(session.get('property_type', '')).lower():
                query = query.ilike("property_type", "Independent House")

            # --- PHASE 3: EXECUTION (RETRY LOOP) ---
            properties_list = []
            for attempt in range(3): 
                try:
                    # Execute exactly ONCE here after all filters are set
                    result = query.limit(50).execute()
                    properties_list = result.data
                    break 
                except Exception as dbe:
                    print(f"DB Attempt {attempt+1} failed: {dbe}")
                    time.sleep(1)

            # --- PHASE 4: UI FORMATTING ---
            if len(properties_list) == 0:
                # If no houses found, run the smart suggestion engine
                return {"response": get_smart_suggestions(session, supabase), "status": "suggestion", "properties": [], "data": session}

            # If we found houses, format them for the UI cards
            formatted_list = []
            for item in properties_list:
                item['formatted_rent'] = f"₹{int(item.get('rent_price_inr_per_month', 0)):,}"
                item['display_title'] = f"{item['size_bhk']} BHK in {item.get('society', 'Independent')}"
                formatted_list.append(item)

            # --- PHASE 5: DYNAMIC PERSONALIZATION (Add this now) ---
            # 5.1 Calculate the Map Bounds (search_zone)
            search_zone = None
            if family_coords:
                lats = [c['lat'] for c in family_coords]
                lngs = [c['lng'] for c in family_coords]
                # We add a small buffer (0.02) to the box so it's not too tight
                search_zone = {
                    "min_lat": min(lats) - 0.02,
                    "max_lat": max(lats) + 0.02,
                    "min_lng": min(lngs) - 0.02,
                    "max_lng": max(lngs) + 0.02,
                    "center": {"lat": sum(lats)/len(lats), "lng": sum(lngs)/len(lngs)}
                }

            # 5.2 Recommendation Text (Solo vs Family)
            if session.get('marital_status') in ['Married', 'Family'] or len(family_coords) >= 2:
                hubs_str = " and ".join(session.get('family_hubs', ['work/school']))
                recommendation_text = (
                    f"\n\n💡 **Tatva Family Insight:** I've prioritized the **Golden Midpoint** "
                    f"between {hubs_str} to ensure your family spends less time in traffic! 👨‍👩‍👧‍👦"
                )
            else:
                hubs = session.get('family_hubs', [])
                hub_name = hubs[0] if hubs else "your workplace"
                recommendation_text = (
                    f"\n\n💡 **Tatva Solo Insight:** Since you're moving solo to be near **{hub_name}**, "
                    f"I've optimized for a **15-minute 'Stress-Free' radius**. Welcome to the city! 🚀"
                )
                
            # Define a default center if everything else fails
            default_center = {"lat": 12.9716, "lng": 77.5946}
            final_zone = search_zone if search_zone else {"center": family_coords[0] if family_coords else default_center}

            # Construct the final text response
            clean_bot_reply = bot_reply.split("found")[0].strip()
            final_message = f"{clean_bot_reply}\n\nI've found {len(formatted_list)} matches! 🏠✨{recommendation_text}"

            return {
                "response": final_message,
                "status": "complete",
                "properties": formatted_list,
                "search_zone": final_zone, 
                "family_hubs": family_coords,
                "data": session
            }
        
        # --- 5. NORMAL FLOW ---
        session["history"].append({"role": "user", "content": msg})
        session["history"].append({"role": "assistant", "content": bot_reply})
        return {"response": bot_reply, "status": "incomplete", "data": session}

    except Exception as e:
        print(f"DEBUG ERROR: {str(e)}")
        return {"response": "I encountered a small hiccup. Please try again!", "status": "error"}