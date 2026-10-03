"""Step 3: turn the selected context into an LLM request."""
from __future__ import annotations

from datetime import date

from app.chat.context_selector import SelectedContext
from app.chat.query_understanding import QueryAnalysis
from app.llm.base import ChatMessage, LLMRequest
from app.memory.extractor import Extraction

SYSTEM_PROMPT = """You are Naksh, the warm, grounded astrology guide of MyNaksh.

Rules:
- Personalise using ONLY the user context below. Never invent facts about the user. If something
  important is missing (e.g. date of birth for a chart-based answer), say so briefly and ask for it.
- Connect guidance to the user's goals and astrological attributes when relevant. Astrology is
  guidance, not certainty: no guarantees, and suggest a professional for medical, legal or financial decisions.
- For follow-up questions like "why?", explain your reasoning by pointing to the specific facts and
  astrological factors behind your previous answer.
- When asked what you remember, list the stored facts plainly and do not add new ones. If nothing is
  stored, say so honestly.
- Be concise (under 150 words) unless the user asks for detail. Respond in {language}."""


def _profile_block(ctx: SelectedContext) -> list[str]:
    lines = [f"- {k.replace('_', ' ').capitalize()}: {v}" for k, v in ctx.profile.items()]
    if ctx.astro:
        a = ctx.astro
        lines.append(f"- Sun sign: {a['sun_sign']} ({a['element']} sign, ruled by {a['ruling_planet']}; "
                     f"typical traits: {', '.join(a['traits'])})")
    if ctx.missing_fields:
        lines.append(f"- Not yet known: {', '.join(f.replace('_', ' ') for f in ctx.missing_fields)}")
    return lines


def build_request(message: str, analysis: QueryAnalysis, ctx: SelectedContext, extraction: Extraction,
                  today: date | None = None) -> LLMRequest:
    today = today or date.today()
    language = ctx.profile.get("preferred_language") or analysis.language_hint or "the user's language (default English)"
    sections = [SYSTEM_PROMPT.format(language=language), f"\nToday's date: {today.isoformat()}"]

    profile_lines = _profile_block(ctx)
    if profile_lines:
        sections.append("\n## User profile\n" + "\n".join(profile_lines))
    if ctx.items:
        sections.append("\n## Relevant long-term memory (Shared Brain)\n"
                        + "\n".join(f"- [{i.area} {i.kind.replace('_', ' ')}] {i.describe()}" for i in ctx.items))
    elif analysis.intent == "recall":
        sections.append("\n## Relevant long-term memory (Shared Brain)\n- (nothing stored for this topic)")
    if extraction.has_updates:
        sections.append("\n## New information in the current message (being saved)\n"
                        + "\n".join(f"- {d}" for d in extraction.describe()))
    if ctx.session_summary:
        sections.append("\n## Earlier in this conversation (summary)\n" + ctx.session_summary)
    if ctx.previous_sessions:
        sections.append("\n## Previous conversations (summaries)\n" + "\n".join(f"- {s}" for s in ctx.previous_sessions))

    messages = [ChatMessage(t.role, t.content) for t in ctx.recent_turns]
    messages.append(ChatMessage("user", message))

    last_assistant = next((t.content for t in reversed(ctx.recent_turns) if t.role == "assistant"), None)
    profile_for_mock = dict(ctx.profile)
    metadata = {
        "task": "chat",
        "intent": analysis.intent,
        "areas": analysis.areas,
        "profile": {**profile_for_mock, **{k: v for k, v in extraction.profile.items() if k == "name"}},
        "astro": ctx.astro,
        "items": [i.describe() for i in ctx.items],
        "new_facts": extraction.describe(),
        "missing_fields": ctx.missing_fields,
        "last_assistant_message": last_assistant,
    }
    return LLMRequest(system="\n".join(sections), messages=messages, metadata=metadata)
