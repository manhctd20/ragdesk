# Phát triển

Dành cho người sửa code. Cách chạy máy chủ xem [Vận hành](van-hanh.md).

**Giao diện:** chạy backend như mục [Chạy](van-hanh.md#chạy) trong Vận hành, rồi:

```bash
cd frontend
npm run dev
```

Mở `http://localhost:5173`. Vite chuyển các request `/api` sang cổng 8000.

**Test và kiểm tra:**

```bash
cd backend && .venv/bin/pip install -r requirements-dev.txt
cd backend && ANONYMIZED_TELEMETRY=False .venv/bin/pytest
cd frontend && npm test
cd frontend && npm run lint
```

- Lint dùng `oxlint`.
- Test frontend chỉ giả lập `fetch`. Hợp đồng JSON giữa hai bên được kiểm ở test backend `tests/test_app.py`.

**Cấu trúc**

```
backend/
  app.py      FastAPI: route, mật khẩu quản trị, kiểm file tải lên, phục vụ frontend/dist
  ingest.py   đọc PDF / Word / Excel thành đoạn + metadata
  search.py   embedding, Chroma, BM25, RRF
  worker.py   luồng index nền (một file một lúc), thay file, khôi phục khi khởi động
  store.py    bảng documents (SQLite)
  llm.py      gọi Claude / OpenAI / Gemini qua client chuẩn OpenAI: stream câu trả lời, viết lại câu hỏi
  ask.py      luồng một lần hỏi: lọc lịch sử, viết lại câu, tìm, stream (sự kiện meta / delta / error / done)
  eval.py     đo chất lượng tìm kiếm
frontend/src/
  App.tsx, Sidebar.tsx, Chat.tsx, Answer.tsx, TaiLieu.tsx
  api.ts      gọi API + đọc SSE     history.ts  lịch sử + theme     format.ts  tô màu, trích dẫn
docs/         thiết kế, kế hoạch, bản phác giao diện
```

## Tài liệu thiết kế

- `docs/2026-11-20-ban-giao-brainstorm.md`: lý do của từng quyết định ở đợt 1.
- `docs/2026-11-20-thiet-ke.md`, `docs/2026-11-20-ke-hoach.md`: thiết kế và kế hoạch đợt 1.
- `docs/2026-11-25-thiet-ke-dot-2a.md`, `docs/2026-11-25-ke-hoach-dot-2a.md`: thiết kế và kế hoạch đợt 2A.
- `docs/2026-11-26-thiet-ke-dot-2c.md`: bản nháp đợt 2C, đang tạm dừng.
- `docs/mockups/`: bản phác giao diện.
