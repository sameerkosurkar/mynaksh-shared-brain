"""Decides what in a user message is worth remembering long-term.

Hybrid strategy
---------------
1. `RuleExtractor` (always on): deterministic regex/lexicon rules for the high-value, well-structured
   facts - profile fields, goals with timeframes, interests, preferences, life events, concerns,
   abandoned plans. Cheap, testable, explainable.
2. `LLMExtractor` (when a real LLM is configured): catches long-tail facts the rules miss. Its output
   is validated against the same schema and rule results take precedence.

What is NOT remembered (salience gate):
  * questions, greetings, thanks, small talk           -> no first-person statement of fact
  * hypotheticals ("what if I...", "suppose I...")       -> not facts
  * other people's plans ("my friend wants to ...")      -> not about the user
  * information-seeking "wants" ("I want to know ...")   -> not a life goal
  * generic statements with no recognised life area      -> too vague to be useful
  * PII such as phone numbers, emails, ID/card numbers   -> redacted before anything is stored
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from app.brain.models import ABANDONED, ACTIVE, KINDS, LIFE_AREAS
from app.lexicon import LANGUAGES, detect_areas, slugify

log = logging.getLogger(__name__)


@dataclass
class Candidate:
    kind: str
    key: str
    title: str
    area: str
    attributes: dict = field(default_factory=dict)
    confidence: float = 0.8
    importance: float = 0.6
    source_text: str = ""
    status: str = ACTIVE

    def describe(self) -> str:
        extra = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in self.attributes.items()
                          if k in ("target_year", "target_month", "timeframe") and v)
        prefix = {"goal": "goal", "interest": "interest", "preference": "preference",
                  "life_event": "life event", "concern": "concern"}[self.kind]
        if self.status == ABANDONED:
            prefix = "dropped goal"
        return f"{prefix}: {self.title}" + (f" ({extra})" if extra else "")


@dataclass
class Extraction:
    profile: dict[str, str] = field(default_factory=dict)
    items: list[Candidate] = field(default_factory=list)
    is_correction: bool = False
    skipped: list[str] = field(default_factory=list)   # why sentences were not stored (for debugging/eval)

    @property
    def has_updates(self) -> bool:
        return bool(self.profile or self.items)

    def describe(self) -> list[str]:
        out = [f"{k.replace('_', ' ')}: {v}" for k, v in self.profile.items()]
        return out + [c.describe() for c in self.items]


# --------------------------------------------------------------------------------------------
# PII redaction
# --------------------------------------------------------------------------------------------
_PII = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[email]"),
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[pan]"),
    (re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}(?:[ -]?\d{4})?\b"), "[id-number]"),   # aadhaar / card
    (re.compile(r"(?:\+?91[ -]?)?\b[6-9]\d{9}\b"), "[phone]"),
]


def redact_pii(text: str) -> str:
    for pat, repl in _PII:
        text = pat.sub(repl, text)
    return text


# --------------------------------------------------------------------------------------------
# Profile rules
# --------------------------------------------------------------------------------------------
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_BIRTH_CTX = re.compile(r"\b(born|birth|dob|birthday|b'?day)\b", re.I)
_NAME_STOP = {"not", "actually", "also", "the", "a", "an", "planning", "preparing", "from", "born", "here",
              "interested", "worried", "looking", "trying", "going", "thinking", "feeling", "very", "so",
              "just", "really", "currently", "working", "married", "single", "fine", "good", "okay", "ok",
              "sorry", "confused", "new", "back", "happy", "sad", "tired", "stressed", "curious", "hoping"}

_NAME_PATTERNS = [
    re.compile(r"\bmy name is not [A-Za-z]+,?\s*(?:it'?s|it is|but|rather)\s+([A-Za-z][A-Za-z'-]+)", re.I),
    re.compile(r"\b(?:my name is|my name's|name'?s|i am called|call me)\s+(?:actually\s+)?([A-Za-z][A-Za-z'-]+)", re.I),
    re.compile(r"\b(?:I am|I'm|Im)\s+([A-Z][a-z]+)(?=\s*(?:[,.!]|$|\band\b|\bfrom\b|\bhere\b))"),  # case-sensitive
]


def _extract_name(text: str) -> Optional[str]:
    for pat in _NAME_PATTERNS:
        m = pat.search(text)
        if m and m.group(1).lower() not in _NAME_STOP:
            return m.group(1).capitalize()
    return None


def _valid_date(y: int, m: int, d: int, today: date) -> Optional[str]:
    try:
        dt = date(y, m, d)
    except ValueError:
        return None
    return dt.isoformat() if 1900 <= y and dt <= today else None


def _extract_dob(text: str, today: date) -> Optional[str]:
    for sentence in _split_sentences(text):
        if not _BIRTH_CTX.search(sentence):
            continue
        s = sentence.lower()
        m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MON + r",?\s+(\d{4})\b", s)
        if m:
            return _valid_date(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1)), today)
        m = re.search(r"\b" + _MON + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", s)
        if m:
            return _valid_date(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2)), today)
        m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", s)
        if m:
            return _valid_date(int(m.group(1)), int(m.group(2)), int(m.group(3)), today)
        m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b", s)   # Indian convention: dd/mm/yyyy
        if m:
            return _valid_date(int(m.group(3)), int(m.group(2)), int(m.group(1)), today)
    return None


def _extract_tob(text: str) -> Optional[str]:
    for sentence in _split_sentences(text):
        if not _BIRTH_CTX.search(sentence):
            continue
        s = sentence.lower()
        m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", s)
        if m:
            h, mi = int(m.group(1)), int(m.group(2) or 0)
            if 1 <= h <= 12 and mi < 60:
                if m.group(3).startswith("p") and h != 12:
                    h += 12
                if m.group(3).startswith("a") and h == 12:
                    h = 0
                return f"{h:02d}:{mi:02d}"
        m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", s)
        if m:
            return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None


_PLACE_STOP = r"(?=\s*(?:[,.;!?]|$|\s+(?:on|at|and|around|but|not|in\s+\d|in\s+(?:the\s+)?(?:year|morning|evening|night|afternoon))\b))"
_PLACE_PATTERNS = [
    re.compile(r"\bborn\b[^.?!]*?\bin\s+(?!the\s+(?:year|morning|evening|night))([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,2}?)" + _PLACE_STOP, re.I),
    re.compile(r"\b(?:birth\s*place|place of birth)\s*(?:is|was|:)?\s*([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,2}?)" + _PLACE_STOP, re.I),
]
_MONTH_WORDS = {"january", "february", "march", "april", "may", "june", "july", "august", "september",
                "october", "november", "december"}


def _extract_place(text: str) -> Optional[str]:
    for pat in _PLACE_PATTERNS:
        m = pat.search(text)
        if m:
            place = m.group(1).strip()
            if place.lower().split()[0] in _MONTH_WORDS:
                continue
            return place.title()
    return None


_LANG_RX = "|".join(LANGUAGES)
_LANG_PATTERNS = [
    re.compile(r"\b(?:prefer|reply|respond|answer|talk|speak|chat|communicate|write|explain)\b[^.?!]*?\b(" + _LANG_RX + r")\b", re.I),
    re.compile(r"\b(?:in|use)\s+(" + _LANG_RX + r")\s+(?:please|only|from now)", re.I),
    re.compile(r"\bmy (?:preferred )?language is\s+(" + _LANG_RX + r")\b", re.I),
]


def _extract_language(text: str) -> Optional[str]:
    for pat in _LANG_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).capitalize()
    return None


# --------------------------------------------------------------------------------------------
# Goals
# --------------------------------------------------------------------------------------------
_GOAL_TRIGGER = re.compile(
    r"\b(?:i(?:'m| am)?\s+(?:really\s+|seriously\s+)?(?:planning|plan|hoping|hope|aiming|aim|want|wanting|wish|"
    r"intend|intending|trying|going|looking|thinking of|thinking about|preparing|prepping|working towards?|"
    r"considering|decided|have decided|will|would like)(?:\s+(?:to|for|on))?"
    r"|my (?:goal|plan|dream|aim|target|resolution) (?:is|for [a-z0-9 ]+ is)(?:\s+to)?"
    r"|i(?:'d| would) (?:like|love) to)\s+(?P<obj>[^.;!?]+)", re.I)

_INFO_SEEKING = re.compile(r"^(?:know|ask|understand|see|check|learn about|find out|talk|chat|hear|discuss|"
                           r"get (?:a |my )?(?:reading|prediction|horoscope)|sleep|eat|go home)\b", re.I)
_TENTATIVE = re.compile(r"\b(maybe|might|not sure|thinking|considering|hoping|wish|someday|probably)\b", re.I)

_NUM_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "few": 3}

# (pattern on the goal phrase, key, title, area). `None` title = derive from the phrase.
_GOAL_CANON: list[tuple[re.Pattern, str, Optional[str], str]] = [
    (re.compile(r"\b(?:switch|chang|leav|quit)\w*\s+(?:my\s+|the\s+|a\s+)?(?:job|jobs|company|role|career|field)"
                r"|\bjob\s+(?:change|switch|hunt)|\bnew job\b|\bcareer (?:change|switch)", re.I),
     "career_change", "Career Change", "career"),
    (re.compile(r"\bpromot", re.I), "promotion", "Promotion", "career"),
    (re.compile(r"\b(?:start|launch|open|build|begin)\w*\s+(?:a\s+|my\s+|our\s+)?(?:own\s+)?"
                r"(?:business|startup|company|venture)", re.I), "start_business", "Start a Business", "career"),
    (re.compile(r"\binterview", re.I), "", None, "career"),
    (re.compile(r"\b(?:get|getting)\s+married\b|\bmarriage\b|\bwedding\b", re.I), "marriage", "Marriage", "relationships"),
    (re.compile(r"\b(?:buy|buying|purchas\w*)\s+(?:a\s+|my\s+)?(?:own\s+)?(?:house|home|flat|apartment|property)", re.I),
     "buy_home", "Buy a Home", "finance"),
    (re.compile(r"\b(?:lose|losing)\s+weight\b|\bget(?:ting)?\s+fit\b|\bfitness\b", re.I), "fitness", "Get Fit", "health"),
    (re.compile(r"\bstudy(?:ing)?\s+abroad\b|\b(?:masters|ms|mba|phd)\b.*\babroad\b", re.I), "study_abroad", "Study Abroad", "education"),
    (re.compile(r"\b(upsc|gate|cat|neet|jee|gmat|gre|ielts|toefl|ca|bank po)\b(?:\s+exam)?", re.I), "", None, "education"),
    (re.compile(r"\b(?:save|saving)\s+(?:money|more)|\binvest(?:ing)?\b", re.I), "savings", "Grow Savings", "finance"),
    (re.compile(r"\b(?:move|moving|relocat\w*|shift\w*)\s+(?:to\s+)?(abroad|[A-Z][a-z]+)", re.I), "", None, "travel"),
]


def _parse_timeframe(phrase: str, today: date) -> tuple[dict, str]:
    """Returns (attributes, phrase-with-timeframe-removed)."""
    # Corrections like "in 2028, not next year": the negated timeframe must not win.
    p = re.sub(r",?\s*(?:and\s+)?not\s+(?:in\s+|by\s+)?(?:next|this)\s+(?:year|month|week)\b|,?\s*not\s+(?:in\s+|by\s+)?20\d{2}\b",
               "", phrase, flags=re.I)
    attrs: dict = {}
    rules = [
        (r"\bnext year\b", lambda m: {"timeframe": "next year", "target_year": today.year + 1}),
        (r"\bthis year\b|\bby (?:the )?end of (?:the |this )?year\b",
         lambda m: {"timeframe": "this year", "target_year": today.year}),
        (r"\b(?:in|by|before|during|around)\s+(20\d{2})\b",
         lambda m: {"timeframe": m.group(1), "target_year": int(m.group(1))}),
        (r"\bnext month\b", lambda m: {"timeframe": "next month", "target_month": _add_months(today, 1)}),
        (r"\bin\s+(\d+|a|an|one|two|three|four|five|six|few)\s+months?\b",
         lambda m: {"timeframe": f"in {m.group(1)} months",
                    "target_month": _add_months(today, _to_int(m.group(1)))}),
        (r"\bin\s+(\d+|a|one|two|three|four|five)\s+years?\b",
         lambda m: {"timeframe": f"in {m.group(1)} years", "target_year": today.year + _to_int(m.group(1))}),
        (r"\bnext week\b", lambda m: {"timeframe": "next week"}),
        (r"\b(?:soon|shortly)\b", lambda m: {"timeframe": "soon"}),
    ]
    for rx, fn in rules:
        m = re.search(rx, p, re.I)
        if m:
            attrs.update(fn(m))
            p = (p[:m.start()] + p[m.end():]).strip()
            break
    return attrs, re.sub(r"\s{2,}", " ", p)


def _to_int(word: str) -> int:
    return int(word) if word.isdigit() else _NUM_WORDS.get(word.lower(), 1)


def _add_months(d: date, n: int) -> str:
    y, m = divmod(d.month - 1 + n, 12)
    return f"{d.year + y:04d}-{m + 1:02d}"


def _clean_title(phrase: str, max_words: int = 6) -> str:
    phrase = re.sub(r"^(?:a|an|the|my|for|to|on|get|be|some)\s+", "", phrase.strip(), flags=re.I)
    phrase = re.sub(r"\b(?:and|but|so|because)\b.*$", "", phrase, flags=re.I).strip(" ,")
    words = phrase.split()[:max_words]
    return " ".join(w if w.isupper() else w.capitalize() for w in words)


def canonical_goal(phrase: str) -> Optional[tuple[str, str, str]]:
    """Map a free-text goal phrase to (key, title, area); None if no life area is recognisable."""
    for pat, key, title, area in _GOAL_CANON:
        m = pat.search(phrase)
        if not m:
            continue
        if title is None:
            if area == "career":       # "<topic> interview"
                topic = _clean_title(phrase[:m.start()].strip())
                title = f"{topic} Interview".strip() if topic else "Job Interview"
            elif area == "education":
                title = f"{m.group(1).upper()} Exam"
            else:
                dest = m.group(1)
                title = "Move Abroad" if dest.lower() == "abroad" else f"Relocate to {dest.title()}"
            key = slugify(title)
        return f"goal:{key}", title, area
    areas = detect_areas(phrase)
    if not areas:
        return None
    title = _clean_title(phrase)
    return (f"goal:{slugify(title)}", title, areas[0]) if title else None


_ABANDON = re.compile(
    r"\b(?:no longer|not (?:planning|going|thinking|looking)|don'?t (?:want|plan)|do not (?:want|plan)|"
    r"decided (?:not|against)|dropped|gave up|given up|cancel(?:l?ed)?|changed my mind about)\b", re.I)


# --------------------------------------------------------------------------------------------
# Interests, concerns, life events, preferences
# --------------------------------------------------------------------------------------------
_INTEREST = re.compile(
    r"\b(?:i(?:'m| am)\s+(?:really\s+|very\s+|deeply\s+)?(?:interested in|into|passionate about|fascinated by)"
    r"|i (?:really\s+)?(?:love|enjoy)|my (?:hobby is|hobbies are|hobbies include|passion is))\s+(?P<obj>[^.;!?]+)", re.I)
_INTEREST_STOP = {"it", "that", "this", "you", "your", "talking", "to", "the", "when", "how", "being", "my"}

_CONCERN = re.compile(
    r"\bi(?:'m| am)\s+(?:really\s+|very\s+|a bit\s+|quite\s+|so\s+|a little\s+)?"
    r"(?:worried|anxious|stressed|concerned|nervous|scared|afraid|tensed?)\s+(?:about|of|for|regarding)\s+"
    r"(?P<obj>[^.;!?]+)", re.I)

_LIFE_EVENTS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"\bi (?:just |recently )?got (?:married)\b|\bmy (?:wedding|marriage) (?:was|happened)\b", re.I),
     "Got Married", "relationships"),
    (re.compile(r"\bi (?:just |recently )?got engaged\b", re.I), "Got Engaged", "relationships"),
    (re.compile(r"\bi (?:just |recently )?(?:got )?divorced\b|\bmy divorce\b", re.I), "Divorce", "relationships"),
    (re.compile(r"\bi (?:just |recently )?(?:got|was) promoted\b|\bi got a promotion\b", re.I), "Got Promoted", "career"),
    (re.compile(r"\bi (?:just |recently )?(?:lost my job|got laid off|was laid off|got fired|was fired)\b", re.I),
     "Lost Job", "career"),
    (re.compile(r"\bi (?:just |recently )?(?:joined|started (?:a |my )?new job|started working at|got a new job)\b", re.I),
     "Started New Job", "career"),
    (re.compile(r"\b(?:i|we) (?:just |recently )?(?:had a baby|became (?:a )?(?:father|mother|parents?))\b", re.I),
     "Became a Parent", "family"),
    (re.compile(r"\bmy (\w+) (?:passed away|died)\b", re.I), "", "family"),
    (re.compile(r"\bi (?:just |recently )?graduated\b", re.I), "Graduated", "education"),
    (re.compile(r"\bi (?:just |recently )?(?:moved|relocated|shifted) to ([A-Z][a-zA-Z]+)", re.I), "", "travel"),
]

_STYLE = re.compile(r"\b(?:prefer|keep|want|like)\b[^.?!]*\b(short|brief|concise|detailed|long|in-depth)\b[^.?!]*"
                    r"\b(?:answers?|responses?|replies|explanations?)\b", re.I)

_QUESTION_START = re.compile(r"^(?:what|why|how|when|where|who|which|should|can|could|will|would|is|are|do|does|"
                             r"did|am|tell me|explain|any)\b", re.I)
_HYPOTHETICAL = re.compile(r"^(?:what if|if i|suppose|imagine|hypothetically|let'?s say)\b", re.I)
_THIRD_PARTY = re.compile(r"^\s*(?:my\s+(?:friend|brother|sister|cousin|colleague|boss|neighbou?r|wife|husband|"
                          r"partner|mother|father|mom|dad|son|daughter)|he|she|they)\b", re.I)
_CORRECTION = re.compile(r"\b(actually|correction|i meant|sorry,? (?:i|my)|that'?s (?:wrong|not right|incorrect)|"
                         r"not [\w ]+, (?:it'?s|but)|instead of)\b", re.I)


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


class RuleExtractor:
    def __init__(self, today: Callable[[], date] = date.today):
        self.today = today

    def extract(self, message: str) -> Extraction:
        today = self.today()
        text = redact_pii(message)
        ex = Extraction(is_correction=bool(_CORRECTION.search(text)))

        # Profile facts: explicit, well-formed patterns are safe to take from anywhere in the message.
        for fld, value in (("name", _extract_name(text)), ("date_of_birth", _extract_dob(text, today)),
                           ("time_of_birth", _extract_tob(text)), ("birth_place", _extract_place(text)),
                           ("preferred_language", _extract_language(text))):
            if value:
                ex.profile[fld] = value
        if "preferred_language" in ex.profile:
            ex.items.append(Candidate("preference", "preference:language", ex.profile["preferred_language"],
                                      "personal", {"type": "language"}, 0.9, 0.7, text))
        m = _STYLE.search(text)
        if m:
            style = "Concise answers" if m.group(1).lower() in ("short", "brief", "concise") else "Detailed answers"
            ex.items.append(Candidate("preference", "preference:response_style", style, "personal",
                                      {"type": "response_style"}, 0.85, 0.5, text))

        for sentence in _split_sentences(text):
            self._sentence(sentence, today, ex)

        # Dedupe by key, keep the first (rules are ordered by priority)
        seen, unique = set(), []
        for c in ex.items:
            if c.key not in seen:
                seen.add(c.key)
                unique.append(c)
        ex.items = unique
        return ex

    def _sentence(self, s: str, today: date, ex: Extraction) -> None:
        if s.endswith("?") or _QUESTION_START.match(s):
            ex.skipped.append(f"question: {s}")
            return
        if _HYPOTHETICAL.match(s):
            ex.skipped.append(f"hypothetical: {s}")
            return
        third_party = bool(_THIRD_PARTY.match(s))

        # Life events (including family events reported by the user)
        for pat, title, area in _LIFE_EVENTS:
            m = pat.search(s)
            if m:
                if not title:
                    title = (f"Moved to {m.group(1).title()}" if area == "travel"
                             else f"Loss of {m.group(1).lower()}")
                ex.items.append(Candidate("life_event", f"life_event:{slugify(title)}", title, area,
                                          {"when": today.isoformat()}, 0.85, 0.75, s))
                return

        if third_party:
            ex.skipped.append(f"about someone else: {s}")
            return

        if _ABANDON.search(s):
            canon = canonical_goal(s)
            if canon:
                key, title, area = canon
                ex.items.append(Candidate("goal", key, title, area, {}, 0.85, 0.7, s, status=ABANDONED))
                return

        m = _GOAL_TRIGGER.search(s)
        if m:
            obj = m.group("obj").strip()
            if _INFO_SEEKING.match(obj):
                ex.skipped.append(f"information request, not a goal: {s}")
            else:
                attrs, phrase = _parse_timeframe(obj, today)
                canon = canonical_goal(phrase) or canonical_goal(s)
                if canon:
                    key, title, area = canon
                    conf = 0.65 if _TENTATIVE.search(s) else 0.85
                    if ex.is_correction:
                        conf = 0.9
                    ex.items.append(Candidate("goal", key, title, area, attrs, conf,
                                              0.9 if attrs else 0.8, s))
                    # "I want to start my own business" also implies an interest in entrepreneurship
                    if key == "goal:start_business":
                        ex.items.append(Candidate("interest", "interest:entrepreneurship", "Entrepreneurship",
                                                  "career", {}, 0.7, 0.5, s))
                else:
                    ex.skipped.append(f"goal with no recognisable life area: {s}")

        m = _CONCERN.search(s)
        if m:
            obj = _clean_title(m.group("obj"))
            areas = detect_areas(m.group("obj"))
            if obj:
                ex.items.append(Candidate("concern", f"concern:{slugify(obj)}", obj, areas[0] if areas else "personal",
                                          {}, 0.8, 0.6, s))

        m = _INTEREST.search(s)
        if m:
            for part in re.split(r",|\band\b|\bor\b", m.group("obj"))[:3]:
                title = _clean_title(part, max_words=4)
                if not title or title.split()[0].lower() in _INTEREST_STOP:
                    continue
                areas = detect_areas(part)
                ex.items.append(Candidate("interest", f"interest:{slugify(title)}", title,
                                          areas[0] if areas else "personal", {}, 0.8, 0.5, s))


# --------------------------------------------------------------------------------------------
# LLM extractor (long tail)
# --------------------------------------------------------------------------------------------
EXTRACTION_SYSTEM_PROMPT = f"""You extract long-term memories about a user from ONE chat message for a personal
astrology assistant. Only extract durable facts ABOUT THE USER that will help future conversations:
goals/plans (with timeframe), interests, preferences, important life events, ongoing concerns.
Do NOT extract: questions, greetings, small talk, hypotheticals, facts about other people, temporary
states (tired, hungry), or any IDs, phone numbers, emails or financial account details.
Return JSON: {{"memories": [{{"kind": one of {list(KINDS)}, "title": "2-5 word title",
"area": one of {list(LIFE_AREAS)}, "timeframe": "optional", "target_year": optional int,
"confidence": 0-1, "importance": 0-1}}]}}. Return {{"memories": []}} if nothing qualifies."""


class LLMExtractor:
    def __init__(self, llm, today: Callable[[], date] = date.today):
        self.llm = llm
        self.today = today

    def extract(self, message: str) -> list[Candidate]:
        from app.llm.base import ChatMessage, LLMRequest  # local import avoids a cycle

        req = LLMRequest(system=EXTRACTION_SYSTEM_PROMPT + f"\nToday's date: {self.today().isoformat()}.",
                         messages=[ChatMessage("user", redact_pii(message))],
                         max_tokens=400, temperature=0.0, json_mode=True, metadata={"task": "extract"})
        result = self.llm.generate(req)
        return self._parse(result.response.text, message)

    @staticmethod
    def _parse(raw: str, message: str) -> list[Candidate]:
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("LLM extractor returned invalid JSON: %s", raw[:200])
            return []
        out = []
        for m in (data.get("memories") or [])[:5]:
            kind, title, area = m.get("kind"), str(m.get("title") or "").strip(), m.get("area")
            if kind not in KINDS or not title or area not in LIFE_AREAS:
                continue
            try:
                conf = float(m.get("confidence", 0.6))
                imp = float(m.get("importance", 0.5))
            except (TypeError, ValueError):
                continue
            attrs = {k: m[k] for k in ("timeframe", "target_year") if m.get(k)}
            key = f"{kind}:{slugify(title)}"
            if kind == "goal":
                canon = canonical_goal(title)
                if canon:
                    key, title, area = canon
            out.append(Candidate(kind, key, title[:60], area, attrs, min(conf, 0.8), min(imp, 1.0),
                                 redact_pii(message)))
        return out
