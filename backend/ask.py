import logging
from contextlib import closing
from collections.abc import Callable, Iterator, Mapping

logger = logging.getLogger(__name__)

HISTORY_TURNS = 3
# Minimum cosine between the question and the best vector match; below it nothing is "relevant enough".
# Set from the corpus measurement (docs/bao-cao-chat-luong-tim-kiem.md, section 2); MIN_RELEVANCE env overrides.
MIN_RELEVANCE = 0.81


def is_low_relevance(top_similarity: float | None, min_relevance: float) -> bool:
    """Shared by the ask pipeline and eval.py. No vector hit (None) is never judged low."""
    return top_similarity is not None and top_similarity < min_relevance


def select_sources(
    query: str,
    chunks: list[dict],
    top_similarity: float | None,
    min_relevance: float,
    rerank: Callable[[str, list[dict]], list[dict]] | None,
) -> tuple[list[dict], bool]:
    """(sources to show, low_relevance). Shared by the ask pipeline and eval.py.
    When nothing is relevant enough the original chunks are kept so the UI can still show the nearest ones."""
    if not chunks:
        return [], False
    if is_low_relevance(top_similarity, min_relevance):
        return chunks, True
    if rerank is None:
        return chunks, False
    kept = rerank(query, chunks)
    return (kept, False) if kept else (chunks, True)


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
    find: Callable[[str, str], tuple[list[dict], float | None]],
    stream_answer: Callable,
    rewrite: Callable,
    env: Mapping[str, str],
    min_relevance: float,
    rerank: Callable[[str, list[dict]], list[dict]] | None = None,
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
    chunks, top = find(query, question)
    sources, low = select_sources(query, chunks, top, min_relevance, rerank)
    yield "meta", {"sources": sources, "query": rewritten, "message": None if chunks else "Chưa có tài liệu nào",
                   "low_relevance": low}
    if sources and not low and provider is not None:
        try:
            got_text = False
            with closing(stream_answer(question, sources, provider, env)) as stream:
                for text in stream:
                    got_text = got_text or bool(text)
                    yield "delta", {"text": text}
            if not got_text:
                raise ValueError("empty LLM response")
        except Exception as e:
            logger.exception("LLM call failed")
            yield "error", {"llm_error": f"Không gọi được AI ngoài ({type(e).__name__})"}
    yield "done", {}
