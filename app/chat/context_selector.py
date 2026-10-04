"""Step 2: choose the *relevant* slice of the Shared Brain + conversation for this message.

Never sends the full graph or full history. Rules by intent:
  smalltalk  -> profile (name) only
  recall     -> memories in the asked-about areas (all areas if none named) + previous-session summary
  followup   -> memories used for the previous answer + recent turns (always)
  advice /
  share_info -> memories in the detected areas; if no area detected, only the top-3 most important
Items are ranked by importance, confidence and recency, then trimmed to a token budget.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from app.brain.models import MemoryItem
from app.chat.query_understanding import QueryAnalysis
from app.memory.short_term import SessionState, Turn
from app.profile.astrology import astro_profile, missing_profile_fields


@dataclass
class SelectedContext:
    profile: dict = field(default_factory=dict)
    astro: dict = field(default_factory=dict)
    items: list[MemoryItem] = field(default_factory=list)
    recent_turns: list[Turn] = field(default_factory=list)
    session_summary: str = ""
    previous_sessions: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    details: list[dict] = field(default_factory=list)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _age_days(iso: str) -> float:
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400)


def score(item: MemoryItem, today: date | None = None) -> float:
    """importance x confidence x recency (half-life 90 days); stale goals are down-weighted."""
    today = today or date.today()
    recency = 0.5 ** (_age_days(item.updated_at) / 90)
    s = 0.5 * item.importance + 0.3 * item.confidence + 0.2 * recency
    ty = item.attributes.get("target_year")
    if item.kind == "goal" and isinstance(ty, int) and ty < today.year:
        s *= 0.5   # memory decay: a goal whose timeframe has passed is probably outdated
    return round(s, 4)


class ContextSelector:
    def __init__(self, max_items: int = 8, max_tokens: int = 1200, max_turns: int = 6):
        self.max_items = max_items
        self.max_tokens = max_tokens
        self.max_turns = max_turns

    def select(self, analysis: QueryAnalysis, profile: dict | None, items: list[MemoryItem],
               session: SessionState, previous_sessions: list[dict]) -> SelectedContext:
        profile = profile or {}
        ctx = SelectedContext(missing_fields=missing_profile_fields(profile))

        # --- profile / astrology (a handful of tokens; always sent when known, because hiding birth
        # details made the model ask the user for data we already had) ---
        ctx.profile = {k: profile[k] for k in ("name", "preferred_language", "date_of_birth", "time_of_birth",
                                               "birth_place") if profile.get(k)}
        if analysis.intent != "smalltalk":
            astro = astro_profile(profile)
            if astro.get("sun_sign"):
                ctx.astro = astro
        if ctx.profile:
            ctx.labels.append("user_profile")
        if ctx.astro:
            ctx.labels.append("astrology_profile")

        # --- long-term memories ---
        ctx.items = self._select_items(analysis, items, session)

        # --- short-term conversation ---
        if analysis.intent != "smalltalk" or session.turns:
            ctx.recent_turns = list(session.turns)[-self.max_turns:]
        ctx.session_summary = session.summary
        if analysis.intent == "recall" and previous_sessions:
            ctx.previous_sessions = [s["summary"] for s in previous_sessions if s.get("summary")][:2]

        self._apply_budget(ctx)

        for it in ctx.items:
            if it.label not in ctx.labels:
                ctx.labels.append(it.label)
            ctx.details.append({"label": it.label, "value": it.describe(), "score": score(it)})
        if ctx.recent_turns:
            ctx.labels.append("conversation_history")
        if ctx.session_summary:
            ctx.labels.append("conversation_summary")
        if ctx.previous_sessions:
            ctx.labels.append("previous_session_summary")
        return ctx

    def _select_items(self, analysis: QueryAnalysis, items: list[MemoryItem],
                      session: SessionState) -> list[MemoryItem]:
        if analysis.intent == "smalltalk" or not items:
            return []
        areas = set(analysis.areas)
        if analysis.intent == "followup":
            last = session.last("assistant")
            used = set(last.meta.get("context_item_ids", [])) if last else set()
            chosen = [i for i in items if i.id in used or (areas and i.area in areas)]
        elif analysis.intent == "recall":
            chosen = [i for i in items if not areas or i.area in areas]
        elif areas:
            chosen = [i for i in items if i.area in areas]
        else:
            chosen = sorted((i for i in items if i.importance >= 0.8), key=score, reverse=True)[:3]
        chosen.sort(key=score, reverse=True)
        return chosen[: self.max_items]

    def _apply_budget(self, ctx: SelectedContext) -> None:
        """Drop the oldest turns first, then the lowest-scored memories, until within budget."""
        def total() -> int:
            return (estimate_tokens(" ".join(i.describe() for i in ctx.items))
                    + estimate_tokens(" ".join(t.content for t in ctx.recent_turns))
                    + estimate_tokens(ctx.session_summary) + estimate_tokens(" ".join(ctx.previous_sessions)))

        while total() > self.max_tokens and len(ctx.recent_turns) > 2:
            ctx.recent_turns.pop(0)
        while total() > self.max_tokens and ctx.items:
            ctx.items.pop()
        if total() > self.max_tokens:
            ctx.session_summary = ctx.session_summary[-400:]
