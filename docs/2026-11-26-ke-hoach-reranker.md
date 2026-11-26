# Kế hoạch triển khai: chấm lại đoạn tìm được (reranker)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chấm lại 5 đoạn tìm được bằng cross-encoder, xếp lại và bỏ đoạn điểm thấp; không còn đoạn nào thì coi là "không liên quan".

**Architecture:** Module mới `backend/rerank.py` (nạp model, chấm, cắt). Hàm dùng chung `select_sources` trong `ask.py` quyết định đoạn nào được hiện và cờ `low_relevance`, dùng cho cả `ask_events` lẫn `eval.py` (giống `is_low_relevance` hiện nay). `app.py` nạp model khi khởi động theo biến môi trường.

**Tech Stack:** Python 3.12, FastAPI, FastEmbed 0.9.1 (`fastembed.rerank.cross_encoder.TextCrossEncoder`), pytest.

**Spec:** `docs/2026-11-26-thiet-ke-reranker.md`

## Global Constraints

- Model mặc định: `BAAI/bge-reranker-v2-m3-int8`; ngưỡng mặc định `RERANK_MIN = -5.0` (bỏ đoạn có điểm **dưới** ngưỡng; bằng ngưỡng thì giữ).
- Biến môi trường: `RERANK_MODEL` (giá trị `off`, không phân biệt hoa thường, tắt hẳn bước chấm lại), `RERANK_MIN` (số thực).
- Chỉ chấm lại 5 đoạn đã tìm (không mở rộng lên 20).
- Cosine cao nhất dưới `MIN_RELEVANCE` thì **không gọi** reranker.
- Câu hỏi không dấu (`unaccent(q) == q`) thì giữ nguyên 5 đoạn và thứ tự, không gọi reranker.
- Reranker cắt hết đoạn thì `low_relevance = true` và `sources` là **5 đoạn ban đầu**, không gọi AI.
- Câu dùng để chấm là câu đã dùng để tìm (`query` trong `ask_events`).
- Nạp model lỗi khi khởi động thì máy chủ dừng (không bắt lỗi).
- Test không được tải model thật: luôn dùng reranker giả hoặc `RERANK_MODEL=off`.
- Không đổi giao diện (frontend đã hiện số đoạn bất kỳ và đã xử lý `low_relevance`).
- Code, comment, commit tiếng Anh; tài liệu tiếng Việt.
- Lệnh test backend: `cd backend && ANONYMIZED_TELEMETRY=False .venv/bin/pytest -q`.

## Review Focus

1. Câu không dấu (kể cả câu tiếng Anh): không mất đoạn nào, giữ thứ tự → test ở Task 1 (`test_rerank_unaccented_query_untouched`, `test_has_diacritics`).
2. Reranker cắt hết đoạn: người dùng vẫn mở được 5 đoạn ban đầu, AI không được gọi → Task 2 (`test_rerank_cuts_all_marks_low_and_keeps_original_sources`).
3. AI ngoài chỉ nhận đúng các đoạn còn lại, số trích dẫn khớp số đoạn hiện → Task 2 (`test_rerank_keeps_subset_and_llm_gets_only_kept`, `test_system_prompt_has_no_fixed_source_count`).
4. `RERANK_MODEL=off`: hành vi y như trước đợt này, không nạp model → Task 2 (`test_rerank_off_keeps_all_sources`).
5. Câu bị chặn bởi cosine hoặc chưa có tài liệu: không tốn 0,6 giây gọi reranker → Task 2 (`test_rerank_not_called_when_cosine_low`, `test_rerank_not_called_without_docs`).

---

### Task 1: Module `rerank.py`

**Files:**
- Create: `backend/rerank.py`
- Test: `backend/tests/test_rerank.py`

**Interfaces:**
- Consumes: `search.unaccent(text: str) -> str`.
- Produces:
  - `DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3-int8"`, `RERANK_MIN = -5.0`
  - `class Reranker: __init__(self, model_name: str = DEFAULT_MODEL)`; `score(self, query: str, texts: list[str]) -> list[float]` (bọc `TextCrossEncoder(model_name).rerank(query, texts)`; không truyền `cache_dir`, FastEmbed tự đọc `FASTEMBED_CACHE_PATH` như `Embedder`).
  - `has_diacritics(text: str) -> bool` (= `unaccent(text) != text`).
  - `rerank(query: str, hits: list[dict], scorer, min_score: float) -> list[dict]`: câu không dấu hoặc `hits` rỗng → trả nguyên `hits`, không gọi `scorer`. Ngược lại gọi `scorer.score(query, [h["text"] for h in hits])` một lần, trả các hit có điểm `>= min_score`, xếp điểm giảm dần, mỗi hit là bản sao có thêm khoá `"rerank_score": float`.

- [ ] **Step 1: Viết test hỏng** trong `tests/test_rerank.py`, dùng `FakeScorer(scores)` có `score(query, texts)` trả `scores` và ghi lại `(query, texts)`:

```python
def test_has_diacritics():
    assert has_diacritics("nghỉ phép năm")
    assert has_diacritics("đi công tác")
    assert not has_diacritics("nghi phep nam bao nhieu ngay")
    assert not has_diacritics("What is the leave policy?")

def test_rerank_sorts_and_cuts():
    s = FakeScorer([-6.0, 2.0, 0.0])
    out = rerank("ai duyệt nghỉ phép", hits("A", "B", "C"), s, -5.0)
    assert [h["id"] for h in out] == ["B", "C"]
    assert [h["rerank_score"] for h in out] == [2.0, 0.0]
    assert s.calls == [("ai duyệt nghỉ phép", ["text A", "text B", "text C"])]

def test_rerank_keeps_score_equal_to_min():
    assert [h["id"] for h in rerank("nghỉ phép", hits("A"), FakeScorer([-5.0]), -5.0)] == ["A"]

def test_rerank_all_below_returns_empty():
    assert rerank("nghỉ kết hôn", hits("A", "B"), FakeScorer([-7.0, -9.0]), -5.0) == []

def test_rerank_unaccented_query_untouched():
    s, h = FakeScorer([-9.0, -9.0]), hits("A", "B")
    assert rerank("nghi phep nam", h, s, -5.0) == h
    assert s.calls == []

def test_rerank_empty_hits_skips_scorer():
    s = FakeScorer([])
    assert rerank("nghỉ phép", [], s, -5.0) == [] and s.calls == []

def test_rerank_does_not_mutate_input():
    h = hits("A")
    rerank("nghỉ phép", h, FakeScorer([1.0]), -5.0)
    assert "rerank_score" not in h[0]
```

(`hits(*ids)` tạo `{"id": i, "text": f"text {i}", "meta": {}, "score": 0.1, "matched": []}`.)

- [ ] **Step 2: Chạy test, xác nhận hỏng** — `.venv/bin/pytest -q tests/test_rerank.py` → FAIL (`ModuleNotFoundError: rerank`).
- [ ] **Step 3: Viết `backend/rerank.py`** theo Interfaces. Comment ngắn ở `RERANK_MIN` trỏ tới `docs/bao-cao-chat-luong-tim-kiem.md` mục 7 và nhắc: đổi model thì đo lại.
- [ ] **Step 4: Chạy test, xác nhận qua** — `.venv/bin/pytest -q tests/test_rerank.py` → PASS.
- [ ] **Step 5: Commit** — `git add backend/rerank.py backend/tests/test_rerank.py && git commit -m "feat(search): cross-encoder rerank module"`

### Task 2: Nối vào luồng hỏi và app

**Files:**
- Modify: `backend/ask.py`, `backend/app.py`, `backend/llm.py` (`SYSTEM`)
- Modify docs: `README.md`, `docs/tinh-nang.md`, `docs/van-hanh.md`
- Test: `backend/tests/test_ask.py`, `backend/tests/test_app.py`, `backend/tests/test_llm.py`

**Interfaces:**
- Consumes: Task 1 (`Reranker`, `rerank`, `DEFAULT_MODEL`, `RERANK_MIN`).
- Produces:
  - `ask.select_sources(query: str, chunks: list[dict], top_similarity: float | None, min_relevance: float, rerank: Callable[[str, list[dict]], list[dict]] | None) -> tuple[list[dict], bool]` trả `(sources, low_relevance)`:
    - `chunks` rỗng → `([], False)`;
    - `is_low_relevance(top_similarity, min_relevance)` → `(chunks, True)`, không gọi `rerank`;
    - `rerank is None` → `(chunks, False)`;
    - `kept = rerank(query, chunks)`; `kept` khác rỗng → `(kept, False)`, rỗng → `(chunks, True)`.
  - `ask_events(..., min_relevance: float, rerank: Callable | None = None)`: dùng `select_sources(query, chunks, top, min_relevance, rerank)`; `meta.sources` là `sources`; `stream_answer` nhận `sources`.
  - `create_app(env=None, *, embedder=None, reranker=None, stream_answer=..., rewrite=..., frontend_dir=DIST)`: `RERANK_MODEL` = `off` → không có reranker; ngược lại trong `lifespan`: `app.state.reranker = reranker or Reranker(env.get("RERANK_MODEL") or DEFAULT_MODEL)`. `rerank_min = float(env.get("RERANK_MIN") or RERANK_MIN)`. `start_ask` truyền `rerank=lambda q, hits: rerank(q, hits, s.reranker, rerank_min)` khi có reranker, ngược lại `None`.

- [ ] **Step 1: Viết test hỏng.** Trong `test_ask.py`, `Fakes` có thêm `rerank(query, chunks)` ghi `rerank_calls` và trả `self.kept` (mặc định trả nguyên `chunks`); `run(...)` truyền `rerank=fakes.rerank`. Dùng 3 chunk `C3` (id `A:0`, `A:1`, `A:2`):

```python
def test_rerank_keeps_subset_and_llm_gets_only_kept():
    f = Fakes(chunks=C3, kept=[C3[1]])
    events = run(f)
    assert events[0][1]["sources"] == [C3[1]] and events[0][1]["low_relevance"] is False
    assert f.stream_calls[0][1] == [C3[1]]

def test_rerank_cuts_all_marks_low_and_keeps_original_sources():
    f = Fakes(chunks=C3, kept=[])
    events = run(f)
    assert names(events) == ["meta", "done"]
    assert events[0][1]["sources"] == C3 and events[0][1]["low_relevance"] is True
    assert f.stream_calls == []

def test_rerank_not_called_when_cosine_low():
    f = Fakes(top=0.3)
    run(f, min_relevance=0.5)
    assert f.rerank_calls == []

def test_rerank_not_called_without_docs():
    f = Fakes(chunks=[])
    run(f)
    assert f.rerank_calls == []

def test_rerank_receives_search_query():
    f = Fakes()
    run(f, history=[turn("nghỉ phép năm")])  # external + history: rewrite → "Câu viết lại?"
    assert f.rerank_calls[0][0] == "Câu viết lại?"
```

Trong `test_llm.py`:

```python
def test_system_prompt_has_no_fixed_source_count():
    assert "[5]" not in llm.SYSTEM
```

Trong `test_app.py`: `make_env` mặc định thêm `"RERANK_MODEL": "off"`; thêm `FakeReranker(scores)` có `score(query, texts)` trả `scores[:len(texts)]` và đếm số lần gọi; `open_client` nhận thêm `reranker=None` truyền vào `create_app`. Tài liệu nạp sẵn trong test phải cho ra ít nhất 2 đoạn (dùng helper nạp file hiện có).

```python
def test_rerank_off_keeps_all_sources(open_client, make_env):
    r = FakeReranker([-99.0] * 5)
    client = open_client(make_env(), reranker=r)  # RERANK_MODEL=off
    # nạp tài liệu, hỏi câu có dấu
    body = resp.json()
    assert r.calls == 0 and body["sources"] and all("rerank_score" not in s for s in body["sources"])

def test_app_reranks_with_env_min(open_client, make_env):
    r = FakeReranker([1.0, -3.0, 1.0, 1.0, 1.0])
    client = open_client(make_env(RERANK_MODEL="", RERANK_MIN="0"), reranker=r)
    # nạp tài liệu, hỏi câu có dấu
    body = resp.json()
    assert all(s["rerank_score"] >= 0 for s in body["sources"]) and body["low_relevance"] is False
```

- [ ] **Step 2: Chạy test, xác nhận hỏng** — `.venv/bin/pytest -q tests/test_ask.py tests/test_app.py tests/test_llm.py` → các test mới FAIL.
- [ ] **Step 3: Sửa code** theo Interfaces. `llm.SYSTEM`: đổi "các nguồn đánh số [1]…[5]" thành "các nguồn đánh số [1], [2]…". Bỏ `[:5]` trong `build_messages` nếu thừa thì để nguyên (không bắt buộc).
- [ ] **Step 4: Chạy cả bộ test** — `cd backend && ANONYMIZED_TELEMETRY=False .venv/bin/pytest -q` → toàn bộ PASS.
- [ ] **Step 5: Sửa tài liệu** (tiếng Việt):
  - `README.md`: "trả về tối đa 5 đoạn liên quan, bỏ đoạn không trả lời được"; dung lượng tải lần đầu "khoảng 1,1 GB".
  - `docs/tinh-nang.md`: mục tìm kiếm thêm bước chấm lại (câu không dấu không cắt; cắt hết thì như "không liên quan"); dòng "Gửi đi … 5 đoạn" thành "các đoạn còn lại sau khi chấm (tối đa 5)"; mục giới hạn cập nhật số 7/9 và hai câu còn lọt, câu tiếng Anh không được cắt.
  - `docs/van-hanh.md`: bảng biến môi trường thêm `RERANK_MODEL`, `RERANK_MIN` (giá trị, ý nghĩa, đổi model thì đo lại bằng `eval.py --corpus`); RAM thêm khoảng 470 MB, mỗi câu thêm khoảng 0,6 giây trên CPU.
- [ ] **Step 6: Commit** — `git add backend/ask.py backend/app.py backend/llm.py backend/tests README.md docs/tinh-nang.md docs/van-hanh.md && git commit -m "feat(ask): rerank retrieved passages and drop unanswerable ones"`

### Task 3: Bộ đo và báo cáo

**Files:**
- Modify: `backend/eval.py`
- Modify docs: `docs/bao-cao-chat-luong-tim-kiem.md`, `docs/lo-trinh.md`, `docs/2026-11-26-thiet-ke-reranker.md` (trạng thái)
- Test: `backend/tests/test_eval.py`

**Interfaces:**
- Consumes: `ask.select_sources` (Task 2); `rerank.Reranker`, `rerank.rerank`, `DEFAULT_MODEL`, `RERANK_MIN` (Task 1).
- Produces:
  - `score(item, hits, seconds, top_similarity=None, min_relevance=MIN_RELEVANCE, low=None)`: `low` khác `None` thì dùng làm `low_relevance`, ngược lại giữ quy tắc cũ. Mỗi dòng thêm `"shown": 0 if low_relevance else len(hits)`.
  - `run_corpus(questions, corpus_dir, options, min_relevance=MIN_RELEVANCE, rerank=None)` và `run_data_dir(questions, min_relevance=MIN_RELEVANCE, rerank=None)`: sau `retrieve`, gọi `select_sources(item["question"], hits, top_sim, min_relevance, rerank)` rồi `score(item, sources, ..., low=low)`. Thời gian đo bao gồm cả bước chấm lại.
  - `summarize`: `tong` thêm `"so_doan_tb"` = trung bình `shown` của câu có đáp án; `print_report` in thêm dòng này.
  - CLI: mặc định nạp `Reranker(os.environ.get("RERANK_MODEL") or DEFAULT_MODEL)` (trừ khi `RERANK_MODEL=off`); cờ `--no-rerank` tắt; `--rerank-min <số>` đổi ngưỡng (mặc định `RERANK_MIN`).

- [ ] **Step 1: Viết test hỏng** trong `test_eval.py` (dùng `FakeEmbedder` sẵn có và bộ corpus tạm như `test_run_corpus...` hiện có):

```python
def test_run_corpus_rerank_cut_all_marks_low(tmp_path):
    # corpus + 1 câu có dấu, có đáp án; rerank giả luôn trả []
    rows, _ = ev.run_corpus(qs, tmp_path / "corpus", {}, min_relevance=0.0, rerank=lambda q, h: [])
    assert rows[0]["low_relevance"] is True and rows[0]["shown"] == 0

def test_run_corpus_rerank_order_drives_rank(tmp_path):
    # corpus có ít nhất 2 đoạn để thứ tự có nghĩa; rerank giả đảo ngược thứ tự hits
    plain, _ = ev.run_corpus(qs, tmp_path / "corpus", {}, min_relevance=0.0)
    rev, _ = ev.run_corpus(qs, tmp_path / "corpus", {}, min_relevance=0.0, rerank=lambda q, h: h[::-1])
    assert rev[0]["shown"] == plain[0]["shown"] >= 2
    assert rev[0]["loc_rank"] == plain[0]["shown"] - plain[0]["loc_rank"] + 1

def test_summarize_reports_avg_shown():
    rows = [ev.score(item, hits("a.pdf", "b.pdf"), 0.1, low=False), ev.score(item, hits("a.pdf"), 0.1, low=True)]
    assert ev.summarize(rows)["tong"]["so_doan_tb"] == 1.0
```

- [ ] **Step 2: Chạy test, xác nhận hỏng** — `.venv/bin/pytest -q tests/test_eval.py` → FAIL.
- [ ] **Step 3: Sửa `eval.py`** theo Interfaces.
- [ ] **Step 4: Chạy cả bộ test** → PASS.
- [ ] **Step 5: Đo thật** (máy chủ app phải tắt; model đã có trong `data/models`):

```
cd backend
FASTEMBED_CACHE_PATH=../data/models ANONYMIZED_TELEMETRY=False .venv/bin/python eval.py --corpus
FASTEMBED_CACHE_PATH=../data/models ANONYMIZED_TELEMETRY=False .venv/bin/python eval.py --corpus --no-rerank
```

Kỳ vọng (từ bản thử): có chấm lại `vitri@5` 0,97 (34/35), `chan_nham` 0,00, `bat_duoc` khoảng 7/9, MRR khoảng 0,90, `so_doan_tb` khoảng 3,3; `--no-rerank` ra đúng số mục 6 của báo cáo (34/35, MRR 0,86, 3/9, `so_doan_tb` 5). Lệch nhiều so với kỳ vọng (ví dụ `chan_nham` > 0) thì dừng và báo, không tự chỉnh ngưỡng.

- [ ] **Step 6: Viết báo cáo** `docs/bao-cao-chat-luong-tim-kiem.md`:
  - Mục 7 "Chấm lại đoạn (reranker)": thử cắt theo cosine trước (không làm được: cắt bao nhiêu cũng mất đoạn đúng câu không dấu, đoạn rác cùng chủ đề có cosine 0,83–0,89 như đoạn đúng); so hai bản model (int8: RAM +473 MB, trung vị 0,62 giây / p95 1,50 giây; đầy đủ: +1085 MB, 0,81 / 2,13 giây; chất lượng gần như nhau); chấm 20 đoạn (5,5–7 giây, 33/35, loại); câu không dấu bị chấm -9 đến -11 nên không cắt; chọn ngưỡng -5 (đoạn đúng thấp nhất của câu có dấu -4,15, chừa 0,85); bảng số từ Step 5; hai câu còn lọt.
  - Mục 6: cập nhật cấu hình cuối và bảng "ban đầu so với cuối" theo số Step 5.
- [ ] **Step 7: Sửa** `docs/lo-trinh.md` (reranker sang "Đã xong"; thêm "Thêm dấu cho câu hỏi không dấu" và "Đo model chấm lại lớn hơn khi có GPU" vào "Tiếp theo"), trạng thái trong `docs/2026-11-26-thiet-ke-reranker.md` thành "đã triển khai".
- [ ] **Step 8: Commit** — `git add backend/eval.py backend/tests/test_eval.py docs && git commit -m "feat(eval): measure reranker cut, report section 7"`
