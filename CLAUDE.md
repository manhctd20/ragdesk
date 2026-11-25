# tra-cuu-noi-bo

Hệ thống hỏi–đáp tài liệu nội bộ (RAG) cho team. **Đợt 1 đã xong (Task 0–14, trên `main`). Cách chạy xem `README.md`.**

- Thiết kế đã duyệt: `docs/2026-11-20-thiet-ke.md`. Kế hoạch đã duyệt: `docs/2026-11-20-ke-hoach.md`. Việc ngoài đợt 1 thì hỏi người dùng trước.
- Bối cảnh và lý do các quyết định: `docs/2026-11-20-ban-giao-brainstorm.md`.
- Điều gì chưa có trong thiết kế/kế hoạch thì hỏi lại người dùng trước khi làm.
- Test backend: `cd backend && ANONYMIZED_TELEMETRY=False .venv/bin/pytest`. Test frontend: `cd frontend && npm test` (lint là `oxlint`).
- Giao diện làm theo skill `/hallmark` (phạm vi app screen), hệ màu Console sáng + tối, font có dấu tiếng Việt, icon chứ không emoji. Bản phác ở `docs/mockups/theme-v2.html`.
