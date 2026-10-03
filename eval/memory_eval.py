"""Offline evaluation of the two decisions the Shared Brain makes on every turn.

1. Memory extraction  - did we store the right facts and nothing else?  (precision / recall)
2. Context selection  - did we send relevant memories and leave out irrelevant ones?

Run:  python -m eval.memory_eval
The labelled sets are small and hand-written; in production they would be grown from sampled,
annotated real conversations and run in CI to catch regressions.
"""
from __future__ import annotations

from datetime import date

from app.brain.models import MemoryItem
from app.chat.context_selector import ContextSelector
from app.chat.query_understanding import analyze
from app.memory.extractor import Extraction, RuleExtractor
from app.memory.short_term import ShortTermMemory

# message -> keys that SHOULD be stored (profile fields as "profile:<field>")
EXTRACTION_CASES: list[tuple[str, set[str]]] = [
    ("My name is Rahul. I was born on 15 August 1995 in Delhi. I'm planning to switch jobs next year.",
     {"profile:name", "profile:date_of_birth", "profile:birth_place", "goal:career_change"}),
    ("I'm preparing for a product management interview next month.", {"goal:product_management_interview"}),
    ("I want to start my own business someday", {"goal:start_business", "interest:entrepreneurship"}),
    ("We are hoping to get married next year", set()),            # "we" plans: ambiguous -> not stored (rules)
    ("I'm planning to get married next year", {"goal:marriage"}),
    ("Please answer in Hindi", {"profile:preferred_language", "preference:language"}),
    ("I love painting and trekking", {"interest:painting", "interest:trekking"}),
    ("I'm really stressed about my finances", {"concern:finances"}),
    ("I got promoted last month!", {"life_event:got_promoted"}),
    ("My father passed away last year", {"life_event:loss_of_father"}),
    ("I was born at 10:30 am in Jaipur on 2 March 1992",
     {"profile:date_of_birth", "profile:time_of_birth", "profile:birth_place"}),
    ("I'm aiming to clear the CAT exam in 2027", {"goal:cat_exam"}),
    ("I want to lose weight this year", {"goal:fitness"}),
    # --- should store nothing ---
    ("What should I focus on for my career?", set()),
    ("Why do you say that?", set()),
    ("Thanks, that was helpful!", set()),
    ("My brother wants to move to Canada", set()),
    ("What if I quit my job tomorrow?", set()),
    ("I want to know what the stars say", set()),
    ("I'm tired today", set()),
    ("I like your answer", set()),
    ("My number is 9876543210", set()),
]

ITEMS = [
    MemoryItem("goal", "goal:career_change", "Career Change", "career", {"target_year": 2027}, importance=0.9),
    MemoryItem("goal", "goal:marriage", "Marriage", "relationships", importance=0.8),
    MemoryItem("concern", "concern:finances", "Finances", "finance", importance=0.6),
    MemoryItem("interest", "interest:yoga", "Yoga", "health", importance=0.5),
]
PROFILE = {"name": "Rahul", "date_of_birth": "1995-08-15", "birth_place": "Delhi"}

# query -> (labels that must be present, labels that must be absent)
CONTEXT_CASES = [
    ("What should I focus on for my career?", {"career_goal"}, {"relationships_goal", "finance_concern", "health_interest"}),
    ("Will I get married soon?", {"relationships_goal"}, {"career_goal", "finance_concern"}),
    ("How should I manage my money?", {"finance_concern"}, {"relationships_goal"}),
    ("Is yoga good for my health?", {"health_interest"}, {"career_goal", "relationships_goal"}),
    ("What do you remember about me?", {"career_goal", "relationships_goal", "finance_concern"}, set()),
    ("Hello!", set(), {"career_goal", "relationships_goal", "finance_concern", "health_interest"}),
]


def extracted_keys(ex: Extraction) -> set[str]:
    return {f"profile:{k}" for k in ex.profile} | {c.key for c in ex.items}


def run() -> dict:
    extractor = RuleExtractor(today=lambda: date(2026, 10, 3))
    tp = fp = fn = 0
    failures = []
    for msg, expected in EXTRACTION_CASES:
        got = extracted_keys(extractor.extract(msg))
        tp += len(got & expected)
        fp += len(got - expected)
        fn += len(expected - got)
        if got != expected:
            failures.append((msg, sorted(expected), sorted(got)))
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0

    selector, ok, ctx_fail = ContextSelector(), 0, []
    for query, must, must_not in CONTEXT_CASES:
        session = ShortTermMemory().get("u", "s")
        ctx = selector.select(analyze(query, Extraction(), False), PROFILE, ITEMS, session, [])
        labels = set(ctx.labels)
        if must <= labels and not (must_not & labels):
            ok += 1
        else:
            ctx_fail.append((query, sorted(labels)))

    print(f"Memory extraction : precision {precision:.2f}  recall {recall:.2f}  "
          f"({len(EXTRACTION_CASES) - len(failures)}/{len(EXTRACTION_CASES)} messages exact)")
    for msg, exp, got in failures:
        print(f"   x {msg!r}\n       expected {exp}\n       got      {got}")
    print(f"Context selection : {ok}/{len(CONTEXT_CASES)} queries had all relevant and no irrelevant memories")
    for q, labels in ctx_fail:
        print(f"   x {q!r} -> {labels}")
    return {"precision": precision, "recall": recall, "context_accuracy": ok / len(CONTEXT_CASES)}


if __name__ == "__main__":
    run()
