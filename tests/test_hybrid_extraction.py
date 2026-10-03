"""The LLM extractor adds long-tail memories the rules miss, without duplicating rule results."""
import json

from app.config import Settings
from app.llm.base import LLMProvider, LLMResponse
from app.llm.fallback import FallbackLLM
from tests.conftest import chat


class FakeRealLLM(LLMProvider):
    name, model = "fake", "fake-1"

    def generate(self, request):
        if request.json_mode:
            return LLMResponse(json.dumps({"memories": [
                {"kind": "goal", "title": "Switch jobs", "area": "career", "target_year": 2027, "confidence": 0.9},
                {"kind": "interest", "title": "Vedic astrology", "area": "spirituality", "confidence": 0.9,
                 "importance": 0.6}]}), self.name, self.model)
        return LLMResponse("ok", self.name, self.model)


def test_hybrid_mode_merges_llm_memories(store):
    from fastapi.testclient import TestClient
    from app.main import build_container, create_app
    settings = Settings(_env_file=None, graph_backend="memory", extraction_mode="hybrid")
    client = TestClient(create_app(build_container(settings, store=store, llm=FallbackLLM([FakeRealLLM()]))))
    body = chat(client, "u", "s", "I'm planning to switch jobs next year and I've been reading about vedic astrology a lot lately.")
    keys = [u["key"] for u in body["memory_updates"]]
    assert keys.count("goal:career_change") == 1            # rule result wins, LLM duplicate dropped
    assert "interest:vedic_astrology" in keys               # long-tail fact only the LLM found
