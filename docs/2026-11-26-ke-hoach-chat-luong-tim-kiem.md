# Kế hoạch triển khai: đo và nâng chất lượng tìm kiếm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Mục tiêu:** Dựng bộ đo chạy lại được (tài liệu mẫu + câu hỏi + `eval.py`), đo bản hiện tại, rồi sửa tách từ, câu không liên quan và cách đọc/cắt file, mỗi thay đổi được giữ hay bỏ theo số đo.

**Kiến trúc:**
- Bộ mẫu nằm ở `backend/eval_data/` (file sinh sẵn, commit vào repo).
- `eval.py` nạp bộ mẫu vào một `DATA_DIR` tạm qua đúng đường nạp thật, rồi chạy câu hỏi qua đúng hàm `search`.
- Mỗi chỗ sửa có một "núm chỉnh" (tham số) để `eval.py` bật/tắt và so sánh. Giá trị mặc định trong code là giá trị số đo chọn.

**Stack:** Python 3.12, `pypdf` 7.1.1, `python-docx`, `openpyxl`, `fpdf2` (dev), `rank-bm25`, Chroma; React/TS cho phần hiển thị.

**Spec:** `docs/2026-11-26-thiet-ke-chat-luong-tim-kiem.md` (gọi tắt **TKCL**). Đọc cùng kế hoạch.

**Lệnh test:**
- backend: `cd backend && ANONYMIZED_TELEMETRY=False .venv/bin/pytest -q`
- frontend: `cd frontend && npm test && npm run lint && npm run build`
- bộ đo: `cd backend && ANONYMIZED_TELEMETRY=False .venv/bin/python eval.py --corpus [tham số]`

## Ràng buộc chung

- **Bộ mẫu ở `backend/eval_data/`**, không phải `backend/eval/` như TKCL ghi: thư mục `eval/` trùng tên với module `eval.py` khi import. Gồm `corpus/<thư mục>/<file>`, `questions.json`, `make_corpus.py`.
- Bộ mẫu có 8–12 file, 3–4 thư mục, đủ các ca khó ở TKCL mục 3. Có khoảng 40 câu, đủ 7 nhóm ở TKCL mục 4, với tên nhóm đúng như sau: `dung-chu`, `dien-dat-khac`, `tu-ghep-viet-tat`, `khong-dau`, `bang`, `hai-cot`, `khong-lien-quan`. Nội dung đều là dữ liệu giả.
- **Quy tắc giữ/bỏ** (TKCL mục 5):
  - điểm chính là `vitri@5` trên các câu có đáp án; `MRR` dùng để phân xử khi bằng nhau;
  - giữ thay đổi khi điểm chính tăng ≥ 1 câu và không nhóm nào mất > 1 câu;
  - nhóm `khong-lien-quan` chỉ dùng để đặt ngưỡng.
- **Ngưỡng:** chọn mức cao nhất không chặn nhầm câu có đáp án nào, rồi trừ **0,02** (cosine). Biến môi trường `MIN_RELEVANCE` ghi đè được. Dưới ngưỡng thì không gọi AI để trả lời; bước viết lại câu hỏi nối tiếp vẫn chạy như đợt 2A.
- **Chuỗi hiển thị cố định:** `Không tìm thấy đoạn nào đủ liên quan`, nút `Xem các đoạn gần nhất`.
- **PDF mẫu hai cột:** ghi chữ hết cột trái rồi mới sang cột phải. Báo cáo ghi rõ đây là **bằng chứng yếu**.
- **Không thêm thư viện runtime mới.** Chỉ DDL trong thay đổi schema: `ALTER TABLE ... ADD COLUMN` lúc khởi động; không có câu `UPDATE` dữ liệu có sẵn.
- **Báo cáo** ghi ở `docs/bao-cao-chat-luong-tim-kiem.md`. Mỗi task đo đều thêm một mục có: lệnh đã chạy, bảng số trước và sau, quyết định giữ hay bỏ, lý do.
- Test hiện có phải vẫn xanh, trừ chỗ TKCL cố ý đổi.

## Rủi ro cần soi khi review

1. **Câu hỏi chỉ có dấu câu hoặc rỗng sau khi tách** (ví dụ `"?"`, `"..."`): không lỗi, phần từ khoá trả rỗng, phần vector vẫn chạy. Test ở Task 3.
2. **Câu hỏi trộn có dấu và không dấu** (`"nghỉ phep"`): vẫn khớp đoạn có "nghỉ phép" và tô đúng chữ "nghỉ phép". Test ở Task 3.
3. **Đoạn đứng đầu sau khi trộn kết quả không phải đoạn giống nhất theo vector:** ngưỡng phải tính theo độ giống **cao nhất của nhánh vector**, không theo đoạn đứng đầu sau trộn. Test ở Task 4.
4. **Ô gộp nằm giữa dữ liệu Excel (không phải tiêu đề), hoặc sheet trống:** không lỗi; giá trị ô gộp lặp cho các ô nó phủ. Test ở Task 6.
5. **Xoá một tài liệu đúng lúc nó đang được index lại theo cách đọc mới:** sau khi mọi việc trong hàng đợi chạy xong, tài liệu đó không được "sống lại". Test ở Task 8.

---

### Task 1: Bộ tài liệu mẫu và câu hỏi

**Files:**
- Create: `backend/eval_data/make_corpus.py`, `backend/eval_data/corpus/**` (file sinh ra), `backend/eval_data/questions.json`
- Test: `backend/tests/test_eval_data.py`

**Interfaces:**
- Produces:
  - `questions.json` là mảng các `{"question": str, "group": str, "expect": [{"filename": str, "page"?: int, "section"?: str, "sheet"?: str, "row"?: int}]}`;
  - `filename` là tên file (không kèm thư mục), chuẩn NFC;
  - `section` đúng nguyên văn chữ của Heading chứa đoạn;
  - `row` là số dòng Excel (đánh từ 1, như `read_xlsx` đang ghi), hoặc số dòng trong bảng Word (dòng tiêu đề là 1);
  - câu `khong-lien-quan` có `expect: []`.
- `make_corpus.py out_dir --font <đường dẫn TTF có dấu>`: sinh lại toàn bộ `corpus/`.

- [ ] **Bước 1: Viết `test_eval_data.py` (đỏ)**:
  - `test_every_expected_file_exists`;
  - `test_groups_and_counts`: đủ 7 nhóm; tổng 36–44 câu; `khong-lien-quan` có ≥ 8 câu, `expect == []`; các nhóm khác `expect` khác rỗng;
  - `test_hard_cases_present`: có ≥ 1 PDF hai cột, ≥ 1 docx có ≥ 2 bảng, ≥ 1 xlsx có ô gộp ở dòng tiêu đề và ≥ 8 cột.
  - Test thứ ba mở file bằng `python-docx`/`openpyxl`. PDF hai cột nhận ra qua tên file chứa `hai-cot`.
- [ ] **Bước 2: Chạy cho thấy đỏ:** `.venv/bin/pytest tests/test_eval_data.py -q`.
- [ ] **Bước 3: Viết `make_corpus.py`, sinh `corpus/`, soạn `questions.json`.**
  - Font: `/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf` trên máy này.
  - PDF hai cột: dùng `fpdf2` vẽ hai cột, ghi hết cột trái rồi sang cột phải.
  - Ít nhất 3 câu trong nhóm `khong-lien-quan` phải **gần chủ đề**, ví dụ hỏi một chế độ không có trong quy chế.
  - Có cặp quy định cũ/mới cùng chủ đề; câu hỏi về cặp này có `expect` ghi cả hai vị trí.
- [ ] **Bước 4: Chạy cho thấy xanh**, cùng lệnh ở bước 2.
- [ ] **Bước 5: Commit:** `test(eval): synthetic Vietnamese corpus and question set`.

### Task 2: `eval.py` đo bộ mẫu, và báo cáo số đo ban đầu

**Files:**
- Modify: `backend/eval.py`, `backend/tests/test_eval.py`
- Create: `docs/bao-cao-chat-luong-tim-kiem.md`

**Interfaces:**
- Consumes (Task 1): định dạng `questions.json`.
- Produces (`eval.py`):
  - `hit_matches(expect: dict, meta: dict) -> bool`:
    - so `filename` theo NFC;
    - có `page`, `section` hoặc `sheet` + `row` thì phải khớp đúng;
    - `expect` chỉ có `filename` thì chỉ so file.
  - `first_rank(expect: list[dict], hits: list[dict], by_file: bool) -> int | None`: hạng (đánh từ 1) của hit đầu tiên khớp bất kỳ phần tử nào trong `expect`; `by_file=True` chỉ so file.
  - `summarize(rows: list[dict]) -> dict[str, dict]`:
    - `rows` là `{"group", "file_rank", "loc_rank", "low_relevance", "has_answer", "seconds"}`;
    - kết quả có khoá `"tong"` (chỉ các câu có đáp án) và từng nhóm, mỗi khoá gồm `file@1, file@5, vitri@5, MRR, so_cau`;
    - nhóm `khong-lien-quan` có thêm `bat_duoc` (tỉ lệ `low_relevance`);
    - `"tong"` có thêm `chan_nham` (tỉ lệ câu có đáp án bị `low_relevance`), `giay_trung_vi`, `giay_p95`.
  - `run_corpus(questions: list[dict], corpus_dir: Path, options: dict) -> tuple[list[dict], float]`:
    - tạo `DATA_DIR` tạm;
    - nạp mọi file qua `ingest` + `Embedder` + `Index` + `Bm25Holder` thật;
    - chạy `search` cho từng câu;
    - trả về các dòng và số giây nạp.
  - CLI: `python eval.py --corpus [--chunk-size N] [--no-bigrams] [--no-unaccent] [--pdf-mode plain|layout] [--min-relevance X]`. Task này chỉ cần `--corpus`; các cờ còn lại được thêm ở task làm ra núm chỉnh tương ứng.
  - In bảng tóm tắt theo nhóm và danh sách câu trượt.
  - `python eval.py <file.json>` vẫn chạy trên `DATA_DIR` thật. Nhận định dạng cũ `{question, filename, where}`: chỉ tính theo file. Nhận cả định dạng mới có `expect`.

- [ ] **Bước 1: Viết test (đỏ)** trong `test_eval.py`, chỉ dùng dữ liệu giả (không có model):
  - `test_hit_matches_location_and_file_only`;
  - `test_first_rank`: hạng 1, hạng 3, không có (`None`), và trường hợp `expect` có hai vị trí;
  - `test_summarize_groups_and_totals`: 4 dòng giả cho ra đúng `vitri@5`, `MRR`, `bat_duoc`, `chan_nham`;
  - `test_legacy_format_scores_by_file`.
  - Giữ hoặc sửa các test cũ theo định dạng mới.
- [ ] **Bước 2: Chạy cho thấy đỏ:** `.venv/bin/pytest tests/test_eval.py -q`.
- [ ] **Bước 3: Hiện thực.**
  - `run_corpus` dùng `tempfile.TemporaryDirectory` và gọi thẳng `ingest` + `Index.add` + `Bm25Holder.rebuild`, không qua `Worker`, cho nhanh và gọn.
  - `low_relevance` lấy từ kết quả `search` nếu có (từ Task 4 trở đi); trước đó luôn là `False`.
- [ ] **Bước 4: Chạy cho thấy xanh**, cùng lệnh ở bước 2. Sau đó chạy cả bộ backend.
- [ ] **Bước 5: Chạy đo bản hiện tại:** `.venv/bin/python eval.py --corpus`. Ghi vào báo cáo mục **"0. Số đo ban đầu"**: bảng theo nhóm, thời gian nạp, thời gian tìm, và 5 câu trượt tiêu biểu.
- [ ] **Bước 6: Commit:** `feat(eval): corpus mode with per-group metrics; baseline report`.

### Task 3: Tách từ: cặp tiếng và bản bỏ dấu

**Files:**
- Modify: `backend/search.py`, `backend/eval.py`
- Test: `backend/tests/test_search.py`

**Interfaces:**
- Produces (`search.py`):
  - `unaccent(text: str) -> str`: bỏ dấu tiếng Việt; `đ`/`Đ` thành `d`/`D`.
  - `tokenize(text: str, *, bigrams: bool = BIGRAMS, unaccent_tokens: bool = UNACCENT) -> list[str]`:
    - các tiếng chữ thường NFC;
    - thêm `a_b` cho mỗi cặp tiếng liền nhau khi `bigrams`;
    - thêm bản bỏ dấu của mọi token đã có khi `unaccent_tokens`, chỉ thêm khi bản đó khác bản gốc.
  - Hằng số `BIGRAMS`, `UNACCENT`. Giá trị mặc định do số đo quyết.
  - `Bm25Holder(bigrams: bool = BIGRAMS, unaccent_tokens: bool = UNACCENT)` có `tokenize(text) -> list[str]` dùng đúng tuỳ chọn đó. `search` tách câu hỏi bằng `bm25.tokenize`, để lúc dựng chỉ mục và lúc tìm luôn dùng cùng một cách tách.
  - `matched`:
    - danh sách các tiếng **có trong chữ của đoạn**, giữ nguyên dạng có dấu, không trùng lặp;
    - một tiếng được chọn khi bản bỏ dấu của nó trùng bản bỏ dấu của một tiếng trong `highlight or question`;
    - không gồm cặp tiếng.
  - `eval.py` có thêm cờ `--no-bigrams`, `--no-unaccent`.

- [ ] **Bước 1: Viết test (đỏ):**
  - `test_tokenize_bigrams_and_unaccent`: `tokenize("Nghỉ phép năm")` chứa `nghỉ`, `phép`, `năm`, `nghỉ_phép`, `phép_năm`, `nghi`, `phep`, `nghi_phep`;
  - `test_unaccent_d`: `unaccent("Đề nghị") == "De nghi"`;
  - `test_tokenize_punctuation_only`: `tokenize("?") == []`;
  - `test_tokenize_single_syllable`: một tiếng thì không có cặp;
  - `test_tokenize_flags_off`: tắt cả hai cờ thì kết quả giống `re.findall(r"\w+", …)` như cũ;
  - `test_search_unaccented_query_matches_and_highlights_accented`: câu hỏi `"nghi phep"` (và cả `"nghỉ phep"`) tìm ra đoạn "Nhân viên được nghỉ phép 12 ngày", và `matched` chứa `"nghỉ"`, `"phép"`. Dùng `FakeEmbedder` hiện có trong `test_search.py`.
- [ ] **Bước 2: Chạy cho thấy đỏ:** `.venv/bin/pytest tests/test_search.py -q`.
- [ ] **Bước 3: Hiện thực** theo Interfaces. `unaccent` dùng `unicodedata.normalize("NFD")`, bỏ các ký tự dấu kết hợp (category `Mn`), rồi xử lý riêng `đ`/`Đ`.
- [ ] **Bước 4: Chạy cho thấy xanh**, rồi chạy cả bộ backend.
- [ ] **Bước 5: Đo bốn tổ hợp** bằng `eval.py --corpus` (mặc định, `--no-bigrams`, `--no-unaccent`, tắt cả hai). Theo quy tắc giữ/bỏ, đặt `BIGRAMS`/`UNACCENT` theo số đo. Ghi báo cáo mục **"1. Tách từ"**.
- [ ] **Bước 6: Commit:** `feat(search): syllable bigrams and unaccented tokens for BM25`.

### Task 4: Ngưỡng "không liên quan" ở backend

**Files:**
- Modify: `backend/search.py`, `backend/ask.py`, `backend/app.py`, `backend/eval.py`
- Test: `backend/tests/test_search.py`, `backend/tests/test_ask.py`, `backend/tests/test_app.py`

**Interfaces:**
- Consumes (Task 3): `search(...)`.
- Produces:
  - `Index.dense_scored(qvec, doc_ids, k=20) -> list[tuple[str, float]]`: id kèm cosine. Khoảng cách L2 bình phương `d2` của Chroma đổi bằng `1 - d2 / 2`. Builder kiểm với tài liệu Chroma 1.5.9 xem khoảng cách trả về có phải L2 bình phương không.
  - `search(...)` trả thêm `"similarity": float | None` trên mỗi hit (`None` khi hit chỉ đến từ BM25).
  - `top_similarity(...)`: hàm thuần, trả cosine cao nhất của **nhánh vector**, kể cả khi đoạn đó không lọt vào top 5 sau trộn. Tên và cách truyền do builder đặt, miễn `ask_events` lấy được giá trị này.
  - Hằng số `MIN_RELEVANCE` trong `ask.py`. Giá trị do số đo quyết, trước khi đo để `0.0`.
  - `ask_events(..., min_relevance: float)`: sự kiện `meta` thêm `"low_relevance": bool`. Khi `True`:
    - **không** gọi `stream_answer`;
    - không có sự kiện `error`;
    - `sources` vẫn là 5 đoạn gần nhất, để giao diện cho xem khi người dùng bấm mở;
    - `message` là `None`.
  - `create_app` đọc `MIN_RELEVANCE` từ env (số thực); không có thì dùng hằng số. `/api/ask` JSON thêm `low_relevance`.
  - `eval.py` có thêm cờ `--min-relevance`; mỗi dòng kết quả ghi `low_relevance`.

- [ ] **Bước 1: Viết test (đỏ):**
  - `test_dense_scored_cosine`: vector giống hệt câu hỏi thì cosine ≈ 1, vector vuông góc ≈ 0;
  - `test_top_similarity_uses_dense_branch`: đoạn BM25 đứng đầu sau trộn có cosine thấp, đoạn vector tốt nhất đứng thứ 6 → giá trị là cosine của đoạn vector (rủi ro 3);
  - `test_low_relevance_skips_answer` trong `test_ask.py`: dưới ngưỡng thì sự kiện là `meta(low_relevance=True)`, `done`, và `stream_answer` không bị gọi; trên ngưỡng thì như cũ;
  - `test_ask_json_and_stream_agree_on_low_relevance` trong `test_app.py`;
  - `test_min_relevance_env_override`.
- [ ] **Bước 2: Chạy cho thấy đỏ:** `.venv/bin/pytest tests/test_search.py tests/test_ask.py tests/test_app.py -q`.
- [ ] **Bước 3: Hiện thực** theo Interfaces.
- [ ] **Bước 4: Chạy cho thấy xanh**, rồi chạy cả bộ backend.
- [ ] **Bước 5: Đặt ngưỡng.**
  - Chạy `eval.py --corpus` để lấy cosine cao nhất của từng câu; `eval.py` in thêm cột này.
  - Chọn ngưỡng theo mục Ràng buộc chung và đặt vào `MIN_RELEVANCE`.
  - Chạy lại để xác nhận `chan_nham == 0`.
  - Ghi báo cáo mục **"2. Câu không liên quan"**: bảng cosine của câu có đáp án và câu không liên quan, ngưỡng chọn, tỉ lệ `bat_duoc`. Dưới 50% thì ghi đề xuất làm reranker ở đợt sau.
- [ ] **Bước 6: Commit:** `feat(search): relevance threshold; skip AI answer when nothing is relevant`.

### Task 5: Giao diện cho kết quả dưới ngưỡng

**Files:**
- Modify: `frontend/src/api.ts`, `frontend/src/Answer.tsx`, `frontend/src/Chat.tsx`, `frontend/src/app.css`
- Test: `frontend/src/Answer.test.tsx`, `frontend/src/Chat.test.tsx`

**Interfaces:**
- Consumes (Task 4): `meta.low_relevance`, JSON `low_relevance`.
- Produces:
  - `AskResult.low_relevance?: boolean`; sự kiện `meta` trong `AskEvent` có `low_relevance?: boolean`.
  - `Answer` khi `result.low_relevance`:
    - hiện `Không tìm thấy đoạn nào đủ liên quan`;
    - có nút `Xem các đoạn gần nhất` (đóng mặc định, có `aria-expanded`), bấm thì mở thẻ nguồn;
    - không có câu trả lời, không có chip.
  - Áp cho cả hai chế độ.

- [ ] **Bước 1: Viết test (đỏ):**
  - `low relevance shows the notice and hides cards until expanded`;
  - `low relevance in external mode shows no answer and no "Đang viết câu trả lời…" after meta`;
  - `old turns without low_relevance render as before`.
- [ ] **Bước 2: Chạy cho thấy đỏ:** `npx vitest run src/Answer.test.tsx src/Chat.test.tsx`.
- [ ] **Bước 3: Hiện thực.** Sửa hàm chờ trong `Chat` để không còn hiện "Đang viết…" khi `low_relevance`. Style chỉ dùng token màu có sẵn.
- [ ] **Bước 4: Chạy cả bộ frontend, lint, build cho thấy xanh.**
- [ ] **Bước 5: Commit:** `feat(frontend): show low-relevance notice with expandable nearest passages`.

### Task 6: Bảng Word và Excel

**Files:**
- Modify: `backend/ingest.py`
- Test: `backend/tests/test_ingest.py`

**Interfaces:**
- Produces:
  - `_table_rows(table) -> list[tuple[int, str]]` trong `ingest.py`: số dòng và chữ của mỗi dòng bảng Word.
    - Dòng đầu là tiêu đề **chỉ khi** bảng có ≥ 2 dòng, ≥ 2 cột, mọi ô dòng đầu có chữ, không ô nào ở dòng đầu chỉ là số, và tên cột không trùng nhau.
    - Là tiêu đề thì mỗi dòng sau thành `Cột: giá trị; …` (bỏ ô trống). Không thì nối các ô bằng `; ` như cũ.
  - Đoạn bảng Word mang `section` của Heading chứa nó, và thêm `row` (số dòng trong bảng, dòng tiêu đề là 1). Đoạn văn thường giữ nguyên.
  - `read_xlsx`:
    - mở bằng `load_workbook(..., read_only=False, data_only=True)`, vì chế độ `read_only` không đọc được ô gộp;
    - giá trị ô gộp áp cho mọi ô nó phủ;
    - dòng tiêu đề đầu tiên có ô gộp ngang → ghép với dòng dưới thành `Nhóm – Cột`, và dữ liệu bắt đầu từ dòng thứ ba;
    - dòng dài hơn `ROW_MAX_CHARS = 1200` ký tự (ước cho giới hạn 512 token của e5; builder ghi cách ước vào báo cáo) thì cắt bằng `split` thành nhiều đoạn, mỗi đoạn giữ `sheet` và `row`.
  - Hằng số `INGEST_VERSION` trong `ingest.py`: bắt đầu `2`, tăng mỗi lần cách đọc/cắt đổi.

- [ ] **Bước 1: Viết test (đỏ)** trong `test_ingest.py`, file mẫu tạo ngay trong test như các test hiện có:
  - `test_docx_table_with_header_becomes_column_value`;
  - `test_docx_table_without_clear_header_keeps_old_format`: dòng đầu có ô số; và bảng 1 dòng;
  - `test_docx_table_keeps_section_and_row`;
  - `test_xlsx_merged_header_two_rows`;
  - `test_xlsx_merged_cell_in_data_repeats_value` (rủi ro 4);
  - `test_xlsx_empty_sheet_is_skipped` (rủi ro 4);
  - `test_xlsx_long_row_split_keeps_sheet_and_row`.
- [ ] **Bước 2: Chạy cho thấy đỏ:** `.venv/bin/pytest tests/test_ingest.py -q`.
- [ ] **Bước 3: Hiện thực** theo Interfaces.
- [ ] **Bước 4: Chạy cho thấy xanh**, rồi chạy cả bộ backend.
- [ ] **Bước 5: Đo** `eval.py --corpus` trước và sau, so riêng nhóm `bang`. Áp quy tắc giữ/bỏ cho từng phần (bảng Word, Excel) và ghi báo cáo mục **"3. Bảng Word và Excel"**.
- [ ] **Bước 6: Commit:** `feat(ingest): column-aware Word tables, merged Excel headers, long-row split`.

### Task 7: PDF hai cột và kích thước đoạn

**Files:**
- Modify: `backend/ingest.py`, `backend/eval.py`
- Test: `backend/tests/test_ingest.py`

**Interfaces:**
- Produces:
  - `ingest(path, file_type, *, chunk_size: int = CHUNK_SIZE, pdf_mode: str = PDF_MODE) -> list[Chunk]`; độ chồng lấn bằng `round(chunk_size * 0.2)`.
  - `read_pdf(path, *, chunk_size, mode)`: `mode` là `"plain"` (cách hiện tại) hoặc `"layout"` (`extract_text(extraction_mode="layout")`).
  - Hằng số `CHUNK_SIZE`, `PDF_MODE` do số đo quyết; trước khi đo là `500` và `"plain"`.
  - `eval.py` có thêm cờ `--chunk-size`, `--pdf-mode`.

- [ ] **Bước 1: Viết test (đỏ):**
  - `test_ingest_chunk_size_param`: đoạn dài cắt theo 300 thì nhiều đoạn hơn khi cắt theo 800;
  - `test_read_pdf_layout_mode_runs`: một PDF một trang tạo bằng `fpdf2` ra được chữ ở cả hai chế độ;
  - `test_ingest_defaults_unchanged`: không truyền tham số thì cho cùng kết quả như trước Task 7.
- [ ] **Bước 2: Chạy cho thấy đỏ:** `.venv/bin/pytest tests/test_ingest.py -q`.
- [ ] **Bước 3: Hiện thực** theo Interfaces.
- [ ] **Bước 4: Chạy cho thấy xanh**, rồi chạy cả bộ backend.
- [ ] **Bước 5: Đo.**
  - `--pdf-mode plain|layout`: so nhóm `hai-cot` và các câu nằm trong PDF một cột.
  - `--chunk-size 300|500|800`.
  - Đặt `PDF_MODE`, `CHUNK_SIZE` theo quy tắc giữ/bỏ. Có thay đổi thì tăng `INGEST_VERSION`.
  - Ghi báo cáo mục **"4. PDF hai cột"** (ghi rõ đây là bằng chứng yếu) và **"5. Kích thước đoạn"**.
- [ ] **Bước 6: Commit:** `feat(ingest): PDF extraction mode and chunk size chosen by measurement`.

### Task 8: Index lại tài liệu cũ theo cách đọc mới

**Files:**
- Modify: `backend/store.py`, `backend/worker.py`, `backend/app.py`
- Test: `backend/tests/test_store.py`, `backend/tests/test_worker.py`, `backend/tests/test_app.py`

**Interfaces:**
- Consumes (Task 6–7): `INGEST_VERSION`.
- Produces:
  - Bảng `documents` thêm cột `ingest_version INTEGER` và `reindex INTEGER NOT NULL DEFAULT 0`. `store.init` chạy `ALTER TABLE ... ADD COLUMN` khi `PRAGMA table_info` chưa có cột; không có câu `UPDATE`.
  - `store.create(..., reindex: bool = False)`. Worker ghi `ingest_version = INGEST_VERSION` khi index xong.
  - `Worker.reindex_outdated() -> int`:
    - với mỗi tài liệu `ready` có `ingest_version` NULL hoặc nhỏ hơn `INGEST_VERSION`, mà chưa có dòng `reindex` nào đang chờ cho nó:
      - chép file gốc từ `files/<thư mục>/<tên>` sang `files/.tmp/<id mới>`;
      - tạo dòng mới với `replaces_id = id cũ`, `reindex = 1`, `status = indexing`;
      - đưa vào hàng đợi index;
    - trả về số tài liệu đã đưa vào hàng đợi. Gọi sau `recover()` lúc khởi động.
  - Dòng `reindex = 1` lỗi khi index: **xoá dòng mới**, xoá các đoạn của nó, giữ nguyên bản cũ, ghi `logger.warning`; không đánh dấu tài liệu là lỗi.
  - `recover()`: dòng `indexing` có `reindex = 1` thì xoá, không đánh dấu lỗi. `reindex_outdated()` gọi ngay sau sẽ tạo lại.
  - `GET /api/documents` không trả các dòng `reindex = 1`.
  - Xoá tài liệu (`_delete`) cũng xoá luôn dòng `reindex` đang chờ của nó (`replaces_id = id bị xoá`). Khi job index của dòng đó chạy tới mà dòng không còn thì bỏ qua (như hiện nay với dòng không còn `status = indexing`).

- [ ] **Bước 1: Viết test (đỏ):**
  - `test_store_adds_columns_to_existing_db`: DB tạo theo schema cũ (không có hai cột) → sau `init` có đủ cột, dữ liệu cũ còn nguyên, `ingest_version` là NULL;
  - `test_reindex_outdated_swaps_in_new_chunks`: bản cũ vẫn tìm được trong lúc chờ; xong thì chỉ còn bản mới với `ingest_version = INGEST_VERSION`;
  - `test_reindex_failure_keeps_old_and_hides_error`: không có dòng lỗi nào, bản cũ còn;
  - `test_recover_drops_interrupted_reindex_rows`;
  - `test_current_version_docs_not_reindexed`;
  - `test_delete_during_pending_reindex_does_not_resurrect` (rủi ro 5): xoá bản cũ khi job reindex của nó đang chờ → chạy hết hàng đợi → không còn tài liệu nào tên đó;
  - `test_documents_listing_hides_reindex_rows`.
- [ ] **Bước 2: Chạy cho thấy đỏ:** `.venv/bin/pytest tests/test_store.py tests/test_worker.py tests/test_app.py -q`.
- [ ] **Bước 3: Hiện thực** theo Interfaces.
- [ ] **Bước 4: Chạy cả bộ backend cho thấy xanh.**
- [ ] **Bước 5: Commit:** `feat(worker): re-index documents ingested with an older reader version`.

### Task 9: Tài liệu và kiểm tay

**Files:**
- Modify: `docs/tinh-nang.md`, `docs/van-hanh.md`, `docs/lo-trinh.md`, `docs/bao-cao-chat-luong-tim-kiem.md`, `docs/2026-11-26-thiet-ke-chat-luong-tim-kiem.md` (dòng trạng thái)

- [ ] **Bước 1: Cập nhật tài liệu.**
  - `tinh-nang.md`: tách từ (cặp tiếng, không dấu), ngưỡng không liên quan và nút "Xem các đoạn gần nhất", cách đọc bảng/Excel mới, index lại tự động. Bỏ hoặc sửa các dòng giới hạn đã hết đúng ("Tìm từ khoá tách theo từng tiếng", "Không có ngưỡng").
  - `van-hanh.md`: biến `MIN_RELEVANCE`; cách chạy `eval.py --corpus` và các cờ; ghi rằng sau khi nâng cấp tài liệu cũ sẽ tự index lại.
  - `lo-trinh.md`: thêm dòng đã xong; ghi các đề xuất từ báo cáo (reranker, ưu tiên bản quy định mới…) vào "Tiếp theo".
  - Báo cáo: thêm mục **"Kết luận"**: cấu hình cuối, số đo cuối so với ban đầu.
- [ ] **Bước 2: Kiểm tay.** Chạy app với `data/` thật đang có:
  - thấy tài liệu cũ được index lại;
  - hỏi một câu không dấu ra đúng đoạn;
  - hỏi một câu lạc đề thấy thông báo "Không tìm thấy đoạn nào đủ liên quan".
- [ ] **Bước 3: Chạy lại cả hai bộ test**, đều xanh.
- [ ] **Bước 4: Commit:** `docs: search quality results and updated docs`.
