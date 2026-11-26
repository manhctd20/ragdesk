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
