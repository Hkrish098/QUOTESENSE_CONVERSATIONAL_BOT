import json
from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise ValueError("GROQ_API_KEY not found in environment variables. Check your .env file.")

client = Groq(api_key=api_key)

def get_smart_suggestions(session, supabase):
    """
    This function runs when the main search returns 0.
    It 'probes' the DB with relaxed filters to find the 'Why' behind 0 results.
    """
    
    # 1. Prepare Data
    budget = int(float(session.get('rent_price_inr_per_month', 0)))
    # Ensure we use the correct key for location
    loc = session.get('location') or session.get('location_name') or ""
    bhk = session.get('size_bhk')

    # 2. Probe A: Increase budget by 25% 
    # FIX: Wrapped in int() to prevent "31250.0" bigint error
    probe_budget = supabase.table("properties") \
        .select("listing_id") \
        .ilike("location", f"%{loc}%") \
        .eq("size_bhk", bhk) \
        .lte("rent_price_inr_per_month", int(budget * 1.25)) \
        .limit(5).execute()
    
    # 3. Probe B: Expand Metro distance to 3.0km
    probe_metro = supabase.table("properties") \
        .select("listing_id") \
        .ilike("location", f"%{loc}%") \
        .eq("size_bhk", bhk) \
        .lte("rent_price_inr_per_month", budget) \
        .lte("dist_to_metro_km", 3.0) \
        .limit(5).execute()

    # 4. Create the 'Analyst Prompt'
    analyst_prompt = f"""
    User wanted: {bhk} BHK in {loc} for ₹{budget} within 1km Metro.
    
    Database Findings:
    - Increasing budget by 25% (₹{int(budget*1.25)}): Found {len(probe_budget.data)} properties.
    - Increasing Metro distance to 3km: Found {len(probe_metro.data)} properties.
    
    Role: Senior Bangalore Real Estate Advisor.
    Task: Explain WHY there are 0 matches and suggest the best trade-off.
    Tone: Professional, empathetic, and data-driven.
    Advice: Explain that for {loc}, a slight budget increase often saves hours of commute. 
    Keep the response to 2-3 concise sentences.
    """

    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": "You are the Tatva Suggestion Engine. Analyze the findings and give a strategic recommendation."},
                  {"role": "user", "content": analyst_prompt}]
    )

    return completion.choices[0].message.content