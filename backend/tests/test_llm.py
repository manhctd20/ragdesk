import json

import httpx2
import openai
import pytest

from llm import (
    BASE_URLS, ENV_VARS, LIMIT_PARAM, MAX_OUTPUT, NOT_FOUND, SYSTEM, build_messages, providers, rewrite,
    stream_answer,
)

FOLDER = "Phòng Bí Mật"
QUESTION = "Nghỉ phép năm được bao nhiêu ngày?"
ENV = {"GEMINI_API_KEY": "g-key-123", "GEMINI_MODEL": "gemini-test"}
ALL_ENV = {
    **ENV,
    "ANTHROPIC_API_KEY": "a-key-123", "CLAUDE_MODEL": "claude-test",
    "OPENAI_API_KEY": "o-key-123", "OPENAI_MODEL": "openai-test",
}


def hit(i, **loc):
    return {
        "id": f"doc{i}:0",
        "text": f"Nội dung đoạn số {i}",
        "meta": {"doc_id": f"doc{i}", "filename": f"tai-lieu-{i}.pdf", "folder": FOLDER, "file_type": "pdf", **loc},
        "score": 1 / (60 + i),
        "matched": [],
    }


def five_chunks():
    return [hit(1, page=3), hit(2, section="Chế độ nghỉ"), hit(3, sheet="Bảng lương", row=7), hit(4, page=1),
            hit(5, page=2)]


def test_constants():
    assert list(ENV_VARS) == ["claude", "openai", "gemini"]
    assert ENV_VARS["claude"] == ("ANTHROPIC_API_KEY", "CLAUDE_MODEL")
    assert ENV_VARS["openai"] == ("OPENAI_API_KEY", "OPENAI_MODEL")
    assert ENV_VARS["gemini"] == ("GEMINI_API_KEY", "GEMINI_MODEL")
    assert BASE_URLS["claude"] == "https://api.anthropic.com/v1/"
    assert BASE_URLS["openai"] is None
    assert BASE_URLS["gemini"] == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert LIMIT_PARAM == {"claude": "max_tokens", "openai": "max_completion_tokens", "gemini": "max_tokens"}
    assert MAX_OUTPUT == 4000
    assert NOT_FOUND == "Không tìm thấy trong tài liệu"


@pytest.mark.parametrize(
    "env,expected",
    [
        (ALL_ENV, ["claude", "openai", "gemini"]),
        (ENV, ["gemini"]),
        ({"OPENAI_API_KEY": "o", "OPENAI_MODEL": "m"}, ["openai"]),
        ({"ANTHROPIC_API_KEY": "a", "CLAUDE_MODEL": "c", "GEMINI_API_KEY": "g", "GEMINI_MODEL": "m"},
         ["claude", "gemini"]),
        ({"ANTHROPIC_API_KEY": "a"}, []),
        ({"OPENAI_API_KEY": "o"}, []),
        ({"OPENAI_MODEL": "m"}, []),
        ({"GEMINI_API_KEY": "k"}, []),
        ({"GEMINI_MODEL": "m"}, []),
        ({"GEMINI_API_KEY": "  ", "GEMINI_MODEL": "m"}, []),
        ({"GEMINI_API_KEY": "k", "GEMINI_MODEL": " \t"}, []),
        ({"GEMINI_API_KEY": "", "GEMINI_MODEL": ""}, []),
        ({}, []),
    ],
)
def test_providers(env, expected):
    assert providers(env) == expected


def test_build_messages_five_chunks():
    msgs = build_messages(QUESTION, five_chunks())
    assert [m["role"] for m in msgs] == ["system", "user"]
    system, user = msgs[0]["content"], msgs[1]["content"]
    for i in range(1, 6):
        assert f"[{i}]" in user
        assert f"tai-lieu-{i}.pdf" in user
        assert f"Nội dung đoạn số {i}" in user
    assert QUESTION in user
    assert user.index(QUESTION) > user.index("[5]")
    assert NOT_FOUND in system
    assert "trang 3" in user
    assert "mục Chế độ nghỉ" in user
    assert "Bảng lương" in user and "dòng 7" in user
    for m in msgs:
        assert FOLDER not in m["content"]
        assert "doc1" not in m["content"]


def test_build_messages_caps_at_five():
    chunks = [hit(i, page=i) for i in range(1, 8)]
    user = build_messages(QUESTION, chunks)[1]["content"]
    for i in range(1, 6):
        assert f"[{i}]" in user
    assert "[6]" not in user and "[7]" not in user
    assert "tai-lieu-6.pdf" not in user and "tai-lieu-7.pdf" not in user


def completion(content):
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "gemini-test",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
    }


def client_with(handler):
    return httpx2.Client(transport=httpx2.MockTransport(handler))


def sse(*deltas, finish="stop"):
    """Fake OpenAI streaming body: first a role-only chunk, then one chunk per delta, then finish + [DONE]."""
    def frame(delta, finish_reason=None):
        data = {
            "id": "chatcmpl-1", "object": "chat.completion.chunk", "created": 0, "model": "m",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }
        return f"data: {json.dumps(data)}\n\n"

    body = frame({"role": "assistant"})
    body += "".join(frame({"content": d}) for d in deltas)
    body += frame({}, finish) + "data: [DONE]\n\n"
    return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())


@pytest.mark.parametrize(
    "provider,url,limit",
    [
        ("claude", "https://api.anthropic.com/v1/chat/completions", "max_tokens"),
        ("openai", "https://api.openai.com/v1/chat/completions", "max_completion_tokens"),
        ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "max_tokens"),
    ],
)
def test_stream_answer_each_provider(provider, url, limit):
    seen = []

    def handler(request):
        seen.append(request)
        return sse("Được 12 ngày [1]")

    out = list(stream_answer(QUESTION, five_chunks(), provider, ALL_ENV, http_client=client_with(handler)))

    assert out == ["Được 12 ngày [1]"]
    assert len(seen) == 1
    req = seen[0]
    assert req.method == "POST"
    assert str(req.url) == url
    key, model = ENV_VARS[provider]
    assert req.headers["authorization"] == f"Bearer {ALL_ENV[key]}"
    body = json.loads(req.content)
    assert body["model"] == ALL_ENV[model]
    assert body["stream"] is True
    assert body[limit] == 4000
    assert not ({"max_tokens", "max_completion_tokens"} - {limit}) & body.keys()
    assert "temperature" not in body
    assert "top_p" not in body
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert FOLDER not in json.dumps(body, ensure_ascii=False)


def test_stream_answer_yields_text_and_skips_empty():
    def handler(request):
        return sse("Cần ", "", None, "duyệt [1].")

    out = list(stream_answer(QUESTION, five_chunks(), "gemini", ENV, http_client=client_with(handler)))

    assert out == ["Cần ", "duyệt [1]."]


def test_stream_answer_status_error_raises():
    def handler(request):
        return httpx2.Response(401, json={"error": {"message": "bad key", "code": 401}})

    with pytest.raises(openai.APIStatusError):
        next(stream_answer(QUESTION, five_chunks(), "gemini", ENV, http_client=client_with(handler)))


def test_rewrite_sends_turns_and_returns_text():
    seen = []
    turns = [
        {"question": "Nghỉ phép năm được bao nhiêu ngày?", "answer": "Được 12 ngày [1]."},
        {"question": "Còn nghỉ ốm?", "answer": "Được 30 ngày [2]."},
    ]

    def handler(request):
        seen.append(request)
        return httpx2.Response(200, json=completion("  Nghỉ ốm ai duyệt?\n"))

    out = rewrite("thế ai duyệt?", turns, "claude", ALL_ENV, http_client=client_with(handler))

    assert out == "Nghỉ ốm ai duyệt?"
    assert len(seen) == 1
    assert str(seen[0].url) == "https://api.anthropic.com/v1/chat/completions"
    body = json.loads(seen[0].content)
    assert "stream" not in body or body["stream"] is False
    assert body["max_tokens"] == 4000
    assert "temperature" not in body and "top_p" not in body
    sent = "\n".join(m["content"] for m in body["messages"])
    for t in turns:
        assert t["question"] in sent and t["answer"] in sent
    assert "thế ai duyệt?" in sent
    assert sent.index("thế ai duyệt?") > sent.index("Được 30 ngày [2].")


@pytest.mark.parametrize("content", ["", None])
def test_rewrite_empty_returns_empty_string(content):
    def handler(request):
        return httpx2.Response(200, json=completion(content))

    turns = [{"question": "q", "answer": "a"}]
    assert rewrite("câu hỏi", turns, "gemini", ENV, http_client=client_with(handler)) == ""


def test_system_forbids_markdown():
    assert "markdown" in SYSTEM.lower()
    assert NOT_FOUND in SYSTEM
    assert "[1]" in SYSTEM
    assert build_messages(QUESTION, five_chunks())[0]["content"] == SYSTEM


def test_system_prompt_has_no_fixed_source_count():
    assert "[5]" not in SYSTEM
