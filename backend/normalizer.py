import re

# Common Bengaluru Neighborhood Aliases
BENGALURU_AREAS = {
    'hsr': 'HSR Layout', 'hsr layout': 'HSR Layout',
    'btm': 'BTM Layout', 'btm layout': 'BTM Layout',
    'indiranagar': 'Indiranagar', 'indira nagar': 'Indiranagar',
    'koramangala': 'Koramangala', 'kora': 'Koramangala',
    'bellandur': 'Bellandur', 'marathahalli': 'Marathahalli',
    'jayanagar': 'Jayanagar', 'jp nagar': 'JP Nagar',
    'whitefield': 'Whitefield', 'ecity': 'Electronic City',
    'electronic city': 'Electronic City'
}

def normalize_bool(value):
    """Converts messy human strings into True/False/None"""
    if value is None: return None
    if isinstance(value, bool): return value
    
    s = str(value).lower().strip()
    # Positive signals
    if any(word in s for word in ['yes', 'yeah', 'love', 'need', 'want', 'nearby', 'must', 'available', 'true', '1']):
        return True
    # Negative signals
    if any(word in s for word in ['no', 'nope', 'dont', 'not', 'none', 'false', '0']):
        return False
    return None

def normalize_location(loc_str):
    """Maps shortcuts like 'HSR' to 'HSR Layout'"""
    if not loc_str: return loc_str
    s = loc_str.lower().strip()
    return BENGALURU_AREAS.get(s, loc_str.title())

def normalize_property_type(val):
    """Maps messy text, typos, and synonyms to the exact Supabase DB values."""
    if not val:
        return None
        
    s = str(val).lower().strip()
    
    # User Rule: Home == Independent House
    if any(word in s for word in ['home', 'house', 'independ', 'individual']):
        return 'Independent House'
        
    # Catch Apartment & common typos
    if any(word in s for word in ['apart', 'flat', 'aprtment', 'appartment']):
        return 'Apartment'
        
    if 'villa' in s:
        return 'Villa'
        
    if 'pg' in s or 'paying' in s:
        return 'PG'
        
    if 'hostel' in s:
        return 'Hostel'
        
    if 'co-liv' in s or 'coliv' in s:
        return 'Co-living'
        
    return str(val).title() # Fallback for anything else