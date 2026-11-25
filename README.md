# Tra cứu nội bộ

Hệ thống hỏi–đáp trên tài liệu nội bộ (RAG) cho team, chạy trong mạng LAN. Quản trị nạp file PDF, Word, Excel. Mọi người gõ câu hỏi bằng tiếng Việt hoặc tiếng Anh và nhận lại các đoạn tài liệu liên quan nhất, kèm vị trí trong file. Quản trị có thể cho phép thêm chế độ "AI ngoài": Gemini viết câu trả lời từ các đoạn đó, có trích dẫn nguồn.

Thiết kế chi tiết: `docs/2026-11-20-thiet-ke.md`. Lý do của từng quyết định: `docs/2026-11-20-ban-giao-brainstorm.md`.

## Làm được gì (đợt 1)

**Nạp tài liệu** (trang Tài liệu, cần mật khẩu quản trị)
- Nhận `.pdf`, `.docx`, `.xlsx`, tối đa 20 MB mỗi file. Không nhận `.doc`, `.xls` đời cũ.
- Chọn hoặc kéo thả nhiều file một lần; file được gửi lần lượt. File sai đuôi hoặc quá cỡ bị báo riêng, các file còn lại vẫn gửi.
- Xếp tài liệu theo **một cấp thư mục**, có bộ lọc theo thư mục. Thư mục đang lọc nằm trên URL (`/tai-lieu?thu-muc=...`).
- Index chạy nền từng file một, có tiến độ `đoạn x/y`.
- **Tải lên trùng tên trong cùng thư mục là thay file.** Bản cũ vẫn tìm được cho tới khi bản mới index xong. Bản mới lỗi thì giữ nguyên bản cũ.
- Báo lỗi rõ từng file: PDF chỉ có ảnh scan, PDF có mật khẩu, file hỏng, file không có chữ.
- Xoá có xác nhận ngay trong dòng. File đang index thì chưa xoá được.
- Máy chủ tắt giữa lúc index: lần khởi động sau, file đó chuyển sang lỗi "Bị gián đoạn khi index, hãy tải lên lại". Không để lại đoạn rác.

**Cách đọc file**
- PDF: theo trang, giữ số trang.
- Word: theo đoạn văn, giữ tiêu đề mục gần nhất (Heading 1–3). Bảng trong Word đọc từng dòng.
- Excel: mỗi sheet lấy dòng đầu có dữ liệu làm tên cột. **Mỗi dòng sau đó thành một đoạn** dạng `Cột A: giá trị; Cột B: giá trị`, kèm tên sheet và số dòng. Lấy giá trị đã tính, không lấy công thức.
- PDF và Word được cắt thành đoạn khoảng 500 ký tự, chồng lấn khoảng 100.

**Tìm kiếm**
- Hybrid: tìm theo nghĩa bằng vector (`intfloat/multilingual-e5-small`, chạy CPU trên máy chủ) cộng tìm theo từ khoá (BM25). Hai kết quả được trộn bằng RRF, giữ **5 đoạn** tốt nhất.
- Mỗi đoạn hiện tên file, vị trí (trang / mục / sheet + dòng), và tô màu các từ khớp với câu hỏi.

**Hai chế độ trả lời** (công tắc cạnh ô hỏi)
- **Chỉ nội bộ** (mặc định): chỉ trả các đoạn tìm được. Không gọi AI nào, tài liệu không rời máy chủ.
- **AI ngoài** (Gemini): chỉ bật được khi quản trị cho phép. Người dùng bật cho từng câu hỏi, gửi xong thì công tắc tự về tắt.
  - Gửi đi đúng ba thứ: câu hỏi, 5 đoạn tìm được, system prompt. Không bao giờ gửi cả file, tên thư mục hay lịch sử chat.
  - Câu trả lời là văn bản thuần, có số trích dẫn `[1]`… và thẻ nguồn.
  - Gọi Gemini lỗi thì vẫn hiện 5 đoạn, kèm một dòng báo lỗi.

**Giao diện**
- Thanh bên có "Cuộc hỏi mới", lịch sử hỏi chia theo ngày (Hôm nay / Hôm qua / Tuần trước / Cũ hơn), mục Tài liệu và nút đổi sáng/tối.
- Lịch sử lưu trên trình duyệt của từng người. Mỗi cuộc hỏi có link riêng `/c/<id>`, nhưng chỉ mở được trên đúng trình duyệt đã hỏi.
- Dùng được trên điện thoại: dưới 60rem, thanh bên thu vào nút Menu.

## Yêu cầu

- **Python 3.12.**
- **Node ≥ 22.12** để chạy test frontend. Chỉ build thì Node ≥ 20.19 là đủ.
- **Internet ở lần chạy đầu:** `pip`, `npm`, và tải model embedding khoảng 500 MB từ Hugging Face. Sau đó tìm kiếm chạy offline, trừ chế độ AI ngoài và font Google Fonts.
- Không cần GPU.

## Cài đặt

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

```bash
cd frontend
npm ci
npm run build
```

`npm run build` tạo `frontend/dist`. Backend phục vụ luôn thư mục này, nên chỉ cần một cổng, không cần Nginx.

## Chạy

Từ thư mục gốc của repo:

```bash
cd backend
DATA_DIR=../data \
ADMIN_PASSWORD=<mật khẩu không dấu> \
FASTEMBED_CACHE_PATH=../data/models \
ANONYMIZED_TELEMETRY=False \
  .venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
```

Mở `http://<địa chỉ máy chủ>:8000/`.

- `--host 0.0.0.0` cho cả mạng LAN vào được. Chỉ thử trên máy mình thì dùng `--host 127.0.0.1`.
- **Lần đầu khởi động sẽ chậm** vì phải tải model embedding.
- **Nên đặt `FASTEMBED_CACHE_PATH`.** Không đặt thì model nằm trong `/tmp/fastembed_cache` và mất sau mỗi lần khởi động lại máy, nên lần chạy sau lại phải tải lại.
- **`DATA_DIR` tính theo thư mục đang đứng.** Chạy từ `backend/` thì phải để `../data`. Để mặc định `./data` thì dữ liệu sẽ nằm trong `backend/data`.

**Bật chế độ AI ngoài:** thêm ba biến sau. Tên model không có mặc định, tự điền theo tên Google đang cung cấp.

```bash
ALLOW_EXTERNAL=true GEMINI_API_KEY=<key> GEMINI_MODEL=<tên model>
```

## Biến môi trường

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|
| `ADMIN_PASSWORD` | có | | Mật khẩu quản trị. Thiếu thì máy chủ không khởi động. **Chỉ dùng ký tự ASCII (không dấu)**: header HTTP không mang được chữ có dấu, và trang Tài liệu từ chối mật khẩu có dấu |
| `ALLOW_EXTERNAL` | | `false` | Công tắc tổng cho chế độ AI ngoài. Đặt `true` để bật (không phân biệt hoa thường) |
| `GEMINI_API_KEY` + `GEMINI_MODEL` | | | Khai đủ cả hai, cộng `ALLOW_EXTERNAL=true`, thì AI ngoài mới bật được |
| `DATA_DIR` | | `./data` | Nơi lưu file gốc, SQLite và index |
| `MAX_UPLOAD_MB` | | `20` | Cỡ tối đa mỗi file |
| `FASTEMBED_CACHE_PATH` | | `/tmp/fastembed_cache` | Nơi lưu model embedding. Nên đặt ra ngoài `/tmp` |
| `ANONYMIZED_TELEMETRY` | | | Đặt `False` để Chroma không gửi telemetry |

Đợt 1 chỉ hỗ trợ Gemini. Các biến của Claude và OpenAI (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`…) bị bỏ qua.

## Sử dụng

**Người hỏi**
1. Mở trang chủ, gõ câu hỏi, nhấn Enter để gửi. Shift+Enter để xuống dòng. Bộ gõ tiếng Việt không bị gửi nhầm khi đang gõ dấu.
2. Kết quả là các đoạn liên quan nhất, kèm tên file và vị trí. Mở file gốc để đọc thêm.
3. Muốn có câu trả lời viết sẵn thì bật công tắc "AI ngoài" trước khi gửi. Công tắc bị khoá kèm dòng giải thích nghĩa là quản trị chưa cho phép.
4. Lịch sử hỏi nằm ở thanh bên trái. Mỗi câu hỏi là độc lập: AI không nhớ câu trước.

**Quản trị**
1. Vào **Tài liệu**, bấm "Mở khoá quản trị", nhập `ADMIN_PASSWORD`. Trạng thái mở khoá giữ đến khi đóng tab hoặc bấm "Khoá lại".
2. Nhập tên thư mục (gợi ý từ các thư mục đã có), rồi chọn hoặc kéo thả file.
3. Chờ cột trạng thái chuyển từ "Đang index" sang "Sẵn sàng". Trang tự cập nhật mỗi 2 giây khi còn file đang index.
4. Muốn cập nhật một file thì tải lên bản mới **cùng tên, cùng thư mục**.
5. Xoá: bấm thùng rác ở dòng đó, rồi "Xoá file".

Ai cũng xem được danh sách tài liệu. Chỉ tải lên và xoá mới cần mật khẩu.

## Dữ liệu và sao lưu

Mọi thứ nằm trong `DATA_DIR`. Git bỏ qua thư mục này.

```
data/
  app.sqlite3          danh sách tài liệu, trạng thái
  chroma/              vector, chữ và metadata của các đoạn
  files/<thư mục>/     file gốc
  models/              model embedding (nếu đặt FASTEMBED_CACHE_PATH như trên)
```

**Sao lưu:** tắt máy chủ rồi chép cả `DATA_DIR`. Không chép lúc máy chủ đang chạy, vì dữ liệu có thể đang được ghi dở.

## Đo chất lượng tìm kiếm

Chuẩn bị khoảng 20 câu hỏi thật, mỗi câu ghi tên file chứa câu trả lời. Mẫu ở `backend/eval_questions.example.json`:

```json
[{"question": "Nghỉ phép năm được bao nhiêu ngày?", "filename": "Quy định nghỉ phép.pdf", "where": "trang 1"}]
```

**Tắt máy chủ trước**, vì hai tiến trình không dùng chung index Chroma được. Sau đó chạy:

```bash
cd backend
DATA_DIR=../data FASTEMBED_CACHE_PATH=../data/models ANONYMIZED_TELEMETRY=False \
  .venv/bin/python eval.py <file câu hỏi>.json
```

Kết quả là tỉ lệ câu có đúng file nằm trong top 5, kèm danh sách câu trượt. Đây là số liệu dùng để quyết định có cần thêm reranker hay tách từ tiếng Việt ở đợt sau không.

## Phát triển

**Giao diện:** chạy backend như mục Chạy, rồi:

```bash
cd frontend
npm run dev
```

Mở `http://localhost:5173`. Vite chuyển các request `/api` sang cổng 8000.

**Test và kiểm tra:**

```bash
cd backend && .venv/bin/pip install -r requirements-dev.txt
cd backend && ANONYMIZED_TELEMETRY=False .venv/bin/pytest
cd frontend && npm test
cd frontend && npm run lint
```

- Lint dùng `oxlint`.
- Test frontend chỉ giả lập `fetch`. Hợp đồng JSON giữa hai bên được kiểm ở test backend `tests/test_app.py`.

**Cấu trúc**

```
backend/
  app.py      FastAPI: route, mật khẩu quản trị, kiểm file tải lên, phục vụ frontend/dist
  ingest.py   đọc PDF / Word / Excel thành đoạn + metadata
  search.py   embedding, Chroma, BM25, RRF
  worker.py   luồng index nền (một file một lúc), thay file, khôi phục khi khởi động
  store.py    bảng documents (SQLite)
  llm.py      gọi Gemini qua client chuẩn OpenAI
  eval.py     đo chất lượng tìm kiếm
frontend/src/
  App.tsx, Sidebar.tsx, Chat.tsx, Answer.tsx, TaiLieu.tsx
  api.ts      gọi API     history.ts  lịch sử + theme     format.ts  tô màu, trích dẫn
docs/         thiết kế, kế hoạch, bản phác giao diện
```

## Giới hạn của đợt 1

- **Không phân quyền.** Ai vào được mạng nội bộ cũng đọc được nội dung mọi tài liệu qua câu hỏi. Chỉ nạp tài liệu cả team được xem.
- **Mật khẩu quản trị dùng chung** và đi qua HTTP thường trong LAN. Nên đặt sau HTTPS khi triển khai thật.
- **PDF scan (chỉ có ảnh) không đọc được**, file báo lỗi. Chưa có OCR.
- **Tìm từ khoá tách theo từng tiếng**, nên kém với từ ghép tiếng Việt. Phần tìm theo nghĩa bù lại phần lớn.
- **Không có ngưỡng "không liên quan":** đã có tài liệu thì luôn trả 5 đoạn, kể cả khi câu hỏi lạc đề.
- **Mỗi câu hỏi độc lập**, không hỏi nối tiếp được. Câu trả lời AI ngoài không stream: chờ xong mới hiện cả khối.
- **Index chạy trên CPU,** file lớn sẽ chậm.
- **Lớp tương thích OpenAI của Gemini đang beta,** Google không cam kết giữ lâu dài.
- **Lịch sử chỉ nằm trên một trình duyệt,** không đồng bộ giữa các máy và chưa có nút xoá từng cuộc hỏi.

## Riêng tư

- **Lịch sử hỏi đáp nằm trong localStorage của trình duyệt** và chứa nguyên văn các đoạn tài liệu đã tìm được. Máy dùng chung thì nên xoá dữ liệu trình duyệt sau khi dùng.
- **Font Geist tải từ Google Fonts.** Mỗi lần mở trang, trình duyệt gửi request tới Google. Mạng LAN không ra internet thì giao diện dùng font hệ thống, vẫn đọc được. Google Fonts có subset tiếng Việt cho Geist và Geist Mono (đã kiểm ngày 25/11/2026).

## Các đợt tiếp theo

Danh sách dưới đây gom từ những mục thiết kế đã ghi "để đợt sau". **Chưa chốt thứ tự**: mỗi đợt sẽ brainstorm và duyệt thiết kế trước khi code, như đợt 1.

**Đã có hướng làm trong thiết kế**
- **Thêm Claude và OpenAI cho chế độ AI ngoài.** Cùng một client chuẩn OpenAI, chỉ đổi `base_url`, key và tên model. Khi quản trị khai từ 2 nhà trở lên, công tắc cạnh ô hỏi có thêm danh sách chọn nhà.
- **Đăng nhập theo người và phân quyền theo thư mục.**
  - Thư mục đã được ghi vào metadata từng đoạn, nên lọc theo quyền không phải index lại.
  - Thay luôn mật khẩu quản trị dùng chung.
- **OCR cho PDF scan,** thay cho việc báo lỗi như hiện nay.
- **Hỏi nối tiếp có ngữ cảnh:** gửi kèm các lượt hỏi trước khi dùng AI ngoài.
- **Stream câu trả lời AI ngoài,** nếu thấy chờ lâu khó chịu.

**Làm khi có số liệu hoặc phần cứng**
- **Reranker và tách từ ghép tiếng Việt** (ví dụ `underthesea`): chỉ làm khi `eval.py` với câu hỏi thật cho thấy tìm kiếm chưa đủ tốt.
- **Ngưỡng "không liên quan":** cũng cần số liệu từ `eval.py` để đặt.
- **LLM chạy ngay trên máy chủ:** cần máy có GPU. Khi đó chế độ nội bộ cũng có câu trả lời viết sẵn mà tài liệu không rời máy.

**Vận hành khi triển khai thật**
- HTTPS, chạy như dịch vụ hệ thống, sao lưu `DATA_DIR` định kỳ.
- Tự host font nếu máy người dùng không ra được internet.
