import os
import joblib
import pandas as pd
import json
from groq import Groq
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict
from schemas import RentalState  # Import your standardized object

app = FastAPI(title="Quotesense Engine (Stateful)")

# --- 1. CONFIGURATION & CORS ---
# Enable CORS so your local frontend can talk to your deployed Render backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL_NAME = "llama-3.3-70b-versatile"

# Load ML Model and Features
model = joblib.load("models/blr_rent_model.joblib")
model_features = joblib.load("models/model_features.joblib")

# Session Memory (Global Dictionary)
user_sessions: Dict[str, dict] = {}

class ChatRequest(BaseModel):
    user_id: str
    message: str

# --- 2. THE CORE LOGIC ---
@app.post("/chat")
async def chat_handler(request: ChatRequest):
    u_id, msg = request.user_id, request.message.lower()

    # Initialize session if new
    if u_id not in user_sessions:
        user_sessions[u_id] = RentalState().model_dump()
    
    session = user_sessions[u_id]

    # --- STAGE A: Handle Follow-up First (The Gatekeeper) ---
    if session.get("stage") == "awaiting_amenities":
        if any(word in msg for word in ["yes", "sure", "tell me", "okay"]):
            # Logic to pull average stats from your dataset
            df = pd.read_csv("cleaned_data_v2_no_leakage.csv")
            active_zone = next((z for z in ['zone_East', 'zone_North', 'zone_South', 'zone_West'] if session.get(z) == 1), "zone_South")
            gym_pct = round(df[df[active_zone] == 1]['gym_nearby'].mean() * 100)
            
            session["stage"] = "complete"
            return {
                "response": f"Interesting choice! In that zone, about {gym_pct}% of properties include a gym. Anything else I can help with?",
                "status": "complete"
            }
        else:
            session["stage"] = "complete"
            return {"response": "No problem! Let me know if you want to estimate another property.", "status": "complete"}

    # --- STAGE B: Stateful LLM Extraction (The Bucket Strategy) ---
    # We pass the CURRENT session back to the LLM so it knows what's missing
    system_prompt = f"""
    You are a Bangalore Rental Expert. Extract features from the message into JSON.
    CURRENT DATA BUCKET: {json.dumps({k: v for k, v in session.items() if v != 0})}
    
    Rules:
    1. Keys to use: {model_features}
    2. Area Mapping:
       - East: Indiranagar, Whitefield -> zone_East: 1, location_premium_index: 33
       - North: Hebbal, Yelahanka -> zone_North: 1, location_premium_index: 21
       - South: Koramangala, HSR Layout -> zone_South: 1, location_premium_index: 31
    3. Return ONLY JSON. Do not guess values; if missing, keep them as they are in the Current Data.
    """

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": msg}
            ],
            response_format={"type": "json_object"}
        )
        extracted_data = json.loads(completion.choices[0].message.content)
        session.update(extracted_data) # Update the global session state
    except Exception as e:
        print(f"Groq Error: {e}")

    # --- STAGE C: Decision Logic & ML Prediction ---
    has_bhk = session.get('size_bhk', 0) > 0
    has_sqft = session.get('total_sqft', 0) > 0
    has_zone = any(session.get(z, 0) == 1 for z in ['zone_East', 'zone_North', 'zone_South', 'zone_West'])

    if has_bhk and has_sqft and has_zone:
        # Final Bucket is full -> Run Prediction
        input_df = pd.DataFrame([session])[model_features]
        prediction = model.predict(input_df)[0]
        
        session["stage"] = "awaiting_amenities" # Transition to follow-up stage
        
        return {
            "response": f"Excellent! For that {session['size_bhk']}BHK ({session['total_sqft']} sqft), the estimated market rent is ₹{round(prediction, -2):,}. Shall I tell you more about the nearby amenities?",
            "status": "complete",
            "prediction": round(prediction, -2),
            "data": session
        }
    else:
        # Determine what is still missing (Conversational Flow)
        if not has_zone:
            resp = "Which area in Bangalore are you looking at? (e.g., HSR Layout, Indiranagar)"
        elif not has_bhk:
            resp = "Got the area! Are you looking for a 1BHK, 2BHK, or 3BHK?"
        else:
            resp = f"I've noted the {session['size_bhk']}BHK. Roughly how many sqft is the property?"

        return {"response": resp, "status": "incomplete", "data": session}