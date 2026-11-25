import logging
from contextlib import closing
from collections.abc import Callable, Iterator, Mapping

logger = logging.getLogger(__name__)

HISTORY_TURNS = 3


def external_turns(history: list[dict], provider: str) -> list[dict]:
    return [
        {"question": t["question"], "answer": t["answer"]}
        for t in history
        if t.get("mode") == "external" and t.get("answer") and t.get("provider") == provider
    ]


def internal_query(question: str, history: list[dict]) -> str:
    return f"{history[-1]['question']} {question}" if history else question


def ask_events(
    question: str,
    mode: str,
    provider: str | None,
    history: list[dict],
    *,
    find: Callable[[str, str], list[dict]],
    stream_answer: Callable,
    rewrite: Callable,
    env: Mapping[str, str],
) -> Iterator[tuple[str, dict]]:
    history = history[-HISTORY_TURNS:]
    query = question
    rewritten = None
    if provider is None:
        query = internal_query(question, history)
    elif turns := external_turns(history, provider):
        try:
            rewritten = rewrite(question, turns, provider, env).strip() or None
        except Exception:
            logger.exception("Question rewrite failed")
        if rewritten:
            question = query = rewritten
    chunks = find(query, question)
    yield "meta", {"sources": chunks, "query": rewritten, "message": None if chunks else "Chưa có tài liệu nào"}
    if chunks and provider is not None:
        try:
            with closing(stream_answer(question, chunks, provider, env)) as stream:
                for text in stream:
                    yield "delta", {"text": text}
        except Exception as e:
            logger.exception("LLM call failed")
            yield "error", {"llm_error": f"Không gọi được AI ngoài ({type(e).__name__})"}
    yield "done", {}
