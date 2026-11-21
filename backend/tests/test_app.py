import asyncio
import os
import subprocess
import sys
import time
import unicodedata
import uuid
from contextlib import ExitStack
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from fpdf import FPDF
from openpyxl import Workbook

import store
from app import clean_name, create_app
from ingest import Chunk
from search import Index

DIM = 384
PW = "pw-dung-du-dai"
ADMIN = {"X-Admin-Password": PW}
WRONG = {"X-Admin-Password": "sai-mat-khau"}
SECRET = "g-key-SECRET"
EXTERNAL = {"ALLOW_EXTERNAL": "true", "GEMINI_API_KEY": SECRET, "GEMINI_MODEL": "gemini-test"}
FOLDER = "Nhân sự"
INTERRUPTED = "Bị gián đoạn khi index, hãy tải lên lại"
NO_DOCS = "Chưa có tài liệu nào"
MIB = 1024 * 1024
BACKEND = Path(__file__).resolve().parent.parent


class FakeEmbedder:
    def embed_passages(self, texts):
        return [[1.0] + [0.0] * (DIM - 1) for _ in texts]

    def embed_query(self, text):
        return [1.0] + [0.0] * (DIM - 1)


class FakeAnswer:
    def __init__(self, reply="Trả lời [1]", exc=None):
        self.reply = reply
        self.exc = exc
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.exc:
            raise self.exc
        return self.reply

    def provider(self, i=0):
        args, kwargs = self.calls[i]
        return kwargs["provider"] if "provider" in kwargs else args[2]


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


def pdf_bytes(text="Quy dinh nghi phep nam"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    pdf.cell(text=text)
    return bytes(pdf.output())


def wait_for(cond, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return
        time.sleep(0.05)
    raise AssertionError("timed out waiting for worker")


@pytest.fixture
def data(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def files(data):
    return data / "files"


@pytest.fixture
def make_env(data):
    def _make(**extra):
        return {"ADMIN_PASSWORD": PW, "DATA_DIR": str(data), "MAX_UPLOAD_MB": "1", **extra}
    return _make


@pytest.fixture
def open_client(tmp_path, make_env):
    stack = ExitStack()

    def _open(env=None, answer=None, frontend_dir=None):
        application = create_app(
            env if env is not None else make_env(),
            embedder=FakeEmbedder(),
            answer=answer if answer is not None else FakeAnswer(),
            frontend_dir=frontend_dir if frontend_dir is not None else tmp_path / "dist",
        )
        client = stack.enter_context(TestClient(application))
        stack.callback(application.state.worker.queue.join)
        return client

    yield _open
    stack.close()


def upload(c, data, filename, folder=FOLDER, headers=ADMIN):
    return c.post("/api/documents", files={"file": (filename, data)}, data={"folder": folder}, headers=headers)


def status(doc_id):
    row = store.get(doc_id)
    return row and row["status"]


def upload_ready(c, tmp_path, filename="Quy định.xlsx", folder=FOLDER, rows=2):
    r = upload(c, xlsx_bytes(tmp_path, rows), filename, folder)
    assert r.status_code == 202, r.text
    doc_id = r.json()["id"]
    wait_for(lambda: status(doc_id) == "ready")
    return doc_id


def regular_files(root):
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def ask(c, question="nội dung", mode="internal", provider=None):
    body = {"question": question, "mode": mode}
    if provider is not None:
        body["provider"] = provider
    return c.post("/api/ask", json=body)


def source_doc_ids(resp):
    return {s["meta"]["doc_id"] for s in resp.json()["sources"]}


@pytest.mark.parametrize("raw,expected", [
    (unicodedata.normalize("NFD", "Nhân sự"), "Nhân sự"),
    ("a/b\\c", "a b c"),
    ("a\x00b\x1fc\x7fd", "abcd"),
    ("  .x. ", "x"),
    ("Quy định.xlsx", "Quy định.xlsx"),
])
def test_clean_name(raw, expected):
    out = clean_name(raw)
    assert out == expected
    assert out == unicodedata.normalize("NFC", out)


@pytest.mark.parametrize("raw", ["..", "/", "", "   ", " . ", "\x00"])
def test_clean_name_rejects_empty(raw):
    with pytest.raises(HTTPException) as e:
        clean_name(raw)
    assert e.value.status_code == 400


@pytest.mark.parametrize("pw", [None, ""])
def test_lifespan_requires_admin_password(make_env, tmp_path, pw):
    env = make_env()
    if pw is None:
        del env["ADMIN_PASSWORD"]
    else:
        env["ADMIN_PASSWORD"] = pw
    application = create_app(env, embedder=FakeEmbedder(), answer=FakeAnswer(), frontend_dir=tmp_path / "dist")

    async def run():
        async with application.router.lifespan_context(application):
            pass

    with pytest.raises(SystemExit, match="ADMIN_PASSWORD is required"):
        asyncio.run(run())


def test_import_without_admin_password(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "ADMIN_PASSWORD"}
    env["ANONYMIZED_TELEMETRY"] = "False"
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [os.environ.get("PYTHONPATH"), str(BACKEND)]))
    r = subprocess.run([sys.executable, "-c", "import app; print(type(app.app).__name__)"],
                       cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert "FastAPI" in r.stdout


def test_config_defaults(open_client):
    c = open_client()
    r = c.get("/api/config")
    assert r.status_code == 200
    assert r.json() == {"allow_external": False, "providers": [], "max_upload_mb": 1}


def test_config_external_enabled(open_client, make_env):
    c = open_client(make_env(**{**EXTERNAL, "ALLOW_EXTERNAL": "TRUE"}))
    r = c.get("/api/config")
    assert r.json() == {"allow_external": True, "providers": ["gemini"], "max_upload_mb": 1}
    assert SECRET not in r.text


def test_config_external_without_model(open_client, make_env):
    env = make_env(**EXTERNAL)
    del env["GEMINI_MODEL"]
    r = open_client(env).get("/api/config")
    assert r.json()["providers"] == []
    assert r.json()["allow_external"] is False
    assert SECRET not in r.text


def test_config_ignores_other_vendors(open_client, make_env):
    env = make_env(ALLOW_EXTERNAL="true", ANTHROPIC_API_KEY="a-key", CLAUDE_MODEL="c",
                   OPENAI_API_KEY="o-key", OPENAI_MODEL="o")
    r = open_client(env).get("/api/config")
    assert r.json()["providers"] == []
    assert r.json()["allow_external"] is False


def test_config_default_max_upload(open_client, make_env):
    env = make_env()
    del env["MAX_UPLOAD_MB"]
    assert open_client(env).get("/api/config").json()["max_upload_mb"] == 20


def test_admin_check(open_client):
    c = open_client()
    r = c.post("/api/admin/check", headers=ADMIN)
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    t0 = time.monotonic()
    r = c.post("/api/admin/check", headers=WRONG)
    assert r.status_code == 401
    assert time.monotonic() - t0 >= 0.9

    assert c.post("/api/admin/check").status_code == 401
    assert c.post("/api/admin/check", headers={"X-Admin-Password": ""}).status_code == 401
    assert c.post("/api/admin/check", headers={"X-Admin-Password": PW + "x"}).status_code == 401
    assert PW not in r.text


@pytest.mark.parametrize("headers", [{}, WRONG])
def test_upload_requires_password(open_client, files, tmp_path, headers):
    c = open_client()
    r = upload(c, xlsx_bytes(tmp_path, 2), "a.xlsx", headers=headers)
    assert r.status_code == 401
    assert store.list() == []
    assert regular_files(files) == []


def test_upload_success(open_client, files, tmp_path):
    c = open_client()
    data = xlsx_bytes(tmp_path, 2)
    r = upload(c, data, "Quy định.xlsx")
    assert r.status_code == 202
    row = r.json()
    assert row["status"] == "indexing"
    assert row["filename"] == "Quy định.xlsx"
    assert row["folder"] == FOLDER
    assert row["file_type"] == "xlsx"
    assert row["size_bytes"] == len(data)
    assert row["replaces_id"] is None

    wait_for(lambda: status(row["id"]) == "ready")
    assert (files / FOLDER / "Quy định.xlsx").read_bytes() == data

    listing = c.get("/api/documents").json()
    assert [d["id"] for d in listing["documents"]] == [row["id"]]
    assert listing["documents"][0]["status"] == "ready"
    assert listing["folders"] == [{"name": FOLDER, "count": 1}]
    assert c.get("/api/documents", params={"folder": ""}).json()["documents"][0]["id"] == row["id"]
    assert c.get("/api/documents", params={"folder": "Khác"}).json()["documents"] == []


def test_upload_traversal_filename_stays_in_files(open_client, data, files, tmp_path):
    c = open_client()
    r = upload(c, pdf_bytes(), "../../etc/x.pdf", folder="Mau")
    assert r.status_code == 202, r.text
    assert r.json()["filename"] == "etc x.pdf"
    doc_id = r.json()["id"]
    wait_for(lambda: status(doc_id) == "ready")
    assert (files / "Mau" / "etc x.pdf").is_file()
    found = list(tmp_path.rglob("*x.pdf"))
    assert found
    for p in found:
        assert p.resolve().is_relative_to(files.resolve())


@pytest.mark.parametrize("folder", ["..", "/", " . ", "../..", "\x00"])
def test_upload_bad_folder(open_client, files, tmp_path, folder):
    c = open_client()
    assert upload(c, xlsx_bytes(tmp_path, 2), "a.xlsx", folder=folder).status_code == 400
    assert store.list() == []
    assert regular_files(files) == []


@pytest.mark.parametrize("missing", ["file", "folder"])
def test_upload_missing_field(open_client, files, tmp_path, missing):
    c = open_client()
    kw = {"files": {"file": ("a.xlsx", xlsx_bytes(tmp_path, 2))}, "data": {"folder": FOLDER}}
    kw.pop("files" if missing == "file" else "data")
    assert c.post("/api/documents", headers=ADMIN, **kw).status_code == 422
    assert store.list() == []
    assert regular_files(files) == []


def test_upload_empty_folder_rejected(open_client, files, tmp_path):
    c = open_client()
    assert upload(c, xlsx_bytes(tmp_path, 2), "a.xlsx", folder="").status_code in (400, 422)
    assert store.list() == []


def test_nfd_and_nfc_folders_merge(open_client, tmp_path):
    c = open_client()
    nfd = unicodedata.normalize("NFD", FOLDER)
    assert nfd != FOLDER
    a = upload(c, xlsx_bytes(tmp_path, 2), "a.xlsx", folder=nfd)
    b = upload(c, xlsx_bytes(tmp_path, 2), "b.xlsx", folder=FOLDER)
    assert a.status_code == b.status_code == 202
    assert a.json()["folder"] == FOLDER
    wait_for(lambda: status(a.json()["id"]) == status(b.json()["id"]) == "ready")

    listing = c.get("/api/documents").json()
    assert listing["folders"] == [{"name": FOLDER, "count": 2}]
    filtered = c.get("/api/documents", params={"folder": nfd}).json()["documents"]
    assert {d["id"] for d in filtered} == {a.json()["id"], b.json()["id"]}


def test_nfd_filename_replaces_nfc(open_client, tmp_path):
    c = open_client()
    old = upload_ready(c, tmp_path, "Quy định.xlsx")
    r = upload(c, xlsx_bytes(tmp_path, 2), unicodedata.normalize("NFD", "Quy định.xlsx"))
    assert r.status_code == 202
    assert r.json()["filename"] == "Quy định.xlsx"
    assert r.json()["replaces_id"] == old
    new = r.json()["id"]
    wait_for(lambda: status(new) == "ready" and store.get(old) is None)
    assert c.app.state.index.collection.get(where={"doc_id": old})["ids"] == []
    assert [d["id"] for d in c.get("/api/documents").json()["documents"]] == [new]


@pytest.mark.parametrize("name", ["x.exe", "x.pdf.exe", "x", "x.doc", "x.xls", "pdf", "..", "../.."])
def test_upload_bad_extension(open_client, files, name):
    c = open_client()
    assert upload(c, b"data", name).status_code == 400
    assert store.list() == []
    assert regular_files(files) == []


def test_upload_uppercase_extension(open_client):
    c = open_client()
    r = upload(c, pdf_bytes(), "X.PDF")
    assert r.status_code == 202
    assert r.json()["file_type"] == "pdf"
    wait_for(lambda: status(r.json()["id"]) != "indexing")


@pytest.mark.parametrize("size", [MIB + 1, 3 * MIB])
def test_upload_too_large(open_client, files, size):
    c = open_client()
    r = upload(c, b"\0" * size, "big.pdf")
    assert r.status_code == 413
    assert store.list() == []
    assert regular_files(files / ".tmp") == []
    assert regular_files(files) == []


def test_upload_exact_limit(open_client):
    c = open_client()
    r = upload(c, b"\0" * MIB, "vua.pdf")
    assert r.status_code == 202
    assert r.json()["size_bytes"] == MIB
    wait_for(lambda: status(r.json()["id"]) != "indexing")


def test_upload_conflict_while_indexing(open_client, tmp_path):
    c = open_client()
    busy = str(uuid.uuid4())
    store.create(busy, "a.xlsx", FOLDER, 10, "xlsx")
    r = upload(c, xlsx_bytes(tmp_path, 2), "a.xlsx")
    assert r.status_code == 409
    assert [row["id"] for row in store.list()] == [busy]

    other = upload(c, xlsx_bytes(tmp_path, 2), "a.xlsx", folder="Khác")
    assert other.status_code == 202
    wait_for(lambda: status(other.json()["id"]) == "ready")


def test_broken_replacement_keeps_old(open_client, files, tmp_path):
    c = open_client()
    old = upload_ready(c, tmp_path, "a.xlsx", rows=3)
    old_bytes = (files / FOLDER / "a.xlsx").read_bytes()

    r = upload(c, b"junk", "a.xlsx")
    assert r.status_code == 202
    new = r.json()["id"]
    assert r.json()["replaces_id"] == old
    wait_for(lambda: status(new) == "error")

    resp = ask(c, "Mục nội dung")
    assert resp.status_code == 200
    assert old in source_doc_ids(resp)
    assert new not in source_doc_ids(resp)
    assert status(old) == "ready"
    assert (files / FOLDER / "a.xlsx").read_bytes() == old_bytes


def test_delete(open_client, files, tmp_path):
    c = open_client()
    keep = upload_ready(c, tmp_path, "giu.xlsx")
    gone = upload_ready(c, tmp_path, "xoa.xlsx")
    assert gone in source_doc_ids(ask(c))

    assert c.delete(f"/api/documents/{gone}").status_code == 401
    assert c.delete(f"/api/documents/{gone}", headers=WRONG).status_code == 401
    assert status(gone) == "ready"

    assert c.delete(f"/api/documents/{uuid.uuid4()}", headers=ADMIN).status_code == 404

    busy = str(uuid.uuid4())
    store.create(busy, "dang.xlsx", FOLDER, 10, "xlsx")
    assert c.delete(f"/api/documents/{busy}", headers=ADMIN).status_code == 409
    assert status(busy) == "indexing"

    r = c.delete(f"/api/documents/{gone}", headers=ADMIN)
    assert r.status_code == 202
    assert r.json() == {"id": gone}
    wait_for(lambda: store.get(gone) is None)
    assert not (files / FOLDER / "xoa.xlsx").exists()
    ids = source_doc_ids(ask(c))
    assert gone not in ids
    assert keep in ids


def test_delete_malicious_id(open_client):
    c = open_client()
    assert c.delete("/api/documents/' OR 1=1--", headers=ADMIN).status_code == 404


def test_restart_recovers_interrupted(open_client, data, files):
    store.init(data / "app.sqlite3")
    doc_id = str(uuid.uuid4())
    store.create(doc_id, "do-dang.xlsx", FOLDER, 10, "xlsx")
    Index(data / "chroma").add(
        doc_id, [Chunk(f"dở {i}", {"sheet": "Bảng", "row": i + 2}) for i in range(3)],
        [[1.0] + [0.0] * (DIM - 1)] * 3,
    )
    tmp = files / ".tmp" / doc_id
    tmp.parent.mkdir(parents=True)
    tmp.write_bytes(b"partial")

    c = open_client()

    row = store.get(doc_id)
    assert row["status"] == "error"
    assert row["error"] == INTERRUPTED
    assert c.app.state.index.collection.get(where={"doc_id": doc_id})["ids"] == []
    assert not tmp.exists()
    assert c.get("/api/documents").json()["documents"][0]["status"] == "error"


def test_ask_no_documents_internal(open_client):
    c = open_client()
    r = ask(c)
    assert r.status_code == 200
    body = r.json()
    assert body["sources"] == []
    assert body["message"] == NO_DOCS


def test_ask_no_documents_external(open_client, make_env):
    fake = FakeAnswer()
    c = open_client(make_env(**EXTERNAL), answer=fake)
    r = ask(c, mode="external")
    assert r.status_code == 200
    assert r.json()["sources"] == []
    assert r.json()["message"] == NO_DOCS
    assert fake.calls == []


@pytest.mark.parametrize("extra,provider", [
    ({}, None),
    ({"ALLOW_EXTERNAL": "false", "GEMINI_API_KEY": SECRET, "GEMINI_MODEL": "gemini-test"}, None),
    ({"ALLOW_EXTERNAL": "yes", "GEMINI_API_KEY": SECRET, "GEMINI_MODEL": "gemini-test"}, None),
    ({"ALLOW_EXTERNAL": "true"}, None),
    ({"ALLOW_EXTERNAL": "true", "GEMINI_API_KEY": SECRET}, None),
    ({"ALLOW_EXTERNAL": "true", "GEMINI_API_KEY": SECRET, "GEMINI_MODEL": " "}, None),
    (EXTERNAL, "foo"),
    ({**EXTERNAL, "ANTHROPIC_API_KEY": "a", "CLAUDE_MODEL": "c"}, "claude"),
    ({**EXTERNAL, "OPENAI_API_KEY": "o", "OPENAI_MODEL": "m"}, "openai"),
    (EXTERNAL, "<script>alert(1)</script>"),
])
def test_ask_external_forbidden(open_client, make_env, tmp_path, extra, provider):
    fake = FakeAnswer()
    c = open_client(make_env(**extra), answer=fake)
    upload_ready(c, tmp_path)
    r = ask(c, mode="external", provider=provider)
    assert r.status_code == 403
    assert "sources" not in r.text
    assert SECRET not in r.text
    assert fake.calls == []


def test_ask_gate_checked_before_search(open_client, make_env):
    fake = FakeAnswer()
    c = open_client(make_env(ALLOW_EXTERNAL="false"), answer=fake)
    assert ask(c, mode="external").status_code == 403
    assert fake.calls == []


def test_ask_external_success(open_client, make_env, tmp_path):
    fake = FakeAnswer("Trả lời [1]")
    c = open_client(make_env(**EXTERNAL), answer=fake)
    doc_id = upload_ready(c, tmp_path)
    r = ask(c, "Mục nội dung", mode="external")
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Trả lời [1]"
    assert body["llm_error"] is None
    assert body["sources"] and doc_id in source_doc_ids(r)
    assert len(fake.calls) == 1
    assert fake.provider() == "gemini"
    args, kwargs = fake.calls[0]
    assert (kwargs.get("question") or args[0]) == "Mục nội dung"


def test_ask_external_explicit_provider(open_client, make_env, tmp_path):
    fake = FakeAnswer()
    c = open_client(make_env(**EXTERNAL), answer=fake)
    upload_ready(c, tmp_path)
    assert ask(c, mode="external", provider="gemini").status_code == 200
    assert fake.provider() == "gemini"


def test_ask_internal_does_not_call_llm(open_client, make_env, tmp_path):
    fake = FakeAnswer()
    c = open_client(make_env(**EXTERNAL), answer=fake)
    doc_id = upload_ready(c, tmp_path)
    r = ask(c, "Mục nội dung")
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] is None
    assert body["llm_error"] is None
    assert body["message"] is None
    assert 0 < len(body["sources"]) <= 5
    hit = body["sources"][0]
    assert {"id", "text", "meta", "score", "matched"} <= set(hit)
    assert doc_id in source_doc_ids(r)
    assert fake.calls == []


def test_ask_llm_error_hides_details(open_client, make_env, tmp_path):
    fake = FakeAnswer(exc=RuntimeError(SECRET))
    c = open_client(make_env(**EXTERNAL), answer=fake)
    upload_ready(c, tmp_path)
    r = ask(c, mode="external")
    assert r.status_code == 200
    body = r.json()
    assert body["sources"]
    assert body["llm_error"]
    assert body["answer"] is None
    assert SECRET not in r.text
    assert len(fake.calls) == 1


@pytest.mark.parametrize("body", [
    {"question": "", "mode": "internal"},
    {"question": "q", "mode": "x"},
    {"mode": "internal"},
    {"question": "q"},
    {"question": None, "mode": "internal"},
])
def test_ask_invalid_input(open_client, body):
    c = open_client()
    assert c.post("/api/ask", json=body).status_code == 422


def test_ask_injection_question_is_plain_text(open_client, tmp_path):
    c = open_client()
    upload_ready(c, tmp_path)
    r = ask(c, "' OR 1=1--")
    assert r.status_code == 200
    assert len(store.list()) == 1


@pytest.fixture
def dist(tmp_path):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<html>INDEX-PAGE</html>", encoding="utf-8")
    (d / "assets" / "app.js").write_text("console.log('APP-JS')", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("TOP-SECRET", encoding="utf-8")
    return d


def test_catch_all(open_client, dist):
    c = open_client(frontend_dir=dist)
    for path in ("/", "/tai-lieu", "/c/abc", "/tai-lieu?thu-muc=Nh%C3%A2n"):
        r = c.get(path)
        assert r.status_code == 200, path
        assert "INDEX-PAGE" in r.text
    r = c.get("/assets/app.js")
    assert r.status_code == 200
    assert "APP-JS" in r.text
    for path in ("/api/khong-co", "/api", "/api/"):
        r = c.get(path)
        assert r.status_code == 404, path
        assert "INDEX-PAGE" not in r.text
    for path in ("/..%2fsecret.txt", "/assets/..%2f..%2fsecret.txt"):
        r = c.get(path)
        assert "TOP-SECRET" not in r.text, path
        assert r.status_code == 404 or "INDEX-PAGE" in r.text, path


def test_catch_all_without_dist(open_client, tmp_path):
    c = open_client(frontend_dir=tmp_path / "khong-co-dist")
    assert c.get("/tai-lieu").status_code == 404
    assert c.get("/api/config").status_code == 200
