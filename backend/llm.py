from collections.abc import Iterator, Mapping

from openai import OpenAI

BASE_URLS = {
    "claude": "https://api.anthropic.com/v1/",
    "openai": None,
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
}
ENV_VARS = {
    "claude": ("ANTHROPIC_API_KEY", "CLAUDE_MODEL"),
    "openai": ("OPENAI_API_KEY", "OPENAI_MODEL"),
    "gemini": ("GEMINI_API_KEY", "GEMINI_MODEL"),
}
# OpenAI reasoning models reject max_tokens and count hidden reasoning against the limit.
LIMIT_PARAM = {"claude": "max_tokens", "openai": "max_completion_tokens", "gemini": "max_tokens"}
MAX_OUTPUT = 4000
NOT_FOUND = "Không tìm thấy trong tài liệu"
SYSTEM = (
    "Chỉ trả lời dựa trên các nguồn đánh số [1], [2]… được cung cấp. "
    "Trích số nguồn trong ngoặc vuông sau mỗi ý. "
    f'Nếu nguồn không có thông tin, trả lời "{NOT_FOUND}". '
    "Trả lời bằng ngôn ngữ của câu hỏi. "
    "Viết văn bản thuần, không dùng markdown (không `**`, `#`, gạch đầu dòng, bảng); xuống dòng bằng dòng trống."
)
REWRITE_SYSTEM = (
    "Bạn viết lại câu hỏi cuối của người dùng thành một câu hỏi đầy đủ ý, tự hiểu được mà không cần các lượt trước. "
    "Chỉ trả về đúng một câu hỏi, cùng ngôn ngữ với câu hỏi cuối. "
    "Không trả lời câu hỏi, không giải thích, không thêm dấu ngoặc kép."
)


def providers(env: Mapping[str, str]) -> list[str]:
    return [p for p, keys in ENV_VARS.items() if all((env.get(k) or "").strip() for k in keys)]


def _where(meta: dict) -> str:
    if "page" in meta:
        return f"trang {meta['page']}"
    if "section" in meta:
        return f"mục {meta['section']}"
    if "sheet" in meta or "row" in meta:
        return f"sheet {meta.get('sheet')}, dòng {meta.get('row')}"
    return ""


def build_messages(question: str, chunks: list[dict]) -> list[dict]:
    sources = "\n\n".join(
        f"[{n}] {c['meta']['filename']}{' — ' + w if (w := _where(c['meta'])) else ''}\n{c['text']}"
        for n, c in enumerate(chunks[:5], 1)
    )
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"{sources}\n\nCâu hỏi: {question}"},
    ]


def _client(provider: str, env: Mapping[str, str], http_client=None) -> OpenAI:
    key, _ = ENV_VARS[provider]
    kwargs = {"base_url": BASE_URLS[provider]} if BASE_URLS[provider] else {}
    return OpenAI(api_key=env[key], http_client=http_client, **kwargs)


def stream_answer(question: str, chunks: list[dict], provider: str,
                  env: Mapping[str, str], http_client=None) -> Iterator[str]:
    stream = _client(provider, env, http_client).chat.completions.create(
        model=env[ENV_VARS[provider][1]],
        messages=build_messages(question, chunks),
        stream=True,
        **{LIMIT_PARAM[provider]: MAX_OUTPUT},
    )
    with stream:
        for chunk in stream:
            # some providers end the stream with a chunk that has no choices (e.g. usage)
            if chunk.choices and (text := chunk.choices[0].delta.content):
                yield text


def rewrite(question: str, turns: list[dict], provider: str,
            env: Mapping[str, str], http_client=None) -> str:
    history = "\n\n".join(f"Câu hỏi: {t['question']}\nTrả lời: {t['answer']}" for t in turns)
    resp = _client(provider, env, http_client).chat.completions.create(
        model=env[ENV_VARS[provider][1]],
        messages=[
            {"role": "system", "content": REWRITE_SYSTEM},
            {"role": "user", "content": f"Các lượt trước:\n{history}\n\nCâu hỏi cuối: {question}"},
        ],
        **{LIMIT_PARAM[provider]: MAX_OUTPUT},
    )
    return (resp.choices[0].message.content or "").strip()

