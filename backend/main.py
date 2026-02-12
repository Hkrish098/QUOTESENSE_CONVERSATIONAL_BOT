import os
import joblib
import pandas as pd
import json
from groq import Groq
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict
from fastapi.responses import JSONResponse

from dotenv import load_dotenv
load_dotenv()

# Using a standard dict if schemas.py is giving issues for now
app = FastAPI(title="Quotesense Engine (Stateful)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"], # Explicitly allow your frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# FIX: Ensure API Key is read correctly
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("❌ ERROR: GROQ_API_KEY not found in environment variables!")

client = Groq(api_key=GROQ_API_KEY)
MODEL_NAME = "llama-3.3-70b-versatile"

# Global paths for Render
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "models/blr_rent_model.joblib")
FEATURES_PATH = os.path.join(BASE_DIR, "models/model_features.joblib")
CSV_PATH = os.path.join(BASE_DIR, "cleaned_data_v2_no_leakage.csv")

try:
    model = joblib.load(MODEL_PATH)
    model_features = joblib.load(FEATURES_PATH)
    print("✅ ML Model and Features loaded successfully.")
except Exception as e:
    print(f"❌ ERROR loading models: {e}")

user_sessions: Dict[str, dict] = {}

class ChatRequest(BaseModel):
    user_id: str
    message: str

@app.post("/chat")
async def chat_handler(request: ChatRequest):
    u_id, msg = request.user_id, request.message
    print(f"--- 📨 New Message from {u_id}: {msg} ---")
    
    # 1. Initialize session
    if u_id not in user_sessions:
        user_sessions[u_id] = {feat: 0 for feat in model_features}
        user_sessions[u_id]["stage"] = "collecting"
        print(f"🆕 Initialized new session for {u_id}")

    session = user_sessions[u_id]

    # 2. Improved System Prompt
    system_prompt = f"""
    You are a Bengaluru Rental Expert.
    Current Data: {json.dumps({k: v for k, v in session.items() if v != 0 and k != "stage"})}
    
    Task: Extract property features into JSON using these keys: {model_features}
    
    Mapping Rules:
    - Koramangala, HSR, Jayanagar, JP Nagar -> zone_South: 1
    - Indiranagar, Whitefield, Marathahalli -> zone_East: 1
    - Hebbal, Yelahanka, Manyata -> zone_North: 1
    - Rajajinagar, Malleshwaram -> zone_West: 1
    - "Swimming pool" -> swimming_pool: 1
    
    CRITICAL: Return ONLY JSON. If a value isn't in the message, keep it as it is in Current Data.
    """

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": msg}],
            response_format={"type": "json_object"}
        )
        extracted = json.loads(completion.choices[0].message.content)
        print(f"📥 Groq Extracted: {extracted}")
        
        # Clean the data (Convert None to 0)
        for key, value in extracted.items():
            if value is not None:
                session[key] = value
    except Exception as e:
        print(f"AI Error: {e}")
        return {"response": "I'm having a bit of a brain fog. Could you repeat that?", "status": "incomplete"}

    # 3. Decision Logic & Prediction Gate
    has_bhk = (session.get('size_bhk') or 0) > 0
    has_sqft = (session.get('total_sqft') or 0) > 0
    has_zone = any((session.get(z) or 0) == 1 for z in ['zone_East', 'zone_North', 'zone_South', 'zone_West'])

    # --- NEW STAGE MANAGER LOGIC ---
    if has_bhk and has_sqft and has_zone:
        # If we have the data but haven't asked for permission yet
        if session.get("stage") == "collecting":
            session["stage"] = "awaiting_confirmation"
            area = "South" if session.get('zone_South') else "East" if session.get('zone_East') else "North" if session.get('zone_North') else "West"
            return {
                "response": f"Got it! I have a {session['size_bhk']}BHK in {area} Bengaluru with {session['total_sqft']} sqft. Should I run the rental estimate now?",
                "status": "incomplete"
            }
        
        # If user says 'yes' or 'go ahead' while in the confirmation stage
        if session.get("stage") == "awaiting_confirmation" and any(word in msg for word in ["yes", "yeah", "go ahead", "do it", "sure"]):
            print("🎯 User confirmed. Running Prediction...")
            data_for_df = {feat: [session.get(feat, 0)] for feat in model_features}
            input_df = pd.DataFrame(data_for_df)
            prediction = model.predict(input_df)[0]
            
            session["stage"] = "complete" # Move to complete
            return {
                "response": f"Excellent! The estimated market rent is ₹{round(prediction, -2):,}. Shall I tell you more about the nearby amenities?",
                "status": "complete",
                "prediction": round(prediction, -2),
                "data": {"total_sqft": session['total_sqft'], "location_name": "Bengaluru"}
            }

    # --- HANDLE REPETITIVE 'YES' AFTER COMPLETION ---
    # --- HANDLE REPETITIVE 'YES' AFTER COMPLETION ---
    if session.get("stage") == "complete":
        if any(word in msg.lower() for word in ["yes", "amenities", "tell me"]):
            session["stage"] = "amenities_info"
            return {
                "response": "In this area, you'll find great parks and schools. Anything else I can help with?",
                "status": "complete"
            }
        else:
            return {
                "response": "No problem! Let me know if you want to estimate another property.",
                "status": "complete"
            }
    # --- 4. FINAL CATCH-ALL (Add this at the very end of the function) ---
    if not has_zone:
        resp = "Which part of Bengaluru are you looking in? (e.g., Koramangala, Indiranagar)"
    elif not has_bhk:
        resp = f"I've noted the location! Are you looking for a 1BHK, 2BHK, or 3BHK?"
    else:
        resp = f"Got it, a {session.get('size_bhk')}BHK. Roughly how many sqft is the property?"

    return {
        "response": resp, 
        "status": "incomplete", 
        "data": session
    }