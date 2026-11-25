import os
from collections.abc import Mapping

from openai import OpenAI

BASE_URLS = {"gemini": "https://generativelanguage.googleapis.com/v1beta/openai/"}
ENV_VARS = {"gemini": ("GEMINI_API_KEY", "GEMINI_MODEL")}
NOT_FOUND = "Không tìm thấy trong tài liệu"
SYSTEM = (
    "Chỉ trả lời dựa trên các nguồn đánh số [1]…[5] được cung cấp. "
    "Trích số nguồn trong ngoặc vuông sau mỗi ý. "
    f'Nếu nguồn không có thông tin, trả lời "{NOT_FOUND}". '
    "Trả lời bằng ngôn ngữ của câu hỏi. "
    "Viết văn bản thuần, không dùng markdown (không `**`, `#`, gạch đầu dòng, bảng); xuống dòng bằng dòng trống."
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


def answer(question: str, chunks: list[dict], provider: str,
           env: Mapping[str, str] = os.environ, http_client=None) -> str:
    key, model = ENV_VARS[provider]
    client = OpenAI(api_key=env[key], base_url=BASE_URLS[provider], http_client=http_client)
    resp = client.chat.completions.create(
        model=env[model], messages=build_messages(question, chunks), max_tokens=1024
    )
    content = resp.choices[0].message.content
    if not content:
        raise ValueError("empty LLM response")
    return content
