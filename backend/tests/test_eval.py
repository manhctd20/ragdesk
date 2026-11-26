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


def test_hit_matches_location_and_file_only():
    meta = {"filename": "a.pdf", "page": 2}
    assert ev.hit_matches({"filename": "a.pdf", "page": 2}, meta)
    assert not ev.hit_matches({"filename": "a.pdf", "page": 3}, meta)
    assert not ev.hit_matches({"filename": "b.pdf", "page": 2}, meta)
    assert ev.hit_matches({"filename": "a.pdf"}, meta)  # filename only: file match
    assert not ev.hit_matches({"filename": "b.pdf"}, meta)
    sheet = {"filename": "b.xlsx", "sheet": "S", "row": 4}
    assert ev.hit_matches({"filename": "b.xlsx", "sheet": "S", "row": 4}, sheet)
    assert not ev.hit_matches({"filename": "b.xlsx", "sheet": "S", "row": 5}, sheet)
    assert not ev.hit_matches({"filename": "b.xlsx", "sheet": "S", "row": 4}, {"filename": "b.xlsx", "sheet": "S"})
    assert ev.hit_matches({"filename": "c.docx", "section": "Điều 2"}, {"filename": "c.docx", "section": "Điều 2"})
    assert not ev.hit_matches({"filename": "c.docx", "section": "Điều 2"}, {"filename": "c.docx", "section": "Điều 3"})


def test_hit_matches_nfd_filename_and_section():
    nfc = "Quy định nghỉ phép.docx"
    nfd = unicodedata.normalize("NFD", nfc)
    assert ev.hit_matches({"filename": nfd, "section": nfd}, {"filename": nfc, "section": nfc})


def test_first_rank():
    hs = [{"meta": {"filename": "a.pdf", "page": p}} for p in (1, 2, 3)]
    assert ev.first_rank([{"filename": "a.pdf", "page": 1}], hs, False) == 1
    assert ev.first_rank([{"filename": "a.pdf", "page": 3}], hs, False) == 3
    assert ev.first_rank([{"filename": "a.pdf", "page": 9}], hs, False) is None
    assert ev.first_rank([{"filename": "b.pdf", "page": 1}], hs, True) is None
    assert ev.first_rank([{"filename": "a.pdf", "page": 9}], hs, True) == 1  # by_file ignores location
    two = [{"filename": "a.pdf", "page": 3}, {"filename": "a.pdf", "page": 2}]
    assert ev.first_rank(two, hs, False) == 2
    assert ev.first_rank([], hs, False) is None


def row(group, file_rank, loc_rank, low=False, has=True, sec=1.0):
    return {"group": group, "file_rank": file_rank, "loc_rank": loc_rank, "low_relevance": low, "has_answer": has, "seconds": sec}


def test_summarize_groups_and_totals():
    rows = [
        row("g1", 1, 1, sec=1.0),
        row("g1", 2, None, low=True, sec=2.0),
        row("g2", 1, 4, sec=3.0),
        row("khong-lien-quan", None, None, low=True, has=False),
    ]
    s = ev.summarize(rows)
    assert s["g1"] == {"file@1": 0.5, "file@5": 1.0, "vitri@5": 0.5, "MRR": 0.5, "so_cau": 2}
    assert s["g2"]["vitri@5"] == 1.0 and s["g2"]["MRR"] == 0.25
    assert s["khong-lien-quan"]["bat_duoc"] == 1.0 and s["khong-lien-quan"]["so_cau"] == 1
    t = s["tong"]
    assert t["so_cau"] == 3
    assert t["vitri@5"] == pytest.approx(2 / 3)
    assert t["MRR"] == pytest.approx((1 + 0 + 0.25) / 3)
    assert t["file@5"] == 1.0 and t["file@1"] == pytest.approx(2 / 3)
    assert t["chan_nham"] == pytest.approx(1 / 3)
    assert t["giay_trung_vi"] == 2.0 and t["giay_p95"] == 3.0


def test_legacy_format_scores_by_file():
    legacy = {"question": "q", "filename": "a.pdf", "where": "trang 1"}
    item = ev.normalize(legacy)
    assert item["expect"] == [{"filename": "a.pdf"}] and item["question"] == "q"
    new = {"question": "q", "group": "g", "expect": [{"filename": "a.pdf", "page": 1}]}
    assert ev.normalize(new) == new
    r = ev.score(item, hits("b.pdf", "a.pdf"), 0.5)
    assert r["file_rank"] == 2 and r["loc_rank"] == 2 and r["has_answer"]


def test_run_corpus_adds_worker_meta(tmp_path, monkeypatch):
    import openpyxl

    d = tmp_path / "corpus" / "tai-chinh"
    d.mkdir(parents=True)
    wb = openpyxl.Workbook()
    wb.active.title = "S"
    wb.active.append(["Khoản", "Mức"])
    wb.active.append(["Công tác phí", "500.000"])
    wb.save(d / "dinh-muc.xlsx")
    monkeypatch.setattr(ev, "Embedder", FakeEmbedder)
    qs = [
        {"question": "công tác phí", "group": "bang", "expect": [{"filename": "dinh-muc.xlsx", "sheet": "S"}]},
        {"question": "không có", "group": "khong-lien-quan", "expect": []},
    ]
    rows, secs = ev.run_corpus(qs, tmp_path / "corpus", {})
    assert secs >= 0 and len(rows) == 2
    assert rows[0]["file_rank"] == 1 and rows[0]["loc_rank"] == 1 and rows[0]["has_answer"]
    assert rows[1]["has_answer"] is False


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


def test_score_low_relevance_uses_ask_rule():
    item = ev.normalize({"question": "q", "group": "g", "expect": []})
    # best dense chunk is outside the shown hits: only the top cosine matters
    low = ev.score(item, hits("a.pdf"), 0.1, top_similarity=0.3, min_relevance=0.5)
    ok = ev.score(item, hits("a.pdf"), 0.1, top_similarity=0.6, min_relevance=0.5)
    assert low["low_relevance"] and low["top_similarity"] == 0.3 and not ok["low_relevance"]
    assert not ev.score(item, [], 0.1, top_similarity=None, min_relevance=0.5)["low_relevance"]


def test_run_corpus_records_top_similarity_and_flag(tmp_path, monkeypatch):
    import openpyxl

    d = tmp_path / "corpus" / "tc"
    d.mkdir(parents=True)
    wb = openpyxl.Workbook()
    wb.active.title = "S"
    wb.active.append(["Khoản", "Mức"])
    wb.active.append(["Công tác phí", "500.000"])
    wb.save(d / "dm.xlsx")
    monkeypatch.setattr(ev, "Embedder", FakeEmbedder)
    qs = [{"question": "công tác phí", "group": "bang", "expect": [{"filename": "dm.xlsx"}]}]
    rows, _ = ev.run_corpus(qs, tmp_path / "corpus", {}, min_relevance=0.0)
    assert rows[0]["top_similarity"] == pytest.approx(1.0, abs=1e-5) and rows[0]["low_relevance"] is False
    rows, _ = ev.run_corpus(qs, tmp_path / "corpus", {}, min_relevance=1.5)
    assert rows[0]["low_relevance"] is True


def test_print_report_lists_top_cosine_and_flag_arg(capsys):
    rows = [
        {**row("g", 1, 1), "question": "có", "top_similarity": 0.8123, "expect": [], "where": "", "got": []},
        {**row("khong-lien-quan", None, None, low=True, has=False), "question": "lạc đề", "top_similarity": 0.7001,
         "expect": [], "where": "", "got": []},
    ]
    ev.print_report(rows)
    out = capsys.readouterr().out
    assert "0.8123" in out and "0.7001" in out and "thấp nhất 0.8123" in out and "cao nhất 0.7001" in out
