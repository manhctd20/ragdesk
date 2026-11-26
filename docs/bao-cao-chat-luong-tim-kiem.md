# Báo cáo chất lượng tìm kiếm

Thiết kế: `docs/2026-11-26-thiet-ke-chat-luong-tim-kiem.md`. Mỗi task đo thêm một mục bên dưới.

Quy tắc giữ/bỏ: điểm chính là `vitri@5` trên các câu có đáp án, `MRR` phân xử khi bằng nhau. Giữ khi điểm chính tăng ≥ 1 câu và không nhóm nào mất > 1 câu.

## 0. Số đo ban đầu

Mã chưa đổi gì ngoài `eval.py`. Bộ mẫu: 10 file, 3 thư mục, 44 câu (35 có đáp án, 9 không liên quan). Embedding thật (multilingual-e5-small), Chroma tạm.

Lệnh đã chạy:

```
cd backend && ANONYMIZED_TELEMETRY=False .venv/bin/python eval.py --corpus
```

| Nhóm | Số câu | file@1 | file@5 | vitri@5 | MRR | Bắt được |
|---|---|---|---|---|---|---|
| **tong** (có đáp án) | 35 | 0,89 | 0,91 | **0,77** (27/35) | 0,73 | - |
| dung-chu | 7 | 1,00 | 1,00 | 1,00 | 1,00 | - |
| dien-dat-khac | 9 | 1,00 | 1,00 | 1,00 | 0,91 | - |
| tu-ghep-viet-tat | 6 | 1,00 | 1,00 | 0,83 | 0,71 | - |
| khong-dau | 4 | 0,00 | 0,25 | 0,00 | 0,00 | - |
| bang | 6 | 1,00 | 1,00 | 0,50 | 0,50 | - |
| hai-cot | 3 | 1,00 | 1,00 | 1,00 | 1,00 | - |
| khong-lien-quan | 9 | - | - | - | - | 0,00 |

- Chặn nhầm: 0,00. Nhóm `khong-lien-quan` bắt được 0/9 vì hiện chưa có ngưỡng.
- Thời gian nạp cả bộ mẫu: 2,4 giây.
- Thời gian tìm mỗi câu: trung vị 0,009 giây, p95 0,012 giây (chưa gồm gọi AI trả lời).

### Nhận xét

- 8 câu trượt `vitri@5`, chia hai nguyên nhân:
  - 4 câu `khong-dau`: câu hỏi không dấu thì cả vector lẫn từ khoá đều lạc đề (file@5 chỉ 1/4).
  - 4 câu hỏi vào bảng Word (3 `bang` + 1 `tu-ghep-viet-tat`): đúng file nhưng sai chỗ, vì reader hiện tại chưa ghi `row` vào meta. Các câu này trượt là điều đã dự kiến.
- Bốn nhóm còn lại (`dung-chu`, `dien-dat-khac`, `hai-cot`, phần lớn `tu-ghep-viet-tat`) đã ổn.
- `hai-cot` đạt 1,00 nhưng PDF hai cột trong bộ mẫu là bằng chứng yếu: file tự sinh, chữ ghi hết cột trái rồi mới sang cột phải.

### 5 câu trượt tiêu biểu

| Nhóm | Câu hỏi | Cần | Nhận (top 1) |
|---|---|---|---|
| khong-dau | nghi phep nam bao nhieu ngay | quy-dinh-nghi-phep-2023/2025.docx, mục 1 | danh-muc-tai-san.xlsx |
| khong-dau | luong thu viec bang bao nhieu phan tram | noi-quy-lao-dong.docx, Điều 4 | danh-muc-tai-san.xlsx |
| khong-dau | tam ung toi da bao nhieu phan tram du toan | quy-trinh-thanh-toan.pdf, trang 3 | dinh-muc-cong-tac-phi.xlsx |
| bang | hệ số lương bậc 3 là bao nhiêu | quy-che-luong-thuong.docx, mục 2, dòng 4 | đúng file, sai chỗ (thiếu `row`) |
| tu-ghep-viet-tat | TP có được phụ cấp điện thoại không | quy-che-luong-thuong.docx, mục 3, dòng 4 | đúng file, sai chỗ (thiếu `row`) |

### Quyết định

Đây là mốc gốc, chưa có thay đổi nào để giữ hay bỏ. Các task sau so với `vitri@5` = 27/35, MRR = 0,73.

## 1. Tách từ

Thay đổi: `tokenize` thêm cặp tiếng liền nhau (`nghỉ_phép`) và bản bỏ dấu của mọi token (`nghi`, `nghi_phep`; `đ` thành `d`). Câu hỏi và chỉ mục BM25 dùng chung một cách tách (`Bm25Holder.tokenize`). `matched` vẫn là các tiếng có dấu nằm trong chữ của đoạn, không gồm cặp tiếng; gõ "nghi phep" vẫn tô đúng "nghỉ phép". Hai phần bật/tắt riêng được bằng `--no-bigrams` và `--no-unaccent`.

Lệnh đã chạy (bốn tổ hợp, cùng bộ mẫu như mục 0):

```
cd backend
ANONYMIZED_TELEMETRY=False .venv/bin/python eval.py --corpus
ANONYMIZED_TELEMETRY=False .venv/bin/python eval.py --corpus --no-bigrams
ANONYMIZED_TELEMETRY=False .venv/bin/python eval.py --corpus --no-unaccent
ANONYMIZED_TELEMETRY=False .venv/bin/python eval.py --corpus --no-bigrams --no-unaccent
```

### Tổng (35 câu có đáp án)

| Tổ hợp | vitri@5 | MRR | file@1 | file@5 |
|---|---|---|---|---|
| Trước (mục 0) = tắt cả hai | 0,77 (27/35) | 0,73 | 0,89 | 0,91 |
| Cặp tiếng + bỏ dấu (mặc định mới) | **0,86 (30/35)** | **0,77** | 0,94 | 1,00 |
| Chỉ bỏ dấu (`--no-bigrams`) | 0,86 (30/35) | 0,75 | 0,91 | 1,00 |
| Chỉ cặp tiếng (`--no-unaccent`) | 0,77 (27/35) | 0,73 | 0,89 | 0,91 |
| Tắt cả hai | 0,77 (27/35) | 0,73 | 0,89 | 0,91 |

Tắt cả hai cho đúng số của mục 0, nên cách tách cũ không bị đổi hành vi khi tắt cờ.

### Theo nhóm, vitri@5 (MRR trong ngoặc)

| Nhóm | Số câu | Trước | Cặp tiếng + bỏ dấu | Chỉ bỏ dấu | Chỉ cặp tiếng |
|---|---|---|---|---|---|
| dung-chu | 7 | 1,00 (1,00) | 1,00 (1,00) | 1,00 (1,00) | 1,00 (1,00) |
| dien-dat-khac | 9 | 1,00 (0,91) | 1,00 (0,91) | 1,00 (0,86) | 1,00 (0,91) |
| tu-ghep-viet-tat | 6 | 0,83 (0,71) | 0,83 (0,71) | 0,83 (0,71) | 0,83 (0,75) |
| khong-dau | 4 | 0,00 (0,00) | **0,75 (0,36)** | 0,75 (0,36) | 0,00 (0,00) |
| bang | 6 | 0,50 (0,50) | 0,50 (0,50) | 0,50 (0,50) | 0,50 (0,50) |
| hai-cot | 3 | 1,00 (1,00) | 1,00 (1,00) | 1,00 (1,00) | 1,00 (1,00) |

Thời gian nạp 2,0 đến 3,2 giây, tìm mỗi câu trung vị 0,013 đến 0,015 giây: không đổi đáng kể.

### Quyết định

**Giữ cả hai: `BIGRAMS = True`, `UNACCENT = True`.**

Lý do:
- Điểm chính tăng 3 câu (27 lên 30), không nhóm nào mất câu nào: qua quy tắc giữ/bỏ.
- Toàn bộ mức tăng đến từ bản bỏ dấu (nhóm `khong-dau` từ 0/4 lên 3/4). Cặp tiếng riêng lẻ không thêm câu nào trên bộ mẫu này (`--no-unaccent` bằng mốc gốc).
- Khi hai phần cùng bật và chỉ bỏ dấu bằng nhau ở 30/35, MRR phân xử: 0,77 so với 0,75, nên giữ cặp tiếng. Chênh lệch nhỏ (một câu `dien-dat-khac` lên hạng 1), nên đây là bằng chứng yếu cho cặp tiếng; chi phí chỉ là chỉ mục BM25 to hơn trong RAM.
- BM25 dựng lại trong RAM khi khởi động nên không cần index lại file đã nạp.

Còn trượt sau thay đổi (5 câu): 1 câu `khong-dau` ("nghi phep nam bao nhieu ngay": đúng hai file quy định nghỉ phép nhưng sai đoạn, hạng 1 đến 5 toàn đoạn khác mục 1), 4 câu hỏi vào bảng Word (thiếu `row`, chờ task đọc bảng). Câu `khong-dau` còn lại này cần xem lại sau khi có các thay đổi khác.

## 2. Câu không liên quan

Lệnh đã chạy (ngưỡng tạm `MIN_RELEVANCE = 0.0` để chỉ đo, rồi đặt ngưỡng và chạy lại):

```
cd backend
ANONYMIZED_TELEMETRY=False .venv/bin/python eval.py --corpus
ANONYMIZED_TELEMETRY=False .venv/bin/python eval.py --corpus --min-relevance 0.8313   # tham chiếu: ngưỡng tối đa
```

Độ giống (cosine) tính từ nhánh vector của Chroma: collection dùng không gian `l2` mặc định nên `distances` trả về là **L2 bình phương** `d2`; vector đã chuẩn hoá nên `cos = 1 - d2 / 2` (kiểm bằng thực nghiệm: vector trùng 0,0, vuông góc 2,0, lệch 45 độ 0,586). Giá trị lấy là cosine **cao nhất của cả nhánh vector** (top 20), không phụ thuộc đoạn đứng đầu sau khi trộn với BM25.

### Cosine cao nhất theo nhóm

| Nhóm | Số câu | Thấp nhất | Cao nhất |
|---|---|---|---|
| khong-dau | 4 | **0,8313** | 0,8467 |
| dien-dat-khac | 9 | 0,8498 | 0,9014 |
| tu-ghep-viet-tat | 6 | 0,8549 | 0,9264 |
| hai-cot | 3 | 0,8549 | 0,8948 |
| dung-chu | 7 | 0,8724 | 0,9135 |
| bang | 6 | 0,8725 | 0,9167 |
| **Câu có đáp án (35)** | 35 | **0,8313** | 0,9264 |
| **khong-lien-quan** | 9 | 0,7910 | 0,8942 |

### 9 câu không liên quan, xếp theo cosine

| Cosine | Câu | Chặn ở ngưỡng 0,81 |
|---|---|---|
| 0,7910 | thời tiết Hà Nội ngày mai thế nào? | có |
| 0,7923 | đội nào vô địch World Cup 2022? | có |
| 0,8054 | cách nấu phở bò ngon | có |
| 0,8130 | công ty có cho nuôi thú cưng không? | không |
| 0,8164 | giá vàng hôm nay bao nhiêu? | không |
| 0,8453 | công ty hỗ trợ học phí học ngoại ngữ bao nhiêu? | không |
| 0,8653 | công ty có cho nghỉ kết hôn hưởng nguyên lương không? | không |
| 0,8657 | làm thêm giờ vào ngày lễ được trả bao nhiêu phần trăm lương? | không |
| 0,8942 | nhân viên có được làm việc từ xa mấy ngày một tuần? | không |

### Chọn ngưỡng

- Mức cao nhất không chặn nhầm câu có đáp án nào: **khoảng 0,8312** (câu `khong-dau` "tam ung toi da bao nhieu phan tram du toan", 0,8313; ngưỡng 0,8313 đã chặn nhầm 1/35 câu).
- Trừ khoảng an toàn 0,02: 0,8112, **làm tròn xuống thành `MIN_RELEVANCE = 0.81`** (hằng số trong `backend/ask.py`, ghi đè bằng biến môi trường `MIN_RELEVANCE`).

| | Trước (ngưỡng 0,0) | Sau (ngưỡng 0,81) |
|---|---|---|
| `chan_nham` (câu có đáp án bị chặn) | 0,00 (0/35) | **0,00 (0/35)** |
| `bat_duoc` (câu không liên quan bị chặn) | 0,00 (0/9) | **0,33 (3/9)** |
| `vitri@5`, `MRR`, `file@5` | 0,86 / 0,77 / 1,00 | không đổi |

Để so sánh, ngưỡng tối đa 0,8313 bắt được 5/9 nhưng đã chặn nhầm 1 câu; không dùng vì vi phạm nguyên tắc "thà lọt còn hơn giấu".

### Quyết định

**Bật ngưỡng 0,81.** Theo quy tắc nó không chặn nhầm câu nào, nên giữ dù tỉ lệ bắt được thấp.

### Nhận xét

- **`bat_duoc` = 33%, dưới một nửa**: ngưỡng chỉ bắt được câu lạc đề hẳn (thời tiết, bóng đá, nấu ăn). Các câu cùng chủ đề công ty nhưng tài liệu không có (nghỉ kết hôn, làm thêm giờ ngày lễ, làm việc từ xa, học phí) có cosine 0,85 đến 0,89, nằm lẫn trong dải của câu có đáp án (0,83 đến 0,93). Một ngưỡng cosine không tách được hai loại này.
- **Đề xuất cho đợt sau: làm reranker** (cross-encoder chấm lại cặp câu hỏi và đoạn) để bắt được loại "gần chủ đề nhưng không có đáp án".
- Model `multilingual-e5-small` cho cosine dồn vào dải hẹp (0,79 đến 0,93), nên khoảng an toàn 0,02 chiếm phần đáng kể của dải. Bộ mẫu nhỏ (35 câu có đáp án, 9 câu không liên quan, dữ liệu giả); ngưỡng cần đo lại khi có dữ liệu thật.
