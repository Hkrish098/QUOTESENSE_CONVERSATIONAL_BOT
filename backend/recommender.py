import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def get_smart_suggestions(session, supabase):
    """
    Refined Recommender: Handles PG vs Home personas and 
    stops hardcoded 'Metro' hallucinations.
    """
    persona = session.get('persona', 'home')
    target_table = "PG_Listings" if persona == "pg" else "properties"
    
    budget = int(float(session.get('rent_price_inr_per_month', 0)))
    loc = session.get('location') or ""
    bhk = session.get('size_bhk', 0)
    
    is_metro_search = persona == "home" and session.get('dist_to_metro_km', 0) > 0

    # Probe A: Increase budget by 25%
    probe_budget = supabase.table(target_table) \
        .select("listing_id") \
        .ilike("location", f"%{loc}%") \
        .eq("size_bhk", bhk) \
        .lte("rent_price_inr_per_month", int(budget * 1.25)) \
        .limit(5).execute()
    
    # Probe B: Relax constraints
    probe_relaxed = None
    relaxed_logic_desc = ""

    if persona == "home":
        if is_metro_search:
            probe_relaxed = supabase.table("properties") \
                .select("listing_id").ilike("location", f"%{loc}%") \
                .eq("size_bhk", bhk).lte("rent_price_inr_per_month", budget) \
                .lte("dist_to_metro_km", 3.0).limit(5).execute()
            relaxed_logic_desc = "Increasing Metro distance to 3km"
        else:
            probe_relaxed = supabase.table("properties") \
                .select("listing_id").ilike("location", f"%{loc}%") \
                .eq("size_bhk", bhk).lte("rent_price_inr_per_month", budget) \
                .limit(5).execute()
            relaxed_logic_desc = "Removing size/sqft constraints"
    else:
        probe_relaxed = supabase.table("PG_Listings") \
            .select("listing_id").ilike("location", f"%{loc}%") \
            .eq("size_bhk", bhk).lte("rent_price_inr_per_month", budget) \
            .limit(5).execute()
        relaxed_logic_desc = "Relaxing amenity/food preferences"

    search_type = "PG Sharing" if persona == "pg" else "BHK Home"
    
    findings = f"- Increasing budget to ₹{int(budget*1.25)}: Found {len(probe_budget.data)} properties."
    if probe_relaxed:
        findings += f"\n- {relaxed_logic_desc}: Found {len(probe_relaxed.data)} properties."

    # ✅ FRIENDLY PROMPT FIX
    analyst_prompt = f"""
    User wanted: {bhk} {search_type} in {loc} for ₹{budget}.
    
    Database Findings:
    {findings}
    
    Role: You are 'Tatva', a warm and empathetic Bengaluru Rental Expert.
    Task: The user's exact search returned 0 matches. Gently explain this, and use the 'Database Findings' to suggest an alternative. 
    
    STRICT RULES:
    1. DO NOT mention 'Metro' unless it appears in the Findings above.
    2. Be conversational and empathetic (e.g., "I searched everywhere, but...").
    3. End by asking the user if they'd like to try one of the alternatives you found (e.g., "Should we increase the budget to ₹{int(budget*1.25)}, or look at a wider area?").
    4. Keep it to 2-3 friendly sentences.
    """

    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "You are Tatva, a friendly rental assistant."},
            {"role": "user", "content": analyst_prompt}
        ]
    )

    return completion.choices[0].message.content