import unicodedata

import openpyxl.xml
import pytest
from docx import Document
from fpdf import FPDF
from openpyxl import Workbook, load_workbook
from pypdf import PdfWriter

import ingest
from ingest import IngestError

SCAN = "PDF chỉ có ảnh scan, không đọc được chữ"
LOCKED = "PDF có mật khẩu"
BROKEN = "File hỏng, không mở được"
EMPTY = "File không có nội dung chữ"


def _no_none(chunks):
    for c in chunks:
        assert None not in c.meta.values()


def make_pdf(path, pages=("Page one about annual leave policy", "Page two about travel allowance")):
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)
    for text in pages:
        pdf.add_page()
        pdf.multi_cell(0, 10, text)
    pdf.output(str(path))
    return path


def make_xlsx(path, rows, title="Nghỉ"):
    wb = Workbook()
    ws = wb.active
    ws.title = title
    for r_idx, row in enumerate(rows, start=1):
        for c_idx, value in enumerate(row, start=1):
            if value is not None:
                ws.cell(row=r_idx, column=c_idx, value=value)
    wb.save(path)
    return path


def raises_msg(msg, path, file_type):
    with pytest.raises(IngestError) as e:
        ingest.ingest(path, file_type)
    assert str(e.value) == msg


# PDF

def test_pdf_two_pages_keep_page_numbers(tmp_path):
    chunks = ingest.ingest(make_pdf(tmp_path / "a.pdf"), "pdf")
    assert {c.meta["page"] for c in chunks} == {1, 2}
    page1 = " ".join(c.text for c in chunks if c.meta["page"] == 1)
    page2 = " ".join(c.text for c in chunks if c.meta["page"] == 2)
    assert "annual leave" in page1 and "travel" not in page1
    assert "travel allowance" in page2
    _no_none(chunks)


def test_read_pdf_direct(tmp_path):
    chunks = ingest.read_pdf(make_pdf(tmp_path / "a.pdf"))
    assert all(isinstance(c, ingest.Chunk) for c in chunks)
    assert {c.meta["page"] for c in chunks} == {1, 2}


def test_blank_pdf_reports_scan(tmp_path):
    w = PdfWriter()
    w.add_blank_page(200, 200)
    p = tmp_path / "scan.pdf"
    w.write(p)
    raises_msg(SCAN, p, "pdf")


def test_pdf_with_open_password_is_rejected(tmp_path):
    w = PdfWriter(clone_from=make_pdf(tmp_path / "src.pdf"))
    w.encrypt(user_password="secret", algorithm="AES-128")
    p = tmp_path / "locked.pdf"
    w.write(p)
    raises_msg(LOCKED, p, "pdf")


def test_pdf_aes_owner_password_only_is_readable(tmp_path):
    w = PdfWriter(clone_from=make_pdf(tmp_path / "src.pdf"))
    w.encrypt(user_password="", owner_password="owner", algorithm="AES-128")
    p = tmp_path / "owner.pdf"
    w.write(p)
    chunks = ingest.ingest(p, "pdf")
    assert {c.meta["page"] for c in chunks} == {1, 2}
    assert any("annual leave" in c.text for c in chunks)


def test_junk_pdf_is_broken(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-garbage \x00\x01\x02 not a pdf")
    raises_msg(BROKEN, p, "pdf")


# Word

def make_docx(path):
    d = Document()
    d.add_paragraph("Intro text before any heading.")
    d.add_heading("4.2 Nghỉ phép", level=2)
    d.add_paragraph("Người lao động được nghỉ phép năm 12 ngày.")
    d.add_heading("4.3 Công tác", level=2)
    d.add_paragraph("Công tác phí 500.000 đồng mỗi ngày.")
    t = d.add_table(rows=1, cols=2)
    t.cell(0, 0).text = "A"
    t.cell(0, 1).text = "B"
    d.add_paragraph(unicodedata.normalize("NFD", "Thử dấu tiếng Việt"))
    d.save(path)
    return path


def test_docx_sections_tables_and_nfc(tmp_path):
    chunks = ingest.ingest(make_docx(tmp_path / "a.docx"), "docx")
    _no_none(chunks)

    intro = [c for c in chunks if "Intro text" in c.text]
    assert len(intro) == 1 and "section" not in intro[0].meta

    leave = [c for c in chunks if "12 ngày" in c.text]
    assert len(leave) == 1 and leave[0].meta["section"] == "4.2 Nghỉ phép"

    travel = [c for c in chunks if "500.000" in c.text]
    assert len(travel) == 1 and travel[0].meta["section"] == "4.3 Công tác"
    assert not any("12 ngày" in c.text and "500.000" in c.text for c in chunks)

    assert any("A; B" in c.text for c in chunks)

    nfc = unicodedata.normalize("NFC", "Thử dấu tiếng Việt")
    assert any(nfc in c.text for c in chunks)
    assert all(unicodedata.is_normalized("NFC", c.text) for c in chunks)
    assert all(unicodedata.is_normalized("NFC", c.meta.get("section", "")) for c in chunks)


def make_table_docx(path, rows, heading="3. Phụ cấp"):
    d = Document()
    d.add_heading(heading, level=1)
    d.add_paragraph("Đoạn văn trước bảng.")
    t = d.add_table(rows=len(rows), cols=len(rows[0]))
    for r, row in zip(t.rows, rows):
        for cell, text in zip(r.cells, row):
            cell.text = text
    d.save(path)
    return path


def test_docx_table_with_header_becomes_column_value(tmp_path):
    p = make_table_docx(tmp_path / "t.docx", [
        ["Bậc", "Hệ số", "Chức danh"],
        ["1", "1.0", "Nhân viên"],
        ["2", "", "Chuyên viên"],
    ])
    rows = ingest._table_rows(Document(p).tables[0])
    assert rows == [
        (1, "Bậc; Hệ số; Chức danh"),
        (2, "Bậc: 1; Hệ số: 1.0; Chức danh: Nhân viên"),
        (3, "Bậc: 2; Chức danh: Chuyên viên"),
    ]


def test_docx_text_only_data_first_table_still_indexes_row_one(tmp_path):
    p = make_table_docx(tmp_path / "t.docx", [
        ["Phép năm", "12 ngày"],
        ["Nghỉ ốm", "Theo BHXH"],
        ["Nghỉ cưới", "3 ngày"],
    ])
    chunks = ingest.ingest(p, "docx")
    assert any(c.text == "Phép năm; 12 ngày" and c.meta["row"] == 1 for c in chunks)


@pytest.mark.parametrize("rows", [
    [["Bậc", "2024"], ["1", "1.0"]],  # a header cell is only a number
    [["Loại", "Loại"], ["a", "b"]],  # duplicate column names
    [["Loại", ""], ["a", "b"]],  # empty header cell
    [["Loại", "Mức"]],  # single row
    [["Loại"], ["a"]],  # single column
])
def test_docx_table_without_clear_header_keeps_old_format(tmp_path, rows):
    p = make_table_docx(tmp_path / "t.docx", rows)
    got = ingest._table_rows(Document(p).tables[0])
    assert got == [(n, "; ".join(c for c in row if c)) for n, row in enumerate(rows, start=1)]


def test_docx_table_keeps_section_and_row(tmp_path):
    p = make_table_docx(tmp_path / "t.docx", [["Bậc", "Hệ số"], ["1", "1.0"], ["2", "1.3"]])
    chunks = ingest.ingest(p, "docx")
    _no_none(chunks)
    rows = [c for c in chunks if "row" in c.meta]
    assert [(c.text, c.meta) for c in rows] == [
        ("Bậc; Hệ số", {"section": "3. Phụ cấp", "row": 1}),
        ("Bậc: 1; Hệ số: 1.0", {"section": "3. Phụ cấp", "row": 2}),
        ("Bậc: 2; Hệ số: 1.3", {"section": "3. Phụ cấp", "row": 3}),
    ]
    prose = [c for c in chunks if "Đoạn văn" in c.text]
    assert len(prose) == 1 and prose[0].meta == {"section": "3. Phụ cấp"}


def test_read_docx_direct(tmp_path):
    chunks = ingest.read_docx(make_docx(tmp_path / "a.docx"))
    assert any(c.meta.get("section") == "4.2 Nghỉ phép" for c in chunks)


def test_empty_docx_has_no_text(tmp_path):
    p = tmp_path / "empty.docx"
    Document().save(p)
    raises_msg(EMPTY, p, "docx")


def test_junk_docx_is_broken(tmp_path):
    p = tmp_path / "x.docx"
    p.write_bytes(b"this is not a zip file")
    raises_msg(BROKEN, p, "docx")


# Excel

def test_xlsx_header_and_rows(tmp_path):
    p = make_xlsx(tmp_path / "a.xlsx", [
        ["Loại nghỉ", "Báo trước"],
        ["Phép năm", "3 ngày"],
        ["Nghỉ ốm", None],
    ])
    chunks = ingest.ingest(p, "xlsx")
    assert [c.text for c in chunks] == [
        "Loại nghỉ: Phép năm; Báo trước: 3 ngày",
        "Loại nghỉ: Nghỉ ốm",
    ]
    assert [c.meta for c in chunks] == [{"sheet": "Nghỉ", "row": 2}, {"sheet": "Nghỉ", "row": 3}]


def test_xlsx_blank_first_row_uses_second_as_header(tmp_path):
    p = make_xlsx(tmp_path / "a.xlsx", [
        [None, None],
        ["Loại nghỉ", "Báo trước"],
        ["Phép năm", "3 ngày"],
    ])
    chunks = ingest.read_xlsx(p)
    assert [c.text for c in chunks] == ["Loại nghỉ: Phép năm; Báo trước: 3 ngày"]
    assert chunks[0].meta["row"] == 3


def test_xlsx_blank_data_row_keeps_real_row_numbers(tmp_path):
    p = make_xlsx(tmp_path / "a.xlsx", [
        ["Loại nghỉ"],
        ["Phép năm"],
        [None],
        ["Nghỉ ốm"],
    ])
    chunks = ingest.ingest(p, "xlsx")
    assert [(c.text, c.meta["row"]) for c in chunks] == [("Loại nghỉ: Phép năm", 2), ("Loại nghỉ: Nghỉ ốm", 4)]


def test_xlsx_empty_header_cell_uses_column_letter(tmp_path):
    p = make_xlsx(tmp_path / "a.xlsx", [
        ["Loại nghỉ", None, "Ghi chú"],
        ["Phép năm", "3 ngày", "x"],
    ])
    chunks = ingest.ingest(p, "xlsx")
    assert [c.text for c in chunks] == ["Loại nghỉ: Phép năm; B: 3 ngày; Ghi chú: x"]


def test_xlsx_whole_floats_print_as_int(tmp_path):
    p = make_xlsx(tmp_path / "a.xlsx", [
        ["Loại nghỉ", "Số ngày", "Hệ số"],
        ["Phép năm", 12.0, 1.5],
    ])
    chunks = ingest.ingest(p, "xlsx")
    assert [c.text for c in chunks] == ["Loại nghỉ: Phép năm; Số ngày: 12; Hệ số: 1.5"]


def test_xlsx_multiple_sheets_skip_empty_sheet(tmp_path):
    wb = Workbook()
    wb.active.title = "Trống"
    ws = wb.create_sheet("Công tác")
    ws.append(["Loại", "Mức"])
    ws.append(["Trong nước", "500.000"])
    p = tmp_path / "a.xlsx"
    wb.save(p)
    chunks = ingest.ingest(p, "xlsx")
    assert [(c.text, c.meta) for c in chunks] == [("Loại: Trong nước; Mức: 500.000", {"sheet": "Công tác", "row": 2})]


def make_merged_xlsx(path, rows, merges, title="Sheet"):
    p = make_xlsx(path, rows, title)
    wb = load_workbook(p)
    for m in merges:
        wb.active.merge_cells(m)
    wb.save(p)
    return p


GROUP_ROWS = [
    ["Đối tượng", None, "Ăn ở", None, "Ghi chú"],
    ["Địa bàn", "Cấp bậc", "Tiền ăn", "Lưu trú", None],
    ["Hà Nội", "Nhân viên", 300000, 200000, "Có hóa đơn"],
]
GROUP_MERGES = ["A1:B1", "C1:D1", "E1:E2"]


def test_xlsx_merged_group_header_is_off_by_default(tmp_path):
    chunks = ingest.ingest(make_merged_xlsx(tmp_path / "m.xlsx", GROUP_ROWS, GROUP_MERGES), "xlsx")
    assert [(c.text, c.meta["row"]) for c in chunks] == [
        ("Đối tượng: Địa bàn; B: Cấp bậc; Ăn ở: Tiền ăn; D: Lưu trú; Ghi chú: Ghi chú", 2),
        ("Đối tượng: Hà Nội; B: Nhân viên; Ăn ở: 300000; D: 200000; Ghi chú: Có hóa đơn", 3),
    ]


def test_xlsx_merged_header_two_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "GROUP_HEADER", True)
    p = make_merged_xlsx(tmp_path / "m.xlsx", GROUP_ROWS, GROUP_MERGES)
    chunks = ingest.ingest(p, "xlsx")
    assert [(c.text, c.meta["row"]) for c in chunks] == [
        ("Đối tượng – Địa bàn: Hà Nội; Đối tượng – Cấp bậc: Nhân viên; Ăn ở – Tiền ăn: 300000; "
         "Ăn ở – Lưu trú: 200000; Ghi chú: Có hóa đơn", 3),
    ]


def test_xlsx_horizontal_merge_below_first_row_keeps_one_row_header(tmp_path):
    p = make_merged_xlsx(tmp_path / "m.xlsx", [
        ["Loại", "Mức", "Ghi chú"],
        ["Phép năm", "12", None],
        ["Nghỉ ốm", "Theo BHXH", None],
    ], ["B3:C3"])
    chunks = ingest.ingest(p, "xlsx")
    assert [c.text for c in chunks] == [
        "Loại: Phép năm; Mức: 12",
        "Loại: Nghỉ ốm; Mức: Theo BHXH; Ghi chú: Theo BHXH",
    ]
    assert [c.meta["row"] for c in chunks] == [2, 3]


def test_xlsx_merged_cell_in_data_repeats_value(tmp_path):
    p = make_merged_xlsx(tmp_path / "m.xlsx", [
        ["Địa bàn", "Cấp bậc", "Mức"],
        ["Hà Nội", "Nhân viên", 1],
        [None, "Trưởng phòng", 2],
        [None, "Giám đốc", 3],
    ], ["A2:A4"])
    chunks = ingest.ingest(p, "xlsx")
    assert [c.text for c in chunks] == [
        "Địa bàn: Hà Nội; Cấp bậc: Nhân viên; Mức: 1",
        "Địa bàn: Hà Nội; Cấp bậc: Trưởng phòng; Mức: 2",
        "Địa bàn: Hà Nội; Cấp bậc: Giám đốc; Mức: 3",
    ]
    assert [c.meta["row"] for c in chunks] == [2, 3, 4]


def test_xlsx_empty_sheet_is_skipped(tmp_path):
    wb = Workbook()
    wb.active.title = "Trống"
    wb.active.merge_cells("A1:C2")  # merged range with no value must not invent text
    ws = wb.create_sheet("Số liệu")
    ws.append(["Loại", "Mức"])
    ws.append(["Phép năm", "12"])
    p = tmp_path / "e.xlsx"
    wb.save(p)
    chunks = ingest.ingest(p, "xlsx")
    assert {c.meta["sheet"] for c in chunks} == {"Số liệu"}


def test_xlsx_long_row_split_keeps_sheet_and_row(tmp_path):
    long = _words_text(2 * ingest.ROW_MAX_CHARS)
    p = make_xlsx(tmp_path / "l.xlsx", [
        ["Câu hỏi", "Trả lời"],
        ["Ngắn", "ok"],
        ["Dài", long],
    ])
    chunks = ingest.ingest(p, "xlsx")
    assert [c.text for c in chunks if c.meta["row"] == 2] == ["Câu hỏi: Ngắn; Trả lời: ok"]
    parts = [c for c in chunks if c.meta["row"] == 3]
    assert len(parts) >= 2
    assert all(c.meta == {"sheet": "Nghỉ", "row": 3} for c in parts)
    assert all(len(c.text) <= ingest.ROW_MAX_CHARS for c in parts)
    assert parts[0].text.startswith("Câu hỏi: Dài; Trả lời: tu0 ")
    assert "tu0" in parts[0].text and long.split()[-1] in parts[-1].text


def test_ingest_version_is_two():
    assert ingest.INGEST_VERSION == 2


def test_xlsx_without_extension_is_readable(tmp_path):
    src = make_xlsx(tmp_path / "a.xlsx", [["Loại nghỉ"], ["Phép năm"]])
    tmp_dir = tmp_path / ".tmp"
    tmp_dir.mkdir()
    p = tmp_dir / "0b8f8c1e-5d7c-4c1e-9a43-6f1d2b7c9e10"
    src.rename(p)
    chunks = ingest.ingest(p, "xlsx")
    assert [c.text for c in chunks] == ["Loại nghỉ: Phép năm"]


def test_xlsx_header_only_has_no_text(tmp_path):
    p = make_xlsx(tmp_path / "h.xlsx", [["Loại nghỉ", "Báo trước"]])
    raises_msg(EMPTY, p, "xlsx")


def test_xlsx_fully_empty_has_no_text(tmp_path):
    p = tmp_path / "e.xlsx"
    Workbook().save(p)
    raises_msg(EMPTY, p, "xlsx")


def test_junk_xlsx_is_broken(tmp_path):
    p = tmp_path / "x.xlsx"
    p.write_bytes(b"PK\x03\x04 truncated junk")
    raises_msg(BROKEN, p, "xlsx")


def test_openpyxl_uses_defusedxml():
    assert openpyxl.xml.DEFUSEDXML is True


# split

def _words_text(n_chars):
    words, i = [], 0
    while len(" ".join(words)) < n_chars:
        words.append(f"tu{i}")
        i += 1
    return " ".join(words)[:n_chars].rstrip()


def test_split_long_text_bounded_and_overlapping():
    text = _words_text(1200)
    parts = ingest.split(text)
    assert len(parts) >= 3
    assert all(len(p) <= 500 for p in parts)
    for prev, nxt in zip(parts, parts[1:]):
        assert any(prev.endswith(nxt[:n]) for n in range(20, 101)), (prev[-120:], nxt[:120])
    covered = set(" ".join(parts).split())
    assert set(text.split()) <= covered


def test_split_cuts_at_paragraph_break_first():
    p1 = ". ".join(f"Đoạn một câu {i} về nghỉ phép" for i in range(10)) + "."
    p2 = ". ".join(f"Đoạn hai câu {i} về công tác" for i in range(10)) + "."
    assert 250 < len(p1) < 400 and 250 < len(p2) < 400
    parts = ingest.split(p1 + "\n\n" + p2)
    assert len(parts) == 2
    assert parts[0] == p1
    assert parts[1].endswith(p2)


def test_split_long_vietnamese_sentences_bounded_nfc():
    para = ". ".join(f"Câu số {i} nói về nghỉ phép năm" for i in range(30))
    parts = ingest.split(para + "\n\n" + para)
    assert all(len(p) <= 500 for p in parts)
    assert all(unicodedata.is_normalized("NFC", p) for p in parts)


def test_split_without_separators_still_bounded():
    parts = ingest.split("x" * 1200)
    assert all(len(p) <= 500 for p in parts)
    assert sum(len(p) for p in parts) >= 1200


def test_split_short_text_single_chunk():
    assert ingest.split("Nghỉ phép năm 12 ngày.") == ["Nghỉ phép năm 12 ngày."]
    exact = _words_text(500)
    assert ingest.split(exact) == [exact]


def test_split_empty_and_whitespace():
    assert ingest.split("") == []
    assert ingest.split("   \n\n \t ") == []
