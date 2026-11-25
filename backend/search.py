import re
import unicodedata
from pathlib import Path

import chromadb
from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType
from rank_bm25 import BM25Okapi

from ingest import Chunk

_MODEL = "intfloat/multilingual-e5-small"

TextEmbedding.add_custom_model(
    model=_MODEL,
    pooling=PoolingType.MEAN,
    normalization=True,
    sources=ModelSource(hf=_MODEL),
    dim=384,
    model_file="onnx/model.onnx",
)


class Embedder:
    def __init__(self):
        self._model = TextEmbedding(_MODEL)

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed([f"passage: {t}" for t in texts])]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.embed([f"query: {text}"]))).tolist()


class Index:
    def __init__(self, path: str | Path):
        self.collection = chromadb.PersistentClient(path=str(path)).get_or_create_collection(
            "chunks", embedding_function=None
        )

    def add(self, doc_id: str, chunks: list[Chunk], vectors, start: int = 0) -> None:
        self.collection.add(
            ids=[f"{doc_id}:{start + i}" for i in range(len(chunks))],
            documents=[c.text for c in chunks],
            embeddings=vectors,
            metadatas=[{**c.meta, "doc_id": doc_id} for c in chunks],
        )

    def delete_doc(self, doc_id: str) -> None:
        self.collection.delete(where={"doc_id": doc_id})

    def all_texts(self) -> tuple[list[str], list[str]]:
        got = self.collection.get(include=["documents"])
        return got["ids"], got["documents"]

    def dense(self, qvec, doc_ids: frozenset[str], k: int = 20) -> list[str]:
        if not doc_ids or self.count() == 0:
            return []
        res = self.collection.query(
            query_embeddings=[qvec], n_results=k, where={"doc_id": {"$in": sorted(doc_ids)}}
        )
        return res["ids"][0]

    def get(self, ids: list[str]) -> list[dict]:
        if not ids:
            return []
        got = self.collection.get(ids=ids, include=["documents", "metadatas"])
        by_id = {i: {"id": i, "text": t, "meta": m} for i, t, m in zip(got["ids"], got["documents"], got["metadatas"])}
        return [by_id[i] for i in ids if i in by_id]

    def count(self) -> int:
        return self.collection.count()


def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", unicodedata.normalize("NFC", text).lower())


class Bm25Holder:
    def __init__(self):
        self.current: tuple[BM25Okapi | None, list[str], frozenset[str]] = (None, [], frozenset())

    def rebuild(self, ids: list[str], texts: list[str]) -> None:
        bm = BM25Okapi([tokenize(t) for t in texts]) if texts else None
        self.current = (bm, ids, frozenset(i.rsplit(":", 1)[0] for i in ids))


def bm25_rank(bm, ids: list[str], tokens: list[str], k: int = 20) -> list[str]:
    if bm is None or not tokens:
        return []
    scores = bm.get_scores(tokens)
    top = sorted(range(len(ids)), key=lambda i: -scores[i])[:k]
    return [ids[i] for i in top if scores[i] > 0]


def rrf(*rankings: list[str], k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda x: -x[1])


def search(question: str, embedder, index: Index, bm25: Bm25Holder, top: int = 5, highlight: str | None = None) -> list[dict]:
    bm, ids, doc_ids = bm25.current
    if not doc_ids or index.count() == 0:
        return []
    tokens = tokenize(question)
    ranked = rrf(index.dense(embedder.embed_query(question), doc_ids, 20), bm25_rank(bm, ids, tokens, 20))[:top]
    scores = dict(ranked)
    shown = tokenize(highlight or question)
    results = []
    for hit in index.get([cid for cid, _ in ranked]):
        present = set(tokenize(hit["text"]))
        matched = list(dict.fromkeys(t for t in shown if t in present))
        results.append({**hit, "score": scores[hit["id"]], "matched": matched})
    return results
