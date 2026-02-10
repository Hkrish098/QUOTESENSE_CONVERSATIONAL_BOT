from fastapi import FastAPI
from pydantic import BaseModel
import joblib
import pandas as pd

app = FastAPI()

# Load model and feature list
model = joblib.load("models/blr_rent_model.joblib")
model_features = joblib.load("models/model_features.joblib")

# Temporary memory (In production, this will be Supabase)
user_sessions = {}

@app.post("/chat")
async def chat_handler(user_id: str, message: str):
    # 1. SEND message to LLM (Gemini/OpenAI) 
    # 2. ASK LLM: "Extract rental features from this text: {message}"
    # 3. LLM returns JSON (e.g., {"size_bhk": 2})
    
    # 4. Update session
    if user_id not in user_sessions:
        user_sessions[user_id] = {feat: 0 for feat in model_features} # Default everything to 0
    
    # Update features from LLM result...
    
    # 5. Check if we have enough to predict
    if user_sessions[user_id]['total_sqft'] > 0 and user_sessions[user_id]['size_bhk'] > 0:
        prediction = model.predict(pd.DataFrame([user_sessions[user_id]]))[0]
        return {"response": f"Based on what you told me, the estimated rent is ₹{round(prediction)}.", "complete": True}
    else:
        return {"response": "That's helpful! How many square feet is the house?", "complete": False}