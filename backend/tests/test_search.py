import re
import unicodedata

import pytest

from ingest import Chunk
from search import Bm25Holder, Embedder, Index, bm25_rank, retrieve, rrf, search, tokenize, top_similarity, unaccent

DIM = 384


def vec(i=0):
    v = [0.0] * DIM
    v[i % DIM] = 1.0
    return v


class FixedEmbedder:
    def __init__(self):
        self.queries = []

    def embed_passages(self, texts):
        return [vec(0) for _ in texts]

    def embed_query(self, text):
        self.queries.append(text)
        return vec(0)


class ExplodingEmbedder:
    def embed_passages(self, texts):
        raise AssertionError("embedder must not be called")

    def embed_query(self, text):
        raise AssertionError("embedder must not be called")


def add_doc(index, doc_id, texts, start=0):
    chunks = [Chunk(t, {"page": i + 1}) for i, t in enumerate(texts)]
    index.add(doc_id, chunks, [vec(0) for _ in chunks], start=start)


def rebuild(holder, index):
    holder.rebuild(*index.all_texts())


# unit

def test_rrf_scores_and_order():
    assert rrf(["a", "b"], ["a", "c"])[0] == ("a", 2 / 61)
    assert rrf(["a", "b"], ["c", "b"])[0][0] == "b"
    assert dict(rrf(["a", "b"], ["c", "b"]))["b"] == pytest.approx(1 / 62 + 1 / 62)
    assert rrf() == []
    assert rrf([], []) == []


def test_tokenize_lowercase_strip_punct_keep_diacritics():
    assert tokenize("Nghỉ phép, NĂM!", bigrams=False, unaccent_tokens=False) == ["nghỉ", "phép", "năm"]
    assert tokenize("") == []
    assert tokenize("  ...!?  ") == []


def test_tokenize_nfd_equals_nfc():
    s = "Nghỉ phép năm, Công tác phí"
    assert tokenize(unicodedata.normalize("NFD", s)) == tokenize(unicodedata.normalize("NFC", s))
    assert tokenize(unicodedata.normalize("NFD", "nghỉ"), bigrams=False, unaccent_tokens=False) == ["nghỉ"]


def test_tokenize_bigrams_and_unaccent():
    toks = tokenize("Nghỉ phép năm", bigrams=True, unaccent_tokens=True)
    for t in ("nghỉ", "phép", "năm", "nghỉ_phép", "phép_năm", "nghi", "phep", "nghi_phep"):
        assert t in toks
    assert len(toks) == len(set(toks))


def test_unaccent_d():
    assert unaccent("Đề nghị") == "De nghi"
    assert unaccent("đường") == "duong"


def test_tokenize_punctuation_only():
    assert tokenize("?", bigrams=True, unaccent_tokens=True) == []
    assert tokenize("...", bigrams=True, unaccent_tokens=True) == []


def test_tokenize_single_syllable():
    assert tokenize("nghỉ", bigrams=True, unaccent_tokens=False) == ["nghỉ"]
    assert tokenize("vpn", bigrams=True, unaccent_tokens=True) == ["vpn"]


def test_tokenize_flags_off():
    s = "Nghỉ phép, NĂM! Đề nghị"
    assert tokenize(s, bigrams=False, unaccent_tokens=False) == re.findall(
        r"\w+", unicodedata.normalize("NFC", s).lower()
    )


def test_bm25_holder_tokenize_uses_its_options():
    assert Bm25Holder(bigrams=False, unaccent_tokens=False).tokenize("Nghỉ phép") == ["nghỉ", "phép"]
    assert "nghi_phep" in Bm25Holder(bigrams=True, unaccent_tokens=True).tokenize("Nghỉ phép")


def test_bm25_holder_empty_and_rebuild():
    h = Bm25Holder()
    assert h.current == (None, [], frozenset())
    h.rebuild([], [])
    bm, ids, docs = h.current
    assert ids == [] and docs == frozenset()
    h.rebuild(["d1:0", "d1:1", "d2:0"], ["nghỉ phép", "công tác", "vpn"])
    bm, ids, docs = h.current
    assert bm is not None
    assert ids == ["d1:0", "d1:1", "d2:0"]
    assert docs == frozenset({"d1", "d2"})


def test_bm25_rank_drops_non_positive_scores():
    h = Bm25Holder()
    h.rebuild(["x", "y", "z"], ["nghỉ phép năm", "công tác phí", "kết nối vpn"])
    bm, ids, _ = h.current
    assert bm25_rank(bm, ids, ["phép"]) == ["x"]
    assert bm25_rank(bm, ids, tokenize("Mật khẩu wifi")) == []
    assert bm25_rank(bm, ids, []) == []


def test_bm25_rank_respects_k():
    h = Bm25Holder()
    ids = [f"d:{i}" for i in range(60)]
    h.rebuild(ids, ["phép"] * 25 + ["khác"] * 35)
    bm, ids, _ = h.current
    assert len(bm25_rank(bm, ids, ["phép"], k=20)) == 20
    assert len(bm25_rank(bm, ids, ["phép"])) == 20


# integration: real Chroma, fake embedder

@pytest.fixture
def index(tmp_path):
    return Index(tmp_path / "chroma")


def test_collection_has_no_embedding_function(index):
    assert index.collection._embedding_function is None


def test_add_ids_meta_get_count_delete(index):
    add_doc(index, "A", ["một", "hai"])
    add_doc(index, "A", ["ba"], start=2)
    add_doc(index, "B", ["bốn"])
    assert index.count() == 4
    got = index.get(["A:2", "A:0", "Z:9"])
    assert [g["id"] for g in got] == ["A:2", "A:0"]
    assert got[0]["text"] == "ba"
    assert got[0]["meta"]["doc_id"] == "A" and got[0]["meta"]["page"] == 1
    ids, texts = index.all_texts()
    assert dict(zip(ids, texts)) == {"A:0": "một", "A:1": "hai", "A:2": "ba", "B:0": "bốn"}
    index.delete_doc("A")
    assert index.collection.get(where={"doc_id": "A"})["ids"] == []
    assert index.count() == 1


def test_index_persists_across_instances(tmp_path):
    add_doc(Index(tmp_path / "chroma"), "A", ["một"])
    assert Index(tmp_path / "chroma").count() == 1


def test_dense_filters_by_doc_ids(index):
    add_doc(index, "A", ["một", "hai"])
    add_doc(index, "B", ["ba"])
    assert index.dense(vec(0), frozenset()) == []
    assert sorted(index.dense(vec(0), frozenset({"A"}))) == ["A:0", "A:1"]
    assert len(index.dense(vec(0), frozenset({"A", "B"}), k=2)) == 2


def test_dense_on_empty_index(index):
    assert index.dense(vec(0), frozenset({"A"})) == []


def test_search_empty_index_does_not_embed(index):
    assert search("nghỉ phép", ExplodingEmbedder(), index, Bm25Holder()) == []


def test_search_excludes_doc_still_indexing(index):
    holder = Bm25Holder()
    add_doc(index, "A", ["quy định nghỉ phép năm", "công tác phí trong nước"])
    rebuild(holder, index)
    add_doc(index, "B", ["nghỉ phép năm báo trước", "nghỉ phép năm báo trước mấy ngày"])
    q = "nghỉ phép năm báo trước mấy ngày"

    res = search(q, FixedEmbedder(), index, holder)
    ids = [r["id"] for r in res]
    assert ids and all(i.startswith("A:") for i in ids)

    rebuild(holder, index)
    ids = [r["id"] for r in search(q, FixedEmbedder(), index, holder)]
    assert any(i.startswith("B:") for i in ids)


def test_search_result_shape_score_and_matched(index):
    holder = Bm25Holder()
    add_doc(index, "A", ["Nghỉ phép năm 12 ngày", "Kết nối VPN công ty", "Quy trình mua sắm thiết bị"])
    rebuild(holder, index)
    emb = FixedEmbedder()
    res = search("Phép năm, phép nghỉ?", emb, index, holder, top=5)
    assert emb.queries == ["Phép năm, phép nghỉ?"]
    top = res[0]
    assert set(top) == {"id", "text", "meta", "score", "similarity", "matched"}
    assert top["similarity"] == pytest.approx(1.0, abs=1e-5)
    assert top["id"] == "A:0"
    assert top["text"] == "Nghỉ phép năm 12 ngày"
    assert top["meta"]["doc_id"] == "A"
    assert top["matched"] == ["phép", "năm", "nghỉ"]
    assert 0 < top["score"] <= 2 / 61
    assert all(r["score"] >= s["score"] for r, s in zip(res, res[1:]))
    assert top["score"] > res[1]["score"]
    other = next(r for r in res if r["id"] == "A:1")
    assert other["matched"] == []


def test_search_top_limits_results(index):
    holder = Bm25Holder()
    add_doc(index, "A", [f"đoạn nghỉ phép số {i}" for i in range(8)])
    rebuild(holder, index)
    assert len(search("nghỉ phép", FixedEmbedder(), index, holder)) == 5
    assert len(search("nghỉ phép", FixedEmbedder(), index, holder, top=2)) == 2


def test_search_tolerates_deleted_doc_in_stale_snapshot(index):
    holder = Bm25Holder()
    add_doc(index, "A", ["nghỉ phép năm"])
    add_doc(index, "B", ["nghỉ phép ốm"])
    rebuild(holder, index)
    index.delete_doc("B")
    ids = [r["id"] for r in search("nghỉ phép", FixedEmbedder(), index, holder)]
    assert ids == ["A:0"]


# slow: real embedder

@pytest.mark.slow
def test_real_embedder_ranks_leave_chunk_first(index):
    emb = Embedder()
    docs = {
        "leave": "Người lao động phải gửi đơn ít nhất 03 ngày làm việc trước ngày nghỉ phép năm.",
        "travel": "Định mức công tác phí cho chuyến đi trong nước là 500.000 đồng mỗi ngày.",
        "vpn": "Để kết nối VPN công ty, cài phần mềm và đăng nhập bằng tài khoản email.",
    }
    for doc_id, text in docs.items():
        vecs = emb.embed_passages([text])
        assert len(vecs) == 1 and len(vecs[0]) == DIM
        index.add(doc_id, [Chunk(text, {"page": 1})], vecs)
    assert len(emb.embed_query("x")) == DIM
    holder = Bm25Holder()
    rebuild(holder, index)

    res = search("nghỉ phép năm báo trước mấy ngày", emb, index, holder)
    assert res[0]["id"] == "leave:0"
    assert "nghỉ" in res[0]["matched"] and "phép" in res[0]["matched"]

    index.delete_doc("leave")
    assert index.collection.get(where={"doc_id": "leave"})["ids"] == []
    assert index.count() == 2


def test_highlight_limits_matched(index):
    holder = Bm25Holder()
    add_doc(index, "A", ["Nghỉ phép năm 12 ngày", "Kết nối VPN công ty"])
    rebuild(holder, index)
    res = search("nghỉ phép năm ai duyệt", FixedEmbedder(), index, holder, highlight="ngày")
    assert res[0]["id"] == "A:0"
    assert res[0]["matched"] == ["ngày"]


@pytest.mark.parametrize("question", ["nghi phep", "nghỉ phep"])
def test_search_unaccented_query_matches_and_highlights_accented(index, question):
    holder = Bm25Holder(bigrams=True, unaccent_tokens=True)
    add_doc(index, "A", ["Kết nối VPN công ty", "Nhân viên được nghỉ phép 12 ngày", "Quy trình mua sắm"])
    rebuild(holder, index)
    res = search(question, FixedEmbedder(), index, holder, top=1)
    assert res[0]["id"] == "A:1"
    assert res[0]["matched"] == ["nghỉ", "phép"]


def test_dense_scored_cosine(index):
    add_doc(index, "A", ["một"])  # vec(0)
    index.add("B", [Chunk("hai", {"page": 1})], [vec(1)])
    scored = dict(index.dense_scored(vec(0), frozenset({"A", "B"})))
    assert scored["A:0"] == pytest.approx(1.0, abs=1e-5)
    assert scored["B:0"] == pytest.approx(0.0, abs=1e-5)
    assert [i for i, _ in index.dense_scored(vec(0), frozenset({"A", "B"}))] == ["A:0", "B:0"]
    assert index.dense_scored(vec(0), frozenset()) == []


def test_top_similarity_pure():
    assert top_similarity([("a", 0.2), ("b", 0.7)]) == 0.7
    assert top_similarity([]) is None


def test_top_similarity_uses_dense_branch(index):
    # P leads after the merge (BM25 rank 1 + dense rank 2) but is orthogonal to the query;
    # Q is the best vector match yet is cut from the shown hits.
    holder = Bm25Holder()
    index.add("A", [Chunk("nghỉ phép năm", {"page": 1}), Chunk("xe công", {"page": 2}), Chunk("mua sắm", {"page": 3})],
              [vec(1), vec(0), vec(2)])
    rebuild(holder, index)
    hits, top = retrieve("nghỉ phép năm", FixedEmbedder(), index, holder, top=1)
    assert [h["id"] for h in hits] == ["A:0"]
    assert hits[0]["similarity"] == pytest.approx(0.0, abs=1e-5)
    assert top == pytest.approx(1.0, abs=1e-5)


def test_retrieve_bm25_only_hit_has_no_similarity(index):
    holder = Bm25Holder()
    index.add("A", [Chunk(f"đoạn số {i}", {"page": i}) for i in range(25)] + [Chunk("hiếm gặp zzz", {"page": 99})],
              [vec(0)] * 25 + [vec(300)])
    rebuild(holder, index)
    hits, _ = retrieve("zzz", FixedEmbedder(), index, holder, top=30)
    rare = next(h for h in hits if h["text"] == "hiếm gặp zzz")  # outside the vector top 20
    assert rare["similarity"] is None


def test_retrieve_empty_index(index):
    assert retrieve("q", ExplodingEmbedder(), index, Bm25Holder()) == ([], None)


def _tokenize_reference(text, bigrams, unaccent_tokens):
    """The first implementation (list membership, uncached unaccent): the output the fast one must match."""
    tokens = re.findall(r"\w+", unicodedata.normalize("NFC", text).lower())
    if bigrams:
        tokens += [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
    if unaccent_tokens:
        tokens += [u for u in map(unaccent, tokens) if u not in tokens]
    return tokens


@pytest.mark.parametrize("text", [
    "Nghỉ phép năm, nghi phep nam; Đề nghị đường dây",
    "vpn VPN Vpn 12 12_3 đ Đ",
    unicodedata.normalize("NFD", "Quy định nghỉ phép"),
    "?", "", "a a a a",
])
@pytest.mark.parametrize("bigrams", [True, False])
@pytest.mark.parametrize("unaccent_tokens", [True, False])
def test_tokenize_output_identical_to_first_implementation(text, bigrams, unaccent_tokens):
    assert tokenize(text, bigrams=bigrams, unaccent_tokens=unaccent_tokens) == _tokenize_reference(
        text, bigrams, unaccent_tokens)
