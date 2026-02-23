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
from supabase import create_client, Client
from prompts import get_system_prompt
from recommender import get_smart_suggestions # Import the new engine

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

# Supabase Client
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# We keep this for AI extraction compatibility
MODEL_FEATURES = [
    'location', 'size_bhk', 'total_sqft', 'rent_price_inr_per_month', 
    'furnishing', 'bath', 'balcony', 'property_type', 'building_age', 
    'four_wheeler_parking', 'two_wheeler_parking', 'pets_allowed', 
    'dietary_preference', 'swimming_pool', 'gym_nearby'
]

user_sessions: Dict[str, dict] = {}

class ChatRequest(BaseModel):
    user_id: str
    message: str

def safe_int(val, default=0):
    if val is None: return default
    try:
        # 1. Convert to string and remove commas (handles "1,200" or "1,2")
        str_val = str(val).replace(',', '')
        
        # 2. Extract all numeric sequences
        nums = re.findall(r'\d+', str_val)
        
        if nums:
            # Pick the last number found (the most recent edit)
            return int(nums[-1])
        return default
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

        # --- 3. TRIGGER LOGIC ---
        force_pattern = r"\b(search now|show listings|list matches)\b"
        user_forced_it = re.search(force_pattern, msg.lower())
        
        has_location = session.get('location') != ""
        has_bhk = int(float(session.get('size_bhk', 0))) > 0
        should_trigger = (ai_intent == "show_listings" or user_forced_it) and has_location and has_bhk

        # --- 4. SEARCH & FALLBACK BLOCK ---
        if should_trigger:
            query = supabase.table("properties").select("*")
            query = query.ilike("location", f"%{session.get('location')}%")
            query = query.eq("size_bhk", int(float(session.get('size_bhk', 0))))
            
            # Property Type logic
            if any(x in msg.lower() for x in ["villa", "house", "all"]):
                session["property_type"] = "any"
            if session["property_type"] != "any":
                query = query.eq("property_type", session["property_type"])

            # Filter with safe integers
            budget = safe_int(session.get('rent_price_inr_per_month', 0))
            if budget > 0:
                query = query.gte("rent_price_inr_per_month", int(budget - 5000)).lte("rent_price_inr_per_month", int(budget + 5000))

            sqft_val = safe_int(session.get('total_sqft', 0))
            if sqft_val > 0:
                query = query.gte("total_sqft", int(sqft_val * 0.8)).lte("total_sqft", int(sqft_val * 1.2))

            # Step 1: Execute the normal search
            result = query.limit(20).execute()
            properties_list = result.data

            # Step 2: Handle 0 results with the Suggestion Engine
            if len(properties_list) == 0:
                # We only trigger this heavy logic IF the database actually returned zero
                suggestion_msg = get_smart_suggestions(session, supabase)
                
                # Update history so the bot understands it just gave advice
                session["history"].append({"role": "user", "content": msg})
                session["history"].append({"role": "assistant", "content": suggestion_msg})
                
                return {
                    "response": suggestion_msg,
                    "status": "suggestion", 
                    "properties": [],
                    "data": session
                }

            # Step 3: If properties ARE found, format and return them
            formatted_list = []
            for item in properties_list:
                item['formatted_rent'] = f"₹{int(item.get('rent_price_inr_per_month', 0)):,}"
                item['formatted_deposit'] = f"₹{int(item.get('legal_security_deposit', 0)):,}"
                item['parking_badge'] = "Car + Bike" if item.get('four_wheeler_parking') else "2-Wheeler"
                
                society = item.get('society', 'Independent')
                item['display_title'] = f"{item['size_bhk']} BHK in {society}"
                
                formatted_list.append(item)

            clean_bot_reply = bot_reply.split("I've found")[0].strip()
            final_message = f"{clean_bot_reply}\n\nI've found {len(formatted_list)} properties matching your exact criteria! 🏠✨"
            
            return {
                "response": final_message,
                "status": "complete",
                "properties": formatted_list,
                "data": session 
            }
        
        # --- 5. NORMAL FLOW ---
        session["history"].append({"role": "user", "content": msg})
        session["history"].append({"role": "assistant", "content": bot_reply})
        return {"response": bot_reply, "status": "incomplete", "data": session}

    except Exception as e:
        print(f"DEBUG ERROR: {str(e)}")
        return {"response": "I encountered a small hiccup. Please try again!", "status": "error"}