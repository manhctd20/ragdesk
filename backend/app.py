import asyncio
import hmac
import json
import logging
import os
import threading
import unicodedata
import uuid
from collections.abc import Iterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

import llm
import store
from ask import MIN_RELEVANCE, ask_events
from search import Bm25Holder, Embedder, Index, retrieve
from worker import Worker

DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
MIB = 1024 * 1024
FILE_TYPES = {".pdf": "pdf", ".docx": "docx", ".xlsx": "xlsx"}
logger = logging.getLogger(__name__)
_upload_lock = threading.Lock()


def clean_name(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = "".join(ch for ch in s if unicodedata.category(ch)[0] != "C")
    s = s.replace("/", " ").replace("\\", " ").replace("..", " ").strip(" .")
    if not s:
        raise HTTPException(400, "Tên không hợp lệ")
    return s


class HistoryTurn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    mode: Literal["internal", "external"]
    provider: str | None = None
    answer: str | None = Field(None, max_length=8000)


class AskBody(BaseModel):
    question: str = Field(min_length=1)
    mode: Literal["internal", "external"]
    provider: str | None = None
    history: list[HistoryTurn] = Field(default_factory=list, max_length=3)


def sse_stream(events: Iterator[tuple[str, dict]]) -> Iterator[str]:
    try:
        for name, data in events:
            yield f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    finally:
        events.close()  # client disconnect: propagate to the upstream LLM stream


def create_app(env: Mapping[str, str] | None = None, *, embedder=None, stream_answer=llm.stream_answer,
               rewrite=llm.rewrite, frontend_dir: Path = DIST) -> FastAPI:
    env = os.environ if env is None else env
    password = env.get("ADMIN_PASSWORD") or ""
    max_mb = int(env.get("MAX_UPLOAD_MB") or 20)
    allow_external = (env.get("ALLOW_EXTERNAL") or "").lower() == "true"
    data_dir = Path(env.get("DATA_DIR") or "./data")
    min_relevance = float(env.get("MIN_RELEVANCE") or MIN_RELEVANCE)
    configured = llm.providers(env)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not password:
            raise SystemExit("ADMIN_PASSWORD is required")
        store.init(data_dir / "app.sqlite3")
        index = Index(data_dir / "chroma")
        bm25 = Bm25Holder()
        files_root = data_dir / "files"
        worker = Worker(index, embedder or Embedder(), bm25, files_root)
        worker.recover()
        worker.start()
        app.state.worker, app.state.index, app.state.bm25, app.state.files_root = worker, index, bm25, files_root
        app.state.embedder = worker.embedder
        yield

    app = FastAPI(lifespan=lifespan)

    async def require_admin(x_admin_password: str | None = Header(None)) -> None:
        if not hmac.compare_digest((x_admin_password or "").encode(), password.encode()):
            await asyncio.sleep(1)
            raise HTTPException(401, "Sai mật khẩu")

    @app.get("/api/config")
    def config():
        return {"allow_external": allow_external and bool(configured), "providers": configured,
                "max_upload_mb": max_mb}

    @app.post("/api/admin/check", dependencies=[Depends(require_admin)])
    def admin_check():
        return {"ok": True}

    @app.get("/api/documents")
    def documents(folder: str = ""):
        folder = unicodedata.normalize("NFC", folder)
        return {"documents": store.list(folder or None), "folders": store.folders()}

    @app.post("/api/documents", status_code=202, dependencies=[Depends(require_admin)],
              max_body_size=(max_mb + 1) * MIB)
    def upload(file: UploadFile = File(...), folder: str = Form(...)):
        folder = clean_name(folder)
        filename = clean_name(file.filename or "")
        file_type = FILE_TYPES.get(Path(filename).suffix.lower())
        if file_type is None:
            raise HTTPException(400, "Chỉ nhận file .pdf, .docx, .xlsx")
        files_root = app.state.files_root
        if not (files_root / folder / filename).resolve().is_relative_to(files_root.resolve()):
            raise HTTPException(400, "Tên không hợp lệ")
        with _upload_lock:
            if any(r["filename"] == filename and r["status"] == "indexing" for r in store.list(folder)):
                raise HTTPException(409, "File cùng tên đang được index")
            old = store.find_ready(folder, filename)
            doc_id = str(uuid.uuid4())
            tmp = files_root / ".tmp" / doc_id
            tmp.parent.mkdir(parents=True, exist_ok=True)
            size = 0
            try:
                with tmp.open("wb") as out:
                    while chunk := file.file.read(MIB):
                        size += len(chunk)
                        if size > max_mb * MIB:
                            raise HTTPException(413, f"File vượt quá {max_mb} MB")
                        out.write(chunk)
                row = store.create(doc_id, filename, folder, size, file_type, old["id"] if old else None)
            except BaseException:
                tmp.unlink(missing_ok=True)
                raise
        app.state.worker.enqueue_index(doc_id)
        return row

    @app.delete("/api/documents/{doc_id}", status_code=202, dependencies=[Depends(require_admin)])
    def delete_document(doc_id: str):
        row = store.get(doc_id)
        if row is None:
            raise HTTPException(404, "Không có tài liệu")
        if row["status"] == "indexing":
            raise HTTPException(409, "File đang index, chờ xong rồi xoá")
        app.state.worker.enqueue_delete(doc_id)
        return {"id": doc_id}

    def start_ask(body: AskBody) -> tuple[str | None, Iterator[tuple[str, dict]]]:
        # ask_events treats provider=None as internal, so internal requests never carry a provider
        provider = None
        if body.mode == "external":
            provider = body.provider or (configured[0] if configured else None)
            if not allow_external or provider not in configured:
                raise HTTPException(403, "Chưa cho phép gửi ra ngoài")
        s = app.state
        events = ask_events(
            body.question, body.mode, provider, [t.model_dump() for t in body.history],
            find=lambda query, highlight: retrieve(query, s.embedder, s.index, s.bm25, highlight=highlight),
            stream_answer=stream_answer, rewrite=rewrite, env=env, min_relevance=min_relevance,
        )
        return provider, events

    @app.post("/api/ask")
    def ask(body: AskBody):
        provider, events = start_ask(body)
        result = {"answer": None, "sources": [], "llm_error": None, "message": None, "query": None,
                  "low_relevance": False, "provider": provider}
        parts = []
        for name, data in events:
            if name == "delta":
                parts.append(data["text"])
            elif name != "done":
                result.update(data)
        result["answer"] = "".join(parts) or None
        return result

    @app.post("/api/ask/stream")
    def ask_stream(body: AskBody):
        _, events = start_ask(body)
        return StreamingResponse(sse_stream(events), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/{path:path}")
    def frontend(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404)
        root = frontend_dir.resolve()
        target = (root / path).resolve()
        if target.is_file() and target.is_relative_to(root):
            return FileResponse(target)
        if (root / "index.html").is_file():
            return FileResponse(root / "index.html")
        raise HTTPException(404)

    return app


app = create_app()
