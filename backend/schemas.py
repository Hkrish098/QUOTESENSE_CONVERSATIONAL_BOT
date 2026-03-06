"""
schemas.py — Pydantic validation layer between the SLM extractor and the session.

Changes in this version:
  - clean_location now calls normalise_area() to fix misspellings like
    "jayanaagr" → "Jayanagar", "hsr" → "HSR Layout", etc.
  - coerce_to_bool validator now handles "true"/"false" strings from the
    tool schema (all boolean fields are now typed as string in ai_tools.py).
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from location_areas import normalise_area


# ─────────────────────────────────────────────────────────────────────────────
# Internal coercion helpers
# ─────────────────────────────────────────────────────────────────────────────

def _to_int(v) -> Optional[int]:
    """
    Converts any LLM value to int or None.
    Handles: "20k", "1.5 lakhs", "2L", "2BHK", "20,000", 25000, 25000.0
    Returns None for zero, null-ish, or unparseable values.
    """
    if isinstance(v, bool):
        return None                          # bool ⊂ int in Python — reject it

    if v is None:
        return None

    if isinstance(v, (int, float)):
        result = int(v)
        return result if result != 0 else None

    if isinstance(v, str):
        s = v.strip().lower().replace(",", "")

        if s in ("", "null", "none", "n/a", "false", "true", "na", "0"):
            return None

        # Lakhs: "1.5 lakh", "2 lakhs", "2L", "2l"
        lakh = re.match(r"^(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|l)$", s)
        if lakh:
            result = int(float(lakh.group(1)) * 100_000)
            return result if result != 0 else None

        # Thousands: "20k", "20 k"
        kilo = re.match(r"^(\d+(?:\.\d+)?)\s*k$", s)
        if kilo:
            result = int(float(kilo.group(1)) * 1_000)
            return result if result != 0 else None

        # Leading digits: "2BHK", "600 sqft", "25000"
        digits = re.match(r"^(\d+(?:\.\d+)?)", s)
        if digits:
            result = int(float(digits.group(1)))
            return result if result != 0 else None

    return None


def _to_bool(v) -> Optional[bool]:
    """
    Converts any value to True / False / None.
      True  ← actual True, "true", "yes", "1", "needed", "available", "nearby"
      False ← actual False, "false", "no", "0", "not needed"
      None  ← "null", "NULL", None, or anything ambiguous (means: not mentioned)

    NOTE: Because ai_tools.py now types all boolean fields as "string",
    the LLM will return "true"/"false"/"null" strings. This function
    handles all those cases correctly.
    """
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return True if v == 1 else (False if v == 0 else None)
    if isinstance(v, str):
        vl = v.strip().lower()
        if vl in ("yes", "true", "1", "needed", "available", "nearby", "required"):
            return True
        if vl in ("no", "false", "0", "not needed"):
            return False
        if vl in ("null", "none", "n/a", ""):
            return None
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic model
# ─────────────────────────────────────────────────────────────────────────────

class RentalExtractionMonitor(BaseModel):
    """
    Validates + sanitises data extracted by the SLM tool-call.
    Extra fields are silently ignored (extra="ignore").
    """

    model_config = {
        "extra": "ignore",           # never crash on unknown LLM fields
        "validate_assignment": True,
    }

    # ── Core ──────────────────────────────────────────────────────────────────
    location: Optional[str] = Field(None)
    property_type: Optional[str] = Field(None)
    rent_price_inr_per_month: Optional[int] = Field(None)

    # ── Home essentials ───────────────────────────────────────────────────────
    size_bhk: Optional[int] = Field(None)
    total_sqft: Optional[int] = Field(None)
    furnishing: Optional[str] = Field(None)
    marital_status: Optional[str] = Field(None)

    # ── PG essentials ─────────────────────────────────────────────────────────
    Sharing: Optional[int] = Field(None)
    gender_preference: Optional[str] = Field(None)
    nearby_hub: Optional[str] = Field(None)

    # ── Loose amenities ───────────────────────────────────────────────────────
    two_wheeler_parking: Optional[bool] = Field(None)
    four_wheeler_parking: Optional[bool] = Field(None)
    gym_nearby: Optional[bool] = Field(None)

    # ─────────────────────────────────────────────────────────────────────────
    # Field validators
    # ─────────────────────────────────────────────────────────────────────────

    @field_validator(
        "rent_price_inr_per_month", "size_bhk", "Sharing", "total_sqft",
        mode="before",
    )
    @classmethod
    def coerce_to_int(cls, v):
        return _to_int(v)

    @field_validator("two_wheeler_parking", "four_wheeler_parking", "gym_nearby", mode="before")
    @classmethod
    def coerce_to_bool(cls, v):
        return _to_bool(v)

    @field_validator("location", mode="before")
    @classmethod
    def clean_location(cls, v):
        if not isinstance(v, str):
            return None
        s = v.strip()

        # Reject vague pseudo-locations
        junk = {"best", "anywhere", "safe area", "null", "none", "n/a", ""}
        if s.lower() in junk:
            return None

        # ← KEY FIX: normalise misspellings and casing
        return normalise_area(s)

    @field_validator("property_type", mode="before")
    @classmethod
    def normalise_property_type(cls, v):
        if not isinstance(v, str):
            return None
        mapping = {
            "flat": "Apartment",
            "apartment": "Apartment",
            "home": "Independent House",
            "house": "Independent House",
            "independent house": "Independent House",
            "villa": "Villa",
            "pg": "PG",
            "hostel": "PG",
            "co-living": "PG",
            "coliving": "PG",
            "paying guest": "PG",
        }
        return mapping.get(v.strip().lower(), v)

    @field_validator("furnishing", mode="before")
    @classmethod
    def normalise_furnishing(cls, v):
        if not isinstance(v, str):
            return None
        mapping = {
            "semi": "Semi-Furnished",
            "semi-furnished": "Semi-Furnished",
            "semi furnished": "Semi-Furnished",
            "full": "Fully-Furnished",
            "fully": "Fully-Furnished",
            "fully-furnished": "Fully-Furnished",
            "fully furnished": "Fully-Furnished",
            "unfurnished": "Unfurnished",
            "un-furnished": "Unfurnished",
            "bare": "Unfurnished",
            "empty": "Unfurnished",
        }
        return mapping.get(v.strip().lower(), v)

    @field_validator("gender_preference", mode="before")
    @classmethod
    def normalise_gender(cls, v):
        if not isinstance(v, str):
            return None
        mapping = {
            "boys": "Boys", "boy": "Boys", "male": "Boys", "gents": "Boys",
            "girls": "Girls", "girl": "Girls", "female": "Girls", "ladies": "Girls",
            "unisex": "Unisex", "any": "Unisex", "both": "Unisex", "mixed": "Unisex",
        }
        return mapping.get(v.strip().lower(), v)

    @field_validator("marital_status", mode="before")
    @classmethod
    def normalise_marital(cls, v):
        if not isinstance(v, str):
            return None
        vl = v.strip().lower()
        married_kw = {"married", "wife", "husband", "partner", "family", "spouse", "couple"}
        single_kw  = {"single", "alone", "bachelor", "solo", "bachelors"}
        if any(k in vl for k in married_kw):
            return "Married"
        if any(k in vl for k in single_kw):
            return "Single"
        return v

    # ─────────────────────────────────────────────────────────────────────────
    # Cross-field validator
    # ─────────────────────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def prevent_persona_bleed(self) -> "RentalExtractionMonitor":
        """
        Only clears cross-persona fields when property_type is EXPLICITLY known.
        Never clears fields when property_type is None (early in conversation).
        """
        if self.property_type == "PG":
            self.size_bhk = None
            self.total_sqft = None
            self.marital_status = None

        elif self.property_type in ("Apartment", "Independent House", "Villa"):
            self.Sharing = None
            self.gender_preference = None
            self.nearby_hub = None

        return self