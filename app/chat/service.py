"""The end-to-end pipeline:

  message -> understand query -> select relevant context -> build LLM context -> generate
          -> update short-term memory -> update Shared Brain (long-term memory)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from app.chat.context_selector import ContextSelector
from app.chat.prompt_builder import build_request
from app.chat.query_understanding import analyze
from app.llm.base import LLMError
from app.llm.fallback import FallbackLLM
from app.memory.extractor import LLMExtractor, RuleExtractor
from app.memory.short_term import ShortTermMemory
from app.memory.updater import MemoryUpdater

log = logging.getLogger(__name__)

FALLBACK_REPLY = ("I'm having trouble reaching my guidance engine right now, so I can't give you a proper "
                  "answer this moment. I have still noted what you shared. Please try again shortly.")


@dataclass
class ChatResult:
    response: str
    context_used: list[str]
    context_details: list[dict]
    memory_updates: list[dict]
    intent: str
    life_areas: list[str]
    missing_profile_fields: list[str]
    llm_provider: str
    llm_model: str
    degraded: bool
    brain_available: bool
    warnings: list[str] = field(default_factory=list)
    latency_ms: int = 0


class ChatService:
    def __init__(self, store, llm: FallbackLLM, short_term: ShortTermMemory, selector: ContextSelector,
                 extraction_mode: str = "rules", min_confidence: float = 0.5,
                 today: Callable[[], date] = date.today):
        self.store = store
        self.llm = llm
        self.short_term = short_term
        self.selector = selector
        self.rules = RuleExtractor(today)
        self.llm_extractor = LLMExtractor(llm, today) if extraction_mode == "hybrid" and llm.is_real else None
        self.updater = MemoryUpdater(store, min_confidence)
        self.today = today

    def chat(self, user_id: str, session_id: str, message: str) -> ChatResult:
        start = time.monotonic()
        warnings: list[str] = []

        # 0. Load user (auto-create on first contact)
        profile = self.store.get_user(user_id)
        if profile is None:
            self.store.upsert_user(user_id, {})
            profile = {}
            warnings.append("new_user")

        session = self.short_term.get(user_id, session_id)
        last_assistant = session.last("assistant")

        # 1. Understand the query (rule extraction runs here so facts in this message are usable now)
        extraction = self.rules.extract(message)
        analysis = analyze(message, extraction, has_history=bool(session.turns),
                           prev_areas=last_assistant.meta.get("areas") if last_assistant else None)

        # 2. Select relevant long-term context (graph query filtered by life area)
        effective_profile = {**profile, **extraction.profile}
        fetch_areas = None if analysis.intent in ("recall", "followup") or not analysis.areas else analysis.areas
        items = self.store.get_items(user_id, areas=fetch_areas) if analysis.intent != "smalltalk" else []
        previous = (self.store.get_recent_sessions(user_id, exclude_session_id=session_id)
                    if analysis.intent == "recall" else [])
        ctx = self.selector.select(analysis, effective_profile, items, session, previous)
        if not ctx.items and analysis.intent in ("recall", "advice"):
            warnings.append("no_relevant_memory")

        # 3. Build LLM context & 4. generate
        request = build_request(message, analysis, ctx, extraction, self.today())
        try:
            result = self.llm.generate(request)
            text, provider, model, degraded = (result.response.text, result.response.provider,
                                               result.response.model, result.degraded)
        except LLMError as exc:
            log.error("LLM unavailable: %s", exc)
            text, provider, model, degraded = FALLBACK_REPLY, "none", "none", True
            warnings.append("llm_unavailable")

        # 5. Short-term memory
        self.short_term.append(user_id, session_id, "user", message, {"intent": analysis.intent})
        self.short_term.append(user_id, session_id, "assistant", text, {
            "areas": analysis.areas, "context_item_ids": [i.id for i in ctx.items]})

        # 6. Long-term memory update (rules always; LLM extractor only for statements worth the cost)
        updates = self._update_memory(user_id, message, extraction, analysis.intent, warnings)
        try:
            state = self.short_term.get(user_id, session_id)
            summary = (state.summary + " " + " | ".join(t.content[:120] for t in state.turns if t.role == "user")).strip()
            self.store.record_session(user_id, session_id, summary[-800:], state.turn_count)
        except Exception:  # noqa: BLE001
            log.exception("failed to record session")

        brain_ok = not getattr(self.store, "degraded", False)
        if not brain_ok:
            warnings.append("shared_brain_degraded")

        return ChatResult(
            response=text, context_used=ctx.labels, context_details=ctx.details, memory_updates=updates,
            intent=analysis.intent, life_areas=analysis.areas, missing_profile_fields=ctx.missing_fields,
            llm_provider=provider, llm_model=model, degraded=degraded or not brain_ok,
            brain_available=brain_ok, warnings=warnings, latency_ms=int((time.monotonic() - start) * 1000))

    def _update_memory(self, user_id, message, extraction, intent, warnings) -> list[dict]:
        if self.llm_extractor and intent in ("share_info", "advice") and not message.strip().endswith("?") \
                and len(message.split()) >= 5:
            try:
                rule_keys = {c.key for c in extraction.items}
                rule_slots = {(c.kind, c.area) for c in extraction.items}
                for cand in self.llm_extractor.extract(message):
                    if cand.key not in rule_keys and (cand.kind, cand.area) not in rule_slots:
                        extraction.items.append(cand)
            except Exception as exc:  # noqa: BLE001 - extractor is best-effort
                log.warning("LLM extraction skipped: %s", exc)
        if not extraction.has_updates:
            return []
        try:
            return self.updater.apply(user_id, extraction)
        except Exception:  # noqa: BLE001
            log.exception("memory update failed")
            warnings.append("memory_update_failed")
            return []
