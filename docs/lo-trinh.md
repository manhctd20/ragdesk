# Lộ trình

Mỗi đợt đều đi theo cùng một cách: bàn yêu cầu, viết thiết kế, người dùng duyệt, lập kế hoạch rồi mới code.

## Đã xong

| Đợt | Nội dung | Tài liệu |
|---|---|---|
| 1 | Nạp PDF, Word, Excel theo thư mục; tìm kiếm hybrid (vector + từ khoá); chế độ "Chỉ nội bộ" và "AI ngoài" (Gemini); lịch sử trên trình duyệt; giao diện sáng/tối, dùng được trên điện thoại | [thiết kế](2026-11-20-thiet-ke.md), [kế hoạch](2026-11-20-ke-hoach.md) |
| 2A | Thêm Claude và OpenAI, chọn nhà trên giao diện; hỏi nối tiếp; câu trả lời hiện dần (stream) | [thiết kế](2026-11-25-thiet-ke-dot-2a.md), [kế hoạch](2026-11-25-ke-hoach-dot-2a.md) |
| Chất lượng tìm kiếm | Bộ đo `eval.py --corpus` (tài liệu mẫu + 44 câu); tách từ có cặp tiếng và bỏ dấu (gõ không dấu vẫn ra); ngưỡng "không liên quan" 0,81 kèm nút "Xem các đoạn gần nhất"; đọc bảng Word thành `Cột: giá trị`, ô gộp và dòng dài trong Excel; đoạn 800 ký tự; tài liệu cũ tự index lại. Trên bộ mẫu: `vitri@5` 0,77 lên 0,97, MRR 0,73 lên 0,87 | [thiết kế](2026-11-26-thiet-ke-chat-luong-tim-kiem.md), [kế hoạch](2026-11-26-ke-hoach-chat-luong-tim-kiem.md), [báo cáo](bao-cao-chat-luong-tim-kiem.md) |

## Tạm dừng

- **2C. Đăng nhập theo người và phân quyền theo thư mục.**
  - Tạm dừng ngày 26/11/2026 vì hiện chưa có tài liệu nào cần giới hạn người đọc; cả team cùng được đọc mọi thứ sẽ nạp vào.
  - Đã chốt: tài khoản tạo ngay trong app, quyền theo nhóm, thư mục chưa gán nhóm thì chỉ quản trị xem được, thư mục "Chung" ai đăng nhập cũng xem được.
  - Làm tiếp khi có tài liệu chỉ một số người được đọc (lương, hợp đồng, hồ sơ nhân sự…). Bản nháp: [thiết kế 2C](2026-11-26-thiet-ke-dot-2c.md).
  - Muốn đưa lịch sử hỏi lên máy chủ (dùng được trên nhiều máy) thì phải làm 2C trước, vì máy chủ cần biết lịch sử đó của ai.

## Tiếp theo (chưa chốt thứ tự)

**Từ báo cáo chất lượng tìm kiếm** (xem [kết luận](bao-cao-chat-luong-tim-kiem.md#6-kết-luận))
- **Reranker:** ngưỡng chỉ bắt được 3/9 câu không liên quan (câu lạc đề hẳn). Câu cùng chủ đề công ty mà tài liệu không có vẫn lọt; cần cross-encoder chấm lại cặp câu hỏi và đoạn.
- **Đo lại ngưỡng 0,81 trên tài liệu thật** vì đặt từ dữ liệu giả; cần vài chục câu hỏi thật, cả câu có và không có đáp án.
- **Ưu tiên bản quy định mới** khi có hai bản cùng chủ đề (nghỉ phép 2023 và 2025): cần ngày hiệu lực của từng tài liệu trước.
- **Câu không dấu còn trượt** ("nghi phep nam bao nhieu ngay": đúng file, sai đoạn); xem lại cùng reranker.

**Đã có hướng làm**
- **B. OCR cho PDF scan,** thay cho việc báo lỗi như hiện nay. Chạy ngay trên máy chủ để tài liệu không rời mạng nội bộ; cần cài thêm Tesseract và index sẽ chậm hơn.

**Làm khi có số liệu hoặc phần cứng**
- **Tách từ ghép tiếng Việt** (ví dụ `underthesea`): cặp tiếng và bỏ dấu đã đủ trên bộ mẫu; chỉ làm khi `eval.py` với câu hỏi thật cho thấy còn chưa đủ tốt (xem [Vận hành](van-hanh.md#đo-chất-lượng-tìm-kiếm)).
- **LLM chạy ngay trên máy chủ:** cần máy có GPU. Khi đó chế độ nội bộ cũng có câu trả lời viết sẵn mà tài liệu không rời máy.

**Cần kiểm khi có key AI thật**
- Stream và dòng "Hiểu là" khi hỏi nối tiếp với từng nhà; model suy luận của OpenAI không trả về rỗng.

**Vận hành khi triển khai thật**
- HTTPS, chạy như dịch vụ hệ thống, sao lưu `DATA_DIR` định kỳ.
- Tự host font nếu máy người dùng không ra được internet.
