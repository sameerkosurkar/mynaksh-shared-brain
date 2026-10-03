"""Simplified astrology helpers.

This is intentionally a stub: we only compute the (tropical) sun sign from the date of birth and
attach a few static attributes. Moon/ascendant need an ephemeris plus exact time & place, which is
out of scope - we only report whether the profile *would* allow it.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

# (sign, (start_month, start_day)) in calendar order; a date belongs to the last sign whose start <= date.
_SIGN_STARTS = [
    ("Capricorn", (1, 1)), ("Aquarius", (1, 20)), ("Pisces", (2, 19)), ("Aries", (3, 21)),
    ("Taurus", (4, 20)), ("Gemini", (5, 21)), ("Cancer", (6, 21)), ("Leo", (7, 23)),
    ("Virgo", (8, 23)), ("Libra", (9, 23)), ("Scorpio", (10, 23)), ("Sagittarius", (11, 22)),
    ("Capricorn", (12, 22)),
]

SIGN_INFO: dict[str, dict[str, object]] = {
    "Aries": {"element": "Fire", "ruling_planet": "Mars", "traits": ["bold", "driven", "impatient"],
              "career_hint": "initiative and leadership roles"},
    "Taurus": {"element": "Earth", "ruling_planet": "Venus", "traits": ["steady", "practical", "stubborn"],
               "career_hint": "patient, long-term skill building"},
    "Gemini": {"element": "Air", "ruling_planet": "Mercury", "traits": ["curious", "communicative", "restless"],
               "career_hint": "communication, networking and variety"},
    "Cancer": {"element": "Water", "ruling_planet": "Moon", "traits": ["caring", "intuitive", "protective"],
               "career_hint": "roles where trust and care matter"},
    "Leo": {"element": "Fire", "ruling_planet": "Sun", "traits": ["confident", "creative", "proud"],
            "career_hint": "visibility, leadership and owning outcomes"},
    "Virgo": {"element": "Earth", "ruling_planet": "Mercury", "traits": ["analytical", "precise", "self-critical"],
              "career_hint": "detail, process and craftsmanship"},
    "Libra": {"element": "Air", "ruling_planet": "Venus", "traits": ["diplomatic", "fair", "indecisive"],
              "career_hint": "collaboration, negotiation and design"},
    "Scorpio": {"element": "Water", "ruling_planet": "Mars", "traits": ["intense", "strategic", "private"],
                "career_hint": "deep focus and transformation projects"},
    "Sagittarius": {"element": "Fire", "ruling_planet": "Jupiter", "traits": ["optimistic", "adventurous", "blunt"],
                    "career_hint": "learning, teaching and expansion"},
    "Capricorn": {"element": "Earth", "ruling_planet": "Saturn", "traits": ["disciplined", "ambitious", "reserved"],
                  "career_hint": "structured growth and long-term goals"},
    "Aquarius": {"element": "Air", "ruling_planet": "Saturn", "traits": ["independent", "inventive", "detached"],
                 "career_hint": "innovation and unconventional paths"},
    "Pisces": {"element": "Water", "ruling_planet": "Jupiter", "traits": ["empathetic", "imaginative", "dreamy"],
               "career_hint": "creative and people-centred work"},
}


def sun_sign(dob: Optional[date]) -> Optional[str]:
    if dob is None:
        return None
    current = "Capricorn"
    for sign, (m, d) in _SIGN_STARTS:
        if (dob.month, dob.day) >= (m, d):
            current = sign
    return current


def parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def astro_profile(profile: dict) -> dict:
    """Astrology attributes derivable from the profile (stubbed)."""
    sign = sun_sign(parse_iso_date(profile.get("date_of_birth")))
    out: dict[str, object] = {"sun_sign": sign}
    if sign:
        out.update(SIGN_INFO[sign])
    out["full_chart_available"] = bool(
        profile.get("date_of_birth") and profile.get("time_of_birth") and profile.get("birth_place"))
    return out


def missing_profile_fields(profile: dict) -> list[str]:
    """Fields needed for a personalised (astrological) reading that we do not have yet."""
    return [f for f in ("name", "date_of_birth", "time_of_birth", "birth_place") if not profile.get(f)]
