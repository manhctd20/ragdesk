from fastembed.rerank.cross_encoder import TextCrossEncoder

from search import unaccent

DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3-int8"
# Set from the corpus measurement (docs/bao-cao-chat-luong-tim-kiem.md, section 7); RERANK_MIN env overrides.
# Each model has its own score scale: re-measure with `eval.py --corpus` after changing RERANK_MODEL.
RERANK_MIN = -5.0


class Reranker:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model = TextCrossEncoder(model_name)

    def score(self, query: str, texts: list[str]) -> list[float]:
        return [float(s) for s in self._model.rerank(query, texts)]


def has_diacritics(text: str) -> bool:
    return unaccent(text) != text


def rerank(query: str, hits: list[dict], scorer, min_score: float) -> list[dict]:
    """Hits scored by the cross-encoder, best first, those below min_score dropped.
    Unaccented queries pass through untouched: the model scores their right passages very low."""
    if not hits or not has_diacritics(query):
        return hits
    scored = [{**h, "rerank_score": s} for h, s in zip(hits, scorer.score(query, [h["text"] for h in hits]))]
    return sorted((h for h in scored if h["rerank_score"] >= min_score), key=lambda h: -h["rerank_score"])
