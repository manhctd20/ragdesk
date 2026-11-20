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


def split(text: str, size: int = 500, overlap: int = 100) -> list[str]:
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


def read_pdf(path) -> list[Chunk]:
    reader = PdfReader(path)
    if reader.is_encrypted and not reader.decrypt(""):
        raise IngestError(_LOCKED)
    pages = [(n, _nfc(p.extract_text() or "")) for n, p in enumerate(reader.pages, start=1)]
    if not any("".join(t.split()) for _, t in pages):
        raise IngestError(_SCAN)
    return [Chunk(part, {"page": n}) for n, t in pages for part in split(t)]


def read_docx(path) -> list[Chunk]:
    blocks: list[tuple[str | None, list[str]]] = [(None, [])]
    for item in Document(path).iter_inner_content():
        if isinstance(item, Table):
            blocks[-1][1].extend("; ".join(c.text.strip() for c in r.cells if c.text.strip()) for r in item.rows)
            continue
        text = item.text.strip()
        if item.style is not None and item.style.name.lower() in ("heading 1", "heading 2", "heading 3"):
            blocks.append((_nfc(text), []))
        blocks[-1][1].append(text)
    return [
        Chunk(part, {"section": section} if section else {})
        for section, lines in blocks
        for part in split("\n".join(line for line in lines if line))
    ]


def _cell(value) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return _nfc(str(value).strip()) if value is not None else ""


def read_xlsx(path) -> list[Chunk]:
    chunks = []
    with open(path, "rb") as f:
        wb = load_workbook(f, read_only=True, data_only=True)
        try:
            for ws in wb.worksheets:
                header = None
                for row_no, row in enumerate(ws.iter_rows(values_only=True), start=1):
                    cells = [_cell(v) for v in row]
                    if not any(cells):
                        continue
                    if header is None:
                        header = [c or get_column_letter(i) for i, c in enumerate(cells, start=1)]
                        continue
                    text = "; ".join(f"{header[i] if i < len(header) else get_column_letter(i + 1)}: {c}"
                                     for i, c in enumerate(cells) if c)
                    chunks.append(Chunk(text, {"sheet": _nfc(ws.title), "row": row_no}))
        finally:
            wb.close()
    return chunks


_READERS = {"pdf": read_pdf, "docx": read_docx, "xlsx": read_xlsx}


def ingest(path: str | Path, file_type: str) -> list[Chunk]:
    reader = _READERS[file_type]
    try:
        chunks = reader(path)
    except IngestError:
        raise
    except Exception as e:
        raise IngestError(_BROKEN) from e
    if not chunks:
        raise IngestError(_EMPTY)
    return chunks
