import pytest

from app.memory.extractor import LLMExtractor, RuleExtractor, redact_pii
from tests.conftest import TODAY

ex = RuleExtractor(today=lambda: TODAY)


def keys(message):
    return {c.key: c for c in ex.extract(message).items}


@pytest.mark.parametrize("message,expected", [
    ("My name is Rahul. I was born on 15 August 1995 in Delhi.",
     {"name": "Rahul", "date_of_birth": "1995-08-15", "birth_place": "Delhi"}),
    ("I'm Priya, born 03/11/1998 at 6:30 pm in Pune",
     {"name": "Priya", "date_of_birth": "1998-11-03", "time_of_birth": "18:30", "birth_place": "Pune"}),
    ("I was born on August 15, 1995", {"date_of_birth": "1995-08-15"}),
    ("Please reply in Hindi from now on.", {"preferred_language": "Hindi"}),
    ("my name is not Rahul, it's Rohit", {"name": "Rohit"}),
])
def test_profile_fields(message, expected):
    assert ex.extract(message).profile == expected


def test_future_or_invalid_dates_are_ignored():
    assert "date_of_birth" not in ex.extract("I was born on 31 February 1995").profile
    assert "date_of_birth" not in ex.extract("I was born on 1 January 2099").profile


@pytest.mark.parametrize("message,key,attrs", [
    ("I'm planning to switch jobs next year.", "goal:career_change", {"target_year": 2027}),
    ("I want to buy a house by 2029", "goal:buy_home", {"target_year": 2029}),
    ("I'm preparing for a product management interview next month.",
     "goal:product_management_interview", {"target_month": "2026-11"}),
    ("My goal is to get married in two years", "goal:marriage", {"target_year": 2028}),
    ("I am preparing for UPSC exam", "goal:upsc_exam", {}),
])
def test_goals_with_timeframes(message, key, attrs):
    found = keys(message)
    assert key in found
    for k, v in attrs.items():
        assert found[key].attributes[k] == v


def test_correction_ignores_negated_timeframe():
    goal = keys("Actually I plan to switch jobs in 2028, not next year.")["goal:career_change"]
    assert goal.attributes["target_year"] == 2028


def test_tentative_goals_get_lower_confidence():
    assert keys("Maybe I will switch jobs someday")["goal:career_change"].confidence < \
        keys("I'm planning to switch jobs")["goal:career_change"].confidence


def test_interests_concerns_life_events():
    found = keys("I am interested in entrepreneurship and yoga. I'm worried about my health. I got promoted last week!")
    assert found["interest:entrepreneurship"].area == "career"
    assert found["interest:yoga"].area == "health"
    assert found["concern:health"].kind == "concern"
    assert found["life_event:got_promoted"].area == "career"


@pytest.mark.parametrize("message", [
    "What should I focus on for my career?",
    "Why do you say that?",
    "thanks!",
    "What if I quit my job?",
    "My friend wants to start a business.",
    "I want to know about my future",
    "I'm going to sleep now",
    "I like that answer",
])
def test_not_remembered(message):
    assert not ex.extract(message).has_updates


def test_pii_is_redacted_before_storage():
    text = "Call me on 9876543210 or mail rahul@example.com, PAN ABCDE1234F"
    red = redact_pii(text)
    assert "9876543210" not in red and "rahul@example.com" not in red and "ABCDE1234F" not in red
    goal = keys("My number is 9876543210 and I want to buy a house in 2027")["goal:buy_home"]
    assert "9876543210" not in goal.source_text


def test_llm_extractor_output_is_validated_and_canonicalised():
    raw = ('{"memories": [{"kind": "goal", "title": "Switch jobs", "area": "career", "target_year": 2027,'
           ' "confidence": 0.95, "importance": 0.9}, {"kind": "bogus", "title": "x", "area": "career"},'
           ' {"kind": "interest", "title": "Chess", "area": "not-an-area"},'
           ' {"kind": "life_event", "title": "Birth date and place", "area": "personal"}]}')
    out = LLMExtractor._parse(raw, "msg")
    assert [c.key for c in out] == ["goal:career_change"]
    assert out[0].confidence <= 0.8          # LLM-only facts are capped below rule confidence
    assert LLMExtractor._parse("not json", "msg") == []
