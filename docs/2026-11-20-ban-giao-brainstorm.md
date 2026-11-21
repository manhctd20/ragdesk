# Bàn giao: hệ thống hỏi–đáp tài liệu nội bộ (RAG), giai đoạn brainstorm

> **Trạng thái (20/11/2026):** đang brainstorm theo skill `superpowers:brainstorming`. **Chưa có design doc được duyệt, chưa được viết code.** Tài liệu này ghi lại mọi thứ đã bàn để một session mới làm tiếp mà không phải hỏi lại.
>
> Quy ước trong tài liệu:
> - **[Người dùng chốt]**: người dùng đã nói rõ.
> - **[Claude đề xuất]**: Claude đưa ra, người dùng **chưa xác nhận**. Session sau phải nêu lại để người dùng duyệt, không được coi là đã chốt.

---

## 1. Bối cảnh

- Mục tiêu: **tự làm một hệ thống RAG của riêng người dùng**, hiểu được từng bước.

## 2. Yêu cầu

| Mục | Nội dung | Nguồn |
|---|---|---|
| Loại tài liệu | Word, PDF, Excel… | [Người dùng chốt] |
| Ngôn ngữ | Tiếng Việt hoặc tiếng Anh | [Người dùng chốt] |
| Người dùng | Người dùng và đồng nghiệp, hướng tới cả team dùng | [Người dùng chốt] |
| Bảo mật | Tài liệu nội bộ, có thể nhạy cảm. Cần **công tắc bật/tắt gửi dữ liệu ra ngoài** | [Người dùng chốt] |
| Phân quyền | **Chưa làm đợt này.** "Cần chạy ok trước rồi mới tính thêm" | [Người dùng chốt] |
| Máy chạy / phần cứng | **Tối ưu sau**, chưa quyết | [Người dùng chốt] |
| Giao diện | Tự làm UI riêng, không dùng Open WebUI. Lý do: muốn làm cái của riêng mình, không bị ràng buộc (ví dụ logo) | [Người dùng chốt] |

## 3. Các hướng đã cân nhắc

### 3.1 Cách xây hệ thống. Người dùng chọn **A**
- **A. Tự viết bản nhỏ, chỉ một đường đi qua các bước:** ✅ được chọn.
- **B. Dùng sản phẩm có sẵn (Open WebUI, AnythingLLM):** loại vì không học được cách RAG hoạt động, khó sửa khi tìm sai.

### 3.2 Giao diện. Người dùng chọn **tự làm UI riêng**
- Phương án dùng nguyên Open WebUI rồi cắm backend vào như một "model" (Open WebUI hỗ trợ kết nối API chuẩn OpenAI với Base URL tuỳ chỉnh): **bị loại.** Lý do của người dùng: license Open WebUI cấm đổi hoặc xoá thương hiệu "Open WebUI", trừ khi ≤ 50 người dùng trong 30 ngày hoặc có bản enterprise. Claude đã kiểm file LICENSE của Open WebUI ngày 20/11/2026.
- Chọn: **tự làm UI, bố cục lấy cảm hứng từ Open WebUI.**

## 4. Giao diện đã chốt

Bản phác nằm trong `docs/mockups/`, mở trực tiếp bằng trình duyệt:
- `layout.html`: 3 bố cục A/B/C. **Người dùng chọn A.**
- `theme.html`: 2 chất liệu (Coral sáng, Console tối).
- `theme-v2.html`: **bản đã chốt:** hệ Console, có chế độ sáng và tối.

Tên file và nội dung trong bản phác (NoiQuy_2026.docx…) là **dữ liệu mẫu tự đặt**, không phải tài liệu thật.

| Mục | Nội dung | Nguồn |
|---|---|---|
| Bố cục | **A, kiểu Open WebUI:** thanh bên trái gồm nút "Cuộc hỏi mới", lịch sử chat chia theo ngày, mục "Tài liệu", nút đổi sáng/tối. Khung chat ở giữa. Nguồn trích dẫn hiện thành thẻ nhỏ dưới câu trả lời | [Người dùng chốt] |
| Quy chuẩn thiết kế | Làm theo skill **`/hallmark`** (`~/.claude/skills/hallmark`), phạm vi **app screen** (`references/flow.md` § App screens) | [Người dùng chốt] |
| Icon | **Dùng icon, không dùng emoji.** Bản phác dùng nét kiểu Lucide | [Người dùng chốt]; chọn Lucide là [Claude đề xuất] |
| Màu | **Hệ Console (theme "Benchmark" trong Hallmark), có cả sáng và tối** | [Người dùng chốt] |
| Font | Font hỗ trợ tiếng Việt. Bản phác dùng **Geist** + **Geist Mono** | Yêu cầu hỗ trợ tiếng Việt là [Người dùng chốt]; chọn Geist là [Claude đề xuất] |
| Đổi sáng/tối | Nút mặt trăng/mặt trời góc dưới thanh bên, mặc định theo cài đặt máy | [Claude đề xuất] |
| Hai trạng thái câu trả lời | **Chỉ nội bộ** (mặc định): trả về các đoạn tài liệu, phần khớp tô màu, kèm vị trí (Word: mục; PDF: trang; Excel: sheet + dòng). **Bật AI ngoài:** câu trả lời viết sẵn, có số trích dẫn và thẻ nguồn | [Claude đề xuất], người dùng đã xem trên bản phác, chưa phản đối |
| Công tắc gửi ra ngoài | Nút "Chỉ nội bộ" cạnh ô hỏi, kèm dòng nhắc trạng thái ("Tài liệu không rời khỏi máy chủ") | [Claude đề xuất] |

**Đã kiểm chứng về font:** font gốc của theme Hallmark Console (Host Grotesk, Atkinson Hyperlegible Mono) và Coral (General Sans) **không có subset tiếng Việt** trên Google Fonts. Các font **có** subset `vietnamese`: Geist, Geist Mono, Be Vietnam Pro, Inter, IBM Plex Sans, Onest. Kiểm bằng Google Fonts CSS API ngày 20/11/2026.

Token màu dùng trong bản phác `theme-v2.html` (nguồn: `~/.claude/skills/hallmark/references/themes/console.md`; bản sáng do Claude tự suy ra, chưa qua sloplint):

```css
/* Tối: Console gốc */
--paper: oklch(17% 0.008 250); --paper-2: oklch(21% 0.009 250); --paper-3: oklch(13.5% 0.007 250);
--ink: oklch(95% 0.005 250); --ink-2: oklch(83% 0.008 250); --muted: oklch(71% 0.01 250);
--rule: oklch(31% 0.01 250); --rule-2: oklch(42% 0.012 250);
--accent: oklch(82% 0.15 80); --accent-soft: oklch(29% 0.05 80); --on-accent: oklch(18% 0.04 75);
/* Sáng: suy ra từ Console */
--paper: oklch(98.5% 0.003 250); --paper-2: oklch(96% 0.005 250); --paper-3: oklch(93.5% 0.006 250);
--ink: oklch(21% 0.01 250); --ink-2: oklch(32% 0.012 250); --muted: oklch(48% 0.012 250);
--rule: oklch(89% 0.006 250); --rule-2: oklch(80% 0.008 250);
--accent: oklch(78% 0.15 78); --accent-soft: oklch(93% 0.06 85); --on-accent: oklch(18% 0.04 75);
```

## 5. Câu hỏi đang mở (làm tiếp từ đây)

1. **Đã chốt:** người dùng có cần đăng nhập không?
   - [Người dùng chốt]: đợt này **không đăng nhập để hỏi**; việc **thêm/xoá tài liệu phải nhập mật khẩu quản trị chung**, đặt bằng biến môi trường `ADMIN_PASSWORD` trên máy chủ. Đăng nhập theo người làm cùng phân quyền ở đợt sau.
   - Rủi ro người dùng đã biết và chấp nhận: ai vào được mạng nội bộ cũng **hỏi và đọc được nội dung mọi tài liệu** đã nạp.
   - [Claude đề xuất]: chạy trong mạng nội bộ, lịch sử chat lưu trên trình duyệt của từng người.
2. Phác trang **"Tài liệu"**: upload, danh sách, xoá, trạng thái đang index.
   - [Người dùng chốt]: tài liệu xếp theo **một cấp thư mục**. Lúc tải lên thì chọn hoặc gõ tên thư mục; danh sách có bộ lọc theo thư mục. Thư mục được lưu vào metadata từng đoạn để đợt sau phân quyền.
   - [Người dùng chốt] bản phác `docs/mockups/tai-lieu.html` (đủ 4 trạng thái, sloplint sạch) và các điểm sau: ai cũng **xem** được danh sách tài liệu; tải lên/xoá chỉ hiện sau khi **mở khoá bằng mật khẩu ngay trên đầu trang**; đã mở khoá thì giữ đến khi đóng tab (`sessionStorage`), có nút "Khoá lại"; xoá phải xác nhận ngay trong dòng của bảng; tối đa **20 MB mỗi file**; PDF chỉ có ảnh scan thì **báo lỗi, đợt này không OCR**. Cần đủ 4 trạng thái theo Hallmark: đang tải, trống, lỗi, đầy đủ.
3. **Đã chốt** mặc định của công tắc. [Người dùng chốt]: quản trị có công tắc tổng `ALLOW_EXTERNAL` trên máy chủ. Nếu được phép thì người dùng tự bật cho từng câu hỏi, mặc định **tắt**. Nếu không được phép thì công tắc bị khoá và có dòng giải thích. Khi bật chỉ gửi câu hỏi và khoảng 5 đoạn tìm được, không bao giờ gửi cả file.
4. Chọn nhà cung cấp AI ngoài. [Người dùng chốt]: hỗ trợ **cả ba: Claude, OpenAI, Gemini**.
   - [Người dùng chốt] 20/11/2026, khi làm backend: **đợt 1 chỉ làm Gemini**, Claude và OpenAI làm sau.
   - [Người dùng chốt]: quản trị khai key nhà nào thì nhà đó mới dùng được. Khi có từ 2 nhà trở lên, công tắc cạnh ô hỏi có thêm danh sách để người dùng chọn; chỉ có 1 nhà thì không hiện danh sách.
   - [Claude đề xuất], chưa kiểm chứng: gọi cả ba qua **một client chuẩn OpenAI, chỉ đổi `base_url` + key + tên model**, nếu tài liệu chính thức xác nhận Anthropic và Gemini đều có endpoint tương thích OpenAI. Nếu không thì dùng SDK riêng của từng hãng. Phải kiểm bằng context7 và tài liệu chính thức lúc viết design doc.
5. Viết design doc đầy đủ → builder check bằng subagent → người dùng duyệt → skill `superpowers:writing-plans`.
   - 20/11/2026: người dùng **duyệt hết** các mục [Claude đề xuất] ở mục 4 và 6. Design doc đã viết ở `docs/2026-11-20-thiet-ke.md`, đã qua subagent soát (10 điểm, đã sửa hết). **Người dùng đã duyệt** (cả mục 12). Kế hoạch: `docs/2026-11-20-ke-hoach.md`, chờ duyệt.
   - Phát hiện khi soát: FastEmbed không có sẵn `multilingual-e5-small`, sẽ nạp bằng `add_custom_model` (xem design doc mục 3).
   - Skill `superpowers` chưa được cài trên máy này.

## 6. Đề xuất kỹ thuật (toàn bộ là [Claude đề xuất], chưa duyệt)

| Phần | Đề xuất | Lý do |
|---|---|---|
| Backend | Python + FastAPI | Thư viện đọc file, embedding, Chroma đều là Python |
| Frontend | React + TypeScript + Vite | Hợp stack quen thuộc của người dùng (React/TS) |
| Đọc file | PDF: `pypdf` theo trang. Word: `python-docx`, giữ tiêu đề mục. Excel: `openpyxl`, **mỗi dòng thành một đoạn kèm tên cột** | Excel cắt như văn bản thường sẽ mất nghĩa cột |
| Chunking | `recursive`, khoảng 500 ký tự, overlap khoảng 100 | Cấu hình đã chạy thử: 10 trang → 65 chunk |
| Embedding | FastEmbed `intfloat/multilingual-e5-small` (384 chiều, chạy CPU, local) | Đa ngôn ngữ, đọc được tiếng Việt. Chạy local nên không gửi tài liệu ra ngoài khi index |
| Kho vector | Chroma, lưu trên đĩa | Đã xem thực tế: `chroma.sqlite3` chứa chữ + metadata, file `.bin` chứa vector |
| Tìm kiếm | Hybrid: dense (Chroma) + BM25 (`rank-bm25`, dựng trong RAM), trộn bằng **RRF k=60**, lấy top 10 rồi giữ 5 | Thấy thực tế: điểm 0.033 = 1/61 + 1/61 (cùng đứng đầu cả hai bảng) |
| Metadata mỗi đoạn | Tên file, đường dẫn/thư mục, trang / mục / sheet + dòng | Để hiện nguồn, và để sau này **lọc theo thư mục khi làm phân quyền** mà không phải index lại |
| Prompt | Chỉ trả lời từ nguồn đánh số, trích `[1]`, không có thì nói không tìm thấy | Người đọc kiểm lại được câu trả lời từ nguồn |
| Chế độ nội bộ | Không gọi LLM, chỉ trả các đoạn tìm được | Máy hiện tại không có GPU; LLM chạy local trên CPU sẽ chậm và kém. Gắn model nội bộ sau khi có máy |
| Cache | Không dùng `pickle` | Tránh rủi ro thực thi code khi nạp cache |

## 7. Những gì đã kiểm chứng trên máy (20/11/2026)

- Máy: Linux, Python 3.12.3, Node 24, **không có GPU NVIDIA**, RAM 31 GB, chưa cài `uv` và Ollama.

## 8. Cách tiếp tục trong session mới

Mở terminal tại `~/workspace/tra-cuu-noi-bo`, chạy `claude`, rồi gõ:

```text
Đọc docs/2026-11-20-ban-giao-brainstorm.md. Tiếp tục brainstorm bằng skill superpowers:brainstorming từ mục 5 "Câu hỏi đang mở", bắt đầu bằng câu hỏi về đăng nhập / mật khẩu quản trị. Các mục [Claude đề xuất] chưa được duyệt, hãy nêu lại để tôi xác nhận trước khi viết design doc. Giao diện làm theo skill /hallmark, xem docs/mockups/theme-v2.html.
```
