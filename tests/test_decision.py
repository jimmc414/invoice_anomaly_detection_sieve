from app.decision import decide, fuse_scores


def test_fuse_and_decide():
    score = fuse_scores(0.8, 0.2, True, 0.1)
    assert 80 <= score <= 100
    assert decide(score, 50, 80) == "HOLD"
