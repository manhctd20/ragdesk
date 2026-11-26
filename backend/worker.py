import logging
import os
import queue
import shutil
import threading
import uuid
from pathlib import Path

import store
from ingest import INGEST_VERSION, Chunk, IngestError, ingest
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
        # Held while the worker claims a row or swaps a finished one in, and by callers that must see a
        # consistent "which row is current / is its re-index running" (upload, delete).
        self.lock = threading.RLock()
        self._running: str | None = None

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
        try:
            (self._index if kind == "index" else self._delete)(doc_id)
        finally:
            self._running = None

    def rebuild_bm25(self, also: str | None = None) -> None:
        # Only ready docs (plus `also`) are searchable, so orphan chunks stay hidden.
        ready = {r["id"] for r in store.list() if r["status"] == "ready"} | ({also} if also else set())
        pairs = [(i, t) for i, t in zip(*self.index.all_texts()) if i.rsplit(":", 1)[0] in ready]
        self.bm25.rebuild([i for i, _ in pairs], [t for _, t in pairs])

    def _tmp(self, doc_id: str) -> Path:
        return self.files_root / ".tmp" / doc_id

    def _dest(self, row: dict) -> Path:
        dest = (self.files_root / row["folder"] / row["filename"]).resolve()
        if not dest.is_relative_to(self.files_root.resolve()):
            raise ValueError("destination outside files root")
        return dest

    def _index(self, doc_id: str) -> None:
        with self.lock:
            row = store.get(doc_id)
            self._running = doc_id
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
            self.rebuild_bm25(also=doc_id)  # searchable before clients see "ready"
            with self.lock:
                old = store.get(row["replaces_id"]) if row["reindex"] else None
                # a re-index changes nothing the user sees, so the "when" of the document stays
                store.update(doc_id, status="ready", chunk_count=len(chunks), ingest_version=INGEST_VERSION,
                             reindex=0, **({"updated_at": old["updated_at"]} if old else {}))
                self._drop_replaced(row["replaces_id"])
        except Exception as e:
            if isinstance(e, IngestError):
                message = str(e)
            else:
                message = "Lỗi khi index: " + type(e).__name__
                logger.exception("index failed for doc %s", doc_id)
            if row["reindex"]:  # the old version stays as it was; users never see this row
                logger.warning("re-index of doc %s failed, keeping the old version: %s", row["replaces_id"], message)
                store.delete(doc_id)
            else:
                store.update(doc_id, status="error", error=message)
            tmp.unlink(missing_ok=True)
            try:
                self.index.delete_doc(doc_id)
            except Exception:
                logger.exception("cleanup of failed doc %s failed", doc_id)
        self.rebuild_bm25()

    def _drop_replaced(self, old: str | None) -> None:
        try:
            if old and store.get(old):
                self.index.delete_doc(old)
                store.delete(old)
        except Exception:
            logger.exception("cleanup of replaced doc %s failed", old)

    def _delete(self, doc_id: str) -> None:
        self.cancel_reindex(doc_id)
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
            if row["reindex"]:
                store.delete(row["id"])  # reindex_outdated() queues it again
            else:
                store.update(row["id"], status="error", error=INTERRUPTED)
        self.rebuild_bm25()

    def cancel_reindex(self, doc_id: str) -> bool:
        """Drop the queued re-index of doc_id (its job then finds no row). False if it is running now."""
        with self.lock:
            rows = [r for r in store.list_indexing() if r["reindex"] and r["replaces_id"] == doc_id]
            if any(r["id"] == self._running for r in rows):
                return False
            for r in rows:
                store.delete(r["id"])
                self._tmp(r["id"]).unlink(missing_ok=True)
        return True

    def reindex_outdated(self) -> int:
        """Queue a re-index, from the stored original, of every ready doc read by an older ingest version."""
        pending = {r["replaces_id"] for r in store.list_indexing() if r["reindex"]}
        count = 0
        for row in store.list():
            if row["status"] != "ready" or (row["ingest_version"] or 0) >= INGEST_VERSION or row["id"] in pending:
                continue
            new = str(uuid.uuid4())
            tmp = self._tmp(new)
            try:
                tmp.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self._dest(row), tmp)
            except (OSError, ValueError) as e:
                logger.warning("skip re-index of doc %s: %s", row["id"], e)
                tmp.unlink(missing_ok=True)
                continue
            store.create(new, row["filename"], row["folder"], tmp.stat().st_size, row["file_type"],
                         replaces_id=row["id"], reindex=True,
                         created_at=row["created_at"], updated_at=row["updated_at"])
            self.enqueue_index(new)
            count += 1
        return count
