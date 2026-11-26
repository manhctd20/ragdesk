import threading
import time
import uuid

import pytest
from docx import Document
from openpyxl import Workbook
from pypdf import PdfWriter

import store
from search import Bm25Holder, Index
from ingest import INGEST_VERSION
from worker import BATCH, Worker

DIM = 384
FOLDER = "Nhân sự"
NAME = "Quy định.xlsx"
INTERRUPTED = "Bị gián đoạn khi index, hãy tải lên lại"


class FakeEmbedder:
    def __init__(self, fail_on=None, exc=None, on_call=None):
        self.calls = []
        self.fail_on = fail_on
        self.exc = exc
        self.on_call = on_call
        self.lock = threading.Lock()

    def embed_passages(self, texts):
        with self.lock:
            self.calls.append(list(texts))
            n = len(self.calls)
        if self.on_call:
            self.on_call(texts)
        if self.fail_on == n:
            raise self.exc
        return [[1.0] + [0.0] * (DIM - 1) for _ in texts]

    def embed_query(self, text):
        return [1.0] + [0.0] * (DIM - 1)


def xlsx_bytes(tmp_path, n_rows, prefix="Mục"):
    wb = Workbook()
    ws = wb.active
    ws.title = "Bảng"
    ws.append(["Tên", "Nội dung"])
    for i in range(n_rows):
        ws.append([f"{prefix} {i}", f"{prefix} nội dung {i}"])
    p = tmp_path / f"src-{uuid.uuid4()}.xlsx"
    wb.save(p)
    return p.read_bytes()


def docx_empty_bytes(tmp_path):
    p = tmp_path / f"src-{uuid.uuid4()}.docx"
    Document().save(p)
    return p.read_bytes()


def blank_pdf_bytes(tmp_path):
    p = tmp_path / f"src-{uuid.uuid4()}.pdf"
    w = PdfWriter()
    w.add_blank_page(200, 200)
    w.write(p)
    return p.read_bytes()


class Env:
    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        store.init(tmp_path / "data" / "app.sqlite3")
        self.files = tmp_path / "data" / "files"
        self.files.mkdir(parents=True)
        self.index = Index(tmp_path / "data" / "chroma")
        self.bm25 = Bm25Holder()
        self.embedder = FakeEmbedder()
        self.worker = Worker(self.index, self.embedder, self.bm25, self.files)

    def tmp_file(self, doc_id):
        return self.files / ".tmp" / doc_id

    def dest(self, folder=FOLDER, filename=NAME):
        return self.files / folder / filename

    def upload(self, data, folder=FOLDER, filename=NAME, file_type="xlsx", replaces_id=None):
        doc_id = str(uuid.uuid4())
        t = self.tmp_file(doc_id)
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_bytes(data)
        store.create(doc_id, filename, folder, len(data), file_type, replaces_id=replaces_id)
        return doc_id

    def index_now(self, data, **kw):
        doc_id = self.upload(data, **kw)
        self.worker.run_job("index", doc_id)
        return doc_id

    def chunk_ids(self, doc_id):
        return set(self.index.collection.get(where={"doc_id": doc_id})["ids"])

    def bm25_ids(self):
        return set(self.bm25.current[1])

    def bm25_docs(self):
        return self.bm25.current[2]


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def wait_for(cond, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return
        time.sleep(0.05)
    raise AssertionError("timed out waiting for worker")


def test_batch_size():
    assert BATCH == 32


def test_index_success(env, tmp_path):
    data = xlsx_bytes(tmp_path, 3)
    doc_id = env.index_now(data)

    got = env.index.collection.get(where={"doc_id": doc_id}, include=["metadatas", "documents"])
    assert len(got["ids"]) == 3
    for meta in got["metadatas"]:
        assert meta["doc_id"] == doc_id
        assert meta["filename"] == NAME
        assert meta["folder"] == FOLDER
        assert meta["file_type"] == "xlsx"
        assert meta["sheet"] == "Bảng"
        assert meta["row"] in (2, 3, 4)
        assert None not in meta.values()
    assert sorted(m["row"] for m in got["metadatas"]) == [2, 3, 4]

    assert env.dest().read_bytes() == data
    assert not env.tmp_file(doc_id).exists()

    row = store.get(doc_id)
    assert row["status"] == "ready"
    assert row["error"] is None
    assert row["chunk_count"] == 3
    assert (row["progress_done"], row["progress_total"]) == (3, 3)

    assert set(got["ids"]) <= env.bm25_ids()
    assert doc_id in env.bm25_docs()
    assert not any(t.startswith("passage: ") for c in env.embedder.calls for t in c)


def test_embed_error_in_second_batch_cleans_up(env, tmp_path):
    env.embedder.fail_on = 2
    env.embedder.exc = RuntimeError("/secret/path")
    doc_id = env.index_now(xlsx_bytes(tmp_path, 40))

    assert len(env.embedder.calls) == 2
    assert len(env.embedder.calls[0]) == BATCH
    assert env.chunk_ids(doc_id) == set()
    assert not env.tmp_file(doc_id).exists()
    assert not env.dest().exists()
    row = store.get(doc_id)
    assert row["status"] == "error"
    assert row["error"] == "Lỗi khi index: RuntimeError"
    assert doc_id not in env.bm25_docs()


def test_scan_pdf_reports_error(env, tmp_path):
    doc_id = env.index_now(blank_pdf_bytes(tmp_path), filename="scan.pdf", file_type="pdf")
    row = store.get(doc_id)
    assert row["status"] == "error"
    assert row["error"] == "PDF chỉ có ảnh scan, không đọc được chữ"
    assert not env.tmp_file(doc_id).exists()
    assert not env.dest(filename="scan.pdf").exists()


def test_empty_docx_reports_no_text(env, tmp_path):
    doc_id = env.index_now(docx_empty_bytes(tmp_path), filename="rong.docx", file_type="docx")
    row = store.get(doc_id)
    assert row["status"] == "error"
    assert row["error"] == "File không có nội dung chữ"
    assert not env.tmp_file(doc_id).exists()
    assert env.embedder.calls == []
    assert env.index.count() == 0


def test_replace_with_broken_file_keeps_old(env, tmp_path):
    old_data = xlsx_bytes(tmp_path, 3)
    old = env.index_now(old_data)
    old_chunks = env.chunk_ids(old)

    new = env.index_now(b"PK\x03\x04 junk", replaces_id=old)

    assert store.get(old)["status"] == "ready"
    assert env.chunk_ids(old) == old_chunks and len(old_chunks) == 3
    assert env.dest().read_bytes() == old_data
    assert old_chunks <= env.bm25_ids()
    row = store.get(new)
    assert row["status"] == "error"
    assert row["error"] == "File hỏng, không mở được"
    assert env.chunk_ids(new) == set()
    assert not env.tmp_file(new).exists()


def test_replace_success_swaps_old_for_new(env, tmp_path):
    old = env.index_now(xlsx_bytes(tmp_path, 3, prefix="Cũ"))
    new_data = xlsx_bytes(tmp_path, 2, prefix="Mới")
    new = env.index_now(new_data, replaces_id=old)

    assert env.chunk_ids(old) == set()
    new_chunks = env.chunk_ids(new)
    assert len(new_chunks) == 2
    assert set(env.index.collection.get()["ids"]) == new_chunks
    assert store.get(old) is None
    assert store.get(new)["status"] == "ready"
    assert env.dest().read_bytes() == new_data
    assert env.bm25_ids() == new_chunks
    assert env.bm25_docs() == frozenset({new})
    assert not env.tmp_file(new).exists()


def test_replace_when_old_already_deleted(env, tmp_path):
    old = env.index_now(xlsx_bytes(tmp_path, 3))
    env.worker.run_job("delete", old)
    new_data = xlsx_bytes(tmp_path, 2, prefix="Mới")
    new = env.index_now(new_data, replaces_id=old)
    assert store.get(new)["status"] == "ready"
    assert env.dest().read_bytes() == new_data
    assert env.bm25_docs() == frozenset({new})


def test_delete_ready_doc(env, tmp_path):
    keep = env.index_now(xlsx_bytes(tmp_path, 2, prefix="Giữ"), filename="giu.xlsx")
    gone = env.index_now(xlsx_bytes(tmp_path, 3))
    gone_chunks = env.chunk_ids(gone)
    assert gone_chunks <= env.bm25_ids()

    env.worker.run_job("delete", gone)

    assert env.chunk_ids(gone) == set()
    assert not env.dest().exists()
    assert store.get(gone) is None
    assert env.bm25_ids() == env.chunk_ids(keep)
    assert env.bm25_docs() == frozenset({keep})
    assert env.dest(filename="giu.xlsx").exists()


def test_delete_error_row_keeps_ready_twin(env, tmp_path):
    ready_data = xlsx_bytes(tmp_path, 3)
    ready = env.index_now(ready_data)
    ready_chunks = env.chunk_ids(ready)
    failed = env.index_now(b"junk", replaces_id=ready)
    assert store.get(failed)["status"] == "error"

    env.worker.run_job("delete", failed)

    assert store.get(failed) is None
    assert env.dest().read_bytes() == ready_data
    assert env.chunk_ids(ready) == ready_chunks
    assert store.get(ready)["status"] == "ready"
    assert ready_chunks <= env.bm25_ids()


def test_recover_cleans_interrupted_rows(env, tmp_path):
    from ingest import Chunk

    ready = env.index_now(xlsx_bytes(tmp_path, 3))
    ready_chunks = env.chunk_ids(ready)

    partial = env.upload(xlsx_bytes(tmp_path, 40), filename="do-dang.xlsx")
    env.index.add(partial, [Chunk(f"dở {i}", {"sheet": "Bảng", "row": i + 2}) for i in range(5)],
                  [[1.0] + [0.0] * (DIM - 1)] * 5)
    assert len(env.chunk_ids(partial)) == 5

    bm25 = Bm25Holder()
    restarted = Worker(Index(tmp_path / "data" / "chroma"), FakeEmbedder(), bm25, env.files)
    restarted.recover()

    assert env.chunk_ids(partial) == set()
    assert not env.tmp_file(partial).exists()
    row = store.get(partial)
    assert row["status"] == "error"
    assert row["error"] == INTERRUPTED
    assert store.list_indexing() == []

    assert store.get(ready)["status"] == "ready"
    assert env.chunk_ids(ready) == ready_chunks
    assert env.dest().exists()
    assert set(bm25.current[1]) == ready_chunks
    assert bm25.current[2] == frozenset({ready})


def test_queue_runs_jobs_one_at_a_time(env, tmp_path):
    seen = []
    ids = {}

    def on_call(texts):
        owner = "A" if "AAA" in texts[0] else "B"
        a_status = store.get(ids["A"])["status"] if "A" in ids else None
        seen.append((owner, a_status))

    env.embedder.on_call = on_call
    ids["A"] = env.upload(xlsx_bytes(tmp_path, 40, prefix="AAA"), filename="a.xlsx")
    ids["B"] = env.upload(xlsx_bytes(tmp_path, 40, prefix="BBB"), filename="b.xlsx")

    env.worker.start()
    env.worker.enqueue_index(ids["A"])
    env.worker.enqueue_index(ids["B"])
    wait_for(lambda: all(store.get(i)["status"] != "indexing" for i in ids.values()))

    owners = [o for o, _ in seen]
    assert owners == ["A", "A", "B", "B"]
    first_b = owners.index("B")
    assert seen[first_b][1] == "ready"
    for i in ids.values():
        row = store.get(i)
        assert row["status"] == "ready"
        assert row["chunk_count"] == 40
        assert (row["progress_done"], row["progress_total"]) == (40, 40)


def test_worker_thread_survives_failed_jobs(env, tmp_path, monkeypatch, caplog):
    real_rebuild = env.worker.rebuild_bm25
    raised = []

    def rebuild_once_broken(**kw):
        if not raised:
            raised.append(True)
            raise RuntimeError("bm25 boom")
        real_rebuild(**kw)

    monkeypatch.setattr(env.worker, "rebuild_bm25", rebuild_once_broken)
    env.worker.start()
    env.worker.enqueue_delete("does-not-exist")
    env.worker.enqueue_index("does-not-exist")
    missing_tmp = env.upload(b"", filename="mat.xlsx")
    env.tmp_file(missing_tmp).unlink()
    env.worker.enqueue_index(missing_tmp)
    good = env.upload(xlsx_bytes(tmp_path, 2), filename="tot.xlsx")
    env.worker.enqueue_index(good)

    wait_for(lambda: store.get(good)["status"] == "ready")
    wait_for(lambda: env.worker.queue.unfinished_tasks == 0)
    assert raised == [True]
    assert any("job delete failed for doc does-not-exist" in r.getMessage() for r in caplog.records)
    assert store.get(missing_tmp)["status"] == "error"
    assert good in env.bm25_docs()


@pytest.mark.parametrize("folder,filename", [("..", "evil.xlsx"), ("A", "../../evil.xlsx")])
def test_path_traversal_from_db_is_rejected(env, tmp_path, folder, filename):
    doc_id = env.index_now(xlsx_bytes(tmp_path, 2), folder=folder, filename=filename)
    row = store.get(doc_id)
    assert row["status"] == "error"
    assert list(tmp_path.rglob("evil.xlsx")) == []
    assert not env.tmp_file(doc_id).exists()
    assert env.chunk_ids(doc_id) == set()
    assert doc_id not in env.bm25_docs()


def test_replace_fails_when_move_fails_keeps_old(env, tmp_path):
    from ingest import Chunk

    old = str(uuid.uuid4())
    store.create(old, NAME, FOLDER, 10, "xlsx")
    store.update(old, status="ready", chunk_count=2, progress_done=2, progress_total=2)
    env.index.add(old, [Chunk("cũ một", {"sheet": "Bảng", "row": 2}), Chunk("cũ hai", {"sheet": "Bảng", "row": 3})],
                  [[1.0] + [0.0] * (DIM - 1)] * 2)
    env.worker.rebuild_bm25()
    old_chunks = env.chunk_ids(old)
    assert old_chunks <= env.bm25_ids()

    blocker = env.dest()
    blocker.mkdir(parents=True)
    (blocker / "keep.txt").write_bytes(b"keep")

    new = env.index_now(xlsx_bytes(tmp_path, 2, prefix="Mới"), replaces_id=old)

    assert store.get(old)["status"] == "ready"
    assert env.chunk_ids(old) == old_chunks
    assert old_chunks <= env.bm25_ids()
    row = store.get(new)
    assert row["status"] == "error"
    assert row["error"].startswith("Lỗi khi index: ")
    assert env.chunk_ids(new) == set()
    assert new not in env.bm25_docs()
    assert not env.tmp_file(new).exists()
    assert blocker.is_dir() and (blocker / "keep.txt").read_bytes() == b"keep"


def test_replace_cleanup_failure_keeps_new_ready(env, tmp_path, monkeypatch):
    old = env.index_now(xlsx_bytes(tmp_path, 3, prefix="Cũ"))
    real_delete = env.index.delete_doc

    def flaky_delete(doc_id):
        if doc_id == old:
            raise RuntimeError("chroma down")
        real_delete(doc_id)

    monkeypatch.setattr(env.index, "delete_doc", flaky_delete)
    new_data = xlsx_bytes(tmp_path, 2, prefix="Mới")
    new = env.index_now(new_data, replaces_id=old)

    row = store.get(new)
    assert row["status"] == "ready"
    assert row["chunk_count"] == 2
    assert len(env.chunk_ids(new)) == 2
    assert env.dest().read_bytes() == new_data
    assert env.chunk_ids(new) <= env.bm25_ids()
    assert new in env.bm25_docs()
    assert not env.tmp_file(new).exists()


def test_delete_ready_row_with_traversal_path_keeps_outside_file(env, tmp_path):
    doc_id = str(uuid.uuid4())
    store.create(doc_id, "evil.xlsx", "..", 10, "xlsx")
    store.update(doc_id, status="ready", chunk_count=0)
    outside = env.files.parent / "evil.xlsx"
    outside.write_bytes(b"keep")

    env.worker.run_job("delete", doc_id)

    assert store.get(doc_id) is None
    assert outside.read_bytes() == b"keep"


def test_failed_cleanup_marks_error_and_hides_orphan_chunks(env, tmp_path, monkeypatch):
    def broken_delete(doc_id):
        raise RuntimeError("chroma down")

    monkeypatch.setattr(env.index, "delete_doc", broken_delete)
    env.embedder.fail_on = 2
    env.embedder.exc = RuntimeError("chroma down")
    bad = env.index_now(xlsx_bytes(tmp_path, 40))

    row = store.get(bad)
    assert row["status"] == "error"
    assert row["error"] == "Lỗi khi index: RuntimeError"
    assert not env.tmp_file(bad).exists()
    assert len(env.chunk_ids(bad)) == BATCH

    good = env.index_now(xlsx_bytes(tmp_path, 2), filename="Khác.xlsx")
    assert good in env.bm25_docs()
    assert bad not in env.bm25_docs()
    assert not env.chunk_ids(bad) & env.bm25_ids()


def test_doc_is_searchable_before_it_is_marked_ready(env, tmp_path, monkeypatch):
    seen = []
    real_update = store.update

    def spy_update(doc_id, **fields):
        if fields.get("status") == "ready":
            seen.append(doc_id in env.bm25_docs())
        real_update(doc_id, **fields)

    monkeypatch.setattr(store, "update", spy_update)
    env.index_now(xlsx_bytes(tmp_path, 2))
    assert seen == [True]


def make_outdated(env, data, version=None, **kw):
    doc_id = env.index_now(data, **kw)
    store.update(doc_id, ingest_version=version)
    return doc_id


def queued(worker):
    jobs = []
    while not worker.queue.empty():
        jobs.append(worker.queue.get_nowait())
        worker.queue.task_done()
    return jobs


def test_index_writes_ingest_version(env, tmp_path):
    doc_id = env.index_now(xlsx_bytes(tmp_path, 2))
    assert store.get(doc_id)["ingest_version"] == INGEST_VERSION


def test_reindex_outdated_swaps_in_new_chunks(env, tmp_path):
    data = xlsx_bytes(tmp_path, 3, prefix="Cũ")
    old = make_outdated(env, data)
    old_chunks = env.chunk_ids(old)

    assert env.worker.reindex_outdated() == 1
    assert env.worker.reindex_outdated() == 0  # already pending

    [(kind, new)] = queued(env.worker)
    assert kind == "index"
    row = store.get(new)
    assert (row["status"], row["reindex"], row["replaces_id"]) == ("indexing", 1, old)
    assert env.tmp_file(new).read_bytes() == data
    # old stays searchable while the re-index waits
    assert store.get(old)["status"] == "ready"
    assert old_chunks <= env.bm25_ids()

    env.worker.run_job("index", new)

    assert store.get(old) is None
    assert env.chunk_ids(old) == set()
    row = store.get(new)
    assert (row["status"], row["reindex"], row["ingest_version"]) == ("ready", 0, INGEST_VERSION)
    assert len(env.chunk_ids(new)) == 3
    assert env.bm25_docs() == frozenset({new})
    assert env.dest().read_bytes() == data
    assert not env.tmp_file(new).exists()
    assert [r["id"] for r in store.list()] == [new]


def test_reindex_failure_keeps_old_and_hides_error(env, tmp_path, caplog):
    data = xlsx_bytes(tmp_path, 40, prefix="Cũ")
    old = make_outdated(env, data, version=INGEST_VERSION - 1)
    old_chunks = env.chunk_ids(old)
    env.worker.reindex_outdated()
    [(_, new)] = queued(env.worker)
    env.embedder.fail_on = len(env.embedder.calls) + 2
    env.embedder.exc = RuntimeError("boom")

    env.worker.run_job("index", new)

    assert store.get(new) is None
    assert env.chunk_ids(new) == set()
    assert not env.tmp_file(new).exists()
    assert [(r["id"], r["status"]) for r in store.list()] == [(old, "ready")]
    assert store.get(old)["ingest_version"] == INGEST_VERSION - 1
    assert env.chunk_ids(old) == old_chunks
    assert env.bm25_docs() == frozenset({old})
    assert env.dest().read_bytes() == data
    assert any(r.levelname == "WARNING" and old in r.getMessage() for r in caplog.records)


def test_recover_drops_interrupted_reindex_rows(env, tmp_path):
    from ingest import Chunk

    old = make_outdated(env, xlsx_bytes(tmp_path, 3))
    env.worker.reindex_outdated()
    [(_, new)] = queued(env.worker)
    env.index.add(new, [Chunk("dở", {"sheet": "Bảng", "row": 2})], [[1.0] + [0.0] * (DIM - 1)])

    restarted = Worker(Index(tmp_path / "data" / "chroma"), FakeEmbedder(), Bm25Holder(), env.files)
    restarted.recover()

    assert store.get(new) is None
    assert env.chunk_ids(new) == set()
    assert not env.tmp_file(new).exists()
    assert store.get(old)["status"] == "ready"
    assert restarted.reindex_outdated() == 1


def test_current_version_docs_not_reindexed(env, tmp_path):
    current = env.index_now(xlsx_bytes(tmp_path, 2))
    errored = env.index_now(b"junk", filename="hong.xlsx")
    store.update(errored, ingest_version=None)
    assert store.get(errored)["status"] == "error"

    assert env.worker.reindex_outdated() == 0
    assert queued(env.worker) == []
    assert {r["id"] for r in store.list()} == {current, errored}


def test_reindex_skips_missing_original_file(env, tmp_path, caplog):
    gone = make_outdated(env, xlsx_bytes(tmp_path, 2), filename="mat.xlsx")
    env.dest(filename="mat.xlsx").unlink()
    kept = make_outdated(env, xlsx_bytes(tmp_path, 2), filename="con.xlsx")

    assert env.worker.reindex_outdated() == 1
    [(_, new)] = queued(env.worker)
    assert store.get(new)["replaces_id"] == kept
    assert store.get(gone)["status"] == "ready"
    assert list((env.files / ".tmp").iterdir()) == [env.tmp_file(new)]
    assert any(r.levelname == "WARNING" and gone in r.getMessage() for r in caplog.records)


def test_delete_during_pending_reindex_does_not_resurrect(env, tmp_path):
    old = make_outdated(env, xlsx_bytes(tmp_path, 3))
    env.worker.reindex_outdated()
    # what the delete endpoint does: cancel the pending re-index, then queue the delete behind it
    assert env.worker.cancel_reindex(old)
    env.worker.enqueue_delete(old)

    env.worker.start()
    env.worker.queue.join()

    assert store.list() == []
    assert store.list_indexing() == []
    assert env.index.count() == 0
    assert not env.dest().exists()
    assert regular(env.files) == []


def test_delete_job_drops_pending_reindex_row(env, tmp_path):
    old = make_outdated(env, xlsx_bytes(tmp_path, 3))
    env.worker.reindex_outdated()
    [(_, new)] = queued(env.worker)

    env.worker.run_job("delete", old)
    env.worker.run_job("index", new)

    assert store.get(old) is None and store.get(new) is None
    assert env.index.count() == 0
    assert regular(env.files) == []


def test_cancel_reindex_refuses_while_it_runs(env, tmp_path):
    old = make_outdated(env, xlsx_bytes(tmp_path, 3))
    env.worker.reindex_outdated()
    [(_, new)] = queued(env.worker)
    answers = []
    env.embedder.on_call = lambda texts: answers.append(env.worker.cancel_reindex(old))

    env.worker.run_job("index", new)

    assert answers == [False]
    assert store.get(new)["status"] == "ready"
    assert env.worker.cancel_reindex(new)  # nothing pending afterwards


def regular(root):
    return [p for p in root.rglob("*") if p.is_file()]
