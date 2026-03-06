"""
location_areas.py — Bengaluru area name normaliser.

Usage:
    from location_areas import normalise_area
    normalise_area("jayanaagr")      → "Jayanagar"
    normalise_area("jatanagara")     → "Jayanagar"
    normalise_area("jayanagaragara") → "Jayanagar"
    normalise_area("hsr")            → "HSR Layout"
    normalise_area("koramanagla")    → "Koramangala"

Strategy (in order):
  1. Exact match against known aliases / misspellings map.
  2. Exact case-insensitive match against canonical list.
  3. Substring match: if canonical name appears inside the user input
     (catches "jayanagaragara" → contains "jayanagar" → "Jayanagar").
  4. Reverse substring: if user input appears inside a canonical name
     (catches short forms like "hsr" inside "HSR Layout" — already in aliases,
     but this is the fallback safety net).
  5. Title-case the raw input (last resort — at least fixes casing).
"""

# ── Canonical area names ──────────────────────────────────────────────────────
CANONICAL_AREAS = [
    "Jayanagar", "JP Nagar", "BTM Layout", "Banashankari", "Basavanagudi",
    "Koramangala", "HSR Layout", "Bellandur", "Sarjapur Road", "Marathahalli",
    "Whitefield", "Indiranagar", "Domlur", "HAL", "Old Airport Road",
    "Frazer Town", "Ulsoor", "MG Road", "Brigade Road", "Richmond Town",
    "Shivajinagar", "Malleswaram", "Rajajinagar", "Vijayanagar", "Yeshwanthpur",
    "Hebbal", "Manyata Tech Park", "Nagawara", "Thanisandra", "Hennur",
    "Banaswadi", "Kammanahalli", "Kalyan Nagar", "RT Nagar", "Sahakara Nagar",
    "Electronic City", "Begur", "Hosa Road", "Bommanahalli", "Haralur Road",
    "Kadugodi", "ITPL", "Brookefield", "KR Puram", "Hoodi", "Mahadevapura",
    "Yelahanka", "Devanahalli", "Doddaballapur Road", "Tumkur Road",
    "Magadi Road", "Mysore Road", "Kanakapura Road", "Bannerghatta Road",
    "Hulimavu", "Gottigere", "Konanakunte", "Electronic City Phase 1",
    "Electronic City Phase 2", "Bommasandra", "Jigani", "Attibele",
    "Chandapura", "Sarjapur", "Varthur", "Gunjur", "Panathur",
    "Wilson Garden", "Langford Town", "Cleveland Town", "Lingarajapuram",
    "CV Raman Nagar", "Kasturinagar", "Ramamurthy Nagar",
    "Vimanapura", "Peenya", "Dasarahalli", "HBR Layout", "Horamavu",
    "Krishnarajapuram", "Munnekolala", "Basaveshwara Nagar", "Nandini Layout",
    "Nagarabhavi", "RR Nagar", "Uttarahalli", "Anekal",
]

# ── Alias map: lowercase input → canonical ────────────────────────────────────
_ALIASES: dict[str, str] = {
    # Jayanagar
    "jayanagar": "Jayanagar", "jayanaagr": "Jayanagar", "jayanagr": "Jayanagar",
    "jaya nagar": "Jayanagar", "jaynagar": "Jayanagar", "jyanagar": "Jayanagar",
    "jatanagar": "Jayanagar", "jatanagara": "Jayanagar", "jayanagara": "Jayanagar",
    "jayanagaragara": "Jayanagar", "jaanagar": "Jayanagar", "jayangar": "Jayanagar",

    # JP Nagar
    "jp nagar": "JP Nagar", "jpnagar": "JP Nagar",
    "j.p nagar": "JP Nagar", "j.p. nagar": "JP Nagar",

    # BTM Layout
    "btm": "BTM Layout", "btm layout": "BTM Layout", "btm layot": "BTM Layout",

    # HSR Layout
    "hsr": "HSR Layout", "hsr layout": "HSR Layout", "h.s.r": "HSR Layout",
    "hsr layot": "HSR Layout", "hsr laout": "HSR Layout",

    # Koramangala
    "koramangala": "Koramangala", "koramanagla": "Koramangala",
    "koramangla": "Koramangala", "koramagala": "Koramangala",
    "kormangala": "Koramangala", "kormangla": "Koramangala",
    "koramngala": "Koramangala", "koramanagala": "Koramangala",

    # Indiranagar
    "indiranagar": "Indiranagar", "indiranagr": "Indiranagar",
    "indira nagar": "Indiranagar", "indranagar": "Indiranagar",
    "indiranagara": "Indiranagar",

    # Whitefield
    "whitefield": "Whitefield", "whitefeild": "Whitefield",
    "white field": "Whitefield", "whtiefield": "Whitefield",

    # Marathahalli
    "marathahalli": "Marathahalli", "marathalli": "Marathahalli",
    "marathahally": "Marathahalli", "maratha halli": "Marathahalli",
    "marathaahalli": "Marathahalli",

    # Bellandur
    "bellandur": "Bellandur", "bellandoor": "Bellandur", "bellndur": "Bellandur",

    # Electronic City
    "electronic city": "Electronic City", "electroniccity": "Electronic City",
    "e city": "Electronic City", "ecity": "Electronic City",
    "electronic cty": "Electronic City",

    # Banashankari
    "banashankari": "Banashankari", "banasnkari": "Banashankari",
    "bansankari": "Banashankari", "banasankari": "Banashankari",

    # Malleswaram
    "malleswaram": "Malleswaram", "malleshwaram": "Malleswaram",
    "maleshwaram": "Malleswaram", "malleswram": "Malleswaram",

    # Yeshwanthpur
    "yeshwanthpur": "Yeshwanthpur", "yeshwantpur": "Yeshwanthpur",
    "yeshwanthapur": "Yeshwanthpur",

    # Basavanagudi
    "basavanagudi": "Basavanagudi", "basavnagudi": "Basavanagudi",
    "basavanagudy": "Basavanagudi",

    # Rajajinagar
    "rajajinagar": "Rajajinagar", "rajaji nagar": "Rajajinagar",
    "rajajinaagr": "Rajajinagar",

    # Vijayanagar
    "vijayanagar": "Vijayanagar", "vijay nagar": "Vijayanagar",
    "vijayanaagr": "Vijayanagar",

    # Sarjapur
    "sarjapur": "Sarjapur Road", "sarjapur road": "Sarjapur Road",
    "sarjapura": "Sarjapur Road", "sarjapura road": "Sarjapur Road",

    # Hebbal
    "hebbal": "Hebbal", "hebbala": "Hebbal", "hebal": "Hebbal",

    # Yelahanka
    "yelahanka": "Yelahanka", "yelahnaka": "Yelahanka", "yelhanka": "Yelahanka",

    # CV Raman Nagar
    "cv raman nagar": "CV Raman Nagar", "c.v. raman nagar": "CV Raman Nagar",
    "cv ramana nagar": "CV Raman Nagar",

    # KR Puram
    "kr puram": "KR Puram", "k.r. puram": "KR Puram", "krpuram": "KR Puram",

    # RR Nagar
    "rr nagar": "RR Nagar", "r.r. nagar": "RR Nagar", "rrnagar": "RR Nagar",

    # Hennur
    "hennur": "Hennur", "hnnur": "Hennur", "hennoor": "Hennur",

    # Manyata
    "manyata": "Manyata Tech Park", "manyata tech park": "Manyata Tech Park",
    "manyatha": "Manyata Tech Park", "manyatha tech park": "Manyata Tech Park",
}

# Pre-build lowercase → canonical for step 2
_CANONICAL_LOWER: dict[str, str] = {a.lower(): a for a in CANONICAL_AREAS}

# Pre-build sorted canonical list for step 3/4 (longest first avoids short-match false positives)
_CANONICAL_SORTED = sorted(CANONICAL_AREAS, key=lambda x: len(x), reverse=True)


def normalise_area(raw: str) -> str:
    """
    Returns the canonical Bengaluru area name.

    Priority:
      1. Known alias / typo map (fastest, most precise).
      2. Exact canonical match (case-insensitive).
      3. Canonical name is a substring of user input
         e.g. "jayanagaragara" contains "jayanagar" → "Jayanagar".
      4. User input is a substring of a canonical name (≥4 chars to avoid false positives)
         e.g. "nagar" inside multiple names — only match if unique enough.
      5. Title-case fallback.
    """
    if not raw or not isinstance(raw, str):
        return raw

    key = raw.strip().lower()

    # 1. Known alias / typo
    if key in _ALIASES:
        return _ALIASES[key]

    # 2. Exact canonical match
    if key in _CANONICAL_LOWER:
        return _CANONICAL_LOWER[key]

    # 3. Canonical name appears as substring inside user input
    #    (handles "jayanagaragara" → contains "jayanagar")
    for canonical in _CANONICAL_SORTED:
        if canonical.lower() in key:
            return canonical

    # 4. User input appears as substring inside a canonical name
    #    Only when input is ≥ 4 chars (avoids matching "mg" in "MG Road" for bad inputs)
    if len(key) >= 4:
        matches = [c for c in _CANONICAL_SORTED if key in c.lower()]
        if len(matches) == 1:
            return matches[0]

    # 5. Fallback — at least normalise casing
    return raw.strip().title()