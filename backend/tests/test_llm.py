import json

import httpx2
import openai
import pytest

from llm import BASE_URLS, ENV_VARS, NOT_FOUND, SYSTEM, answer, build_messages, providers

FOLDER = "Phòng Bí Mật"
QUESTION = "Nghỉ phép năm được bao nhiêu ngày?"
ENV = {"GEMINI_API_KEY": "g-key-123", "GEMINI_MODEL": "gemini-test"}


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
    assert BASE_URLS == {"gemini": "https://generativelanguage.googleapis.com/v1beta/openai/"}
    assert ENV_VARS == {"gemini": ("GEMINI_API_KEY", "GEMINI_MODEL")}
    assert NOT_FOUND == "Không tìm thấy trong tài liệu"


@pytest.mark.parametrize(
    "env,expected",
    [
        (ENV, ["gemini"]),
        ({"GEMINI_API_KEY": "k"}, []),
        ({"GEMINI_MODEL": "m"}, []),
        ({"GEMINI_API_KEY": "  ", "GEMINI_MODEL": "m"}, []),
        ({"GEMINI_API_KEY": "k", "GEMINI_MODEL": " \t"}, []),
        ({"GEMINI_API_KEY": "", "GEMINI_MODEL": ""}, []),
        ({}, []),
        ({"ANTHROPIC_API_KEY": "a", "CLAUDE_MODEL": "c", "OPENAI_API_KEY": "o", "OPENAI_MODEL": "m"}, []),
        ({**ENV, "ANTHROPIC_API_KEY": "a", "CLAUDE_MODEL": "c", "OPENAI_API_KEY": "o", "OPENAI_MODEL": "m"},
         ["gemini"]),
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


def test_answer_calls_gemini_endpoint():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx2.Response(200, json=completion("Được 12 ngày [1]"))

    out = answer(QUESTION, five_chunks(), "gemini", ENV, http_client=client_with(handler))

    assert out == "Được 12 ngày [1]"
    assert len(seen) == 1
    req = seen[0]
    assert req.method == "POST"
    assert str(req.url) == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert req.headers["authorization"] == "Bearer g-key-123"
    raw = req.content.decode()
    body = json.loads(raw)
    assert body["model"] == "gemini-test"
    assert body["max_tokens"] == 1024
    assert "temperature" not in body
    assert "top_p" not in body
    assert "stream" not in body or body["stream"] is False
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert FOLDER not in raw and FOLDER not in json.dumps(body, ensure_ascii=False)


def test_answer_status_error_raises():
    def handler(request):
        return httpx2.Response(401, json={"error": {"message": "bad key", "code": 401}})

    with pytest.raises(openai.APIStatusError):
        answer(QUESTION, five_chunks(), "gemini", ENV, http_client=client_with(handler))


@pytest.mark.parametrize("content", ["", None])
def test_answer_empty_content_raises(content):
    def handler(request):
        return httpx2.Response(200, json=completion(content))

    with pytest.raises(ValueError):
        answer(QUESTION, five_chunks(), "gemini", ENV, http_client=client_with(handler))


def test_system_forbids_markdown():
    assert "markdown" in SYSTEM.lower()
    assert NOT_FOUND in SYSTEM
    assert "[1]" in SYSTEM
    assert build_messages(QUESTION, five_chunks())[0]["content"] == SYSTEM
