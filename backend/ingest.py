import os
import unicodedata
from pathlib import Path
from typing import NamedTuple

import defusedxml  # noqa: F401  openpyxl switches to defusedxml when the package is importable
from docx import Document
from docx.table import Table
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from pypdf import PdfReader

_SCAN = "PDF chỉ có ảnh scan, không đọc được chữ"
_LOCKED = "PDF có mật khẩu"
_BROKEN = "File hỏng, không mở được"
_EMPTY = "File không có nội dung chữ"
_SEPS = ("\n\n", "\n", ". ", " ")

# Bump whenever the way files are read or cut changes, so old documents get re-indexed.
INGEST_VERSION = 3
# Chunk size in characters and PDF text extraction mode ("plain" or "layout"), chosen by measurement
# (docs/bao-cao-chat-luong-tim-kiem.md, mục 4 và 5). Overlap is 20% of the chunk size.
CHUNK_SIZE = 800
PDF_MODE = "plain"
# A row longer than this is cut. Measured against the 512-token limit of multilingual-e5: a 1200-char
# numeric row is already 512 tokens (truncated), prose is ~299 tokens; 900 keeps numeric rows under it.
ROW_MAX_CHARS = 900
# Merged-cell fill needs the full (not read_only) reader, which holds the whole sheet in memory:
# measured 8.1 MB / 150k rows -> 748 MB and 21 s, against 77 MB for read_only. Above this size the
# file is read read_only and merged values are not repeated.
# ponytail: 2 MB is ~200 MB peak, fine next to the embedding model; a big file with merged cells loses
# the repeat. Upgrade path: read <mergeCells> from the sheet XML via zipfile and keep read_only always.
XLSX_MERGE_MAX_BYTES = 2 * 1024 * 1024
# Group + column header names for Excel sheets with a merged group row. Measured: costs one
# question and gains none on the eval corpus, so it is off (docs/bao-cao-chat-luong-tim-kiem.md, mục 3).
GROUP_HEADER = False


class IngestError(Exception):
    pass


class Chunk(NamedTuple):
    text: str
    meta: dict


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _pieces(text: str, seps: tuple, size: int, step: int) -> list[str]:
    if len(text) <= size:
        return [text]
    for i, sep in enumerate(seps):
        if sep in text:
            parts = text.split(sep)
            out = []
            for j, part in enumerate(parts):
                out += _pieces(part + (sep if j < len(parts) - 1 else ""), seps[i + 1:], size, step)
            return out
    return [text[i:i + step] for i in range(0, len(text), step)]


def split(text: str, size: int = CHUNK_SIZE, overlap: int | None = None) -> list[str]:
    overlap = round(size * 0.2) if overlap is None else overlap
    text = _nfc(text).strip()
    out, cur = [], ""
    for piece in _pieces(text, _SEPS, size, size - overlap):
        if cur.strip() and len(cur) + len(piece) > size:
            body = cur.rstrip()
            ws = cur[len(body):]
            out.append(body.strip())
            tail = body[-overlap:]
            if len(body) > overlap and " " in tail:
                tail = tail.split(" ", 1)[1]
            tail = tail.lstrip()
            cur = tail + ws if len(tail) + len(ws) + len(piece) <= size else ""
        cur += piece
    if cur.strip():
        out.append(cur.strip())
    return out


def read_pdf(path, *, chunk_size: int = CHUNK_SIZE, mode: str = PDF_MODE) -> list[Chunk]:
    reader = PdfReader(path)
    if reader.is_encrypted and not reader.decrypt(""):
        raise IngestError(_LOCKED)
    kwargs = {"extraction_mode": "layout"} if mode == "layout" else {}
    pages = [(n, _nfc(p.extract_text(**kwargs) or "")) for n, p in enumerate(reader.pages, start=1)]
    if not any("".join(t.split()) for _, t in pages):
        raise IngestError(_SCAN)
    return [Chunk(part, {"page": n}) for n, t in pages for part in split(t, chunk_size)]


def _is_number(text: str) -> bool:
    return text.translate(str.maketrans("", "", " .,%-")).isdigit()


def _table_rows(table) -> list[tuple[int, str]]:
    grid = [[_nfc(c.text.strip()) for c in r.cells] for r in table.rows]
    head = grid[0] if grid else []
    is_header = (
        len(grid) >= 2 and len(head) >= 2 and all(head)
        and not any(_is_number(h) for h in head) and len(set(head)) == len(head)
    )
    if not is_header:
        return [(n, "; ".join(c for c in row if c)) for n, row in enumerate(grid, start=1)]
    # the header row is kept as a plain row too: a misdetected header then loses nothing
    return [(1, "; ".join(head))] + [
        (n, "; ".join(f"{h}: {c}" for h, c in zip(head, row) if c)) for n, row in enumerate(grid[1:], start=2)
    ]


def read_docx(path, *, chunk_size: int = CHUNK_SIZE) -> list[Chunk]:
    chunks: list[Chunk] = []
    section, lines = None, []

    def flush():
        meta = {"section": section} if section else {}
        chunks.extend(Chunk(part, dict(meta)) for part in split("\n".join(line for line in lines if line), chunk_size))

    for item in Document(path).iter_inner_content():
        if isinstance(item, Table):
            flush()
            lines = []
            for n, text in _table_rows(item):
                meta = {"section": section, "row": n} if section else {"row": n}
                chunks.extend(Chunk(part, dict(meta)) for part in split(text, chunk_size))
            continue
        text = item.text.strip()
        if item.style is not None and item.style.name.lower() in ("heading 1", "heading 2", "heading 3"):
            flush()
            section, lines = _nfc(text), []
        lines.append(text)
    flush()
    return chunks


def _cell(value) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return _nfc(str(value).strip()) if value is not None else ""


def _grid(ws, merges: bool = True) -> list[list[str]]:
    """Cell texts of a sheet; the value of a merged range is repeated on every cell it covers (merges=False: not)."""
    grid = [[_cell(v) for v in row] for row in ws.iter_rows(values_only=True)]
    for rng in ws.merged_cells.ranges if merges else ():
        value = _cell(ws.cell(rng.min_row, rng.min_col).value)
        for r in range(rng.min_row, min(rng.max_row, len(grid)) + 1):
            for c in range(rng.min_col, min(rng.max_col, len(grid[r - 1])) + 1):
                grid[r - 1][c - 1] = value
    return grid


def _header(ws, grid, first: int, merges: bool = True) -> tuple[list[str], int]:
    """Column names and the first data row. With GROUP_HEADER, a header row holding a horizontal merge
    is a group row: it joins the row below as `Group – Column`. Otherwise the first row is the header,
    as written (cells covered by a merge stay empty and get a column letter)."""
    grouped = GROUP_HEADER and merges and any(r.min_row == first and r.max_col > r.min_col for r in ws.merged_cells.ranges)
    if grouped and first < len(grid) and any(grid[first]):
        names = [g if g == c or not c else f"{g} – {c}" if g else c for g, c in zip(grid[first - 1], grid[first])]
        start = first + 2
    else:
        names = [_cell(c.value) for c in ws[first]] if merges else grid[first - 1]
        start = first + 1
    return [n or get_column_letter(i) for i, n in enumerate(names, start=1)], start


def read_xlsx(path) -> list[Chunk]:
    chunks = []
    with open(path, "rb") as f:
        merges = os.path.getsize(path) <= XLSX_MERGE_MAX_BYTES  # read_only drops merged-cell info
        wb = load_workbook(f, read_only=not merges, data_only=True)
        try:
            for ws in wb.worksheets:
                grid = _grid(ws, merges)
                first = next((i for i, cells in enumerate(grid, start=1) if any(cells)), None)
                if first is None:
                    continue
                header, start = _header(ws, grid, first, merges)
                for row_no, cells in enumerate(grid[start - 1:], start=start):
                    if not any(cells):
                        continue
                    text = "; ".join(f"{header[i] if i < len(header) else get_column_letter(i + 1)}: {c}"
                                     for i, c in enumerate(cells) if c)
                    for part in [text] if len(text) <= ROW_MAX_CHARS else split(text, ROW_MAX_CHARS, 100):
                        chunks.append(Chunk(part, {"sheet": _nfc(ws.title), "row": row_no}))
        finally:
            wb.close()
    return chunks


_READERS = {"pdf": read_pdf, "docx": read_docx, "xlsx": read_xlsx}


def ingest(path: str | Path, file_type: str, *, chunk_size: int = CHUNK_SIZE, pdf_mode: str = PDF_MODE) -> list[Chunk]:
    reader = _READERS[file_type]
    # Excel rows are cut at ROW_MAX_CHARS, not at the chunk size
    kwargs = {"pdf": {"chunk_size": chunk_size, "mode": pdf_mode}, "docx": {"chunk_size": chunk_size}}.get(file_type, {})
    try:
        chunks = reader(path, **kwargs)
    except IngestError:
        raise
    except Exception as e:
        raise IngestError(_BROKEN) from e
    if not chunks:
        raise IngestError(_EMPTY)
    return chunks
