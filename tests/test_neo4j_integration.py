"""Runs the same Shared Brain operations against a real Neo4j.

Skipped automatically when Neo4j is not reachable. Start it with `docker compose up -d neo4j`.
"""
import os
import uuid

import pytest

from app.brain.models import MemoryItem

URI = os.getenv("NEO4J_TEST_URI", "bolt://localhost:7687")
PASSWORD = os.getenv("NEO4J_PASSWORD", "mynaksh-dev-password")


@pytest.fixture(scope="module")
def neo():
    from app.brain.neo4j_store import Neo4jGraphStore
    store = Neo4jGraphStore(URI, "neo4j", PASSWORD)
    try:
        store.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Neo4j not reachable at {URI}: {exc}")
    yield store
    store.close()


def test_round_trip_and_supersede(neo):
    uid = f"it-{uuid.uuid4().hex[:8]}"
    try:
        neo.upsert_user(uid, {"name": "Rahul", "date_of_birth": "1995-08-15"})
        neo.set_zodiac(uid, "Leo")
        old = MemoryItem("goal", "goal:career_change", "Career Change", "career", {"target_year": 2027})
        neo.upsert_item(uid, old)
        assert neo.find_active_item(uid, "goal:career_change").attributes == {"target_year": 2027}
        assert neo.get_items(uid, areas=["health"]) == []

        new = MemoryItem("goal", "goal:career_change", "Career Change", "career", {"target_year": 2028})
        neo.upsert_item(uid, new)
        neo.link_supersedes(new.id, old.id)
        active = neo.get_items(uid, areas=["career"])
        assert [i.attributes["target_year"] for i in active] == [2028]

        brain = neo.get_brain(uid)
        assert brain["user"]["sun_sign"] == "Leo"
        assert brain["supersedes"] == [{"new_id": new.id, "old_id": old.id}]
    finally:
        assert neo.delete_user(uid)
        assert neo.get_user(uid) is None


def test_same_session_id_for_two_users_is_isolated(neo):
    a, b = f"it-{uuid.uuid4().hex[:8]}", f"it-{uuid.uuid4().hex[:8]}"
    try:
        for uid in (a, b):
            neo.upsert_user(uid, {})
            neo.record_session(uid, "session-1", f"summary for {uid}", 2)
        assert [s["summary"] for s in neo.get_recent_sessions(a)] == [f"summary for {a}"]
        assert [s["summary"] for s in neo.get_recent_sessions(b)] == [f"summary for {b}"]
    finally:
        neo.delete_user(a)
        neo.delete_user(b)
