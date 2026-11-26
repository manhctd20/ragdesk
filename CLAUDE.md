# ragdesk

Hệ thống hỏi–đáp tài liệu nội bộ (RAG) cho team. **Đợt 1, 2A, đợt chất lượng tìm kiếm và đợt chấm lại đoạn (reranker) đã xong (trên `main`); 2C tạm dừng. Cách chạy xem `README.md`, lộ trình xem `docs/lo-trinh.md`.**

- Thiết kế đã duyệt: `docs/2026-11-20-thiet-ke.md`. Kế hoạch đã duyệt: `docs/2026-11-20-ke-hoach.md`. Việc ngoài các đợt đã duyệt thì hỏi người dùng trước.
- Bối cảnh và lý do các quyết định: `docs/2026-11-20-ban-giao-brainstorm.md`.
- Điều gì chưa có trong thiết kế/kế hoạch thì hỏi lại người dùng trước khi làm.
- Test backend: `cd backend && ANONYMIZED_TELEMETRY=False .venv/bin/pytest`. Test frontend: `cd frontend && npm test` (lint là `oxlint`).
- Đổi tìm kiếm, tách từ, cắt đoạn hay đọc file thì đo trước và sau: `cd backend && ANONYMIZED_TELEMETRY=False .venv/bin/python eval.py --corpus` (cờ và cách đọc số xem `docs/van-hanh.md`, số hiện tại xem `docs/bao-cao-chat-luong-tim-kiem.md`).
- Giao diện làm theo skill `/hallmark` (phạm vi app screen), hệ màu Console sáng + tối, font có dấu tiếng Việt, icon chứ không emoji. Bản phác ở `docs/mockups/theme-v2.html`.
