import pytest

from app.brain.store import InMemoryGraphStore, ResilientGraphStore
from app.llm.base import LLMError, LLMProvider, LLMResponse
from app.llm.fallback import FallbackLLM
from app.llm.mock import MockProvider
from tests.conftest import chat


class FailingLLM(LLMProvider):
    name, model = "failing", "x"

    def __init__(self, retryable=False):
        self.calls = 0
        self.retryable = retryable

    def generate(self, request):
        self.calls += 1
        raise LLMError("boom", retryable=self.retryable)


class FailingGraph:
    def __getattr__(self, name):
        def fail(*a, **kw):
            raise ConnectionError("neo4j down")
        return fail


@pytest.mark.parametrize("payload", [
    {"user_id": "u", "session_id": "s", "message": ""},
    {"user_id": "u", "session_id": "s", "message": "   "},
    {"user_id": "bad id!", "session_id": "s", "message": "hi"},
    {"user_id": "u", "message": "hi"},
    {"user_id": "u", "session_id": "s", "message": "x" * 2001},
])
def test_invalid_input_returns_422(client, payload):
    r = client.post("/chat", json=payload)
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_input"


def test_invalid_profile_returns_422(client):
    assert client.post("/users", json={"user_id": "u", "date_of_birth": "2999-01-01"}).status_code == 422
    assert client.post("/users", json={"user_id": "u", "time_of_birth": "25:00"}).status_code == 422


def test_unknown_user_endpoints_return_404(client):
    assert client.get("/users/nobody").status_code == 404
    assert client.get("/users/nobody/brain").status_code == 404
    assert client.patch("/users/nobody/profile", json={"name": "X"}).status_code == 404


def test_llm_failure_falls_back_to_secondary_provider(make_client):
    client = make_client(llm=FallbackLLM([FailingLLM(), MockProvider()], max_retries=0))
    body = chat(client, "u1", "s1", "What should I focus on in my career?")
    assert body["llm_provider"] == "mock" and body["degraded"] is True


def test_total_llm_failure_returns_graceful_reply_and_still_saves_memory(make_client):
    client = make_client(llm=FallbackLLM([FailingLLM()], max_retries=0))
    body = chat(client, "u1", "s1", "I'm planning to switch jobs next year.")
    assert "llm_unavailable" in body["warnings"] and body["degraded"] is True
    assert "trouble" in body["response"]
    assert body["memory_updates"][0]["key"] == "goal:career_change"


def test_retryable_llm_errors_are_retried():
    failing = FailingLLM(retryable=True)
    llm = FallbackLLM([failing, MockProvider()], max_retries=1)
    from app.llm.base import LLMRequest
    assert llm.generate(LLMRequest(system="", messages=[])).degraded
    assert failing.calls == 2


def test_graph_failure_degrades_to_in_memory_store(make_client):
    graph = ResilientGraphStore(FailingGraph(), InMemoryGraphStore(), cooldown=60)
    client = make_client(graph=graph)
    body = chat(client, "u1", "s1", "My name is Rahul. I'm planning to switch jobs next year.")
    assert body["brain_available"] is False and "shared_brain_degraded" in body["warnings"]
    # memory still works within the process via the fallback store
    assert "Career Change" in chat(client, "u1", "s2", "What do you remember about my career?")["response"]
    assert client.get("/health").json()["status"] == "degraded"


def test_health_ok(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["llm_provider"] == "mock"
