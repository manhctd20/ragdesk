# Thiết kế đợt 2C: đăng nhập theo người và phân quyền theo thư mục

> **Trạng thái (26/11/2026):** **tạm dừng, chưa duyệt.** Người dùng quyết định chưa làm phần C vì hiện chưa có tài liệu nào cần giới hạn người đọc; cả team cùng được đọc mọi thứ sẽ nạp vào. Khi có tài liệu như vậy thì làm tiếp từ bản này (chưa qua bước builder đọc lại).
> Nền: thiết kế đợt 1 `docs/2026-11-20-thiet-ke.md` (**TK1**) và đợt 2A `docs/2026-11-25-thiet-ke-dot-2a.md` (**TK2A**). Phần B (OCR) để sau.
> Quy ước: **[Người dùng chốt]** là điều người dùng đã nói; **[Claude đề xuất]** là đề xuất của Claude, đã trình bày khi bàn và người dùng không phản đối, vẫn sửa được khi duyệt.

## 1. Mục đích

Hiện nay ai vào được mạng nội bộ cũng hỏi và đọc được nội dung mọi tài liệu, còn quản trị dùng chung một mật khẩu (`ADMIN_PASSWORD`). Phần C cho mỗi người một tài khoản và chỉ cho họ thấy những thư mục họ được phép xem, để team nạp được cả tài liệu không phải ai cũng được đọc.

Người dùng giao cho Claude tự đề xuất phương án [Người dùng chốt]; các quyết định dưới đây là đề xuất đã được người dùng chọn hoặc không phản đối.

## 2. Mục tiêu, không làm, không được xảy ra

**Mục tiêu:**
- Mỗi người đăng nhập bằng tài khoản riêng do quản trị tạo trong app.
- Quyền xem chia theo **nhóm**; mỗi thư mục ghi rõ nhóm nào được xem.
- Mọi chỗ trả nội dung tài liệu đều chỉ trả phần người đó được xem.

**Không làm trong phần C:**
- Đăng nhập bằng Google, LDAP hay SSO của công ty (thiết kế để sau này thay được phần đăng nhập mà giữ nguyên phần nhóm và quyền).
- Người dùng tự đăng ký, tự lấy lại mật khẩu qua email (quên thì quản trị đặt lại).
- Lưu lịch sử hỏi lên máy chủ, đồng bộ giữa nhiều máy.
- Phân quyền theo từng file, hoặc quyền "chỉ được tải lên thư mục X".
- Nhật ký ai đã xem gì (audit log).
- HTTPS (vẫn là việc triển khai, như README đã ghi).

**Không được xảy ra (dù tính năng vẫn "chạy"):**
- Một người thấy được **bất cứ thứ gì** của thư mục họ không có quyền: tên file, tên thư mục, số lượng file, chữ của đoạn tài liệu, hay đoạn đó bị gửi cho AI ngoài khi họ hỏi.
- Gọi được API mà không đăng nhập (trừ đăng nhập và các file giao diện).
- Thành viên thường làm được việc của quản trị nếu gọi thẳng API.
- Tài liệu bị lộ vì quên gán quyền: thư mục chưa gán nhóm phải kín (mục 4).

## 3. Tài khoản và đăng nhập [Người dùng chốt: tài khoản tạo ngay trong app]

**Người dùng** có: email (dùng để đăng nhập, không phân biệt hoa thường), tên hiển thị, vai trò (`member` hoặc `admin`), danh sách nhóm, trạng thái khoá, cờ "phải đổi mật khẩu".

**Vai trò** [Claude đề xuất]:
- `member`: hỏi, xem tài liệu và tab thư mục trong phạm vi quyền.
- `admin`: thấy mọi thư mục; tải lên, xoá tài liệu; quản lý người dùng, nhóm và quyền thư mục. Thay cho `ADMIN_PASSWORD` dùng chung.

**Quản trị đầu tiên** [Claude đề xuất]: lần khởi động mà bảng người dùng còn trống, máy chủ tạo một `admin` từ `ADMIN_EMAIL` + `ADMIN_PASSWORD`. Thiếu một trong hai khi bảng còn trống thì máy chủ không khởi động (như TK1 hiện nay với `ADMIN_PASSWORD`). Đã có người dùng thì hai biến này bị bỏ qua. Đây là dữ liệu khởi tạo đi kèm schema, không phải sửa dữ liệu có sẵn.

**Đăng nhập** [Claude đề xuất]:
- Trang `/dang-nhap`: email, mật khẩu. Chưa đăng nhập thì mọi trang giao diện chuyển về đây; đăng nhập xong quay lại trang đang mở.
- Phiên lưu ở máy chủ (bảng phiên trong SQLite), trình duyệt giữ một cookie `HttpOnly`, `SameSite=Lax`, hết hạn sau **7 ngày**. Chạy HTTP trong LAN nên chưa đặt `Secure`; khi đặt sau HTTPS thì bật.
- Sai email hoặc mật khẩu: chờ 1 giây rồi báo chung một câu "Sai email hoặc mật khẩu" (không nói email có tồn tại hay không).
- Tài khoản bị khoá: không đăng nhập được, và mọi phiên đang mở của người đó bị huỷ ngay.
- Mật khẩu băm bằng `hashlib.scrypt` có sẵn trong Python (có salt), không thêm thư viện. Mật khẩu tối thiểu 8 ký tự.
- Người mới được tạo, hoặc vừa được quản trị đặt lại mật khẩu, phải đổi mật khẩu ngay khi đăng nhập; chưa đổi thì chỉ gọi được API đổi mật khẩu và đăng xuất.
- Có nút "Đăng xuất" ở chân thanh bên, cạnh tên người dùng.

**Chống gửi yêu cầu giả từ trang khác (CSRF)** [Claude đề xuất]: mọi yêu cầu thay đổi dữ liệu (POST, PUT, DELETE) phải có header `X-Requested-With: tcnb`; trình duyệt không cho trang khác tự gắn header này. Kết hợp với `SameSite=Lax`.

## 4. Nhóm và quyền thư mục

**Nhóm** [Người dùng chốt: quyền theo nhóm]: có tên; một người thuộc nhiều nhóm; quản trị tạo, đổi tên, xoá nhóm. Xoá nhóm thì gỡ nhóm đó khỏi mọi người và mọi thư mục.

**Quyền thư mục:** mỗi thư mục có danh sách nhóm được xem. Một `member` xem được thư mục khi thuộc ít nhất một nhóm trong danh sách đó.

**Thư mục chưa gán nhóm nào** [Người dùng chốt: cách 1]: **chỉ quản trị xem được**, cho tới khi được gán nhóm. Áp dụng cho cả thư mục đã có trước khi nâng cấp và thư mục mới được tạo khi tải file lên.

**Thư mục `Chung`** [Người dùng chốt]: ai đăng nhập cũng xem được, không cần gán nhóm. Đây cũng là thư mục mặc định khi tải lên mà để trống tên (đợt 1).

**Quản trị** thấy mọi thư mục, kể cả thư mục chưa gán nhóm.

**Sau khi nâng cấp:** thành viên chỉ thấy thư mục `Chung` cho tới khi quản trị gán nhóm cho các thư mục còn lại. README phải nói rõ bước này.

## 5. Một bộ lọc ở máy chủ cho mọi chỗ

Máy chủ tính một tập **thư mục được xem** cho người đang đăng nhập, rồi dùng đúng tập đó ở mọi nơi trả nội dung tài liệu. Không chỗ nào được tự lọc theo cách riêng.

| Chỗ | Phải lọc thế nào |
|---|---|
| `GET /api/documents` | Chỉ trả file và tab thư mục thuộc tập được xem; số đếm ở tab cũng chỉ tính trong tập đó. `?folder=` trỏ vào thư mục không có quyền thì trả rỗng như thư mục không tồn tại (không trả 403, để không lộ là thư mục đó có thật). |
| Tìm kiếm (`/api/ask`, `/api/ask/stream`) | Chỉ tìm trong tài liệu thuộc tập được xem, cả nhánh vector lẫn BM25. Vì vậy 5 đoạn gửi cho AI ngoài cũng chỉ nằm trong phạm vi quyền. Không có tài liệu nào trong phạm vi quyền thì trả "Chưa có tài liệu nào", như khi kho trống. |
| `GET /api/config` | Không đổi nội dung, nhưng phải đăng nhập mới gọi được. |
| Tải lên, xoá | Chỉ `admin`. |

Lịch sử hỏi gửi kèm (TK2A mục 3) đến từ trình duyệt của chính người đó, nên không phải lọc theo quyền; nhưng câu trả lời cũ trong đó có thể chứa nội dung một thư mục họ vừa bị thu quyền (xem mục 7).

## 6. Giao diện

**Trang đăng nhập** `/dang-nhap`: email, mật khẩu, nút "Đăng nhập", dòng báo lỗi dưới ô. Không có thanh bên.

**Đổi mật khẩu**: khi bị buộc đổi thì hiện ngay sau đăng nhập; ngoài ra mở được từ tên người dùng ở chân thanh bên. Ô mật khẩu cũ, mật khẩu mới, nhập lại.

**Thanh bên**: thêm mục **"Người dùng"** (chỉ `admin` thấy) và ở chân có tên người dùng kèm nút "Đăng xuất".

```
┌ Tra cứu nội bộ ───────────┐
│ + Cuộc hỏi mới            │
│ …                         │
│ 📁 Tài liệu               │
│ 👥 Người dùng  (quản trị) │
│ Minh · Đăng xuất      ☾   │
└───────────────────────────┘
```

**Trang Tài liệu**:
- Bỏ khung "Mở khoá quản trị" và mọi thứ dùng `ADMIN_PASSWORD` ở trình duyệt.
- `member`: chỉ xem danh sách, không có khung tải lên, không có nút xoá.
- `admin`: như hiện nay khi đã mở khoá, cộng thêm ở mỗi tab thư mục (trừ `Chung`) một nút **"Quyền xem"** mở danh sách nhóm để tick; thư mục chưa gán nhóm hiện nhãn "Chỉ quản trị".

**Trang Người dùng** `/nguoi-dung` (chỉ `admin`):
- Bảng người dùng: tên, email, vai trò, nhóm, trạng thái. Thao tác: tạo, sửa tên/vai trò/nhóm, đặt lại mật khẩu (hiện mật khẩu tạm một lần cho quản trị chép), khoá/mở khoá.
- Danh sách nhóm: tạo, đổi tên, xoá (xoá phải xác nhận ngay trong dòng, như xoá file).
- Không xoá hẳn người dùng, chỉ khoá [Claude đề xuất]: giữ được ai đã tạo gì nếu sau này cần.
- Không cho tự hạ quyền, khoá hoặc đổi vai trò của **quản trị cuối cùng** đang hoạt động.

Giao diện theo đúng hệ token màu, font và icon đang có (Hallmark, Console sáng/tối), đủ 4 trạng thái đang tải, trống, lỗi, đầy đủ như các trang hiện có.

## 7. Lịch sử hỏi trên trình duyệt [Claude đề xuất]

- Lịch sử vẫn nằm trong localStorage nhưng **tách theo tài khoản**: key `tcnb:history:<id người dùng>`.
- **Đăng xuất** thì xoá lịch sử của tài khoản đó khỏi trình duyệt.
- Lần đầu đăng nhập sau khi nâng cấp, xoá key cũ dùng chung `tcnb:history` của đợt 1 (nó chứa đoạn tài liệu của mọi thư mục, không gắn với ai).
- Giới hạn đã biết, ghi vào README: người bị thu quyền một thư mục vẫn thấy những câu trả lời cũ về thư mục đó trên máy của họ cho tới khi đăng xuất. Lần hỏi mới thì không còn tìm ra thư mục đó nữa.

## 8. Dữ liệu và API

**Bảng mới trong `app.sqlite3`** (tạo bằng `CREATE TABLE IF NOT EXISTS` lúc khởi động như bảng `documents`; chỉ DDL, không có câu sửa dữ liệu có sẵn): người dùng, phiên đăng nhập, nhóm, người–nhóm, thư mục–nhóm. Tên cột và kiểu để builder quyết, miễn đủ các trường ở mục 3 và 4. Quyền gắn theo **tên thư mục** (thư mục chỉ tồn tại qua cột `folder` của `documents`); thư mục hết file rồi có file lại thì quyền cũ vẫn còn.

**API mới** [Claude đề xuất tên; builder giữ đúng ý]:
- `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` (trả id, email, tên, vai trò, nhóm, cờ phải đổi mật khẩu), `POST /api/auth/password`.
- `GET/POST /api/users`, `PATCH /api/users/{id}`, `POST /api/users/{id}/reset-password` (chỉ `admin`).
- `GET/POST /api/groups`, `PATCH/DELETE /api/groups/{id}` (chỉ `admin`).
- `GET /api/folders` (chỉ `admin`: mọi thư mục kèm nhóm được xem), `PUT /api/folders/{tên}/groups` (chỉ `admin`).

**Bỏ:** header `X-Admin-Password`, endpoint `POST /api/admin/check`, khoá `tcnb:admin` trong sessionStorage.

**Mã lỗi:** chưa đăng nhập hoặc phiên hết hạn → 401 (giao diện chuyển về `/dang-nhap`); đăng nhập rồi nhưng không đủ vai trò → 403; đang bị buộc đổi mật khẩu mà gọi API khác → 403 kèm thông báo riêng để giao diện mở màn đổi mật khẩu.

**`eval.py`** chạy thẳng trên dữ liệu như hiện nay, không qua đăng nhập, tìm trên toàn bộ tài liệu (như quản trị).

**Biến môi trường:** thêm `ADMIN_EMAIL`; `ADMIN_PASSWORD` đổi nghĩa thành mật khẩu của quản trị đầu tiên, chỉ dùng khi chưa có người dùng nào.

## 9. Cách làm đã cân nhắc

**Nguồn tài khoản** [Người dùng chọn cách 1]:
1. **Tài khoản tạo trong app.** Chạy hoàn toàn trong LAN, không phụ thuộc dịch vụ ngoài; đổi lại thêm một bộ mật khẩu phải nhớ. **Được chọn.**
2. Đăng nhập bằng Google: không quản lý mật khẩu, nhưng máy chủ phải ra internet và cần tạo OAuth app.
3. Đặt sau SSO / reverse proxy của công ty: app gần như không làm phần đăng nhập, nhưng cần hạ tầng chưa có và dễ bị giả mạo nếu cấu hình sai.

**Mô hình quyền** [Claude đề xuất, người dùng không phản đối]: theo **nhóm** thay vì gán từng người vào từng thư mục, để thêm người mới chỉ cần xếp nhóm.

**Thư mục chưa gán nhóm** [Người dùng chọn cách 1]: chỉ quản trị xem được (kín mặc định) thay vì mọi người xem được, để không lộ tài liệu vì quên gán quyền; đổi lại sau nâng cấp phải gán quyền cho các thư mục cũ.

**Phiên đăng nhập** [Claude đề xuất]: phiên lưu ở máy chủ + cookie `HttpOnly`, thay vì token JWT lưu ở trình duyệt: khoá tài khoản là huỷ được phiên ngay, và JavaScript không đọc được cookie.

## 10. Kiểm thử

**Tự động:**
- Test âm quan trọng nhất: một `member` không có quyền thư mục X thì **không** nhận được bất cứ gì của X qua: danh sách tài liệu, tab và số đếm, `?folder=X`, kết quả tìm kiếm ở cả `/api/ask` và `/api/ask/stream`, và các đoạn truyền cho AI ngoài (AI giả ghi lại lời gọi).
- Thư mục chưa gán nhóm: `member` không thấy, `admin` thấy; `Chung` thì mọi người thấy.
- Mọi endpoint (trừ đăng nhập và file giao diện) trả 401 khi chưa đăng nhập; endpoint quản trị trả 403 với `member`.
- Phiên: hết hạn → 401; đăng xuất huỷ phiên; khoá tài khoản huỷ mọi phiên của người đó.
- Thiếu `X-Requested-With` ở yêu cầu thay đổi dữ liệu → bị từ chối.
- Quản trị đầu tiên: tạo từ biến môi trường khi bảng trống; bị bỏ qua khi đã có người dùng.
- Buộc đổi mật khẩu: chặn mọi API khác cho tới khi đổi.
- Không hạ quyền / khoá được quản trị cuối cùng.
- Giao diện: chuyển về `/dang-nhap` khi 401; `member` không thấy khung tải lên, nút xoá, mục "Người dùng"; lịch sử tách theo tài khoản và bị xoá khi đăng xuất; key cũ `tcnb:history` bị xoá.

**Kiểm tay:** hai tài khoản trên hai trình duyệt, một thuộc nhóm có quyền và một không; tải file vào thư mục mới, xác nhận người thứ hai không thấy cho tới khi gán nhóm.

## 11. Để builder tự quyết

- Tên bảng, tên cột, cách lưu salt và tham số `scrypt` (theo khuyến nghị hiện hành của tài liệu Python).
- Cách tổ chức code: module mới cho xác thực và quyền, dependency FastAPI cho "đã đăng nhập" và "là admin".
- Cách truyền tập thư mục được xem vào hàm tìm kiếm (miễn lọc cả hai nhánh vector và BM25 bằng cùng một tập).
- Bố cục chi tiết trang Người dùng và hộp "Quyền xem", trong khuôn giao diện hiện có.
