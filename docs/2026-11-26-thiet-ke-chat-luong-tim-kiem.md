# Thiết kế: đo và nâng chất lượng tìm kiếm

> **Trạng thái (26/11/2026):** người dùng đã duyệt. Kế hoạch: `docs/2026-11-26-ke-hoach-chat-luong-tim-kiem.md`.
> Nền: thiết kế đợt 1 `docs/2026-11-20-thiet-ke.md` (**TK1**) và đợt 2A `docs/2026-11-25-thiet-ke-dot-2a.md` (**TK2A**).
> Quy ước: **[Người dùng chốt]** là điều người dùng đã nói; **[Claude đề xuất]** là đề xuất của Claude, đã trình bày khi bàn và người dùng đồng ý hướng, vẫn sửa được khi duyệt.

## 1. Mục đích

Người dùng muốn phần lõi (đọc tài liệu, tìm, trả lời) chạy ổn và đáng tin **trước khi** mở rộng tính năng hay cho nhiều người dùng; OCR và đăng nhập để sau [Người dùng chốt]. Hệ thống chưa từng được đo với câu hỏi kiểu người thật. Đợt này làm hai việc, theo vòng **đo → sửa → đo lại → giữ thay đổi làm điểm tăng**:

1. Dựng **bộ đo** chạy lại được: tài liệu mẫu + câu hỏi + chương trình đo [Người dùng chốt: dùng bộ tài liệu mẫu tự dựng].
2. Sửa ba điểm yếu đã biết [Người dùng chốt: "cần fix cái này"]:
   - tìm từ khoá tách theo từng tiếng, kém với từ ghép tiếng Việt;
   - luôn trả 5 đoạn kể cả khi câu hỏi không liên quan;
   - cách cắt đoạn chưa kiểm với bảng Word, PDF hai cột, Excel nhiều cột.

## 2. Mục tiêu, không làm, không được xảy ra

**Mục tiêu:**
- Có số đo trước và sau cho từng thay đổi, ghi vào một báo cáo trong repo.
- Mỗi thay đổi chỉ được giữ nếu làm tăng điểm tổng mà không làm tụt rõ một nhóm câu hỏi nào (mục 4).
- Câu hỏi không liên quan được báo là không tìm thấy, thay vì trả bừa 5 đoạn.

**Không làm:**
- OCR, đăng nhập, phân quyền.
- Đổi model embedding, thêm reranker, thêm `underthesea`. Chỉ làm khi số đo sau đợt này cho thấy cách nhẹ không đủ; khi đó là một đợt riêng.
- Đo chất lượng câu trả lời của AI ngoài (cần key thật; đợt này chỉ đo phần tìm).
- Dùng tài liệu thật của team (để sau, khi người dùng bổ sung câu hỏi thật).

**Không được xảy ra:**
- Một thay đổi làm điểm tăng trên bộ mẫu nhưng phá hành vi đã có: test hiện tại phải vẫn xanh, trừ chỗ thiết kế này cố ý đổi.
- Ngưỡng "không liên quan" chặn mất câu hỏi đúng: thà để lọt một câu không liên quan còn hơn giấu kết quả của câu đúng (mục 6).
- Tài liệu đã nạp trước khi nâng cấp bị tìm theo cách cắt cũ mà không ai biết (mục 8).

## 3. Bộ tài liệu mẫu [Claude đề xuất]

Nội dung giả nhưng giống tài liệu thật của một công ty Việt Nam, tiếng Việt có dấu, khoảng 8–12 file, chia 3–4 thư mục. Phải chứa đủ các **ca khó**:

| Ca khó | File mẫu (ví dụ) |
|---|---|
| Word có nhiều bảng, bảng có dòng tiêu đề | quy chế lương thưởng: bảng hệ số theo cấp bậc, bảng phụ cấp |
| Word nhiều mục Heading lồng nhau, văn bản dài | nội quy lao động |
| PDF trình bày hai cột | bản tin nội bộ, thông báo chính sách |
| PDF một cột nhiều trang | quy trình thanh toán, quy trình mua hàng |
| Excel nhiều cột (≥ 8), có ô gộp, tiêu đề hai dòng | bảng định mức công tác phí, danh mục tài sản |
| Excel có ô văn bản dài | danh sách câu hỏi thường gặp |
| Nhiều từ ghép, từ viết tắt hay gặp | "nghỉ phép", "công tác phí", "BHXH", "TP" (trưởng phòng), "HĐLĐ" |
| Hai tài liệu nói về cùng chủ đề với số liệu khác nhau | quy định cũ và quy định mới về cùng một chế độ: `expect` ghi **cả hai** vị trí, chỉ đo việc tìm ra được; đợt này **không** làm ưu tiên bản mới hơn (cần thêm thông tin ngày hiệu lực, để đợt sau) [Claude đề xuất] |

- **Cách tạo:** một script sinh file (`python-docx`, `openpyxl`, `fpdf2` đã có trong `requirements-dev.txt`). Các file sinh ra **được commit vào repo**, để chạy đo không phụ thuộc font hay phiên bản thư viện trên máy khác. Script giữ lại để sinh lại khi cần (PDF cần một font TTF có dấu tiếng Việt, đường dẫn truyền vào).
- **Vị trí:** `backend/eval/corpus/<thư mục>/<file>`.

## 4. Bộ câu hỏi [Claude đề xuất]

Khoảng 40 câu, file JSON `backend/eval/questions.json`. Mỗi câu có:
- `question`;
- `expect`: danh sách vị trí đúng `{filename, page | section | sheet + row}`; câu có thể có nhiều vị trí đúng;
- `group`: nhóm để xem điểm riêng.

| Nhóm | Số câu | Ví dụ |
|---|---|---|
| `dung-chu`: dùng đúng chữ trong tài liệu | ~8 | "Hệ số lương bậc 3 là bao nhiêu?" |
| `dien-dat-khac`: diễn đạt khác chữ trong tài liệu | ~8 | "đi công tác Đà Nẵng được bao nhiêu tiền ăn?" |
| `tu-ghep-viet-tat`: từ ghép, viết tắt | ~6 | "HĐLĐ thử việc mấy tháng?" |
| `khong-dau`: gõ không dấu | ~4 | "nghi phep nam bao nhieu ngay" |
| `bang`: câu trả lời nằm trong bảng Word hoặc dòng Excel | ~6 | "phụ cấp ăn trưa của nhân viên kinh doanh" |
| `hai-cot`: câu trả lời nằm trong PDF hai cột | ~3 | |
| `khong-lien-quan`: không có trong tài liệu | ~10 | "công ty có cho nuôi thú cưng không?", "thời tiết Hà Nội mai thế nào?" |

Câu `khong-lien-quan` có `expect: []`. Một phần trong đó **gần chủ đề** của tài liệu (hỏi chế độ không có trong quy chế), để ngưỡng không chỉ chặn được câu lạc đề hoàn toàn.

## 5. Chương trình đo [Claude đề xuất]

Viết lại `backend/eval.py` (giữ cách chạy cũ với file câu hỏi của người dùng trên `DATA_DIR` thật, thêm chế độ chạy bộ mẫu). Chế độ dữ liệu thật nhận **cả định dạng cũ** `{question, filename, where}` (chỉ tính `file@1`, `file@5`, `MRR` theo file) **lẫn định dạng mới** có `expect` [Claude đề xuất]:

- **Chế độ bộ mẫu:** tự tạo một `DATA_DIR` tạm, nạp toàn bộ `backend/eval/corpus` qua đúng đường nạp thật (đọc file → cắt đoạn → embedding → Chroma → BM25), rồi chạy từng câu qua đúng hàm `search` mà `/api/ask` dùng. Không cần tắt máy chủ, không đụng `data/` thật.
- **Số đo**, tổng và theo từng nhóm:
  - `file@1`, `file@5`: đúng file ở vị trí 1 / trong top 5;
  - `vitri@5`: đúng vị trí (trang / mục / sheet + dòng) trong top 5;
  - `MRR`: trung bình 1/hạng của kết quả đúng đầu tiên;
  - với câu `khong-lien-quan`: tỉ lệ bị báo "không tìm thấy" (càng cao càng tốt);
  - với câu có đáp án: tỉ lệ bị chặn nhầm bởi ngưỡng (càng thấp càng tốt);
  - thời gian tìm mỗi câu (trung vị, p95) và thời gian nạp toàn bộ bộ mẫu.
- **So sánh cấu hình:** chạy được với tham số khác nhau (kích thước đoạn, bật/tắt cặp tiếng, ngưỡng) và in bảng so sánh, không phải sửa code.
- **In ra:** bảng tóm tắt và danh sách câu trượt (câu hỏi, cần gì, nhận được gì) để biết sửa chỗ nào.
- Chạy lâu (cần model thật) nên **không nằm trong bộ `pytest` mặc định**; đánh dấu `slow` như test embedding hiện có. Một test nhỏ kiểm phần tính điểm với dữ liệu giả thì chạy mặc định.

**Quy tắc giữ hay bỏ một thay đổi** [Claude đề xuất]:
- **Điểm chính** là `vitri@5` trên các câu **có đáp án** (không tính nhóm `khong-lien-quan`); `MRR` dùng để phân xử khi `vitri@5` bằng nhau.
- Giữ thay đổi khi điểm chính tăng **ít nhất 1 câu** và **không nhóm nào mất quá 1 câu** so với trước. Nhóm nhỏ (3–10 câu) nên một câu là nhiễu; quy tắc đếm theo câu, không theo phần trăm, để tránh bị nhiễu quyết định.
- Nhóm `khong-lien-quan` chỉ dùng để đặt ngưỡng (mục 6), không dùng để giữ hay bỏ các thay đổi khác.

**Báo cáo:** `docs/bao-cao-chat-luong-tim-kiem.md` ghi số đo trước khi sửa, sau từng thay đổi, và cấu hình được chọn cuối cùng kèm lý do.

## 6. Câu hỏi không liên quan [Claude đề xuất: cách a]

- Tính **độ giống (cosine) giữa câu hỏi và đoạn tốt nhất theo vector**. Chroma đang lưu vector đã chuẩn hoá, khoảng cách L2 đổi ra cosine được.
- Dưới **ngưỡng** thì coi là không tìm thấy:
  - **Chỉ nội bộ:** hiện "Không tìm thấy đoạn nào đủ liên quan", bên dưới có nút "Xem các đoạn gần nhất" để mở các đoạn yếu (đóng mặc định).
  - **AI ngoài:** **không gọi AI để trả lời**, hiện như chế độ nội bộ; không có đoạn tài liệu nào bị gửi đi cho câu hỏi đó. Riêng bước **viết lại câu hỏi nối tiếp** (TK2A mục 3) vẫn chạy trước khi tìm như hiện nay, vì phải viết lại xong mới biết tìm có ra không; bước này chỉ gửi câu hỏi và các lượt AI ngoài trước đó của cùng nhà, đúng như TK2A đã chốt [Claude đề xuất].
- **Đặt ngưỡng từ số đo:** chọn ngưỡng **cao nhất mà không chặn nhầm câu có đáp án nào** trong bộ mẫu, rồi **lùi xuống 0,02** (cosine) làm khoảng an toàn (theo mục 2: thà lọt còn hơn giấu) [Claude đề xuất]. Ghi giá trị và lý do vào báo cáo.
- **Ngưỡng bắt được ít câu không liên quan** (ví dụ chỉ bắt câu lạc đề hẳn, lọt câu gần chủ đề): vẫn bật, vì theo cách đặt ở trên nó không chặn nhầm câu đúng. Báo cáo ghi rõ tỉ lệ bắt được; nếu dưới một nửa thì ghi đề xuất làm reranker ở đợt sau [Claude đề xuất].
- Ngưỡng là hằng số trong code (có thể ghi đè bằng biến môi trường `MIN_RELEVANCE` để quản trị chỉnh mà không sửa code).
- Sự kiện `meta` (TK2A mục 5) thêm cờ cho biết kết quả dưới ngưỡng. Tên trường do builder đặt, nhưng `/api/ask` và `/api/ask/stream` phải giống nhau. Lịch sử cũ không có cờ này vẫn hiển thị như trước.

## 7. Tìm từ khoá: từ ghép và không dấu [Claude đề xuất: cách a]

Áp dụng cho **cả lúc dựng BM25 và lúc tách câu hỏi**:
- Giữ từng tiếng như hiện nay, thêm **cặp hai tiếng liền nhau**: "nghỉ phép năm" → `nghỉ`, `phép`, `năm`, `nghỉ_phép`, `phép_năm`.
- Thêm **bản bỏ dấu** của mỗi token (`nghi`, `phep`, `nghi_phep`…). Chữ "đ" bỏ dấu thành "d".
- Mỗi phần (cặp tiếng, bỏ dấu) bật/tắt được trong chương trình đo, để biết riêng từng phần giúp được bao nhiêu.
- **Tô màu từ khớp** (`matched`) vẫn hiển thị theo từ người dùng gõ. Khớp nhờ bản bỏ dấu (gõ "nghi phep", tài liệu có "nghỉ phép") thì vẫn tô đúng chữ "nghỉ phép" trong đoạn. Cách làm do builder chọn.
- BM25 dựng lại trong RAM khi khởi động, nên đổi cách tách từ **không cần index lại** file đã nạp.

## 8. Đọc file và cắt đoạn [Claude đề xuất]

- **Bảng trong Word:** dòng đầu của bảng làm tên cột; mỗi dòng sau thành một đoạn dạng `Cột A: giá trị; Cột B: giá trị`, giống Excel, kèm mục (Heading) chứa bảng. Chỉ coi dòng đầu là tiêu đề khi **chắc chắn** [Claude đề xuất]: bảng có ít nhất 2 dòng và 2 cột, mọi ô dòng đầu đều có chữ, không ô nào ở dòng đầu chỉ là số, và các tên cột không trùng nhau. Không thoả thì giữ cách cũ (nối các ô bằng `; `).
- **Excel:**
  - ô gộp: giá trị ô gộp áp cho mọi ô nó phủ;
  - tiêu đề hai dòng: chỉ áp khi dòng tiêu đề đầu tiên có **ô gộp ngang** phủ nhiều cột (dấu hiệu chắc chắn của tiêu đề nhóm); khi đó ghép thành tên cột `Nhóm – Cột`. Không có ô gộp thì giữ cách cũ: dòng đầu có dữ liệu là tiêu đề [Claude đề xuất];
  - dòng quá dài (vượt giới hạn 512 token của model embedding, ước bằng số ký tự) thì cắt thành nhiều đoạn, mỗi đoạn vẫn mang tên sheet và số dòng.
- **PDF hai cột:** người dùng không có PDF hai cột thật [Người dùng chốt], nên PDF mẫu tự tạo, ghi chữ theo thứ tự như Word và LibreOffice khi xuất PDF (hết cột trái rồi sang cột phải); báo cáo phải ghi rõ kết quả phần này là **bằng chứng yếu**. Đo cả cách đọc hiện tại và chế độ giữ bố cục của `pypdf`, chọn cách cho `vitri@5` cao hơn ở nhóm `hai-cot` mà không làm tụt PDF một cột. Cả hai đều tệ thì ghi vào báo cáo và để một đợt riêng (không thêm thư viện trong đợt này).
- **Kích thước đoạn:** đo 300, 500, 800 ký tự (chồng lấn giữ tỉ lệ khoảng 20%), chọn theo số đo.

**Tài liệu đã nạp trước khi nâng cấp:** cách cắt mới chỉ áp cho file nạp sau. Để không có hai kiểu cắt lẫn lộn, lưu một **số phiên bản cách đọc** cùng mỗi tài liệu. Khi khởi động, tài liệu nào mang phiên bản cũ thì worker tự index lại từ file gốc đã lưu trong `data/files/`, **theo đúng cách thay file đang có** (TK1 mục 3) [Claude đề xuất]: dựng đoạn mới bên cạnh, bản cũ vẫn tìm được trong lúc chờ; xong thì đổi sang bản mới; **lỗi thì giữ nguyên bản cũ** và ghi lỗi vào log, không đánh dấu tài liệu là lỗi; máy chủ tắt giữa chừng thì lần khởi động sau làm lại. Bảng `documents` thêm một cột bằng `ALTER TABLE` lúc khởi động (chỉ DDL). Dòng cũ có giá trị NULL ở cột mới được coi là phiên bản cũ, nên không cần câu UPDATE dữ liệu.

## 9. Cách làm đã cân nhắc

**Dữ liệu đo** [Người dùng chọn]: bộ mẫu tự dựng thay vì tài liệu thật. Không lộ tài liệu nội bộ và làm được ngay; đổi lại điểm có thể khác với tài liệu thật, nên sau này cần bổ sung câu hỏi thật.

**Tách từ** [Người dùng đồng ý cách a]:
- a. Cặp tiếng + bản bỏ dấu, không thêm thư viện. **Được chọn.**
- b. `underthesea`: tách từ đúng nghĩa hơn, nhưng thêm thư viện nặng và index chậm hơn. Chỉ làm nếu a không đủ.

**Không liên quan** [Người dùng đồng ý cách a]:
- a. Ngưỡng độ giống vector. **Được chọn.**
- b. Reranker chấm lại điểm: tin cậy hơn nhưng chậm trên CPU. Chỉ làm nếu a không tách được câu đúng với câu bừa.

**PDF hai cột:** đo cách hiện có trước, chưa thêm thư viện mới.

## 10. Kiểm thử

**Tự động (chạy mặc định):**
- Tách từ: cặp tiếng, bản bỏ dấu, "đ" → "d", chuỗi rỗng, một tiếng.
- Tô màu: gõ không dấu vẫn tô đúng chữ có dấu trong đoạn.
- Ngưỡng: dưới ngưỡng → cờ bật, không gọi AI ngoài (AI giả không bị gọi); trên ngưỡng → như cũ. `/api/ask` và `/api/ask/stream` cho cùng kết quả.
- Bảng Word có tiêu đề → đoạn dạng `Cột: giá trị`; bảng không tiêu đề → như cũ.
- Excel: ô gộp, tiêu đề hai dòng, dòng dài bị cắt vẫn giữ sheet và dòng.
- Phiên bản cách đọc: tài liệu phiên bản cũ được index lại khi khởi động; dòng NULL coi là cũ; tài liệu đang đúng phiên bản thì không bị động tới.
- Phần tính điểm của chương trình đo, với kết quả giả.

**Chạy tay (đánh dấu `slow`):** chạy bộ đo đầy đủ, cập nhật báo cáo.

**Giao diện:** câu dưới ngưỡng hiện thông báo và nút "Xem các đoạn gần nhất"; lịch sử cũ vẫn hiển thị.

## 11. Để builder tự quyết

- Nội dung chi tiết của từng file mẫu và từng câu hỏi, miễn đủ ca khó (mục 3) và đủ nhóm (mục 4).
- Định dạng in bảng so sánh của chương trình đo.
- Cách ước độ dài 512 token theo ký tự.
- Tên trường cờ "dưới ngưỡng" trong sự kiện `meta`, tên cột phiên bản cách đọc.
- Giá trị ngưỡng cụ thể và kích thước đoạn cuối cùng: do số đo quyết, ghi trong báo cáo.
