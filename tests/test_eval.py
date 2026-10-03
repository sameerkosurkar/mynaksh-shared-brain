from eval.memory_eval import run


def test_offline_eval_thresholds():
    scores = run()
    assert scores["precision"] >= 0.9 and scores["recall"] >= 0.9
    assert scores["context_accuracy"] == 1.0
