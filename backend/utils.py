import re


def safe_int(value, default: int = 0) -> int:
    """
    Robust integer parser that handles:
    - Indian formats: "20k" → 20000, "1.5 lakhs" → 150000, "2L" → 200000
    - Comma-formatted: "20,000" → 20000
    - Floats: 2.0 → 2
    - Strings: "2BHK" → 2, "3 BHK" → 3
    - Booleans: always returns default (bool is NOT treated as int here)
    - None / null / empty → default (0)
    """
    # bool is a subclass of int in Python — must be caught FIRST
    if isinstance(value, bool):
        return default

    if value is None:
        return default

    if isinstance(value, (int, float)):
        return int(value)

    if isinstance(value, str):
        v = value.strip().lower().replace(",", "")

        if v in ("", "null", "none", "n/a", "false", "true", "na"):
            return default

        # Lakhs: "1.5 lakh", "2 lakhs", "2L", "2l"
        lakh_match = re.match(r"^(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|l)$", v)
        if lakh_match:
            return int(float(lakh_match.group(1)) * 100_000)

        # Thousands: "20k", "20 k"
        k_match = re.match(r"^(\d+(?:\.\d+)?)\s*k$", v)
        if k_match:
            return int(float(k_match.group(1)) * 1_000)

        # Leading digits — handles "2BHK", "600 sqft", "25000"
        digit_match = re.match(r"^(\d+(?:\.\d+)?)", v)
        if digit_match:
            return int(float(digit_match.group(1)))

    return default


def coerce_bool(value) -> bool | None:
    """
    Converts any value to True / False / None.

      True  ← actual True, "true", "yes", "1", "needed", "available", "nearby"
      False ← actual False, "false", "no", "0", "not needed"
      None  ← "null", "NULL", None, or anything ambiguous (means: not mentioned)

    Returns None (not False) for unknowns so callers can distinguish
    'explicitly denied' from 'not yet mentioned'.
    """
    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        if value == 1:
            return True
        if value == 0:
            return False
        return None

    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("yes", "true", "1", "needed", "available", "nearby", "required"):
            return True
        if v in ("no", "false", "0", "not needed"):
            return False
        if v in ("null", "none", "n/a", ""):
            return None

    return None