"""End-to-end scenarios from the assignment, exercised through the HTTP API.

Runs with the in-memory graph and the deterministic mock LLM, so no Docker or API key is needed.
"""
from tests.conftest import chat

RAHUL_INTRO = "My name is Rahul. I was born on 15 August 1995 in Delhi. I'm planning to switch jobs next year."


def _goals(client, user_id, status="active"):
    brain = client.get(f"/users/{user_id}/brain").json()
    return [e["target"] for e in brain["relationships"]
            if e["type"] == "HAS_GOAL" and e["target"]["status"] == status]


# 1. New user ---------------------------------------------------------------------------------
def test_new_user_is_created_and_asked_for_missing_details(client, ids):
    uid, sid = ids
    body = chat(client, uid, sid, "Hi")
    assert "new_user" in body["warnings"]
    assert body["intent"] == "smalltalk"
    assert set(body["missing_profile_fields"]) >= {"name", "date_of_birth"}
    assert client.get(f"/users/{uid}").status_code == 200


# 2. Creating a long-term memory ---------------------------------------------------------------
def test_intro_message_creates_profile_zodiac_and_goal(client, ids):
    uid, sid = ids
    body = chat(client, uid, sid, RAHUL_INTRO)
    actions = {(u["key"], u["action"]) for u in body["memory_updates"]}
    assert ("goal:career_change", "created") in actions
    assert ("profile:name", "created") in actions

    user = client.get(f"/users/{uid}").json()
    assert user["name"] == "Rahul" and user["birth_place"] == "Delhi" and user["sun_sign"] == "Leo"
    goals = _goals(client, uid)
    assert goals[0]["title"] == "Career Change"
    assert goals[0]["attr_target_year"] == 2027          # "next year" resolved against today (2026)


def test_pm_interview_goal_with_timeframe(client, ids):
    uid, sid = ids
    chat(client, uid, sid, "I'm preparing for a product management interview next month.")
    goal = _goals(client, uid)[0]
    assert goal["title"] == "Product Management Interview"
    assert goal["attr_timeframe"] == "next month" and goal["attr_target_month"] == "2026-11"


# 3. Retrieving a memory in the same conversation ---------------------------------------------
def test_career_question_uses_goal_and_profile(client, ids):
    uid, sid = ids
    chat(client, uid, sid, RAHUL_INTRO)
    body = chat(client, uid, sid, "What should I focus on for my career?")
    assert body["intent"] == "advice"
    assert {"career_goal", "user_profile", "astrology_profile"} <= set(body["context_used"])
    assert "Career Change" in body["response"] and "Leo" in body["response"]
    assert body["memory_updates"] == []                   # a question is not stored as memory


# 4. Follow-up question ---------------------------------------------------------------------------
def test_followup_uses_short_term_context(client, ids):
    uid, sid = ids
    chat(client, uid, sid, RAHUL_INTRO)
    chat(client, uid, sid, "What should I focus on for my career?")
    body = chat(client, uid, sid, "Why do you say that?")
    assert body["intent"] == "followup"
    assert body["life_areas"] == ["career"]               # inherited from the previous turn
    assert "conversation_history" in body["context_used"]
    assert "career_goal" in body["context_used"]          # the memory used for the previous answer
    assert "because" in body["response"]


# 5. New session using previous information --------------------------------------------------
def test_new_session_recalls_long_term_memory(client, ids):
    uid, sid = ids
    chat(client, uid, sid, RAHUL_INTRO)
    body = chat(client, uid, "a-brand-new-session", "What do you remember about my career goals?")
    assert body["intent"] == "recall"
    assert "conversation_history" not in body["context_used"]   # no short-term context in a new session
    assert "career_goal" in body["context_used"]
    assert "Career Change" in body["response"] and "2027" in body["response"]


# 6. Irrelevant memory is not sent / not stored ----------------------------------------------
def test_irrelevant_memories_are_excluded_from_context(client, ids):
    uid, sid = ids
    chat(client, uid, sid, RAHUL_INTRO)
    chat(client, uid, sid, "I'm worried about my relationship with my partner.")
    body = chat(client, uid, "s2", "How is my health looking this year?")
    assert body["life_areas"] == ["health"]
    assert not any(label.startswith(("career", "relationships")) for label in body["context_used"])
    assert "Career Change" not in body["response"]


def test_small_talk_and_other_peoples_plans_are_not_remembered(client, ids):
    uid, sid = ids
    for msg in ("Thanks!", "My friend wants to start a business.", "What if I quit my job?",
                "I want to know about my future"):
        assert chat(client, uid, sid, msg)["memory_updates"] == []
    assert _goals(client, uid) == []


# 7. Correcting existing information ----------------------------------------------------------
def test_correcting_profile_keeps_history_and_recomputes(client, ids):
    uid, sid = ids
    chat(client, uid, sid, RAHUL_INTRO)
    body = chat(client, uid, sid, "Actually, I was born in Mumbai, not Delhi.")
    assert {"action": "corrected", "kind": "profile", "key": "profile:birth_place",
            "title": "birth_place", "detail": "Delhi -> Mumbai"} in body["memory_updates"]
    brain = client.get(f"/users/{uid}/brain").json()
    assert brain["user"]["birth_place"] == "Mumbai"
    assert brain["profile_history"][0]["old_value"] == "Delhi"


def test_correcting_goal_supersedes_old_version(client, ids):
    uid, sid = ids
    chat(client, uid, sid, RAHUL_INTRO)
    body = chat(client, uid, sid, "Actually I plan to switch jobs in 2028, not next year.")
    assert body["memory_updates"][0]["action"] == "updated"
    active, old = _goals(client, uid), _goals(client, uid, "superseded")
    assert len(active) == 1 and active[0]["attr_target_year"] == 2028
    assert len(old) == 1 and old[0]["attr_target_year"] == 2027
    recall = chat(client, uid, "s2", "What do you remember about my career goals?")
    assert "2028" in recall["response"] and "2027" not in recall["response"]


def test_abandoned_goal_is_no_longer_used(client, ids):
    uid, sid = ids
    chat(client, uid, sid, RAHUL_INTRO)
    body = chat(client, uid, sid, "I'm no longer planning to switch jobs.")
    assert body["memory_updates"][0]["action"] == "abandoned"
    assert _goals(client, uid) == []
    assert "career_goal" not in chat(client, uid, "s2", "What should I focus on in my career?")["context_used"]


def test_repeated_fact_is_reinforced_not_duplicated(client, ids):
    uid, sid = ids
    chat(client, uid, sid, RAHUL_INTRO)
    body = chat(client, uid, "s2", "I'm planning to switch jobs next year.")
    assert body["memory_updates"][0]["action"] == "reinforced"
    goals = _goals(client, uid)
    assert len(goals) == 1 and goals[0]["mention_count"] == 2


# 8. Missing user information ---------------------------------------------------------------------
def test_missing_birth_details_are_flagged_and_requested(client, ids):
    uid, sid = ids
    body = chat(client, uid, sid, "What does my zodiac sign say about my career this year?")
    assert "date_of_birth" in body["missing_profile_fields"]
    assert "astrology_profile" not in body["context_used"]
    assert "date of birth" in body["response"].lower()


def test_empty_memory_recall_is_honest(client, ids):
    uid, sid = ids
    body = chat(client, uid, sid, "What do you remember about my career goals?")
    assert "no_relevant_memory" in body["warnings"]
    assert "don't have anything saved" in body["response"]


# Profile API ----------------------------------------------------------------------------------------
def test_profile_api_and_language_preference(client):
    r = client.post("/users", json={"user_id": "priya", "name": "Priya", "date_of_birth": "1998-11-03",
                                    "time_of_birth": "18:30", "birth_place": "Pune", "preferred_language": "Hindi"})
    assert r.status_code == 201
    assert r.json()["sun_sign"] == "Scorpio" and r.json()["missing_profile_fields"] == []
    brain = client.get("/users/priya/brain").json()
    assert any(e["type"] == "PREFERS" and e["target"]["title"] == "Hindi" for e in brain["relationships"])
    r = client.patch("/users/priya/profile", json={"date_of_birth": "1998-03-25"})
    assert r.json()["sun_sign"] == "Aries"
