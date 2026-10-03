from app.brain.models import MemoryItem
from app.chat.context_selector import ContextSelector, score
from app.chat.query_understanding import analyze
from app.memory.extractor import Extraction
from app.memory.short_term import ShortTermMemory
from tests.conftest import TODAY

PROFILE = {"name": "Rahul", "date_of_birth": "1995-08-15", "birth_place": "Delhi"}


def item(title, area, kind="goal", importance=0.8, **attrs):
    return MemoryItem(kind=kind, key=f"{kind}:{title}", title=title, area=area, attributes=attrs, importance=importance)


ITEMS = [item("Career Change", "career", target_year=2027), item("Marriage", "relationships"),
         item("Yoga", "health", kind="interest", importance=0.5)]


def select(message, items=ITEMS, session=None, **kw):
    stm = ShortTermMemory()
    session = session or stm.get("u", "s")
    a = analyze(message, Extraction(), has_history=bool(session.turns))
    return a, ContextSelector(**kw).select(a, PROFILE, items, session, [])


def test_only_matching_life_area_is_selected():
    a, ctx = select("How will my career go?")
    assert a.areas == ["career"]
    assert [i.title for i in ctx.items] == ["Career Change"]
    assert "career_goal" in ctx.labels and "relationships_goal" not in ctx.labels


def test_no_area_falls_back_to_top_important_items_only():
    _, ctx = select("Give me some guidance")
    assert {i.title for i in ctx.items} == {"Career Change", "Marriage"}   # importance >= 0.8 only


def test_smalltalk_sends_no_memories():
    a, ctx = select("Hello")
    assert a.intent == "smalltalk" and ctx.items == [] and ctx.astro == {}


def test_birth_details_only_for_astrology_questions():
    _, ctx = select("How will my career go?")
    assert "date_of_birth" not in ctx.profile
    _, ctx = select("What does my kundli say about my career?")
    assert ctx.profile["date_of_birth"] == "1995-08-15"


def test_followup_reuses_previous_answer_context():
    stm = ShortTermMemory()
    stm.append("u", "s", "user", "What about my career?")
    stm.append("u", "s", "assistant", "Focus on X", {"areas": ["career"], "context_item_ids": [ITEMS[0].id]})
    session = stm.get("u", "s")
    a = analyze("Why do you say that?", Extraction(), True, ["career"])
    ctx = ContextSelector().select(a, PROFILE, ITEMS, session, [])
    assert a.intent == "followup"
    assert [i.title for i in ctx.items] == ["Career Change"]
    assert "conversation_history" in ctx.labels


def test_token_budget_trims_lowest_scored_items():
    many = [item(f"Career goal number {n} " + "x" * 200, "career", importance=n / 20) for n in range(15)]
    _, ctx = select("career advice please", items=many, max_items=15, max_tokens=300)
    assert 0 < len(ctx.items) < 15
    assert ctx.items[0].importance == max(i.importance for i in ctx.items)


def test_stale_goal_is_down_weighted():
    assert score(item("Old", "career", target_year=2020), TODAY) < score(item("New", "career", target_year=2027), TODAY)


def test_short_term_window_rolls_into_summary():
    stm = ShortTermMemory(max_messages=2)
    for n in range(4):
        stm.append("u", "s", "user", f"message {n}")
    s = stm.get("u", "s")
    assert [t.content for t in s.turns] == ["message 2", "message 3"]
    assert "message 0" in s.summary and "message 1" in s.summary
    assert stm.get("other-user", "s").turns == type(s.turns)()   # sessions are isolated per user
