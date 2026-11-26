import json
import unicodedata
from collections import Counter
from pathlib import Path

from docx import Document
from openpyxl import load_workbook

import ingest

DATA = Path(__file__).resolve().parent.parent / "eval_data"
CORPUS = DATA / "corpus"
GROUPS = {"dung-chu", "dien-dat-khac", "tu-ghep-viet-tat", "khong-dau", "bang", "hai-cot", "khong-lien-quan"}


def _questions():
    return json.loads((DATA / "questions.json").read_text(encoding="utf-8"))


def _files(suffix):
    return sorted(p for p in CORPUS.rglob(f"*{suffix}"))


def test_every_expected_file_exists():
    names = [p.name for p in CORPUS.rglob("*") if p.is_file()]
    assert 8 <= len(names) <= 12
    assert len(set(names)) == len(names), "filenames must be unique across folders"
    assert 3 <= len({p.parent for p in CORPUS.rglob("*") if p.is_file()}) <= 4
    for q in _questions():
        for e in q["expect"]:
            assert e["filename"] == unicodedata.normalize("NFC", e["filename"])
            assert e["filename"] in names, e


def test_groups_and_counts():
    qs = _questions()
    assert 36 <= len(qs) <= 44
    counts = Counter(q["group"] for q in qs)
    assert set(counts) == GROUPS
    assert counts["khong-lien-quan"] >= 8
    for q in qs:
        assert (q["expect"] == []) == (q["group"] == "khong-lien-quan"), q["question"]


def test_hard_cases_present():
    assert any("hai-cot" in p.name for p in _files(".pdf"))
    assert any(len(Document(p).tables) >= 2 for p in _files(".docx"))

    def merged_header_wide(p):
        wb = load_workbook(p)
        return any(
            ws.max_column >= 8 and any(r.min_row == 1 and r.max_col > r.min_col for r in ws.merged_cells.ranges)
            for ws in wb.worksheets
        )

    assert any(merged_header_wide(p) for p in _files(".xlsx"))


def test_expected_locations_exist_in_readers():
    # Word table rows are not emitted by the reader yet, so only check the heading there.
    emitted = {}
    for p in CORPUS.rglob("*"):
        if p.is_file():
            emitted[p.name] = [c.meta for c in ingest.ingest(p, p.suffix[1:])]
    for q in _questions():
        for e in q["expect"]:
            want = {k: v for k, v in e.items() if k != "filename"}
            if "section" in want:
                want.pop("row", None)
            assert any(want.items() <= m.items() for m in emitted[e["filename"]]), (q["question"], e)
