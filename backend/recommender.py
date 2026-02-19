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
    
    # 1. Probe A: What if we increase the budget by 20%?
    budget = int(float(session.get('rent_price_inr_per_month', 0)))
    probe_budget = supabase.table("properties").select("listing_id").ilike("location", f"%{session.get('location')}%").eq("size_bhk", session.get('size_bhk')).lte("rent_price_inr_per_month", budget * 1.25).limit(5).execute()
    
    # 2. Probe B: What if we expand the Metro distance?
    probe_metro = supabase.table("properties").select("listing_id").ilike("location", f"%{session.get('location')}%").eq("size_bhk", session.get('size_bhk')).lte("rent_price_inr_per_month", budget).lte("dist_to_metro_km", 3.0).limit(5).execute()

    # 3. Probe C: Nearby Areas (e.g. BTM if searching HSR)
    # You can add logic here to check neighboring zones
    
    # Create the 'Analyst Prompt'
    analyst_prompt = f"""
    User wanted: {session.get('size_bhk')} BHK in {session.get('location')} for {budget}k within 1km Metro.
    
    Database Findings:
    - Increasing budget by 25%: Found {len(probe_budget.data)} properties.
    - Increasing Metro distance to 3km: Found {len(probe_metro.data)} properties.
    
    Role: Senior Bangalore Real Estate Advisor.
    Task: Explain WHY there are 0 matches and suggest the best trade-off.
    Tone: Professional, empathetic, and data-driven.
    Advice: Mention that in Bangalore, paying 5k more to stay near a metro saves money on cabs and hours in traffic.
    """

    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": "You are the Tatva Suggestion Engine. Analyze the findings and give a 2-3 sentence strategic recommendation."},
                  {"role": "user", "content": analyst_prompt}]
    )

    return completion.choices[0].message.content