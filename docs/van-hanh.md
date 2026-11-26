# Vận hành

Cấu hình, chạy máy chủ, dữ liệu, sao lưu và đo chất lượng tìm kiếm. Cài đặt nhanh xem [README](../README.md).

## Yêu cầu

- **Python 3.12.**
- **Node ≥ 22.12** để chạy test frontend. Chỉ build thì Node ≥ 20.19 là đủ.
- **Internet ở lần chạy đầu:** `pip`, `npm`, và tải hai model (tìm kiếm và chấm lại) khoảng 1,1 GB từ Hugging Face. Sau đó tìm kiếm chạy offline, trừ chế độ AI ngoài và font Google Fonts.
- Không cần GPU. RAM: model chấm lại chiếm thêm khoảng 470 MB so với trước.

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
- **Lần đầu khởi động sẽ chậm** vì phải tải model. Tải model lỗi (ví dụ không có mạng) thì máy chủ dừng, không chạy tiếp.
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
| `MIN_RELEVANCE` | | `0.81` | Ngưỡng cosine "không liên quan": đoạn vector tốt nhất thấp hơn thì không gọi AI trả lời, giao diện hiện "Không tìm thấy đoạn nào đủ liên quan" (cách chọn: [báo cáo](bao-cao-chat-luong-tim-kiem.md), mục 2). Nâng lên thì chặn nhiều hơn nhưng dễ giấu nhầm câu có đáp án; hạ xuống thì ngược lại |
| `RERANK_MODEL` | | `BAAI/bge-reranker-v2-m3-int8` | Model chấm lại đoạn (tên model `TextCrossEncoder` của FastEmbed). Đặt `off` để tắt bước chấm lại: mỗi câu lại ra đủ 5 đoạn như trước, nhanh hơn khoảng 0,6 giây và không tốn RAM cho model này |
| `RERANK_MIN` | | `-5.0` | Đoạn có điểm chấm lại thấp hơn bị bỏ (cách chọn: [báo cáo](bao-cao-chat-luong-tim-kiem.md), mục 7). Mỗi model có thang điểm riêng: **đổi `RERANK_MODEL` thì phải đo lại ngưỡng này** bằng `eval.py --corpus --rerank-min <số>` |
| `FASTEMBED_CACHE_PATH` | | `/tmp/fastembed_cache` | Nơi lưu các model (tìm kiếm và chấm lại). Nên đặt ra ngoài `/tmp` |
| `ANONYMIZED_TELEMETRY` | | | Đặt `False` để Chroma không gửi telemetry |

Chỉ khai key mà thiếu tên model (hoặc ngược lại) thì nhà đó coi như chưa khai. Không có nhà nào khai đủ thì công tắc AI ngoài bị khoá dù `ALLOW_EXTERNAL=true`.

## Sau khi nâng cấp: tài liệu cũ tự index lại

Cách đọc file có số phiên bản (`INGEST_VERSION` trong `backend/ingest.py`, hiện là 3). Khởi động máy chủ sau khi nâng cấp mà đổi phiên bản thì tài liệu `Sẵn sàng` nhưng đọc bằng phiên bản cũ hơn sẽ tự được index lại từ file gốc trong `DATA_DIR/files/`, lần lượt từng file ở nền. Không cần làm gì.

- Trong lúc chờ, bản cũ vẫn tìm được; xong thì thay bằng bản mới.
- Index lại lỗi thì giữ bản cũ và ghi cảnh báo vào log (`re-index of doc ... failed`).
- Dòng log `queued N documents for re-index` cho biết có bao nhiêu file được xếp hàng. Nhiều file thì lần đầu sẽ chậm (CPU).
- **Ổ đĩa:** mỗi file được chép sang `DATA_DIR/files/.tmp/` trước khi index, nên cần chỗ trống xấp xỉ **tổng dung lượng các file đã lưu** (xong file nào thì file `.tmp` đó được thay vào chỗ cũ).
- **RAM:** index lại chạy cùng lúc với tìm kiếm, mỗi lần lại dựng lại chỉ mục BM25 trên cả kho đoạn. Cần RAM đủ cho model embedding cộng chỉ mục đó; file Excel lớn hơn 2 MB được đọc ở chế độ tiết kiệm RAM (không lặp giá trị ô gộp). Nếu máy chủ bị kill vì hết RAM thì lần khởi động sau sẽ xếp hàng lại đúng file đó, nên hãy tăng RAM hoặc bỏ file lớn ra trước.
- Ngày tải lên và ngày cập nhật của tài liệu được giữ nguyên qua lần index lại.

## Dữ liệu và sao lưu

Mọi thứ nằm trong `DATA_DIR`. Git bỏ qua thư mục này.

```
data/
  app.sqlite3          danh sách tài liệu, trạng thái
  chroma/              vector, chữ và metadata của các đoạn
  files/<thư mục>/     file gốc
  models/              model tìm kiếm và chấm lại (nếu đặt FASTEMBED_CACHE_PATH như trên)
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

Kết quả là tỉ lệ câu có đúng file nằm trong top 5, kèm danh sách câu trượt. Đây là số liệu dùng để quyết định có cần thêm reranker ở đợt sau không.

### Bộ mẫu `--corpus`

Bộ tài liệu giả (10 file, 44 câu hỏi) nằm ở `backend/eval_data/`, dựng lại bằng `make_corpus.py`. Chế độ này nạp bộ mẫu vào Chroma tạm (không đụng `DATA_DIR`) và in số đo theo nhóm câu: `vitri@5` (đúng file và đúng vị trí trong top 5), `MRR`, `file@1`, `file@5`, tỉ lệ câu không liên quan bị chặn (`bắt được`) và câu có đáp án bị chặn nhầm.

```bash
cd backend
ANONYMIZED_TELEMETRY=False .venv/bin/python eval.py --corpus [cờ]
```

| Cờ | Ý nghĩa |
|---|---|
| `--chunk-size N` | Đổi kích thước đoạn (mặc định 800) |
| `--pdf-mode plain\|layout` | Cách lấy chữ từ PDF (mặc định `plain`) |
| `--no-bigrams` | Tắt cặp tiếng khi tách từ |
| `--no-unaccent` | Tắt bản bỏ dấu khi tách từ |
| `--min-relevance X` | Đổi ngưỡng không liên quan, để thử |

Chạy không cờ cho số đo của cấu hình hiện tại; chạy lại sau mỗi thay đổi cách tách từ hay cách đọc file. Kết quả đã đo và cách chọn cấu hình: [báo cáo chất lượng tìm kiếm](bao-cao-chat-luong-tim-kiem.md). Dạng cũ `eval.py <file câu hỏi>.json` (đo trên `DATA_DIR` thật) vẫn dùng được và cũng nhận `--min-relevance`.
