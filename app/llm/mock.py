"""Deterministic offline provider.

Lets the whole system (API, memory, tests, demo) run without any API key. It does not parse the
prompt text; it reads the structured `metadata` that the prompt builder attaches, so the answers
reflect exactly the context that was selected.
"""
from __future__ import annotations

from app.llm.base import LLMProvider, LLMRequest, LLMResponse

_AREA_TIPS = {
    "career": "build one visible proof of skill, have conversations with people already in the roles you want, "
              "and set a clear timeline for your move",
    "relationships": "communicate openly, give your relationships consistent time, and avoid big decisions "
                     "when emotions run high",
    "health": "keep a steady routine for sleep and movement, and consult a professional for anything persistent",
    "finance": "build an emergency fund first, avoid impulsive investments, and review spending monthly",
    "education": "work in short daily blocks, revise what you learn, and attempt full practice tests early",
    "family": "make time for honest conversations and share responsibilities",
    "spirituality": "keep a short daily practice such as meditation or reflection",
    "travel": "plan in advance and keep some flexibility in your schedule",
    "personal": "pick one small habit and stay consistent with it",
}


class MockProvider(LLMProvider):
    name = "mock"
    model = "mock-astro-v1"

    def generate(self, request: LLMRequest) -> LLMResponse:
        md = request.metadata
        if md.get("task") == "extract":
            return LLMResponse('{"memories": []}', self.name, self.model)
        handler = {
            "smalltalk": self._smalltalk, "recall": self._recall, "followup": self._followup,
            "share_info": self._share_info,
        }.get(md.get("intent"), self._advice)
        return LLMResponse(handler(md).strip(), self.name, self.model)

    # -- helpers ---------------------------------------------------------------
    @staticmethod
    def _hello(md: dict) -> str:
        name = (md.get("profile") or {}).get("name")
        return f"Namaste {name}!" if name else "Namaste!"

    @staticmethod
    def _astro_line(md: dict) -> str:
        astro = md.get("astro") or {}
        if not astro.get("sun_sign"):
            return ""
        lead = f"As a {astro['sun_sign']} ({astro.get('element')} sign, ruled by {astro.get('ruling_planet')}), "
        if (md.get("areas") or ["career"])[0] == "career":
            return lead + f"you tend to do best with {astro.get('career_hint')}."
        traits = list(astro.get("traits") or [])
        return lead + f"you are naturally {', '.join(traits[:-1])} and {traits[-1]}; use that, but watch for being too {traits[-1]}."

    @staticmethod
    def _missing_line(md: dict) -> str:
        missing = md.get("missing_fields") or []
        if "date_of_birth" in missing:
            return "Share your date of birth (and ideally time and place of birth) so I can make this more personal."
        return ""

    # -- intents ---------------------------------------------------------------
    def _smalltalk(self, md: dict) -> str:
        return f"{self._hello(md)} I'm Naksh, your astrology guide. Ask me about your career, relationships, health or anything on your mind."

    def _share_info(self, md: dict) -> str:
        facts = md.get("new_facts") or []
        noted = ("I've noted: " + "; ".join(facts) + ".") if facts else "Thank you for sharing that."
        return " ".join(filter(None, [self._hello(md), noted, self._astro_line(md),
                                      "Ask me what to focus on whenever you're ready.", self._missing_line(md)]))

    def _recall(self, md: dict) -> str:
        items = md.get("items") or []
        areas = md.get("areas") or []
        topic = " and ".join(areas) if areas else "you"
        if not items:
            return (f"I don't have anything saved about your {topic} yet. "
                    "Tell me what you're working towards and I'll remember it for next time.")
        lines = "\n".join(f"- {i}" for i in items)
        return f"Here's what I remember about your {topic}:\n{lines}"

    def _followup(self, md: dict) -> str:
        last = md.get("last_assistant_message")
        if not last:
            return "Could you tell me what you're referring to? I don't have an earlier answer in this conversation."
        reasons = [f"you told me about: {', '.join(md['items'])}"] if md.get("items") else []
        astro = self._astro_line(md)
        if astro:
            reasons.append(astro[0].lower() + astro[1:])
        basis = " Also, ".join(reasons) if reasons else "of what you shared earlier in this conversation"
        snippet = last if len(last) < 160 else last[:157] + "..."
        return f"I said \"{snippet}\" because {basis}"

    def _advice(self, md: dict) -> str:
        areas = md.get("areas") or ["personal"]
        items = md.get("items") or []
        parts = [self._hello(md)]
        if items:
            parts.append(f"Based on what you've shared ({'; '.join(items)}),")
        else:
            parts.append("Here's my guidance:")
        parts.append(f"for {areas[0]}, focus on: {_AREA_TIPS.get(areas[0], _AREA_TIPS['personal'])}.")
        parts.append(self._astro_line(md))
        parts.append(self._missing_line(md))
        return " ".join(p for p in parts if p)
