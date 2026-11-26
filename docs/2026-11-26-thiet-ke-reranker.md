# Thiết kế: chấm lại đoạn tìm được (reranker)

Trạng thái: đã triển khai (kết quả: `bao-cao-chat-luong-tim-kiem.md`, mục 7). Ngày 26/11/2026.

## Vì sao làm

Hiện tại ragdesk luôn hiện đủ 5 đoạn tìm được, kể cả đoạn không trả lời được câu hỏi. Ngưỡng "không liên quan" (cosine 0,81) chỉ chặn được câu lạc đề hẳn: câu cùng chủ đề công ty mà tài liệu không có ("công ty có cho nghỉ kết hôn không?") vẫn ra 5 đoạn về nghỉ phép. Đã đo: cắt từng đoạn theo cosine không làm được, vì cosine chỉ đo "cùng chủ đề", không đo "trả lời được" (xem `bao-cao-chat-luong-tim-kiem.md`, mục 7).

Người dùng muốn: **chỉ hiện đoạn thật sự trả lời được; không có đoạn nào thì báo không tìm thấy.**

## Mục tiêu

- Chấm lại 5 đoạn tìm được bằng một model đọc cặp (câu hỏi, đoạn), xếp lại thứ tự và bỏ đoạn điểm thấp.
- Không đoạn nào qua ngưỡng thì xử lý như câu "không liên quan" hiện nay.
- Đổi model và tắt bước này được bằng biến môi trường, để sau này có máy GPU thì đổi model lớn hơn mà không sửa code.

**Không làm trong đợt này:** thêm dấu cho câu hỏi không dấu; dùng GPU; chấm lại nhiều hơn 5 đoạn; đổi giao diện.

**Không được xảy ra:** giấu mất đoạn đúng của câu có đáp án (thà để lọt còn hơn giấu, như ngưỡng 0,81).

## Số đo từ bản thử (bộ mẫu 44 câu, máy dev chỉ có CPU)

| | Hiện tại | Chấm lại 5 đoạn, `bge-reranker-v2-m3-int8`, ngưỡng -5 |
|---|---|---|
| Câu có đáp án còn tìm đúng | 34/35 | 34/35 |
| MRR | 0,86 | 0,90 |
| Câu không liên quan bị chặn | 3/9 | 7/9 |
| Số đoạn hiện trung bình (câu có đáp án) | 5 | khoảng 3,3 |
| Thời gian thêm mỗi câu | 0 | trung vị 0,6 giây, p95 1,5 giây |
| RAM thêm | 0 | khoảng 470 MB |
| Tải thêm lần đầu | 0 | 0,57 GB |

- Đoạn đúng có điểm thấp nhất (câu có dấu) là -4,15; ngưỡng -5 chừa khoảng an toàn 0,85.
- Câu gõ không dấu: model chấm đoạn đúng rất thấp (khoảng -9 đến -11), cắt theo điểm sẽ giấu đáp án. Vì thế câu không dấu **không cắt**.
- Còn lọt 2 câu ("làm thêm giờ ngày lễ", "làm việc từ xa"): tài liệu có đoạn rất sát chủ đề.

## Các cách đã cân nhắc

- **A. Chấm lại 5 đoạn bằng bản int8, cắt theo ngưỡng, câu không dấu giữ cách cũ.** ✅ Người dùng chọn.
- **B. Như A nhưng bản đầy đủ `bge-reranker-v2-m3`:** chặn thêm tối đa 1 câu, RAM gấp đôi (khoảng 1,1 GB), chậm hơn khoảng 30%. Loại; đổi được bằng biến môi trường nếu cần.
- **Chấm lại 20 đoạn:** 5–7 giây mỗi câu, không tìm thêm câu đúng nào. Loại.
- **Chỉ xếp lại, không cắt:** không giải quyết được điều người dùng muốn. Loại.
- **Model của Jina (đa ngôn ngữ):** giấy phép cấm dùng thương mại. Loại.

## Hành vi

Thứ tự trong một lượt hỏi (cả "Chỉ nội bộ" và "AI ngoài"):

1. Tìm như hiện nay (vector + BM25, RRF, 5 đoạn).
2. Cosine cao nhất dưới `MIN_RELEVANCE` → "không liên quan" như hiện nay, **không gọi reranker** (đỡ 0,6 giây cho câu lạc đề hẳn).
3. Câu hỏi không có dấu (bỏ dấu xong không đổi) → giữ nguyên 5 đoạn và thứ tự, không cắt.
4. Còn lại: chấm 5 đoạn, xếp theo điểm giảm dần, bỏ đoạn có điểm dưới `RERANK_MIN`.
   - Còn ít nhất 1 đoạn → hiện các đoạn đó (1–5 đoạn), AI ngoài chỉ nhận các đoạn đó.
   - Không còn đoạn nào → `low_relevance = true`, giao diện hiện "Không tìm thấy đoạn nào đủ liên quan" và nút "Xem các đoạn gần nhất" mở **5 đoạn ban đầu**, không gọi AI. Giống hệt ngưỡng cosine hiện nay.

Câu hỏi dùng để chấm là câu đã dùng để tìm (câu viết lại khi hỏi nối tiếp với AI ngoài).

## Cấu hình

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `RERANK_MODEL` | `BAAI/bge-reranker-v2-m3-int8` | Model FastEmbed `TextCrossEncoder`. `off` thì tắt bước chấm lại, hành vi như trước đợt này |
| `RERANK_MIN` | `-5.0` | Bỏ đoạn có điểm dưới mức này. Mỗi model có thang điểm riêng: **đổi model thì phải đo lại** bằng `eval.py --corpus` |

Model tải vào cùng chỗ với model vector (`FASTEMBED_CACHE_PATH`), nạp một lần khi khởi động máy chủ.

## Đo lường

- `eval.py --corpus` chạy cả bước chấm lại, dùng **chung một hàm** với luồng hỏi thật (như `is_low_relevance` hiện nay), để số đo khớp với app.
- Thêm cờ `--no-rerank`, `--rerank-min <số>`; báo cáo thêm số đoạn hiện trung bình và thời gian chấm lại.
- Báo cáo `bao-cao-chat-luong-tim-kiem.md` thêm mục 7: số đo cắt theo cosine (không làm được), số đo hai bản model, ngưỡng đã chọn.

## Tài liệu cần sửa

- `README.md`: dung lượng tải lần đầu (khoảng 1,1 GB), RAM, "trả về tối đa 5 đoạn".
- `docs/tinh-nang.md`: mục tìm kiếm, ngưỡng, giới hạn.
- `docs/van-hanh.md`: hai biến mới, cách đo lại ngưỡng khi đổi model, RAM.
- `docs/lo-trinh.md`: chuyển reranker sang "Đã xong"; thêm "thêm dấu cho câu hỏi không dấu" và "đo model lớn hơn khi có GPU".

## Phần để người làm tự quyết

- Chỗ đặt code (module mới hay trong `search.py`), cách truyền reranker vào `ask_events` và `create_app` (theo kiểu `embedder` đang được truyền vào để test không phải tải model).
- System prompt trong `llm.py` đang ghi cố định "[1]…[5]": sửa cho đúng số đoạn thực gửi.

**Quyết định của Claude (người dùng xem lại khi duyệt):**
- Nạp model reranker lỗi khi khởi động (ví dụ lần đầu không có mạng) thì máy chủ dừng hẳn, giống model vector hiện nay, thay vì chạy tiếp mà không chấm lại. Lý do: lỗi lộ ra ngay, không âm thầm kém đi.
- Câu tiếng Anh cũng không có dấu nên rơi vào nhánh "không cắt" (hành vi như trước). Chấp nhận vì không phân biệt chắc chắn được tiếng Anh với tiếng Việt không dấu; câu tiếng Anh vẫn được chặn bởi ngưỡng cosine như hiện nay.
- Đoạn bị cắt không hiện ở đâu cả khi vẫn còn đoạn khác qua ngưỡng (không thêm nút "xem đoạn bị cắt").
