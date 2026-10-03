import itertools
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.brain.store import InMemoryGraphStore
from app.config import Settings
from app.llm.fallback import FallbackLLM
from app.llm.mock import MockProvider
from app.main import build_container, create_app

TODAY = date(2026, 10, 3)


@pytest.fixture
def settings():
    return Settings(_env_file=None, llm_provider="mock", graph_backend="memory", extraction_mode="rules")


@pytest.fixture
def store():
    return InMemoryGraphStore()


@pytest.fixture
def make_client(settings, store):
    def _make(llm=None, graph=None):
        container = build_container(settings, store=graph or store,
                                    llm=llm or FallbackLLM([MockProvider()]), today=lambda: TODAY)
        return TestClient(create_app(container))
    return _make


@pytest.fixture
def client(make_client):
    return make_client()


_ids = itertools.count()


@pytest.fixture
def ids():
    n = next(_ids)
    return f"user-{n}", f"session-{n}"


def chat(client, user_id, session_id, message):
    r = client.post("/chat", json={"user_id": user_id, "session_id": session_id, "message": message})
    assert r.status_code == 200, r.text
    return r.json()
