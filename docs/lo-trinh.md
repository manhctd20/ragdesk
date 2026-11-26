# Lộ trình

Mỗi đợt đều đi theo cùng một cách: bàn yêu cầu, viết thiết kế, người dùng duyệt, lập kế hoạch rồi mới code.

## Đã xong

| Đợt | Nội dung | Tài liệu |
|---|---|---|
| 1 | Nạp PDF, Word, Excel theo thư mục; tìm kiếm hybrid (vector + từ khoá); chế độ "Chỉ nội bộ" và "AI ngoài" (Gemini); lịch sử trên trình duyệt; giao diện sáng/tối, dùng được trên điện thoại | [thiết kế](2026-11-20-thiet-ke.md), [kế hoạch](2026-11-20-ke-hoach.md) |
| 2A | Thêm Claude và OpenAI, chọn nhà trên giao diện; hỏi nối tiếp; câu trả lời hiện dần (stream) | [thiết kế](2026-11-25-thiet-ke-dot-2a.md), [kế hoạch](2026-11-25-ke-hoach-dot-2a.md) |

## Tạm dừng

- **2C. Đăng nhập theo người và phân quyền theo thư mục.**
  - Tạm dừng ngày 26/11/2026 vì hiện chưa có tài liệu nào cần giới hạn người đọc; cả team cùng được đọc mọi thứ sẽ nạp vào.
  - Đã chốt: tài khoản tạo ngay trong app, quyền theo nhóm, thư mục chưa gán nhóm thì chỉ quản trị xem được, thư mục "Chung" ai đăng nhập cũng xem được.
  - Làm tiếp khi có tài liệu chỉ một số người được đọc (lương, hợp đồng, hồ sơ nhân sự…). Bản nháp: [thiết kế 2C](2026-11-26-thiet-ke-dot-2c.md).
  - Muốn đưa lịch sử hỏi lên máy chủ (dùng được trên nhiều máy) thì phải làm 2C trước, vì máy chủ cần biết lịch sử đó của ai.

## Tiếp theo (chưa chốt thứ tự)

**Đã có hướng làm**
- **B. OCR cho PDF scan,** thay cho việc báo lỗi như hiện nay. Chạy ngay trên máy chủ để tài liệu không rời mạng nội bộ; cần cài thêm Tesseract và index sẽ chậm hơn.

**Làm khi có số liệu hoặc phần cứng**
- **Reranker và tách từ ghép tiếng Việt** (ví dụ `underthesea`): chỉ làm khi `eval.py` với câu hỏi thật cho thấy tìm kiếm chưa đủ tốt (xem [Vận hành](van-hanh.md#đo-chất-lượng-tìm-kiếm)).
- **Ngưỡng "không liên quan":** cũng cần số liệu từ `eval.py` để đặt.
- **LLM chạy ngay trên máy chủ:** cần máy có GPU. Khi đó chế độ nội bộ cũng có câu trả lời viết sẵn mà tài liệu không rời máy.

**Cần kiểm khi có key AI thật**
- Stream và dòng "Hiểu là" khi hỏi nối tiếp với từng nhà; model suy luận của OpenAI không trả về rỗng.

**Vận hành khi triển khai thật**
- HTTPS, chạy như dịch vụ hệ thống, sao lưu `DATA_DIR` định kỳ.
- Tự host font nếu máy người dùng không ra được internet.
