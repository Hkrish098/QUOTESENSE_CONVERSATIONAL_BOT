import os
import joblib
import pandas as pd
from groq import Groq
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List
import json

app = FastAPI(title="Nexora-Sentiobot Engine (Groq Powered)")

# --- 1. CONFIGURATION ---
# Get your key from: https://console.groq.com/
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL_NAME = "llama-3.3-70b-versatile"

# Load ML Model and Features
model = joblib.load("models/blr_rent_model.joblib")
model_features = joblib.load("models/model_features.joblib")

# Session Memory
user_sessions: Dict[str, dict] = {}

class ChatRequest(BaseModel):
    user_id: str
    message: str

# --- 2. THE CORE LOGIC ---
@app.post("/chat")
async def chat_handler(request: ChatRequest):
    user_id = request.user_id
    user_msg = request.message

    if user_id not in user_sessions:
        # Initialize with zeros for all 43 columns in your dataset
        user_sessions[user_id] = {feat: 0 for feat in model_features}

    # STEP A: Groq Feature Extraction
    # We tell the AI to map locations to zones (East, West, North, South)
    system_prompt = f"""
    You are a Bangalore Real Estate Data Extractor. 
    Extract details from the user's message into JSON.
    
    Rules:
    1. Keys to use: {model_features}
    2. Area Mapping:
       - East: Indiranagar, Whitefield, Marathahalli, Bellandur -> zone_East: 1
       - North: Hebbal, Yelahanka, Manyata, RT Nagar -> zone_North: 1
       - South: Koramangala, HSR Layout, Jayanagar, JP Nagar, Electronic City -> zone_South: 1
       - West: Rajajinagar, Kengeri, Vijayanagar -> zone_West: 1
    3. If they say "30k", ignore it (we are predicting rent, not filtering by it).
    4. If they say "house" or "flat", assume size_bhk is 1 if not specified, but it's better to ask.
    5. Return ONLY JSON.
    """

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ],
            response_format={"type": "json_object"}
        )
        extracted_data = json.loads(completion.choices[0].message.content)
        user_sessions[user_id].update(extracted_data)
    except Exception as e:
        print(f"Groq Error: {e}")

    # STEP B: Decision Logic
    current_data = user_sessions[user_id]
    
    # Check for the absolute essentials for your Gradient Boosting model
    has_bhk = current_data.get('size_bhk', 0) > 0
    has_sqft = current_data.get('total_sqft', 0) > 0
    has_zone = any(current_data.get(z, 0) == 1 for z in ['zone_East', 'zone_North', 'zone_South', 'zone_West'])

    if has_bhk and has_sqft and has_zone:
        # Prepare data for model
        input_df = pd.DataFrame([current_data])[model_features]
        # Your Gradient Boosting model works its magic here
        prediction = model.predict(input_df)[0]
        
        return {
            "response": f"Excellent! For that {current_data['size_bhk']}BHK ({current_data['total_sqft']} sqft), the estimated market rent is ₹{round(prediction, -2):,}. Shall I tell you more about the nearby amenities?",
            "status": "complete"
        }
    else:
        # Conversation flow
        if not has_zone:
            resp = "Which area in Bangalore are you looking at? (e.g., Koramangala, Hebbal, etc.)"
        elif not has_bhk:
            # Acknowledgement makes it feel human
            area = "South Bangalore" if current_data.get('zone_South') else "that area"
            resp = f"I've noted {area}! Are you looking for a 1BHK, 2BHK, or 3BHK?"
        elif not has_sqft:
            resp = f"Got it, a {current_data['size_bhk']}BHK. Roughly how many sqft is the property?"
        else:
            resp = "Just one last thing—any amenities like a gym or pool?"