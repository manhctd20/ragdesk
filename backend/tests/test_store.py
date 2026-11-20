import sqlite3
import time
from datetime import datetime

import pytest

import store


@pytest.fixture(autouse=True)
def db(tmp_path):
    store.init(tmp_path / "nested" / "app.sqlite3")


def _new(id, folder="A", filename="a.pdf", file_type="pdf", **kw):
    return store.create(id, filename, folder, 1234, file_type, **kw)


def test_create_then_get_returns_all_fields():
    created = _new("d1", folder="Nhân sự", filename="Quy định nghỉ phép.pdf")
    row = store.get("d1")
    assert row == created
    assert row["id"] == "d1"
    assert row["filename"] == "Quy định nghỉ phép.pdf"
    assert row["folder"] == "Nhân sự"
    assert row["size_bytes"] == 1234
    assert row["file_type"] == "pdf"
    assert row["status"] == "indexing"
    assert row["progress_done"] == 0
    assert row["progress_total"] == 0
    assert row["chunk_count"] == 0
    assert row["error"] is None
    assert row["replaces_id"] is None
    datetime.fromisoformat(row["created_at"])
    datetime.fromisoformat(row["updated_at"])


def test_create_keeps_replaces_id():
    _new("old")
    _new("new", replaces_id="old")
    assert store.get("new")["replaces_id"] == "old"


def test_get_missing_returns_none():
    assert store.get("missing") is None


def test_init_is_idempotent(tmp_path):
    _new("d1")
    store.init(tmp_path / "nested" / "app.sqlite3")
    assert store.get("d1")["id"] == "d1"


def test_list_filters_by_folder_and_orders_newest_first():
    _new("a1", folder="A")
    _new("b1", folder="B")
    _new("a2", folder="A")
    assert [r["id"] for r in store.list(folder="A")] == ["a2", "a1"]
    assert [r["id"] for r in store.list()] == ["a2", "b1", "a1"]
    assert store.list(folder="C") == []


def test_folders_counts_every_status():
    _new("a1", folder="A")
    _new("a2", folder="A")
    _new("b1", folder="B")
    store.update("a1", status="error", error="x")
    store.update("b1", status="ready")
    assert store.folders() == [{"name": "A", "count": 2}, {"name": "B", "count": 1}]


def test_folders_empty():
    assert store.folders() == []


def test_find_ready_skips_indexing_and_error():
    _new("i", folder="A", filename="f.pdf")
    _new("e", folder="A", filename="f.pdf")
    store.update("e", status="error", error="x")
    assert store.find_ready("A", "f.pdf") is None
    _new("r", folder="A", filename="f.pdf")
    store.update("r", status="ready")
    assert store.find_ready("A", "f.pdf")["id"] == "r"
    assert store.find_ready("B", "f.pdf") is None
    assert store.find_ready("A", "g.pdf") is None


def test_update_changes_values_and_updated_at():
    before = _new("d1")
    time.sleep(1.1)
    store.update("d1", status="ready", chunk_count=3, progress_done=3, progress_total=3)
    row = store.get("d1")
    assert row["status"] == "ready"
    assert row["chunk_count"] == 3
    assert (row["progress_done"], row["progress_total"]) == (3, 3)
    assert row["created_at"] == before["created_at"]
    assert datetime.fromisoformat(row["updated_at"]) > datetime.fromisoformat(before["updated_at"])


def test_update_rejects_unknown_column():
    _new("d1")
    with pytest.raises(ValueError):
        store.update("d1", bogus=1)
    with pytest.raises(ValueError):
        store.update("d1", **{"status = 'ready' --": 1})
    assert store.get("d1")["status"] == "indexing"


def test_update_values_are_bound_not_interpolated():
    _new("d1")
    _new("d2")
    store.update("d1", error="' OR 1=1--")
    assert store.get("d1")["error"] == "' OR 1=1--"
    assert store.get("d2")["error"] is None


def test_check_constraints_reject_bad_enum_values():
    with pytest.raises(sqlite3.IntegrityError):
        _new("x", file_type="exe")
    _new("d1")
    with pytest.raises(sqlite3.IntegrityError):
        store.update("d1", status="done")
    assert store.get("d1")["status"] == "indexing"


def test_delete_removes_row():
    _new("d1")
    _new("d2")
    store.delete("d1")
    assert store.get("d1") is None
    assert store.get("d2") is not None


def test_list_indexing_returns_only_indexing_rows():
    _new("i1")
    _new("r1")
    _new("e1")
    store.update("r1", status="ready")
    store.update("e1", status="error", error="x")
    assert [r["id"] for r in store.list_indexing()] == ["i1"]
