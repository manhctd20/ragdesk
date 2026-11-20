import logging
import os
import queue
import threading
from pathlib import Path

import store
from ingest import Chunk, IngestError, ingest
from search import Bm25Holder, Index

BATCH = 32
INTERRUPTED = "Bị gián đoạn khi index, hãy tải lên lại"
logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, index: Index, embedder, bm25: Bm25Holder, files_root: Path):
        self.index = index
        self.embedder = embedder
        self.bm25 = bm25
        self.files_root = Path(files_root)
        self.queue: queue.Queue = queue.Queue()

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()

    def enqueue_index(self, doc_id: str) -> None:
        self.queue.put(("index", doc_id))

    def enqueue_delete(self, doc_id: str) -> None:
        self.queue.put(("delete", doc_id))

    def _loop(self) -> None:
        while True:
            kind, doc_id = self.queue.get()
            try:
                self.run_job(kind, doc_id)
            except Exception:
                logger.exception("job %s failed for doc %s", kind, doc_id)
            finally:
                self.queue.task_done()

    def run_job(self, kind: str, doc_id: str) -> None:
        (self._index if kind == "index" else self._delete)(doc_id)

    def rebuild_bm25(self) -> None:
        self.bm25.rebuild(*self.index.all_texts())

    def _tmp(self, doc_id: str) -> Path:
        return self.files_root / ".tmp" / doc_id

    def _dest(self, row: dict) -> Path:
        dest = (self.files_root / row["folder"] / row["filename"]).resolve()
        if not dest.is_relative_to(self.files_root.resolve()):
            raise ValueError("destination outside files root")
        return dest

    def _index(self, doc_id: str) -> None:
        row = store.get(doc_id)
        if row is None or row["status"] != "indexing":
            return
        tmp = self._tmp(doc_id)
        try:
            dest = self._dest(row)
            chunks = ingest(tmp, row["file_type"])
            store.update(doc_id, progress_total=len(chunks))
            extra = {k: row[k] for k in ("filename", "folder", "file_type")}
            for i in range(0, len(chunks), BATCH):
                batch = [Chunk(c.text, {**c.meta, **extra}) for c in chunks[i:i + BATCH]]
                vectors = self.embedder.embed_passages([c.text for c in batch])
                self.index.add(doc_id, batch, vectors, start=i)
                store.update(doc_id, progress_done=i + len(batch))
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp, dest)
            store.update(doc_id, status="ready", chunk_count=len(chunks))
            self._drop_replaced(row["replaces_id"])
        except Exception as e:
            if isinstance(e, IngestError):
                message = str(e)
            else:
                message = "Lỗi khi index: " + type(e).__name__
                logger.exception("index failed for doc %s", doc_id)
            self.index.delete_doc(doc_id)
            tmp.unlink(missing_ok=True)
            store.update(doc_id, status="error", error=message)
        self.rebuild_bm25()

    def _drop_replaced(self, old: str | None) -> None:
        try:
            if old and store.get(old):
                self.index.delete_doc(old)
                store.delete(old)
        except Exception:
            logger.exception("cleanup of replaced doc %s failed", old)

    def _delete(self, doc_id: str) -> None:
        row = store.get(doc_id)
        self.index.delete_doc(doc_id)
        if row is not None:
            if row["status"] == "ready":
                try:
                    self._dest(row).unlink(missing_ok=True)
                except ValueError:
                    logger.warning("skip file removal for doc %s: path outside files root", doc_id)
            store.delete(doc_id)
        self.rebuild_bm25()

    def recover(self) -> None:
        for row in store.list_indexing():
            self.index.delete_doc(row["id"])
            self._tmp(row["id"]).unlink(missing_ok=True)
            store.update(row["id"], status="error", error=INTERRUPTED)
        self.rebuild_bm25()
