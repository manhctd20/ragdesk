import json
import os
import sys
import unicodedata
from collections.abc import Callable
from pathlib import Path

from search import Bm25Holder, Embedder, Index, search


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def evaluate(items: list[dict], search_fn: Callable[[str], list[dict]]) -> tuple[int, list[dict]]:
    correct, misses = 0, []
    for item in items:
        got = [h["meta"]["filename"] for h in search_fn(item["question"])[:5]]
        if _nfc(item["filename"]) in map(_nfc, got):
            correct += 1
        else:
            misses.append({**item, "got": got})
    return correct, misses


def main(argv: list[str]) -> int:
    print("Tắt server trước khi chạy eval (hai tiến trình không dùng chung chroma/).")
    items = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    index = Index(Path(os.environ.get("DATA_DIR", "./data")) / "chroma")
    if index.count() == 0:
        print("Chưa có tài liệu nào")
        return 1
    embedder, bm25 = Embedder(), Bm25Holder()
    bm25.rebuild(*index.all_texts())
    correct, misses = evaluate(items, lambda q: search(q, embedder, index, bm25))
    pct = round(100 * correct / len(items)) if items else 0
    print(f"Đúng file trong top 5: {correct}/{len(items)} ({pct}%)")
    for m in misses:
        print(f"- {m['question']}\n  cần: {m['filename']} ({m.get('where', '')})\n  nhận: {', '.join(m['got']) or '(không có)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
