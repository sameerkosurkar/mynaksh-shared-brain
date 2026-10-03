"""Step 1 of the pipeline: what kind of message is this and which life areas does it touch?

Rule-based on purpose: it runs on every request, must be fast and deterministic, and its
decisions are easy to unit-test. An LLM router could replace it behind the same dataclass.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from app.lexicon import ASTRO_KEYWORDS, detect_areas
from app.memory.extractor import Extraction

RECALL = re.compile(
    r"\b(what do you (?:remember|know)|do you (?:remember|know)|remind me|what did i (?:say|tell|share)|"
    r"what have i (?:told|shared)|what are my (?:goals|plans)|recall|what i told you|anything about me)\b", re.I)
FOLLOWUP_START = re.compile(
    r"^(?:why|how come|how so|what do you mean|explain|elaborate|tell me more|can you explain|could you explain|"
    r"and\b|but\b|really|so\b|ok(?:ay)? so|what else|go on|anything else)", re.I)
ANAPHORA = re.compile(r"\b(that|this|it|those|these|them|you said|above)\b", re.I)
SMALLTALK = re.compile(r"^(?:hi|hello|hey|namaste|namaskar|thanks|thank you|ok|okay|cool|great|good (?:morning|evening|"
                       r"night|afternoon)|bye|goodbye)\b", re.I)
DEVANAGARI = re.compile(r"[ऀ-ॿ]")

INTENTS = ("recall", "followup", "share_info", "smalltalk", "advice")


@dataclass
class QueryAnalysis:
    intent: str
    areas: list[str] = field(default_factory=list)
    wants_astrology: bool = False
    language_hint: Optional[str] = None


def analyze(message: str, extraction: Extraction, has_history: bool,
            prev_areas: Optional[list[str]] = None) -> QueryAnalysis:
    text = message.strip()
    words = len(text.split())
    areas = detect_areas(text)
    is_question = text.endswith("?") or bool(re.match(r"^(?:what|why|how|when|where|who|which|should|can|could|will|"
                                                      r"would|is|are|do|does|did|tell me)\b", text, re.I))

    if RECALL.search(text):
        intent = "recall"
    elif has_history and not areas and (FOLLOWUP_START.match(text) or (words <= 7 and ANAPHORA.search(text))):
        intent = "followup"
        areas = list(prev_areas or [])
    elif extraction.has_updates and not is_question:
        intent = "share_info"
        areas = areas or sorted({c.area for c in extraction.items if c.area != "personal"})
    elif SMALLTALK.match(text) and words <= 6 and not areas:
        intent = "smalltalk"
    else:
        intent = "advice"

    return QueryAnalysis(
        intent=intent,
        areas=areas,
        wants_astrology=bool(ASTRO_KEYWORDS.search(text)),
        language_hint="Hindi" if DEVANAGARI.search(text) else None,
    )
