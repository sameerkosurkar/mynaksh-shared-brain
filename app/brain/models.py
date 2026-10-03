"""Domain objects stored in the Shared Brain."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# kind -> (Neo4j node label, relationship type from User)
KIND_SCHEMA: dict[str, tuple[str, str]] = {
    "goal": ("Goal", "HAS_GOAL"),
    "interest": ("Interest", "INTERESTED_IN"),
    "preference": ("Preference", "PREFERS"),
    "life_event": ("LifeEvent", "EXPERIENCED"),
    "concern": ("Concern", "CONCERNED_ABOUT"),
}
KINDS = tuple(KIND_SCHEMA)

LIFE_AREAS = (
    "career", "relationships", "health", "finance", "education",
    "family", "spirituality", "travel", "personal",
)

PROFILE_FIELDS = ("name", "date_of_birth", "time_of_birth", "birth_place", "preferred_language")

ACTIVE = "active"
SUPERSEDED = "superseded"
ABANDONED = "abandoned"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class MemoryItem:
    """One long-term fact about the user (goal, interest, preference, life event, concern)."""

    kind: str
    key: str                      # canonical identity used for dedupe/conflicts, e.g. "goal:career_change"
    title: str                    # human readable, e.g. "Career Change"
    area: str                     # LifeArea name
    attributes: dict[str, Any] = field(default_factory=dict)   # e.g. {"target_year": 2027}
    confidence: float = 0.7       # how sure we are the fact is correct
    importance: float = 0.6       # how useful it is for future conversations
    status: str = ACTIVE
    source_text: str = ""
    mention_count: int = 1
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=utcnow_iso)
    updated_at: str = field(default_factory=utcnow_iso)

    @property
    def label(self) -> str:
        """Context label used in API responses, e.g. "career_goal"."""
        return f"{self.area}_{self.kind}"

    def describe(self) -> str:
        details = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in self.attributes.items() if v not in (None, ""))
        return f"{self.title}" + (f" ({details})" if details else "")

    # --- serialisation (flat props so they are readable in the Neo4j browser) ---
    def to_props(self) -> dict[str, Any]:
        props = {
            "id": self.id, "kind": self.kind, "key": self.key, "title": self.title, "area": self.area,
            "confidence": self.confidence, "importance": self.importance, "status": self.status,
            "source_text": self.source_text, "mention_count": self.mention_count,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }
        for k, v in self.attributes.items():
            if v is not None:
                props[f"attr_{k}"] = v
        return props

    @classmethod
    def from_props(cls, props: dict[str, Any]) -> "MemoryItem":
        attrs = {k[5:]: v for k, v in props.items() if k.startswith("attr_")}
        base = {k: props[k] for k in (
            "id", "kind", "key", "title", "area", "confidence", "importance", "status",
            "source_text", "mention_count", "created_at", "updated_at") if k in props}
        return cls(attributes=attrs, **base)
