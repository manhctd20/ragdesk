# Tra cứu nội bộ

Hệ thống hỏi–đáp tài liệu nội bộ (RAG) cho team. Quản trị nạp file PDF, Word, Excel; mọi người đặt câu hỏi và nhận về các đoạn liên quan nhất. Có thể bật thêm chế độ "AI ngoài" (Gemini) để tổng hợp câu trả lời từ các đoạn đó.

Thiết kế đầy đủ ở `docs/2026-11-20-thiet-ke.md`.

## Cài đặt

Cần Python 3.12 và Node 24.

**Backend**

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Frontend**

```bash
cd frontend
npm ci
npm run build
```

Backend phục vụ luôn thư mục `frontend/dist`, nên chỉ cần một cổng.

## Chạy

```bash
cd backend
DATA_DIR=../data ADMIN_PASSWORD=<mật khẩu> ANONYMIZED_TELEMETRY=False \
  .venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
```

Mở `http://<địa chỉ máy>:8000/`. Lần chạy đầu tải model embedding nên khởi động chậm.

Khi phát triển giao diện: chạy backend như trên, rồi `cd frontend && npm run dev` và mở `http://localhost:5173` (Vite chuyển `/api` sang cổng 8000).

## Biến môi trường

Đợt 1 chỉ hỗ trợ Gemini. Biến của Claude và OpenAI bị bỏ qua.

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|
| `ADMIN_PASSWORD` | có | | Mật khẩu quản trị. Thiếu thì máy chủ không khởi động. **Chỉ dùng ký tự ASCII (không dấu)**: header HTTP không mang được chữ có dấu, và trang Tài liệu từ chối mật khẩu có dấu |
| `ALLOW_EXTERNAL` | | `false` | Công tắc tổng cho chế độ AI ngoài |
| `GEMINI_API_KEY` + `GEMINI_MODEL` | | | Khai đủ cả hai thì AI ngoài mới bật. Tên model không có mặc định, tự điền |
| `DATA_DIR` | | `./data` | Nơi lưu file, SQLite và index |
| `MAX_UPLOAD_MB` | | `20` | Cỡ tối đa mỗi file |
| `ANONYMIZED_TELEMETRY` | | | Đặt `False` để tắt telemetry của Chroma |

## Dùng

- Trang chủ: gõ câu hỏi, Enter để gửi. Mặc định chỉ tìm nội bộ, tài liệu không rời máy chủ. Công tắc "AI ngoài" gửi câu hỏi cùng 5 đoạn liên quan tới Gemini và tự về tắt sau mỗi câu hỏi.
- Trang Tài liệu: ai cũng xem được danh sách. Tải lên và xoá cần "Mở khoá quản trị" bằng `ADMIN_PASSWORD`; mật khẩu chỉ giữ trong tab đang mở.
- Có thể chọn nhiều file một lần, file được gửi lần lượt.

## Sao lưu

Sao lưu cả thư mục `DATA_DIR` (mặc định `data/`). Tắt máy chủ khi chép để dữ liệu không bị ghi dở.

## Đo chất lượng tìm kiếm

```bash
cd backend
DATA_DIR=../data ANONYMIZED_TELEMETRY=False .venv/bin/python eval.py eval_questions.example.json
```

**Phải tắt máy chủ trước khi chạy** `eval.py`, vì hai tiến trình không dùng chung index Chroma được. Mẫu file câu hỏi ở `backend/eval_questions.example.json`.

## Test

```bash
cd backend && ANONYMIZED_TELEMETRY=False .venv/bin/pytest
cd frontend && npm test
```

## Giới hạn của đợt 1

- Ai vào được mạng nội bộ cũng đọc được mọi tài liệu qua câu hỏi. Chỉ nạp tài liệu cả team được xem.
- PDF scan (chỉ có ảnh) không đọc được, file báo lỗi. Chưa có OCR.
- BM25 tách từ theo khoảng trắng nên kém với từ ghép tiếng Việt; vector đa ngôn ngữ bù phần lớn.
- Mật khẩu quản trị dùng chung và đi qua HTTP thường trong LAN. Nên bật HTTPS khi triển khai thật.
- Index chạy trên CPU nên file lớn chậm; có hiện tiến độ theo đoạn.
- Mỗi câu hỏi độc lập, không gửi lịch sử chat; câu trả lời AI ngoài không stream và chỉ hiện dạng văn bản thuần.
- Lớp tương thích OpenAI của Gemini không cam kết lâu dài.

## Lưu ý về riêng tư và font

- **Lịch sử hỏi đáp nằm trong localStorage của trình duyệt** và chứa nguyên văn các đoạn tài liệu đã tìm được. Máy dùng chung nên xoá dữ liệu trình duyệt sau khi dùng.
- **Rủi ro font:** font Geist tải từ Google Fonts, nên trình duyệt phải ra được internet và mỗi lần mở trang sẽ có request tới Google. Mạng LAN kín thì giao diện rơi về font hệ thống. Đã kiểm ngày 25/11/2026: Google Fonts có subset `vietnamese` (khoảng `U+1EA0-1EF9`, phủ các chữ như ữ ặ ỡ) cho cả Geist (400, 500, 600) và Geist Mono (400, 500). Tham số `&subset=vietnamese` trong URL không có tác dụng với trình duyệt hiện đại; trình duyệt tự chọn đúng subset theo `unicode-range`.
