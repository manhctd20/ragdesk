import json
import unicodedata

import pytest

import eval as ev
import search
from ingest import Chunk
from search import Index

DIM = 384


class FakeEmbedder:
    def embed_passages(self, texts):
        return [[1.0] + [0.0] * (DIM - 1) for _ in texts]

    def embed_query(self, text):
        return [1.0] + [0.0] * (DIM - 1)


def hits(*filenames):
    return [{"id": f"{n}:0", "text": "x", "meta": {"filename": n}, "score": 0.1, "matched": []} for n in filenames]


def test_evaluate_counts_hits_and_reports_misses():
    results = {
        "q1": hits("a.pdf", "b.docx"),
        "q2": hits("c.xlsx", "a.pdf"),
        "q3": hits("b.docx", "c.xlsx"),
    }
    items = [
        {"question": "q1", "filename": "a.pdf", "where": "trang 1"},
        {"question": "q2", "filename": "a.pdf", "where": "trang 2"},
        {"question": "q3", "filename": "a.pdf", "where": "mục 3"},
    ]
    asked = []

    def search_fn(q):
        asked.append(q)
        return results[q]

    correct, misses = ev.evaluate(items, search_fn)

    assert correct == 2
    assert misses == [{**items[2], "got": ["b.docx", "c.xlsx"]}]
    assert asked == ["q1", "q2", "q3"]


def test_evaluate_matches_nfd_against_nfc():
    nfc = "Quy định nghỉ phép.docx"
    items = [{"question": "q", "filename": unicodedata.normalize("NFD", nfc), "where": ""}]
    correct, misses = ev.evaluate(items, lambda q: hits(nfc))
    assert (correct, misses) == (1, [])


def test_evaluate_empty():
    assert ev.evaluate([], lambda q: hits("a.pdf")) == (0, [])


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    d = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(d))
    monkeypatch.setattr(search, "Embedder", FakeEmbedder)
    monkeypatch.setattr(ev, "Embedder", FakeEmbedder, raising=False)
    return d


def write_items(tmp_path, items):
    p = tmp_path / "q.json"
    p.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    return str(p)


def seed(data_dir):
    index = Index(data_dir / "chroma")
    vec = [[1.0] + [0.0] * (DIM - 1)]
    index.add("d1", [Chunk("nghỉ phép năm mười hai ngày", {"filename": "a.pdf", "folder": "F", "page": 1})], vec)
    index.add("d2", [Chunk("bảng lương tháng", {"filename": "b.xlsx", "folder": "F", "sheet": "S", "row": 2})], vec)


def test_main_prints_rate_and_misses(data_dir, tmp_path, capsys):
    seed(data_dir)
    path = write_items(tmp_path, [
        {"question": "nghỉ phép năm", "filename": "a.pdf", "where": "trang 1"},
        {"question": "câu không có", "filename": "khong-co.pdf", "where": "mục 9"},
    ])

    ev.main(["eval.py", path])

    out = capsys.readouterr().out
    assert "Đúng file trong top 5: 1/2" in out
    assert "50" in out
    assert "câu không có" in out and "khong-co.pdf" in out and "mục 9" in out
    assert "a.pdf" in out


def test_main_empty_question_list_no_division_error(data_dir, tmp_path, capsys):
    seed(data_dir)
    ev.main(["eval.py", write_items(tmp_path, [])])
    assert "Đúng file trong top 5: 0/0" in capsys.readouterr().out


def test_main_empty_index_returns_1(data_dir, tmp_path, capsys):
    path = write_items(tmp_path, [{"question": "q", "filename": "a.pdf", "where": ""}])
    assert ev.main(["eval.py", path]) == 1
    assert "Chưa có tài liệu nào" in capsys.readouterr().out
