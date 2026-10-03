"""Provider adapters tested against stubbed HTTP (no network, no keys)."""
import httpx
import pytest

from app.config import Settings
from app.llm import providers
from app.llm.base import ChatMessage, LLMError, LLMRequest
from app.llm.fallback import build_llm

REQ = LLMRequest(system="sys", messages=[ChatMessage("user", "hi"), ChatMessage("assistant", "hello"),
                                         ChatMessage("user", "career?")])


class Capture:
    def __init__(self, status, body):
        self.status, self.body, self.calls = status, body, []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.calls.append((url, headers, json))
        return httpx.Response(self.status, json=self.body, request=httpx.Request("POST", url))


def test_openai_payload_and_parsing(monkeypatch):
    cap = Capture(200, {"choices": [{"message": {"content": " answer "}}]})
    monkeypatch.setattr(providers.httpx, "post", cap)
    resp = providers.OpenAIProvider("k", "gpt-x", "https://api.openai.com/v1", 5).generate(REQ)
    url, headers, body = cap.calls[0]
    assert url.endswith("/chat/completions") and headers["Authorization"] == "Bearer k"
    assert body["messages"][0] == {"role": "system", "content": "sys"} and len(body["messages"]) == 4
    assert resp.text == "answer" and resp.provider == "openai"


def test_anthropic_payload_and_parsing(monkeypatch):
    cap = Capture(200, {"content": [{"type": "text", "text": "namaste"}]})
    monkeypatch.setattr(providers.httpx, "post", cap)
    resp = providers.AnthropicProvider("k", "claude-x", 5).generate(REQ)
    _, headers, body = cap.calls[0]
    assert headers["x-api-key"] == "k" and body["system"] == "sys" and body["messages"][-1]["content"] == "career?"
    assert resp.text == "namaste"


def test_gemini_payload_and_parsing(monkeypatch):
    cap = Capture(200, {"candidates": [{"content": {"parts": [{"text": "thinking", "thought": True},
                                                              {"text": "final"}]}}]})
    monkeypatch.setattr(providers.httpx, "post", cap)
    resp = providers.GeminiProvider("k", "gemini-x", 5).generate(REQ)
    url, headers, body = cap.calls[0]
    assert "gemini-x:generateContent" in url and headers["x-goog-api-key"] == "k"
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
    assert resp.text == "final"                       # thought parts are dropped


@pytest.mark.parametrize("status,retryable", [(429, True), (503, True), (401, False), (400, False)])
def test_http_errors_are_classified(monkeypatch, status, retryable):
    monkeypatch.setattr(providers.httpx, "post", Capture(status, {"error": "x"}))
    with pytest.raises(LLMError) as err:
        providers.GeminiProvider("k", "m", 5).generate(REQ)
    assert err.value.retryable is retryable


def test_missing_key_falls_back_to_mock():
    llm = build_llm(Settings(_env_file=None, llm_provider="gemini", gemini_api_key=""))
    assert [p.name for p in llm.providers] == ["mock"]
    llm = build_llm(Settings(_env_file=None, llm_provider="openai", openai_api_key="k"))
    assert [p.name for p in llm.providers] == ["openai", "mock"] and llm.is_real
