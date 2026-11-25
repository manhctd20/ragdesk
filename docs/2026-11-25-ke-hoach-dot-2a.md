# Kế hoạch triển khai đợt 2A: nâng cấp chế độ AI ngoài

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Mục tiêu:** Thêm Claude và OpenAI, hỏi nối tiếp (cách 2) và stream câu trả lời, đúng `docs/2026-11-25-thiet-ke-dot-2a.md`.

**Kiến trúc:**
- `llm.py` có hai hàm `rewrite` và `stream_answer`, dùng chung một client chuẩn OpenAI cho ba nhà.
- Module mới `ask.py` chứa toàn bộ luồng hỏi (lọc lịch sử, câu truy vấn, viết lại, tìm, trả lời) dưới dạng **một generator sinh sự kiện**. `/api/ask` gom sự kiện thành JSON, `/api/ask/stream` đẩy chúng ra dạng SSE.
- Frontend đọc SSE bằng `fetch` + `ReadableStream` qua hàm `askStream`. `Chat` dựng câu trả lời dần từ các sự kiện.

**Stack:** Python 3.12, FastAPI 0.165, `openai` SDK 3.57.0 (đã pin); React 19, TypeScript, Vitest.

**Spec:** `docs/2026-11-25-thiet-ke-dot-2a.md` (gọi tắt **TK2A**). Đọc cùng kế hoạch này.

**Lệnh test:**
- backend: `cd backend && ANONYMIZED_TELEMETRY=False .venv/bin/pytest`
- frontend: `cd frontend && npm test && npm run lint && npm run build`

## Ràng buộc chung

- Thứ tự nhà, cố định: `claude, openai, gemini`. Biến môi trường và `base_url` đúng bảng TK2A mục 4. OpenAI không đặt `base_url`.
- Không gửi `temperature` / `top_p`. Giới hạn đầu ra `MAX_OUTPUT = 4000`: Claude và Gemini qua `max_tokens`, OpenAI qua `max_completion_tokens`.
- `history` tối đa **3** lượt. `question` mỗi lượt ≤ **2000** ký tự, `answer` ≤ **8000** ký tự. Vượt thì trả 422.
- Chế độ AI ngoài chỉ dùng các lượt `mode == "external"` có `answer` và có `provider` **trùng** nhà hiện tại. Lọc ở máy chủ.
- Chế độ nội bộ không gọi AI nào. Câu truy vấn là `"<câu hỏi lượt ngay trước> <câu hiện tại>"`; `matched` chỉ tính theo câu hiện tại.
- Lần gọi trả lời chỉ gửi câu (đã viết lại nếu có) và 5 đoạn, **không** gửi lịch sử.
- Thứ tự sự kiện SSE: `meta` → `delta`* → `error`? → `done` (luôn có `done`). Lỗi 403/422 trả mã HTTP thường, trước khi stream.
- Chuỗi hiển thị cố định:
  - toast/gợi ý: `Câu hỏi, các đoạn liên quan và các lượt AI ngoài trước đó sẽ gửi tới AI ngoài`
  - dòng câu viết lại: `Hiểu là: <câu>`
  - nhãn chế độ: `AI ngoài (<Tên nhà>): câu trả lời tổng hợp từ các đoạn`
  - tên nhà: `Claude`, `OpenAI`, `Gemini`
- Key localStorage nhớ nhà đã chọn: `tcnb:provider`.
- Chữ từ AI chỉ render bằng text node, không `dangerouslySetInnerHTML` (TK1, bảo mật 1).
- Thư viện bên thứ ba: đọc tài liệu đúng bản đang pin trước khi dùng (CLAUDE.md của người dùng).

## Rủi ro cần soi khi review

1. **Một sự kiện SSE bị cắt giữa hai lần đọc stream**, kể cả cắt giữa một chữ tiếng Việt nhiều byte. Phải ghép lại đúng, không mất hay hỏng chữ. Test ở Task 4.
2. **Model gửi chunk có `delta.content` rỗng hoặc `None`** (chunk đầu chỉ có role, chunk cuối chỉ có `finish_reason`, hoặc chunk không có `choices`). Phải bỏ qua, không làm vỡ stream. Test ở Task 1.
3. **Bước viết lại trả về chuỗi rỗng hoặc chỉ toàn khoảng trắng.** Phải dùng câu gốc, như khi bước này lỗi. Test ở Task 2.
4. **Lịch sử cũ trong localStorage** không có `provider` và `result.query`. Vẫn phải hiển thị được; khi gửi đi thì `provider` là `null`, và máy chủ bỏ lượt đó ra khỏi lịch sử AI ngoài. Test ở Task 4 và Task 5.
5. **Nhà đã nhớ trong `tcnb:provider` không còn bật** (quản trị gỡ key). Ô chọn phải quay về nhà đầu tiên, request không được gửi nhà cũ. Test ở Task 5.

---

### Task 1: `llm.py` gọi ba nhà, stream và viết lại câu hỏi

**Files:**
- Modify: `backend/llm.py`
- Test: `backend/tests/test_llm.py`

**Interfaces:**
- Produces:
  - `BASE_URLS: dict[str, str | None]`
  - `ENV_VARS: dict[str, tuple[str, str]]` theo thứ tự claude, openai, gemini
  - `LIMIT_PARAM: dict[str, str]`
  - `MAX_OUTPUT = 4000`
  - `providers(env) -> list[str]`: giữ nguyên chữ ký
  - `build_messages(question, chunks) -> list[dict]`: giữ nguyên
  - `stream_answer(question: str, chunks: list[dict], provider: str, env: Mapping[str, str], http_client=None) -> Iterator[str]`: sinh từng mẩu chữ, bỏ mẩu rỗng hoặc `None`
  - `rewrite(question: str, turns: list[dict], provider: str, env: Mapping[str, str], http_client=None) -> str`: `turns` là danh sách `{"question", "answer"}`; trả về câu đã viết lại, hoặc chuỗi rỗng nếu model trả rỗng
  - Bỏ hàm `answer`.

- [ ] **Bước 1: Đọc tài liệu chính thức về lớp tương thích OpenAI** của Anthropic và Gemini. Xác nhận cả hai hỗ trợ `stream=True` và tham số `max_tokens`. Không hỗ trợ thì dừng và báo lại, vì TK2A mục 4 có phương án dự phòng cho trường hợp này.
- [ ] **Bước 2: Viết test (đỏ)** trong `test_llm.py`, dùng lại `client_with(handler)` với `httpx2.MockTransport`. Trả SSE giả bằng body `data: {...}\n\n` … `data: [DONE]\n\n`, header `content-type: text/event-stream`.
  - `test_constants`:
    - `list(ENV_VARS) == ["claude", "openai", "gemini"]`
    - `BASE_URLS["claude"] == "https://api.anthropic.com/v1/"`
    - `BASE_URLS["openai"] is None`
    - `LIMIT_PARAM == {"claude": "max_tokens", "openai": "max_completion_tokens", "gemini": "max_tokens"}`
  - `test_providers`: đủ key của cả ba nhà → `["claude", "openai", "gemini"]`; chỉ có `OPENAI_*` → `["openai"]`; thiếu tên model → không bật.
  - `test_stream_answer_each_provider[claude|openai|gemini]`:
    - URL request khớp `base_url` của nhà đó (OpenAI: `https://api.openai.com/v1/chat/completions`);
    - body có `stream: true`, `model` lấy từ env, và đúng tham số giới hạn bằng `4000`;
    - body **không** có `temperature` hay `top_p`.
  - `test_stream_answer_yields_text_and_skips_empty`: các chunk `role-only`, `"Cần "`, `""`, `None`, `"duyệt [1]."`, và chunk chỉ có `finish_reason` → kết quả là `["Cần ", "duyệt [1]."]`.
  - `test_stream_answer_status_error_raises`: HTTP 401 → ném `openai.APIStatusError` ngay lần lặp đầu.
  - `test_rewrite_sends_turns_and_returns_text`:
    - request không stream;
    - nội dung gửi đi chứa câu hỏi và câu trả lời của từng lượt trong `turns`, và câu hiện tại;
    - kết quả đã `strip()`.
  - Đổi `test_answer_*` cũ sang `stream_answer`.
- [ ] **Bước 3: Chạy cho thấy đỏ:** `cd backend && .venv/bin/pytest tests/test_llm.py -q`.
- [ ] **Bước 4: Hiện thực.**
  - Hàm `_client(provider, env, http_client)` truyền `base_url` chỉ khi khác `None`.
  - `stream_answer` dùng `chat.completions.create(..., stream=True, **{LIMIT_PARAM[p]: MAX_OUTPUT})` và đọc `chunk.choices[0].delta.content`.
  - `rewrite` dùng system prompt riêng. Prompt do builder viết, theo TK2A mục 9: trả đúng một câu hỏi đủ nghĩa, cùng ngôn ngữ, không trả lời.
- [ ] **Bước 5: Chạy cho thấy xanh**, cùng lệnh ở bước 3.
- [ ] **Bước 6: Commit:** `feat(llm): Claude and OpenAI providers, streaming answer and question rewrite`.

### Task 2: `ask.py`, luồng hỏi dưới dạng sự kiện

**Files:**
- Create: `backend/ask.py`
- Modify: `backend/search.py` (thêm tham số `highlight`)
- Test: `backend/tests/test_ask.py`, `backend/tests/test_search.py`

**Interfaces:**
- Consumes (Task 1): `stream_answer`, `rewrite`.
- Produces:
  - `search(question, embedder, index, bm25, top=5, highlight: str | None = None)`: `matched` tính theo `tokenize(highlight or question)`.
  - `HISTORY_TURNS = 3`
  - `external_turns(history: list[dict], provider: str) -> list[dict]`: trả `[{"question", "answer"}]` của các lượt `mode == "external"`, `answer` khác rỗng và `provider == provider`.
  - `internal_query(question: str, history: list[dict]) -> str`
  - `ask_events(question: str, mode: str, provider: str | None, history: list[dict], *, find: Callable[[str, str], list[dict]], stream_answer: Callable, rewrite: Callable, env: Mapping[str, str]) -> Iterator[tuple[str, dict]]`:
    - `find(query, highlight)` trả các đoạn;
    - các sự kiện là `("meta", {"sources", "query", "message"})`, `("delta", {"text"})`, `("error", {"llm_error"})`, `("done", {})`;
    - `provider is None` nghĩa là chế độ nội bộ.

- [ ] **Bước 1: Viết test (đỏ)** trong `test_ask.py`. `find`, `stream_answer` và `rewrite` là hàm giả, có ghi lại các lần gọi.
  - `test_internal_never_calls_llm`: `mode="internal"` → không gọi `rewrite` hay `stream_answer`; sự kiện là `meta`, `done`.
  - `test_internal_query_prepends_previous_question`: lịch sử có 2 lượt (một nội bộ, một AI ngoài) → `find` nhận `query == "<câu lượt cuối> <câu hiện tại>"` và `highlight == "<câu hiện tại>"`. Không có lịch sử → `query == câu hiện tại`.
  - `test_external_drops_internal_turns` **(test âm)**: lịch sử có một lượt nội bộ với `question="BÍ-MẬT-NỘI-BỘ"` → chuỗi này không xuất hiện trong bất kỳ đối số nào truyền cho `rewrite` hay `stream_answer`.
  - `test_external_drops_other_provider_turns` **(test âm)**: hỏi `provider="gemini"`, lịch sử có lượt `claude` với `answer="CLAUDE-ONLY"` → `rewrite` không được gọi và chuỗi `"CLAUDE-ONLY"` không xuất hiện ở đâu.
  - `test_external_rewrites_then_searches`:
    - `rewrite` trả `"Nghỉ phép năm ai duyệt?"` → `find` nhận đúng câu đó cho cả `query` và `highlight`;
    - `meta.query == "Nghỉ phép năm ai duyệt?"`;
    - `stream_answer` nhận câu đã viết lại, không nhận lịch sử.
  - `test_external_without_turns_skips_rewrite`: không gọi `rewrite`; `meta.query is None`.
  - `test_rewrite_failure_or_empty_falls_back` (parametrize: ném lỗi / trả `""` / trả `"  "`) → `find` nhận câu gốc, `meta.query is None`, không có sự kiện `error`.
  - `test_external_streams_deltas`: `stream_answer` sinh `["Cần ", "duyệt [1]."]` → sự kiện `meta, delta, delta, done`.
  - `test_external_error_midstream`: sinh `"Cần "` rồi ném lỗi → `meta, delta, error, done`; `llm_error` bắt đầu bằng `"Không gọi được AI ngoài ("`.
  - `test_no_documents_message`: `find` trả `[]` → `meta.message == "Chưa có tài liệu nào"`, không gọi `stream_answer`.
  - `test_only_last_three_turns_used`: lịch sử có 5 lượt AI ngoài cùng nhà → `rewrite` chỉ nhận 3 lượt cuối.
  - Trong `test_search.py` thêm `test_highlight_limits_matched`: `matched` chỉ gồm từ của `highlight`.
- [ ] **Bước 2: Chạy cho thấy đỏ:** `.venv/bin/pytest tests/test_ask.py tests/test_search.py -q`.
- [ ] **Bước 3: Hiện thực `ask.py`** và tham số `highlight` trong `search.py`. Thứ tự trong `ask_events`:
  1. cắt lịch sử còn `HISTORY_TURNS` lượt cuối;
  2. viết lại câu (chỉ chế độ AI ngoài và khi có lượt cùng nhà);
  3. tìm;
  4. phát `meta`;
  5. nếu có đoạn và là chế độ AI ngoài thì stream;
  6. phát `done`.
  Ghi log lỗi bằng `logger.exception`, như `app.py` đang làm.
- [ ] **Bước 4: Chạy cho thấy xanh**, cùng lệnh ở bước 2.
- [ ] **Bước 5: Commit:** `feat(backend): follow-up aware ask pipeline as an event stream`.

### Task 3: `app.py` nhận lịch sử, thêm endpoint stream

**Files:**
- Modify: `backend/app.py`
- Test: `backend/tests/test_app.py`

**Interfaces:**
- Consumes (Task 2): `ask_events`, `search(..., highlight=)`. Consumes (Task 1): `llm.stream_answer`, `llm.rewrite`, `llm.providers`.
- Produces:
  - `create_app(env=None, *, embedder=None, stream_answer=llm.stream_answer, rewrite=llm.rewrite, frontend_dir=DIST)`: bỏ tham số `answer`.
  - `POST /api/ask`: JSON `{answer, sources, llm_error, message, query, provider}`. `answer` là chuỗi ghép các `delta`, hoặc `null` nếu không có delta nào.
  - `POST /api/ask/stream`: `text/event-stream`, mỗi sự kiện dạng `event: <tên>\ndata: <json>\n\n`; `data` dùng `json.dumps(..., ensure_ascii=False)`.
  - `GET /api/config`: `providers` theo thứ tự cố định.

- [ ] **Bước 1: Viết test (đỏ)** trong `test_app.py`. Thay `FakeAnswer` bằng `FakeLLM` có hai hàm `stream_answer` và `rewrite`, ghi lại các lần gọi. Sửa `open_client(..., llm=None)`; hàm `ask(c, ..., history=None)` thêm `history`.
  - `test_history_validation_422` (parametrize): 4 lượt; `question` 2001 ký tự; `answer` 8001 ký tự; `mode="khac"` → mỗi trường hợp đều 422.
  - `test_ask_json_collects_stream`: AI giả sinh `["Trả ", "lời [1]"]` → `answer == "Trả lời [1]"`, `provider == "gemini"`, có khoá `query`.
  - `test_ask_stream_sse`:
    - `c.post("/api/ask/stream", ...)` trả `content-type` bắt đầu bằng `text/event-stream`;
    - parse ra đúng thứ tự `meta, delta, delta, done`;
    - `data` của `meta` có `sources`.
  - `test_ask_stream_403_before_stream`: `ALLOW_EXTERNAL=false` → mã 403, `{"detail": "Chưa cho phép gửi ra ngoài"}`.
  - `test_config_providers_order`: env có đủ key ba nhà → `["claude", "openai", "gemini"]`.
  - `test_unknown_or_unconfigured_provider_403`: `provider="openai"` khi chỉ có Gemini → 403.
  - Sửa các test `/api/ask` cũ theo `FakeLLM`. Giữ nguyên ý của từng test: chế độ nội bộ không gọi AI, lỗi AI vẫn trả `sources`, kiểm quyền trước khi tìm.
- [ ] **Bước 2: Chạy cho thấy đỏ:** `.venv/bin/pytest tests/test_app.py -q`.
- [ ] **Bước 3: Hiện thực.**
  - Model pydantic cho lượt lịch sử: `question: str = Field(min_length=1, max_length=2000)`, `mode: Literal["internal", "external"]`, `provider: str | None = None`, `answer: str | None = Field(None, max_length=8000)`.
  - `AskBody.history: list[HistoryTurn] = Field(default_factory=list, max_length=3)`.
  - Kiểm quyền (403) đặt trước khi tạo generator.
  - `/api/ask/stream` trả `StreamingResponse` từ generator đồng bộ. Starlette chạy generator đồng bộ trong threadpool, nên vòng lặp sự kiện không bị chặn.
- [ ] **Bước 4: Chạy cả bộ backend cho thấy xanh:** `cd backend && ANONYMIZED_TELEMETRY=False .venv/bin/pytest`.
- [ ] **Bước 5: Commit:** `feat(api): history in ask requests and SSE endpoint /api/ask/stream`.

### Task 4: `api.ts` đọc stream, `history.ts` dựng lịch sử gửi đi

**Files:**
- Modify: `frontend/src/api.ts`, `frontend/src/history.ts`
- Create test: `frontend/src/api.test.ts`
- Modify test: `frontend/src/history.test.ts`

**Interfaces:**
- Produces (`api.ts`):
  - `interface HistoryTurn { question: string; mode: Mode; provider: string | null; answer: string | null }`
  - `interface AskRequest { question: string; mode: Mode; provider?: string; history: HistoryTurn[] }`
  - `AskResult` thêm `query?: string | null; provider?: string | null`
  - `type AskEvent = { type: "meta"; sources: Source[]; query: string | null; message: string | null } | { type: "delta"; text: string } | { type: "error"; llm_error: string } | { type: "done" }`
  - `askStream(req: AskRequest, onEvent: (e: AskEvent) => void): Promise<void>`:
    - lỗi HTTP ném `ApiError` như `request()`;
    - mất kết nối, hoặc stream kết thúc khi chưa nhận `done`, thì ném `ApiError(0, "Không kết nối được máy chủ")`;
    - bỏ hàm `ask` cũ.
- Produces (`history.ts`):
  - `Turn` thêm `provider?: string | null`
  - `toHistory(turns: Turn[]): HistoryTurn[]`: 3 lượt cuối, `provider: t.provider ?? null`, `answer: t.result.answer`; không chép `sources` hay `query`.

- [ ] **Bước 1: Viết test (đỏ).**
  - Trong `api.test.ts`, stub `fetch` trả `new Response(ReadableStream)`, đẩy các mảng `Uint8Array` tuỳ ý:
    - `askStream parses events in order`;
    - `handles an event split across chunks, including inside a multi-byte Vietnamese character` (cắt giữa các byte của chữ "ữ");
    - `throws ApiError(403) with detail before streaming`;
    - `throws ApiError(0) when the stream ends without done`;
    - `posts exactly {question, mode, provider, history}`.
  - Trong `history.test.ts`:
    - `toHistory keeps the last 3 turns, maps provider (missing → null) and never includes sources`.
- [ ] **Bước 2: Chạy cho thấy đỏ:** `cd frontend && npx vitest run src/api.test.ts src/history.test.ts`.
- [ ] **Bước 3: Hiện thực.** Dùng `res.body.getReader()` cùng một `TextDecoder` với `{ stream: true }`, cộng dồn vào buffer, tách sự kiện theo `"\n\n"`, đọc dòng `event:` và `data:`.
- [ ] **Bước 4: Chạy cho thấy xanh.** `Chat.tsx` sẽ báo lỗi type vì `ask` đã bị bỏ; Task 5 sửa chỗ đó, nên ở bước này chỉ chạy hai file test trên.
- [ ] **Bước 5: Commit:** `feat(frontend): SSE client and outgoing history`.

### Task 5: `Chat` và `Answer`: stream, chọn nhà, dòng "Hiểu là"

**Files:**
- Modify: `frontend/src/Chat.tsx`, `frontend/src/Answer.tsx`, `frontend/src/format.ts`, `frontend/src/app.css`
- Test: `frontend/src/Chat.test.tsx`, `frontend/src/Answer.test.tsx`

**Interfaces:**
- Consumes (Task 4): `askStream`, `AskEvent`, `toHistory`, `HistoryTurn`.
- Produces:
  - `PROVIDER_LABEL: Record<string, string>` trong `format.ts`: `{claude: "Claude", openai: "OpenAI", gemini: "Gemini"}`.
  - `Answer({ mode, result, question?, provider? })`:
    - lượt AI ngoài có `provider` → nhãn chế độ dùng chuỗi ở mục Ràng buộc chung;
    - `result.query` khác `null` và khác `question` → hiện `Hiểu là: <query>`.
  - `PROVIDER_KEY = "tcnb:provider"` trong `Chat.tsx`.

- [ ] **Bước 1: Viết test (đỏ).** Trong `Chat.test.tsx`, thêm helper `sse(events)` trả về `Response` có body SSE; `stubFetch` bắt `/api/ask/stream`.
  - Sửa `sends exactly ...`: body là `{question, mode: "external", provider: "gemini", history: []}`. Hỏi tiếp trong cùng cuộc thì `history` có lượt trước, chỉ gồm `question, mode, provider, answer`.
  - `streams text progressively`: sau `delta` đầu đã thấy `"Cần "`; sau `done` thấy cả câu, và `onSave` được gọi đúng một lần.
  - `shows sources as soon as meta arrives`: chế độ nội bộ, thẻ nguồn hiện ngay sau `meta`.
  - `error mid-stream keeps text and shows the error, then saves`.
  - `stream cut before done shows Thử lại and does not save`.
  - `provider select appears only with 2+ providers`:
    - 1 nhà thì không có `combobox`;
    - 3 nhà thì có 3 option, mặc định Claude;
    - chọn OpenAI → `localStorage["tcnb:provider"] === "openai"` và request gửi `provider: "openai"`.
  - `remembered provider that is no longer configured falls back to the first`: `tcnb:provider = "openai"`, `providers = ["gemini"]` → request gửi `provider: "gemini"`.
  - `old history without provider/query still renders`: một lượt cũ trong localStorage, không có hai trường mới, vẫn hiển thị được.
  - Sửa test toast: chuỗi mới ở mục Ràng buộc chung.
  - Trong `Answer.test.tsx`:
    - `shows 'Hiểu là' only when query differs from the question`;
    - `label names the provider`.
- [ ] **Bước 2: Chạy cho thấy đỏ:** `npx vitest run src/Chat.test.tsx src/Answer.test.tsx`.
- [ ] **Bước 3: Hiện thực.**
  - Trạng thái `pending` giữ `{question, mode, provider, result: AskResult}`; mỗi sự kiện cập nhật `result`, và khung chờ render `Answer` từ đó.
  - Nhận `done` thì lưu lượt kèm `provider` và `result.query`, như luồng lưu hiện tại.
  - "Đang viết câu trả lời…" chỉ hiện khi là chế độ AI ngoài và chưa có chữ.
  - Ô chọn nhà dùng `<select>` gốc, `aria-label="Nhà cung cấp AI"`, chỉ hiện khi `config.providers.length >= 2`, và bị khoá khi công tắc đang ở "Chỉ nội bộ".
  - Thêm style `.provider` và `.understood` trong `app.css`, chỉ dùng token màu có sẵn.
- [ ] **Bước 4: Chạy cả bộ frontend cho thấy xanh:** `npm test && npm run lint && npm run build`.
- [ ] **Bước 5: Commit:** `feat(frontend): streamed answers, provider picker and follow-up questions`.

### Task 6: Tài liệu và kiểm tay

**Files:**
- Modify: `README.md`, `docs/2026-11-25-thiet-ke-dot-2a.md` (dòng trạng thái)

- [ ] **Bước 1: Sửa README.**
  - Bảng biến môi trường: thêm `ANTHROPIC_API_KEY` + `CLAUDE_MODEL`, `OPENAI_API_KEY` + `OPENAI_MODEL`; bỏ câu "Đợt 1 chỉ hỗ trợ Gemini…".
  - Mục "AI ngoài": thay đoạn "Gửi đi đúng ba thứ" bằng nội dung TK2A mục 3. Thêm hỏi nối tiếp, stream, chọn nhà.
  - Giới hạn: bỏ dòng "không stream"; sửa "Mỗi câu hỏi độc lập" thành mô tả hỏi nối tiếp.
  - Các đợt tiếp theo: gạch phần A khỏi danh sách.
- [ ] **Bước 2: Kiểm tay.**
  - Chạy app theo README, `ALLOW_EXTERNAL=true`, với key thật nếu người dùng cung cấp.
  - Hỏi một câu ở chế độ AI ngoài, rồi hỏi nối tiếp "thế ai duyệt?": thấy dòng "Hiểu là", chữ hiện dần.
  - Không có key: chỉ kiểm chế độ nội bộ (hỏi nối tiếp có ghép câu trước) và ghi rõ trong báo cáo là **chưa kiểm với AI thật**.
- [ ] **Bước 3: Chạy lại cả hai bộ test**, đều xanh.
- [ ] **Bước 4: Đổi dòng trạng thái của TK2A** thành "đã triển khai", rồi commit: `docs: README for phase 2A`.
