# Vận hành

Cấu hình, chạy máy chủ, dữ liệu, sao lưu và đo chất lượng tìm kiếm. Cài đặt nhanh xem [README](../README.md).

## Yêu cầu

- **Python 3.12.**
- **Node ≥ 22.12** để chạy test frontend. Chỉ build thì Node ≥ 20.19 là đủ.
- **Internet ở lần chạy đầu:** `pip`, `npm`, và tải model embedding khoảng 500 MB từ Hugging Face. Sau đó tìm kiếm chạy offline, trừ chế độ AI ngoài và font Google Fonts.
- Không cần GPU.

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

**Bật chế độ AI ngoài:** thêm `ALLOW_EXTERNAL=true` và khai key cùng tên model của ít nhất một nhà. **Tên model không có mặc định**, tự điền theo tên nhà đó đang cung cấp. Model suy luận của OpenAI (o-series, gpt-5…) dùng được.

```bash
ALLOW_EXTERNAL=true \
ANTHROPIC_API_KEY=<key> CLAUDE_MODEL=<tên model> \
OPENAI_API_KEY=<key> OPENAI_MODEL=<tên model> \
GEMINI_API_KEY=<key> GEMINI_MODEL=<tên model>
```

Khai một, hai hoặc cả ba nhà đều được. Thứ tự nhà luôn là Claude, OpenAI, Gemini; nhà đầu tiên đã khai là mặc định.

## Biến môi trường

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|
| `ADMIN_PASSWORD` | có | | Mật khẩu quản trị. Thiếu thì máy chủ không khởi động. **Chỉ dùng ký tự ASCII (không dấu)**: header HTTP không mang được chữ có dấu, và trang Tài liệu từ chối mật khẩu có dấu |
| `ALLOW_EXTERNAL` | | `false` | Công tắc tổng cho chế độ AI ngoài. Đặt `true` để bật (không phân biệt hoa thường) |
| `ANTHROPIC_API_KEY` + `CLAUDE_MODEL` | | | Khai đủ cả hai thì Claude dùng được (cần `ALLOW_EXTERNAL=true`). Tên model không có mặc định |
| `OPENAI_API_KEY` + `OPENAI_MODEL` | | | Như trên, cho OpenAI. Hỗ trợ cả model suy luận (o-series, gpt-5…) |
| `GEMINI_API_KEY` + `GEMINI_MODEL` | | | Như trên, cho Gemini |
| `DATA_DIR` | | `./data` | Nơi lưu file gốc, SQLite và index |
| `MAX_UPLOAD_MB` | | `20` | Cỡ tối đa mỗi file |
| `FASTEMBED_CACHE_PATH` | | `/tmp/fastembed_cache` | Nơi lưu model embedding. Nên đặt ra ngoài `/tmp` |
| `ANONYMIZED_TELEMETRY` | | | Đặt `False` để Chroma không gửi telemetry |

Chỉ khai key mà thiếu tên model (hoặc ngược lại) thì nhà đó coi như chưa khai. Không có nhà nào khai đủ thì công tắc AI ngoài bị khoá dù `ALLOW_EXTERNAL=true`.

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
