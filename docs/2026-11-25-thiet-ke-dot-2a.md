# Thiết kế đợt 2A: nâng cấp chế độ AI ngoài

> **Trạng thái (25/11/2026):** người dùng đã duyệt. Kế hoạch: `docs/2026-11-25-ke-hoach-dot-2a.md`.
> Nền: thiết kế đợt 1 `docs/2026-11-20-thiet-ke.md` (gọi tắt **TK1**). Đợt 2 gồm phần A (tài liệu này) rồi phần C (đăng nhập + phân quyền, thiết kế riêng sau). Phần B (OCR) để sau.
> Quy ước: **[Người dùng chốt]** là điều người dùng đã nói; **[Claude đề xuất]** là đề xuất của Claude, đã trình bày trong lúc bàn và người dùng không phản đối, vẫn sửa được khi duyệt tài liệu này.

## 1. Mục đích

Đợt 1 có chế độ AI ngoài nhưng mới ở mức tối thiểu: chỉ Gemini, mỗi câu hỏi độc lập, chờ xong mới hiện cả khối. Phần A làm chế độ này dùng được hằng ngày:

1. **Thêm Claude và OpenAI** bên cạnh Gemini. Quản trị khai key nhà nào thì nhà đó dùng được. [Người dùng chốt, từ đợt 1]
2. **Hỏi nối tiếp:** hỏi "thế ai duyệt?" sau "nghỉ phép năm bao nhiêu ngày?" vẫn ra đúng. [Người dùng chốt: cách 2, mục 3]
3. **Stream câu trả lời:** chữ hiện dần thay vì chờ cả khối. [Người dùng chốt hướng; cách làm là Claude đề xuất]

## 2. Mục tiêu, không làm, không được xảy ra

**Mục tiêu:** ba việc ở mục 1, chạy được với một, hai hoặc ba nhà cùng lúc.

**Không làm trong phần A:**
- Nút "Dừng" khi đang stream.
- Chọn model ngay trên giao diện (tên model vẫn do quản trị khai bằng biến môi trường, như TK1 mục 8).
- Hỏi nối tiếp bằng AI ở chế độ nội bộ.
- Lưu lịch sử lên máy chủ (lịch sử vẫn nằm trong localStorage; chuyện này thuộc phần C).

**Không được xảy ra (dù tính năng vẫn "chạy"):**
- Nội dung của một lượt **chỉ nội bộ** (câu trả lời, các đoạn tài liệu) bị gửi ra ngoài. Đây là lời hứa "Tài liệu không rời khỏi máy chủ" trên giao diện.
- Chế độ nội bộ gọi bất kỳ AI nào.
- Gọi AI ngoài khi quản trị chưa cho phép (máy chủ vẫn tự kiểm, không tin giao diện, như TK1 mục 4).

## 3. Hỏi nối tiếp [Người dùng chốt: cách 2]

Lịch sử nằm ở trình duyệt, nên mỗi lần hỏi trình duyệt gửi kèm **tối đa 3 lượt gần nhất** của cuộc hỏi đang mở [Claude đề xuất: 3 để prompt gọn và rẻ]. Mỗi lượt gồm `question`, `mode`, `provider` (chuỗi hoặc `null`) và `answer` (chuỗi hoặc `null`).

**Chế độ AI ngoài:**
1. Máy chủ **tự lọc** lịch sử, chỉ giữ các lượt `mode = "external"` có `answer` **và cùng `provider` với câu hỏi hiện tại** [Người dùng chốt: mỗi hãng chỉ thấy những gì đã gửi cho chính hãng đó]. Lượt nội bộ và lượt của nhà khác bị bỏ ở máy chủ, không phụ thuộc giao diện có lọc hay không. Đổi nhà giữa cuộc hỏi thì nhà mới chỉ nhận câu hỏi hiện tại.
2. Còn ít nhất một lượt AI ngoài → gọi AI **một lần không stream** để viết lại câu hỏi hiện tại thành câu đủ nghĩa ("thế ai duyệt?" → "Nghỉ phép năm ai duyệt?"). Không còn lượt nào → bỏ qua bước này, dùng nguyên câu hỏi.
3. Tìm 5 đoạn bằng câu đã viết lại.
4. Gọi AI lần hai (stream) để trả lời. Lần này **chỉ gửi câu đã viết lại + 5 đoạn**, không gửi lại lịch sử. [Claude đề xuất] Lý do: câu trả lời cũ có số trích dẫn `[1]…` trỏ tới bộ nguồn cũ, gửi lại dễ làm AI trích lẫn; ngữ cảnh đã nằm trong câu viết lại.
5. Giao diện hiện câu đã viết lại thành một dòng nhỏ dưới câu hỏi, ví dụ "Hiểu là: Nghỉ phép năm ai duyệt?", để người dùng thấy AI đã hiểu gì. [Claude đề xuất] Chỉ hiện khi câu viết lại khác câu gốc.
6. Bước viết lại lỗi (hết hạn mức, sai key…) → dùng nguyên câu hỏi gốc và đi tiếp, không báo lỗi riêng.

**Chế độ nội bộ:**
- Có lượt trước (bất kể chế độ) → khi tìm, ghép **câu hỏi** của lượt ngay trước vào trước câu hiện tại: `"<câu trước> <câu hiện tại>"`. Chỉ ghép câu hỏi người dùng đã gõ, không ghép câu trả lời. Không gọi AI, không gửi gì ra ngoài.
- Tô màu từ khớp (`matched`) chỉ tính theo **câu hiện tại**, để không tô những từ của câu trước.
- Không hiện dòng "Hiểu là".

**Công tắc vẫn tự về "Chỉ nội bộ" sau mỗi câu hỏi** [Người dùng chốt từ đợt 1: "người dùng tự bật cho từng câu hỏi, mặc định tắt"]. Hỏi nối tiếp bằng AI ngoài thì phải bật lại công tắc cho câu đó; quên bật thì câu hỏi chạy ở chế độ nội bộ (vẫn có ghép câu trước khi tìm), không có gì bị gửi đi.

**Thay đổi so với TK1:** TK1 mục 4 và 12.2 ghi "không bao giờ gửi lịch sử chat". Nay đổi thành: **ở chế độ AI ngoài, gửi thêm câu hỏi và câu trả lời của các lượt AI ngoài trước đó trong cùng cuộc hỏi, cùng một nhà** (lấy trong 3 lượt gần nhất; đều là những thứ đã từng được gửi cho chính nhà đó). Lượt nội bộ vẫn không bao giờ rời máy chủ. Phải sửa theo:
- README, mục "Gửi đi đúng ba thứ".
- Dòng gợi ý và toast khi bật AI ngoài trên giao diện, đổi từ "Câu hỏi và các đoạn liên quan sẽ gửi tới AI ngoài" thành **"Câu hỏi, các đoạn liên quan và các lượt AI ngoài trước đó sẽ gửi tới AI ngoài"**. [Claude đề xuất câu chữ]

## 4. Thêm Claude và OpenAI [Người dùng chốt, theo TK1 mục 8]

Giữ cách của TK1: một client `openai` SDK, mỗi nhà đổi `base_url`, key, tên model.

| Nhà | Biến môi trường | `base_url` |
|---|---|---|
| `claude` | `ANTHROPIC_API_KEY` + `CLAUDE_MODEL` | `https://api.anthropic.com/v1/` |
| `openai` | `OPENAI_API_KEY` + `OPENAI_MODEL` | mặc định của SDK |
| `gemini` | `GEMINI_API_KEY` + `GEMINI_MODEL` | `https://generativelanguage.googleapis.com/v1beta/openai/` (như hiện tại) |

- Khai đủ cả key và tên model thì nhà đó bật. `GET /api/config` trả `providers` theo thứ tự cố định `claude, openai, gemini`.
- Ràng buộc từ TK1: không gửi `temperature` / `top_p`.
- Giới hạn độ dài câu trả lời: Claude và Gemini dùng `max_tokens`; OpenAI dùng `max_completion_tokens`, vì các model suy luận của OpenAI (họ o-series, gpt-5) từ chối `max_tokens` và tính cả phần suy luận ẩn vào giới hạn. Đặt giới hạn đủ rộng (khoảng 4.000) để model suy luận không trả về rỗng. [Claude đề xuất] Builder kiểm lại tên tham số theo tài liệu chính thức của từng nhà, đúng bản SDK đang pin.
- **Builder phải kiểm** bằng tài liệu chính thức (theo CLAUDE.md của người dùng) rằng lớp tương thích OpenAI của Anthropic và Gemini hỗ trợ `stream=True`. Nếu một nhà không hỗ trợ stream, nhà đó trả cả khối như một sự kiện chữ duy nhất, giao diện vẫn chạy được.

**Giao diện chọn nhà** [đã thiết kế ở TK1, chi tiết là Claude đề xuất]:
- 0 nhà hoặc quản trị tắt `ALLOW_EXTERNAL`: như hiện tại (công tắc khoá, bấm hiện toast).
- 1 nhà: không có danh sách, như hiện tại.
- Từ 2 nhà: cạnh công tắc có `<select>` gốc của trình duyệt liệt kê các nhà, chỉ bật được khi công tắc đang ở AI ngoài. Tên hiển thị: "Claude", "OpenAI", "Gemini".
- Nhà đã chọn được nhớ trong localStorage (`tcnb:provider`) cho lần sau; nhà đó không còn trong `providers` thì quay về nhà đầu tiên.
- Mỗi lượt lưu thêm `provider` đã dùng; nhãn chế độ của lượt AI ngoài ghi rõ nhà, ví dụ "AI ngoài (Claude): câu trả lời tổng hợp từ các đoạn".

```
[ 🔓 AI ngoài ] [ Claude ▾ ]   Câu hỏi và các đoạn liên quan sẽ gửi tới AI ngoài   (↑)
```

## 5. Stream câu trả lời [Claude đề xuất]

**Máy chủ:**
- Endpoint mới `POST /api/ask/stream`, cùng body với `/api/ask`, trả `text/event-stream` (SSE).
- Giữ `POST /api/ask` trả JSON như hiện tại (thêm trường mới ở mục 6) cho test và cho ai gọi thẳng API. Hai endpoint dùng chung một hàm lõi sinh ra các sự kiện; `/api/ask` gom các sự kiện lại thành JSON. Không viết hai luồng logic.
- Các sự kiện, theo thứ tự:
  1. `meta`: `{sources, query, message}`, gửi ngay sau khi tìm xong. `query` là câu đã viết lại (hoặc `null` nếu không viết lại); `message` như hiện tại ("Chưa có tài liệu nào").
  2. `delta`: `{text}`, lặp lại, chỉ ở chế độ AI ngoài.
  3. `error`: `{llm_error}`, khi gọi AI lỗi (trước hoặc giữa chừng). Giữ nguyên phần chữ đã gửi.
  4. `done`: `{}`, luôn là sự kiện cuối.
- Lỗi trước khi bắt đầu stream (403 chưa cho phép, 422 body sai) vẫn trả mã HTTP thường kèm `{"detail": ...}`, để giao diện xử lý như hiện tại.

**Giao diện:**
- Trình duyệt đọc stream bằng `fetch` + `ReadableStream` (không dùng `EventSource` vì nó chỉ hỗ trợ GET).
- Dùng stream cho **cả hai chế độ**; chế độ nội bộ chỉ nhận `meta` rồi `done`.
- Nhận `meta` → hiện ngay thẻ nguồn (chế độ nội bộ) hoặc các chip nguồn và dòng "Hiểu là" (AI ngoài). Nhận `delta` → nối chữ vào câu trả lời, vẫn chỉ render text node, không render HTML (TK1, bảo mật 1). Trong lúc chưa có chữ nào vẫn hiện "Đang viết câu trả lời…".
- Số trích dẫn `[n]` chỉ tách thành nhãn khi đã có đủ dấu `]`; trong lúc stream, chữ dở dang hiện nguyên văn.
- Chỉ lưu lượt vào lịch sử khi nhận `done`. Mất kết nối giữa chừng → coi như lỗi mạng như hiện tại (nút "Thử lại"), không lưu lượt dở.
- Có `error` giữa chừng → giữ phần chữ đã có, thêm dòng báo lỗi bên dưới, rồi lưu lượt như bình thường.

## 6. Dữ liệu và API thay đổi

**`POST /api/ask` và `POST /api/ask/stream`, body:**

```json
{
  "question": "thế ai duyệt?",
  "mode": "external",
  "provider": "claude",
  "history": [
    {"question": "Nghỉ phép năm bao nhiêu ngày?", "mode": "external", "provider": "claude", "answer": "12 ngày mỗi năm [1]."}
  ]
}
```

- `history` không bắt buộc, mặc định `[]`. Máy chủ từ chối (422) khi có quá 3 lượt, một câu hỏi quá 2.000 ký tự, hoặc một câu trả lời quá 8.000 ký tự. [Claude đề xuất các giới hạn] Đây là dữ liệu đi từ trình duyệt, phải kiểm ở máy chủ.
- `provider` không gửi → dùng nhà đầu tiên trong `providers`, như hiện tại.

**Kết quả `/api/ask` (JSON)** thêm `query` (chuỗi hoặc `null`) và `provider` (chuỗi hoặc `null`), bên cạnh `answer, sources, llm_error, message`.

**Lịch sử trong localStorage:** mỗi `Turn` thêm `provider?` và `result.query?`. Lịch sử cũ thiếu hai trường này vẫn đọc và hiển thị được.

## 7. Cách làm đã cân nhắc

**Hỏi nối tiếp** [Người dùng chọn cách 2]:
1. Chỉ AI ngoài, chỉ gửi lại các lượt AI ngoài; nội bộ vẫn độc lập. Giữ lời hứa riêng tư, đơn giản nhất. (Claude đề xuất ban đầu.)
2. **Như cách 1, thêm ghép câu hỏi trước khi tìm ở chế độ nội bộ.** Không gửi gì ra ngoài; đổi lại có thể tìm lệch khi người dùng đổi chủ đề trong cùng cuộc hỏi. **Được chọn.**
3. Gửi toàn bộ lịch sử kể cả lượt nội bộ. Hiểu ngữ cảnh tốt nhất nhưng phá lời hứa riêng tư. Loại.

Lượt AI ngoài của nhà khác: **chỉ gửi lượt cùng nhà** [Người dùng chọn] thay vì gửi mọi lượt AI ngoài, để nội dung đã gửi cho hãng này không lọt sang hãng khác; đổi lại, đổi nhà giữa cuộc hỏi thì mất ngữ cảnh.

**Gọi nhiều nhà:**
- **Một client chuẩn OpenAI, đổi `base_url`.** Code một chỗ, đã có từ đợt 1. **Được chọn** (theo TK1).
- SDK riêng từng hãng: gấp ba code; chỉ dùng nếu lớp tương thích của một hãng gây lỗi (TK1 đã ghi hướng thay riêng nhánh đó).

**Stream:**
- **SSE qua `fetch`.** Một chiều máy chủ → trình duyệt, đúng nhu cầu, FastAPI làm được bằng `StreamingResponse`. **Được chọn.**
- WebSocket: hai chiều, nặng hơn mức cần.
- Không stream, giữ chờ cả khối: đúng là đơn giản nhưng không đạt mục tiêu 3.

## 8. Kiểm thử

**Tự động (AI luôn là hàm giả, không gọi mạng):**
- Lọc lịch sử: lượt nội bộ không bao giờ xuất hiện trong bất kỳ lời gọi AI nào, kể cả khi trình duyệt gửi lên. Đây là test âm quan trọng nhất của phần A.
- Lọc theo nhà: lượt AI ngoài của nhà A không bao giờ xuất hiện trong lời gọi tới nhà B (test âm).
- Viết lại câu hỏi: có lượt AI ngoài thì gọi bước viết lại và tìm bằng câu đã viết lại; không có thì không gọi; bước viết lại lỗi thì dùng câu gốc.
- Chế độ nội bộ: truy vấn tìm có ghép câu hỏi trước; `matched` chỉ gồm từ của câu hiện tại; không có lời gọi AI nào.
- Chọn nhà: `providers` đúng theo biến môi trường; `provider` không bật → 403; mỗi nhà dùng đúng `base_url`.
- Stream: thứ tự `meta → delta… → done`; lỗi giữa chừng ra `error` rồi `done`; `/api/ask` gom đúng thành JSON.
- Giới hạn `history` → 422.
- Giao diện: chữ hiện dần; chỉ lưu khi `done`; mất kết nối giữa chừng không lưu và có "Thử lại"; danh sách chọn nhà chỉ hiện khi có từ 2 nhà; lịch sử cũ thiếu trường mới vẫn hiển thị.
- Test `Chat.test.tsx` "body đúng bằng `{question, mode}`" phải đổi theo mục 3 (body giờ có `history` và có thể có `provider`). Giữ ý chính: mỗi lượt trong `history` chỉ có `question`, `mode`, `provider`, `answer`, không bao giờ có `sources` hay chữ của các đoạn tài liệu; tối đa 3 lượt.

**Chưa kiểm được với hệ thống thật:** máy hiện chưa có key của hãng nào. Cần ít nhất một key để thử tay stream và bước viết lại; mỗi nhà chưa có key thì chỉ có test với AI giả.

## 9. Để builder tự quyết

- Câu lệnh (prompt) cho bước viết lại câu hỏi, miễn là: trả về đúng một câu hỏi, cùng ngôn ngữ, không trả lời.
- Cách tổ chức code trong `llm.py` và hàm lõi sinh sự kiện.
- Cách tách số trích dẫn khi stream (miễn đúng mục 5).
- Vị trí và kiểu chữ của dòng "Hiểu là", trong khuôn token màu và font hiện có.
