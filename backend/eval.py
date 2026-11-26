import json
import math
import os
import statistics
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

from ingest import Chunk, ingest
from search import Bm25Holder, Embedder, Index, search

TOP = 5
LOCATION_KEYS = ("page", "section", "sheet", "row")


def _nfc(v):
    return unicodedata.normalize("NFC", v) if isinstance(v, str) else v


def hit_matches(expect: dict, meta: dict) -> bool:
    if _nfc(expect["filename"]) != _nfc(meta.get("filename")):
        return False
    return all(_nfc(expect[k]) == _nfc(meta.get(k)) for k in LOCATION_KEYS if k in expect)


def first_rank(expect: list[dict], hits: list[dict], by_file: bool) -> int | None:
    for rank, hit in enumerate(hits, start=1):
        for e in expect:
            if hit_matches({"filename": e["filename"]} if by_file else e, hit["meta"]):
                return rank
    return None


def normalize(item: dict) -> dict:
    """Legacy {question, filename, where} becomes a file-only `expect`."""
    if "expect" in item:
        return item
    return {**item, "group": item.get("group", "cu"), "expect": [{"filename": item["filename"]}]}


def score(item: dict, hits: list[dict], seconds: float) -> dict:
    expect = item["expect"]
    return {
        "question": item["question"], "group": item["group"], "expect": expect, "where": item.get("where", ""),
        "file_rank": first_rank(expect, hits, True), "loc_rank": first_rank(expect, hits, False),
        "low_relevance": bool(hits and hits[0].get("low_relevance")), "has_answer": bool(expect),
        "seconds": seconds, "got": [h["meta"]["filename"] for h in hits],
    }


def _within(rank) -> bool:
    return rank is not None and rank <= TOP


def _rate(rows: list[dict], pred) -> float:
    return sum(1 for r in rows if pred(r)) / len(rows) if rows else 0.0


def _metrics(rows: list[dict]) -> dict:
    return {
        "file@1": _rate(rows, lambda r: r["file_rank"] == 1),
        "file@5": _rate(rows, lambda r: _within(r["file_rank"])),
        "vitri@5": _rate(rows, lambda r: _within(r["loc_rank"])),
        "MRR": sum(1 / r["loc_rank"] for r in rows if r["loc_rank"]) / len(rows) if rows else 0.0,
        "so_cau": len(rows),
    }


def summarize(rows: list[dict]) -> dict[str, dict]:
    answered = [r for r in rows if r["has_answer"]]
    secs = sorted(r["seconds"] for r in answered)
    out = {"tong": {
        **_metrics(answered),
        "chan_nham": _rate(answered, lambda r: r["low_relevance"]),
        "giay_trung_vi": statistics.median(secs) if secs else 0.0,
        "giay_p95": secs[math.ceil(0.95 * len(secs)) - 1] if secs else 0.0,
    }}
    for g in dict.fromkeys(r["group"] for r in rows):
        grp = [r for r in rows if r["group"] == g]
        if any(r["has_answer"] for r in grp):
            out[g] = _metrics([r for r in grp if r["has_answer"]])
        else:
            out[g] = {"so_cau": len(grp), "bat_duoc": _rate(grp, lambda r: r["low_relevance"])}
    return out


def run_corpus(questions: list[dict], corpus_dir: Path, options: dict) -> tuple[list[dict], float]:
    """Index every corpus file into a throwaway DATA_DIR, then search each question."""
    corpus_dir = Path(corpus_dir)
    embedder = Embedder()
    bm25 = Bm25Holder(**{k: v for k, v in options.items() if k in ("bigrams", "unaccent_tokens")})
    with tempfile.TemporaryDirectory() as tmp:
        index = Index(Path(tmp) / "chroma")
        t0 = time.perf_counter()
        ids, texts = [], []
        for n, path in enumerate(sorted(p for p in corpus_dir.glob("*/*") if p.is_file())):
            file_type = path.suffix.lower().lstrip(".")
            # same extra meta as worker._index, so search hits carry filename/folder/file_type
            extra = {"filename": _nfc(path.name), "folder": _nfc(path.parent.name), "file_type": file_type}
            chunks = [Chunk(c.text, {**c.meta, **extra}) for c in ingest(path, file_type)]
            if not chunks:
                continue
            doc_id = f"d{n}"
            index.add(doc_id, chunks, embedder.embed_passages([c.text for c in chunks]))
            ids += [f"{doc_id}:{i}" for i in range(len(chunks))]
            texts += [c.text for c in chunks]
        bm25.rebuild(ids, texts)
        ingest_seconds = time.perf_counter() - t0
        rows = []
        for item in map(normalize, questions):
            t = time.perf_counter()
            hits = search(item["question"], embedder, index, bm25, top=TOP)
            rows.append(score(item, hits, time.perf_counter() - t))
    return rows, ingest_seconds


def run_data_dir(questions: list[dict]) -> list[dict] | None:
    index = Index(Path(os.environ.get("DATA_DIR", "./data")) / "chroma")
    if index.count() == 0:
        return None
    embedder, bm25 = Embedder(), Bm25Holder()
    bm25.rebuild(*index.all_texts())
    rows = []
    for item in map(normalize, questions):
        t = time.perf_counter()
        hits = search(item["question"], embedder, index, bm25, top=TOP)
        rows.append(score(item, hits, time.perf_counter() - t))
    return rows


def print_report(rows: list[dict]) -> None:
    summary = summarize(rows)
    print(f"{'nhóm':<18}{'số câu':>7}{'file@1':>8}{'file@5':>8}{'vitri@5':>9}{'MRR':>7}{'bắt được':>10}")
    for g, m in summary.items():
        cells = [f"{m[k]:.2f}" if k in m else "-" for k in ("file@1", "file@5", "vitri@5", "MRR", "bat_duoc")]
        print(f"{g:<18}{m['so_cau']:>7}" + "".join(f"{c:>{w}}" for c, w in zip(cells, (8, 8, 9, 7, 10))))
    t = summary["tong"]
    print(f"chặn nhầm: {t['chan_nham']:.2f} | tìm: trung vị {t['giay_trung_vi']:.3f}s, p95 {t['giay_p95']:.3f}s")
    for r in rows:
        if r["has_answer"] and not _within(r["loc_rank"]):
            need = "; ".join(" ".join(str(v) for v in e.values()) for e in r["expect"])
            print(f"- [{r['group']}] {r['question']}\n  cần: {need} {r['where']}".rstrip()
                  + f"\n  nhận: {', '.join(r['got']) or '(không có)'}")


def main(argv: list[str]) -> int:
    print("Tắt server trước khi chạy eval (hai tiến trình không dùng chung chroma/).")
    root = Path(__file__).parent / "eval_data"
    if argv[1] == "--corpus":
        questions = json.loads((root / "questions.json").read_text(encoding="utf-8"))
        options = {k: False for flag, k in (("--no-bigrams", "bigrams"), ("--no-unaccent", "unaccent_tokens")) if flag in argv}
        rows, secs = run_corpus(questions, root / "corpus", options)
        print(f"Thời gian nạp: {secs:.1f}s")
    else:
        rows = run_data_dir(json.loads(Path(argv[1]).read_text(encoding="utf-8")))
        if rows is None:
            print("Chưa có tài liệu nào")
            return 1
        correct = sum(1 for r in rows if r["file_rank"] is not None)
        print(f"Đúng file trong top 5: {correct}/{len(rows)} ({round(100 * correct / len(rows)) if rows else 0}%)")
    print_report(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
