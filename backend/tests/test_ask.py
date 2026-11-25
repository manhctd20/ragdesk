import pytest

from ask import HISTORY_TURNS, ask_events

NO_DOCS = "Chưa có tài liệu nào"
CHUNKS = [{"id": "A:0", "text": "Giám đốc duyệt nghỉ phép", "meta": {}, "score": 0.1, "matched": []}]


def turn(question, mode="external", provider="claude", answer="trả lời"):
    return {"question": question, "mode": mode, "provider": provider, "answer": answer}


class Fakes:
    def __init__(self, chunks=CHUNKS, rewritten="Câu viết lại?", deltas=("Cần ", "duyệt [1]."), fail_after=None, rewrite_exc=None):
        self.chunks, self.rewritten, self.deltas = chunks, rewritten, deltas
        self.fail_after, self.rewrite_exc = fail_after, rewrite_exc
        self.find_calls, self.rewrite_calls, self.stream_calls = [], [], []

    def find(self, query, highlight):
        self.find_calls.append((query, highlight))
        return self.chunks

    def rewrite(self, question, turns, provider, env):
        self.rewrite_calls.append((question, turns, provider, env))
        if self.rewrite_exc:
            raise self.rewrite_exc
        return self.rewritten

    def stream_answer(self, question, chunks, provider, env):
        self.stream_calls.append((question, chunks, provider, env))
        yield from self.deltas
        if self.fail_after is not None:
            raise RuntimeError("boom")


def run(fakes, question="thế ai duyệt?", mode="external", provider="claude", history=()):
    return list(
        ask_events(
            question, mode, provider, list(history),
            find=fakes.find, stream_answer=fakes.stream_answer, rewrite=fakes.rewrite, env={"K": "v"},
        )
    )


def names(events):
    return [n for n, _ in events]


def test_internal_never_calls_llm():
    f = Fakes()
    events = run(f, mode="internal", provider=None, history=[turn("a")])
    assert names(events) == ["meta", "done"]
    assert f.rewrite_calls == [] and f.stream_calls == []
    assert events[0][1] == {"sources": CHUNKS, "query": None, "message": None}


def test_internal_query_prepends_previous_question():
    f = Fakes()
    run(f, "thế ai duyệt?", "internal", None, [turn("nghỉ phép năm", mode="external"), turn("câu lượt cuối", mode="internal", provider=None, answer=None)])
    assert f.find_calls == [("câu lượt cuối thế ai duyệt?", "thế ai duyệt?")]
    f = Fakes()
    run(f, "thế ai duyệt?", "internal", None, [])
    assert f.find_calls == [("thế ai duyệt?", "thế ai duyệt?")]


@pytest.mark.parametrize(
    "bad",
    [
        {"mode": "internal", "provider": "claude", "answer": "x"},
        {"mode": "external", "provider": "claude", "answer": ""},
        {"mode": "external", "provider": "claude", "answer": None},
        {"mode": "external", "provider": "gemini", "answer": "x"},
        {"mode": "external", "provider": None, "answer": "x"},
    ],
    ids=["wrong-mode", "empty-answer", "none-answer", "other-provider", "none-provider"],
)
def test_external_drops_turn_failing_any_clause(bad):
    # each bad turn differs from a valid one in exactly one clause
    f = Fakes()
    run(f, history=[{"question": "BÍ-MẬT-NỘI-BỘ", **bad}, turn("nghỉ phép năm")])
    assert [t["question"] for t in f.rewrite_calls[0][1]] == ["nghỉ phép năm"]
    assert "BÍ-MẬT-NỘI-BỘ" not in repr(f.rewrite_calls) + repr(f.stream_calls) + repr(f.find_calls)


def test_external_drops_other_provider_turns():
    f = Fakes()
    events = run(f, provider="gemini", history=[turn("hỏi trước", provider="claude", answer="CLAUDE-ONLY")])
    assert f.rewrite_calls == []
    assert "CLAUDE-ONLY" not in repr(f.stream_calls) + repr(f.find_calls) + repr(events)


def test_external_rewrites_then_searches():
    f = Fakes(rewritten="Nghỉ phép năm ai duyệt?")
    events = run(f, history=[turn("nghỉ phép năm", answer="12 ngày")])
    assert f.rewrite_calls == [("thế ai duyệt?", [{"question": "nghỉ phép năm", "answer": "12 ngày"}], "claude", {"K": "v"})]
    assert f.find_calls == [("Nghỉ phép năm ai duyệt?", "Nghỉ phép năm ai duyệt?")]
    assert events[0][1]["query"] == "Nghỉ phép năm ai duyệt?"
    assert f.stream_calls == [("Nghỉ phép năm ai duyệt?", CHUNKS, "claude", {"K": "v"})]
    assert "nghỉ phép năm" not in repr(f.stream_calls)


def test_external_without_turns_skips_rewrite():
    f = Fakes()
    events = run(f, history=[])
    assert f.rewrite_calls == []
    assert events[0][1]["query"] is None
    assert f.find_calls == [("thế ai duyệt?", "thế ai duyệt?")]


@pytest.mark.parametrize("kind", ["raise", "empty", "blank"])
def test_rewrite_failure_or_empty_falls_back(kind):
    f = Fakes(rewrite_exc=RuntimeError("api") if kind == "raise" else None, rewritten="" if kind == "empty" else "  ")
    events = run(f, history=[turn("nghỉ phép năm")])
    assert f.find_calls == [("thế ai duyệt?", "thế ai duyệt?")]
    assert events[0][1]["query"] is None
    assert "error" not in names(events)
    assert f.stream_calls[0][0] == "thế ai duyệt?"


def test_external_streams_deltas():
    events = run(Fakes())
    assert names(events) == ["meta", "delta", "delta", "done"]
    assert [d["text"] for n, d in events if n == "delta"] == ["Cần ", "duyệt [1]."]


def test_external_error_midstream():
    events = run(Fakes(deltas=("Cần ",), fail_after=0))
    assert names(events) == ["meta", "delta", "error", "done"]
    assert events[2][1]["llm_error"].startswith("Không gọi được AI ngoài (")
    assert events[2][1]["llm_error"] == "Không gọi được AI ngoài (RuntimeError)"


def test_external_empty_stream_is_an_error():
    events = run(Fakes(deltas=()))
    assert names(events) == ["meta", "error", "done"]
    assert events[1][1]["llm_error"] == "Không gọi được AI ngoài (ValueError)"


def test_no_documents_message():
    f = Fakes(chunks=[])
    events = run(f)
    assert names(events) == ["meta", "done"]
    assert events[0][1]["message"] == NO_DOCS
    assert f.stream_calls == []


def test_only_last_three_turns_used():
    f = Fakes()
    run(f, history=[turn(f"câu {i}", answer=f"đáp {i}") for i in range(5)])
    assert HISTORY_TURNS == 3
    assert [t["question"] for t in f.rewrite_calls[0][1]] == ["câu 2", "câu 3", "câu 4"]
