# Tính năng chi tiết

Mô tả đầy đủ những gì hệ thống đang làm được (đến đợt 2A và đợt nâng chất lượng tìm kiếm), các giới hạn và các lưu ý về riêng tư. Bản tóm tắt ở [README](../README.md).

## Làm được gì

**Nạp tài liệu** (trang Tài liệu, cần mật khẩu quản trị)
- Nhận `.pdf`, `.docx`, `.xlsx`, tối đa 20 MB mỗi file. Không nhận `.doc`, `.xls` đời cũ.
- Chọn hoặc kéo thả nhiều file một lần; file được gửi lần lượt. File sai đuôi hoặc quá cỡ bị báo riêng, các file còn lại vẫn gửi.
- Xếp tài liệu theo **một cấp thư mục**, có bộ lọc theo thư mục. Thư mục đang lọc nằm trên URL (`/tai-lieu?thu-muc=...`).
- Index chạy nền từng file một, có tiến độ `đoạn x/y`.
- **Tài liệu nạp bằng cách đọc file cũ sẽ tự index lại.** Mỗi tài liệu nhớ phiên bản cách đọc đã dùng; khi khởi động, máy chủ xếp hàng index lại từ file gốc những tài liệu có phiên bản cũ hơn bản hiện tại (hiện là 3). Bản cũ vẫn tìm được trong lúc chờ; index lại lỗi thì giữ bản cũ. Không cần tải lên lại.
- **Tải lên trùng tên trong cùng thư mục là thay file.** Bản cũ vẫn tìm được cho tới khi bản mới index xong. Bản mới lỗi thì giữ nguyên bản cũ.
- Báo lỗi rõ từng file: PDF chỉ có ảnh scan, PDF có mật khẩu, file hỏng, file không có chữ.
- Xoá có xác nhận ngay trong dòng. File đang index thì chưa xoá được.
- Máy chủ tắt giữa lúc index: lần khởi động sau, file đó chuyển sang lỗi "Bị gián đoạn khi index, hãy tải lên lại". Không để lại đoạn rác.

**Cách đọc file**
- PDF: theo trang, giữ số trang.
- Word: theo đoạn văn, giữ tiêu đề mục gần nhất (Heading 1–3). **Mỗi dòng của bảng là một đoạn riêng**, ghi kèm mục chứa bảng và số dòng. Nếu dòng đầu chắc chắn là tiêu đề cột thì các dòng sau đọc dạng `Cột: giá trị; Cột: giá trị` (bỏ ô trống); dòng tiêu đề vẫn được nạp thêm như một đoạn thường. Không chắc là tiêu đề thì nối các ô bằng `; `.
- Excel: mỗi sheet lấy dòng đầu có dữ liệu làm tên cột. **Mỗi dòng sau đó thành một đoạn** dạng `Cột A: giá trị; Cột B: giá trị`, kèm tên sheet và số dòng. Lấy giá trị đã tính, không lấy công thức. Ô gộp: giá trị được áp cho mọi ô nó phủ (file lớn hơn 2 MB thì bỏ qua bước này để tiết kiệm RAM). Dòng dài hơn 900 ký tự được cắt thành nhiều đoạn, mỗi đoạn giữ sheet và số dòng.
- PDF và chữ thường của Word được cắt thành đoạn khoảng 800 ký tự, chồng lấn khoảng 160.

**Tìm kiếm**
- Hybrid: tìm theo nghĩa bằng vector (`intfloat/multilingual-e5-small`, chạy CPU trên máy chủ) cộng tìm theo từ khoá (BM25). Hai kết quả được trộn bằng RRF, giữ **5 đoạn** tốt nhất.
- Tìm từ khoá tách theo từng tiếng, **thêm cặp tiếng liền nhau** (ví dụ `nghỉ_phép`) **và bản bỏ dấu** của mỗi tiếng. Nhờ đó gõ không dấu ("nghi phep nam bao nhieu ngay") vẫn ra đúng đoạn, và từ ghép tiếng Việt khớp tốt hơn. Từ được tô màu vẫn là các tiếng có dấu trong đoạn.
- **Ngưỡng "không liên quan":** nếu đoạn giống câu hỏi nhất (theo vector) có độ giống (cosine) dưới `0.81` thì không gọi AI trả lời. Giao diện hiện "Không tìm thấy đoạn nào đủ liên quan" và nút **Xem các đoạn gần nhất** để mở 5 đoạn tìm được, phòng khi ngưỡng chặn nhầm. Áp dụng cả hai chế độ. Chỉnh bằng biến `MIN_RELEVANCE` (xem [Vận hành](van-hanh.md)).
- Mỗi đoạn hiện tên file, vị trí (trang / mục / sheet + dòng), và tô màu các từ khớp với câu hỏi.

**Hai chế độ trả lời** (công tắc cạnh ô hỏi)
- **Chỉ nội bộ** (mặc định): chỉ trả các đoạn tìm được. Không gọi AI nào, tài liệu không rời máy chủ.
- **AI ngoài** (Claude, OpenAI hoặc Gemini): chỉ bật được khi quản trị cho phép. Người dùng bật cho từng câu hỏi, gửi xong thì công tắc tự về tắt.
  - Quản trị khai key nhà nào thì nhà đó dùng được. Từ 2 nhà trở lên, cạnh công tắc có danh sách chọn nhà (Claude, OpenAI, Gemini); nhà đã chọn được nhớ trên trình duyệt. Nhãn của câu trả lời ghi rõ nhà, ví dụ "AI ngoài (Claude)".
  - Gửi đi cho nhà đang chọn: câu hỏi, 5 đoạn tìm được, system prompt, và **câu hỏi cùng câu trả lời của các lượt AI ngoài trước đó trong cùng cuộc hỏi, chỉ những lượt đã hỏi chính nhà này** (lấy trong 3 lượt gần nhất). Không bao giờ gửi cả file hay tên thư mục. Lượt "Chỉ nội bộ" và lượt của nhà khác không bao giờ được gửi: máy chủ tự lọc, không tin giao diện.
  - Câu trả lời hiện dần (stream), là văn bản thuần, có số trích dẫn `[1]`… và thẻ nguồn.
  - Gọi AI lỗi thì vẫn hiện 5 đoạn, kèm một dòng báo lỗi. Lỗi giữa chừng thì giữ phần chữ đã nhận.

**Hỏi nối tiếp** (trong cùng một cuộc hỏi)
- Hỏi tiếp kiểu "thế ai duyệt?" sau "Nghỉ phép năm bao nhiêu ngày?" vẫn ra đúng. Mỗi lần hỏi, trình duyệt gửi kèm tối đa 3 lượt gần nhất.
- **AI ngoài:** nếu có lượt AI ngoài trước đó của cùng nhà, máy chủ nhờ AI viết lại câu hỏi thành câu đủ nghĩa ("Nghỉ phép năm ai duyệt?") rồi mới tìm. Dòng nhỏ "Hiểu là: …" dưới câu hỏi cho thấy AI đã hiểu gì (chỉ hiện khi câu viết lại khác câu gốc). Bước viết lại lỗi thì dùng nguyên câu gốc. Câu trả lời cuối chỉ nhận câu đã viết lại và 5 đoạn, không nhận lại lịch sử.
- **Chỉ nội bộ:** không gọi AI. Khi tìm, câu hỏi ngay trước được ghép vào trước câu hiện tại. Từ khoá được tô màu chỉ tính theo câu hiện tại.
- Công tắc vẫn tự về "Chỉ nội bộ" sau mỗi câu hỏi. Hỏi nối tiếp bằng AI ngoài thì bật lại công tắc cho câu đó; quên bật thì câu hỏi chạy ở chế độ nội bộ.

**Giao diện**
- Thanh bên có "Cuộc hỏi mới", lịch sử hỏi chia theo ngày (Hôm nay / Hôm qua / Tuần trước / Cũ hơn), mục Tài liệu và nút đổi sáng/tối.
- Lịch sử lưu trên trình duyệt của từng người. Mỗi cuộc hỏi có link riêng `/c/<id>`, nhưng chỉ mở được trên đúng trình duyệt đã hỏi.
- Dùng được trên điện thoại: dưới 60rem, thanh bên thu vào nút Menu.

## Giới hạn hiện tại

- **Không phân quyền.** Ai vào được mạng nội bộ cũng đọc được nội dung mọi tài liệu qua câu hỏi. Chỉ nạp tài liệu cả team được xem.
- **Mật khẩu quản trị dùng chung** và đi qua HTTP thường trong LAN. Nên đặt sau HTTPS khi triển khai thật.
- **PDF scan (chỉ có ảnh) không đọc được**, file báo lỗi. Chưa có OCR.
- **Ngưỡng "không liên quan" mới bắt được câu lạc đề hẳn** (thời tiết, bóng đá…). Câu cùng chủ đề công ty mà tài liệu không có (ví dụ hỏi về nghỉ kết hôn khi tài liệu không nói) vẫn ra 5 đoạn gần nhất, vì độ giống lẫn với câu có đáp án. Trên bộ mẫu bắt được 3/9 câu không liên quan, không chặn nhầm câu có đáp án nào. Ngưỡng đặt từ dữ liệu giả, cần đo lại trên tài liệu thật; muốn bắt được loại còn lại thì cần reranker (xem [Lộ trình](lo-trinh.md)).
- **Chưa biết bản quy định nào còn hiệu lực.** Có hai bản cùng chủ đề (ví dụ nghỉ phép 2023 và 2025) thì cả hai đều hiện, không ưu tiên bản mới.
- **Hỏi nối tiếp chỉ nhìn 3 lượt gần nhất,** mỗi câu hỏi tối đa 2.000 ký tự và mỗi câu trả lời tối đa 8.000 ký tự (dài hơn thì bị cắt khi gửi). Đổi nhà giữa cuộc hỏi thì nhà mới chỉ nhận câu hỏi hiện tại, vì không được xem lượt của nhà khác. Ở chế độ nội bộ, đổi chủ đề trong cùng cuộc hỏi có thể làm tìm lệch vì câu trước vẫn được ghép vào.
- **Chưa có nút "Dừng"** khi câu trả lời đang hiện dần. Mất kết nối giữa chừng thì lượt đó không được lưu, bấm "Thử lại".
- **Index chạy trên CPU,** file lớn sẽ chậm.
- **Cả ba nhà gọi qua cùng một client chuẩn OpenAI** (Claude và Gemini qua lớp tương thích của chính hãng). Lớp tương thích của Gemini đang beta, Google không cam kết giữ lâu dài.
- **Tên model do quản trị tự khai,** không chọn được trên giao diện.
- **Lịch sử chỉ nằm trên một trình duyệt,** không đồng bộ giữa các máy và chưa có nút xoá từng cuộc hỏi.

## Riêng tư

- **Lịch sử hỏi đáp nằm trong localStorage của trình duyệt** và chứa nguyên văn các đoạn tài liệu đã tìm được. Máy dùng chung thì nên xoá dữ liệu trình duyệt sau khi dùng.
- **Chế độ AI ngoài gửi nội dung ra bên ngoài.** Mỗi nhà chỉ nhận những gì đã được gửi cho chính nhà đó (câu hỏi, các đoạn liên quan, và các lượt AI ngoài trước đó của nhà đó). Nội dung lượt "Chỉ nội bộ" không bao giờ rời máy chủ.
- **Font Geist tải từ Google Fonts.** Mỗi lần mở trang, trình duyệt gửi request tới Google. Mạng LAN không ra internet thì giao diện dùng font hệ thống, vẫn đọc được. Google Fonts có subset tiếng Việt cho Geist và Geist Mono (đã kiểm ngày 25/11/2026).
