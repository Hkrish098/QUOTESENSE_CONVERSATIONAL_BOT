"""
ai_tools.py — Extraction prompt for the SLM Brain.

PG fix: size_bhk is NEVER extracted for PG persona.
It is derived automatically from Sharing in the merge step.
"""

AMENITY_KEYWORDS: dict[str, list[str]] = {
    "two_wheeler_parking":  ["bike", "scooter", "two wheeler", "2 wheeler", "motorbike"],
    "four_wheeler_parking": ["car", "four wheeler", "4 wheeler", "vehicle parking"],
    "gym_nearby":           ["gym", "fitness", "workout", "has_gym"],
    "food_included":        ["food", "meal", "meals", "mess", "tiffin", "breakfast", "dinner", "lunch"],
    "has_wifi":             ["wifi", "wi-fi", "internet", "broadband"],
    "has_washing_machine":  ["washing machine", "laundry", "washer", "washing"],
}


def amenity_explicitly_mentioned(field: str, message: str) -> bool:
    keywords = AMENITY_KEYWORDS.get(field, [])
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in keywords)


def get_extraction_prompt(session: dict) -> str:
    persona = session.get("persona", "unknown")

    if persona == "pg":
        persona_section = """PERSONA: PG SEARCH

REQUIRED — extract these if mentioned in the latest message:
  - Sharing            : sharing count ONLY ("1"=single, "2"=double, "3"=triple, "4"=four)
  - gender_preference  : "Boys", "Girls", or "Unisex"
  - rent_price_inr_per_month : budget as raw text ("10k", "8000", "1.5 lakhs")
  - location           : Bengaluru area name
  - nearby_hub         : college, tech park, or office name if mentioned
  - food_included      : "true" only if food/meals/mess explicitly mentioned
  - has_washing_machine: "true" only if laundry/washing machine explicitly mentioned
  - has_gym            : "true" only if gym/fitness explicitly mentioned

⛔ NEVER extract for PG: size_bhk, marital_status, family_hubs, total_sqft, furnishing
⛔ size_bhk must always be null for PG — it is set automatically from Sharing."""

    elif persona == "home":
        persona_section = """PERSONA: HOME SEARCH

REQUIRED — extract these if mentioned in the latest message:
  - size_bhk           : bedrooms ("1", "2", "3", "4")
  - rent_price_inr_per_month : budget as raw text
  - location           : Bengaluru area name
  - marital_status     : "Married" if wife/husband/family/partner; "Single" if alone/bachelor/solo
  - family_hubs        : JSON array of workplace/school areas e.g. ["HSR Layout", "Whitefield"]

⛔ NEVER extract for HOME: Sharing, gender_preference, nearby_hub, food_included, has_wifi, has_washing_machine"""

    else:
        persona_section = """PERSONA: UNKNOWN — extract all applicable fields, leave rest null."""

    return f"""You are a strict data-extraction unit. Extract rental parameters from the LATEST user message ONLY.

{persona_section}

ABSOLUTE RULES:
1. Extract ONLY from the LATEST user message. IGNORE conversation history entirely.
2. If a value is not explicitly in the latest message → return null.
3. Return ONLY a raw JSON object. No markdown, no comments, no explanation.
4. Numbers: raw text → "10k", "1.5 lakhs", "25000".
5. Boolean amenities: return "true" ONLY if keyword is clearly stated. Otherwise null.
6. family_hubs: JSON array or null.

Return ONLY the JSON object. Nothing else."""