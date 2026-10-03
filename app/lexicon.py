"""Shared vocabularies used by query understanding and memory extraction."""
from __future__ import annotations

import re

AREA_KEYWORDS: dict[str, list[str]] = {
    "career": ["career", "job", "jobs", "work", "office", "boss", "promotion", "promoted", "interview",
               "business", "startup", "entrepreneur", "entrepreneurship", "company", "salary", "profession",
               "manager", "resign", "appraisal", "colleague", "professional", "product management",
               "hike", "layoff", "laid off", "employer", "naukri"],
    "relationships": ["love", "relationship", "relationships", "marriage", "married", "partner", "girlfriend",
                      "boyfriend", "wife", "husband", "dating", "breakup", "spouse", "wedding", "engaged",
                      "soulmate", "compatibility", "shaadi"],
    "health": ["health", "healthy", "fitness", "fit", "weight", "exercise", "yoga", "diet", "sleep", "stress",
               "illness", "disease", "doctor", "gym", "wellness", "mental", "anxiety", "running"],
    "finance": ["money", "finance", "finances", "financial", "invest", "investment", "investing", "savings",
                "loan", "debt", "wealth", "property", "house", "home", "stock", "stocks", "income", "paisa"],
    "education": ["exam", "exams", "study", "studies", "college", "university", "degree", "course", "mba",
                  "masters", "school", "upsc", "gate", "neet", "jee", "gre", "gmat", "learning", "phd"],
    "family": ["family", "parents", "mother", "father", "mom", "dad", "kids", "children", "son", "daughter",
               "brother", "sister", "baby", "in-laws"],
    "spirituality": ["spiritual", "spirituality", "meditation", "puja", "prayer", "temple", "karma", "dharma"],
    "travel": ["travel", "trip", "abroad", "relocate", "relocation", "visa", "vacation", "moving"],
}

_AREA_PATTERNS = {
    area: re.compile(r"\b(?:" + "|".join(re.escape(k) for k in sorted(kws, key=len, reverse=True)) + r")\b", re.I)
    for area, kws in AREA_KEYWORDS.items()
}

ASTRO_KEYWORDS = re.compile(
    r"\b(zodiac|sign|horoscope|kundli|kundali|chart|planet|planets|rashi|nakshatra|saturn|jupiter|mars|venus|"
    r"mercury|moon|sun sign|ascendant|transit|dasha|astrolog\w*|stars|leo|aries|taurus|gemini|cancer|virgo|"
    r"libra|scorpio|sagittarius|capricorn|aquarius|pisces)\b", re.I)

LANGUAGES = ["hindi", "english", "tamil", "telugu", "marathi", "bengali", "kannada", "gujarati",
             "malayalam", "punjabi", "odia", "urdu"]


def detect_areas(text: str) -> list[str]:
    """Life areas mentioned in `text`, ordered by first occurrence."""
    hits = []
    for area, pat in _AREA_PATTERNS.items():
        m = pat.search(text)
        if m:
            hits.append((m.start(), area))
    return [a for _, a in sorted(hits)]


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60]
