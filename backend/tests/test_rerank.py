from rerank import has_diacritics, rerank


class FakeScorer:
    def __init__(self, scores):
        self.scores, self.calls = scores, []

    def score(self, query, texts):
        self.calls.append((query, texts))
        return self.scores


def hits(*ids):
    return [{"id": i, "text": f"text {i}", "meta": {}, "score": 0.1, "matched": []} for i in ids]


def test_has_diacritics():
    assert has_diacritics("nghỉ phép năm")
    assert has_diacritics("đi công tác")
    assert not has_diacritics("nghi phep nam bao nhieu ngay")
    assert not has_diacritics("What is the leave policy?")


def test_rerank_sorts_and_cuts():
    s = FakeScorer([-6.0, 2.0, 0.0])
    out = rerank("ai duyệt nghỉ phép", hits("A", "B", "C"), s, -5.0)
    assert [h["id"] for h in out] == ["B", "C"]
    assert [h["rerank_score"] for h in out] == [2.0, 0.0]
    assert s.calls == [("ai duyệt nghỉ phép", ["text A", "text B", "text C"])]


def test_rerank_keeps_score_equal_to_min():
    assert [h["id"] for h in rerank("nghỉ phép", hits("A"), FakeScorer([-5.0]), -5.0)] == ["A"]


def test_rerank_all_below_returns_empty():
    assert rerank("nghỉ kết hôn", hits("A", "B"), FakeScorer([-7.0, -9.0]), -5.0) == []


def test_rerank_unaccented_query_untouched():
    s, h = FakeScorer([-9.0, -9.0]), hits("A", "B")
    assert rerank("nghi phep nam", h, s, -5.0) == h
    assert s.calls == []


def test_rerank_empty_hits_skips_scorer():
    s = FakeScorer([])
    assert rerank("nghỉ phép", [], s, -5.0) == [] and s.calls == []


def test_rerank_does_not_mutate_input():
    h = hits("A")
    rerank("nghỉ phép", h, FakeScorer([1.0]), -5.0)
    assert "rerank_score" not in h[0]
