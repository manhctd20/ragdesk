"""Regenerate the synthetic Vietnamese corpus used to measure search quality.

Usage: python make_corpus.py OUT_DIR --font /path/to/NotoSans-Regular.ttf
All content is fake. Questions that point at these files live in questions.json.
"""
import argparse
from pathlib import Path

from docx import Document
from fpdf import FPDF
from openpyxl import Workbook
from openpyxl.styles import Alignment


# ---------------------------------------------------------------- writers
def write_docx(path, title, blocks):
    """blocks: ("h1"|"h2"|"h3"|"p", text) or ("t", rows). First row of a table is its header."""
    doc = Document()
    doc.add_heading(title, 0)
    for kind, body in blocks:
        if kind == "p":
            doc.add_paragraph(body)
        elif kind == "t":
            table = doc.add_table(rows=len(body), cols=len(body[0]), style="Table Grid")
            for r, row in zip(table.rows, body):
                for cell, text in zip(r.cells, row):
                    cell.text = text
        else:
            doc.add_heading(body, int(kind[1]))
    doc.save(path)


def write_pdf(path, font, pages):
    """pages: list of pages; a page is a list of columns; a column is a list of paragraphs.
    A paragraph starting with "# " is a heading. Columns are written left to right, whole."""
    pdf = FPDF()
    pdf.add_font("Noto", fname=font)
    for columns in pages:
        pdf.add_page()
        gutter = 14
        width = (190 - gutter * (len(columns) - 1)) / len(columns)
        for i, col in enumerate(columns):
            pdf.set_xy(10 + i * (width + gutter), 15)
            for para in col:
                head = para.startswith("# ")
                pdf.set_font("Noto", size=15 if head else 11)
                pdf.multi_cell(width, 7 if head else 6, para[2:] if head else para, new_x="LEFT", new_y="NEXT", align="L")
                pdf.ln(2)
    pdf.output(path)


def write_xlsx(path, sheets):
    """sheets: {title: (rows, merges)}; merges are ranges like "A1:B1"."""
    wb = Workbook()
    wb.remove(wb.active)
    for title, (rows, merges) in sheets.items():
        ws = wb.create_sheet(title)
        for row in rows:
            ws.append(row)
        for m in merges:
            ws.merge_cells(m)
            ws[m.split(":")[0]].alignment = Alignment(horizontal="center")
    wb.save(path)


# ---------------------------------------------------------------- content
NOI_QUY = [
    ("h1", "Chương I. Quy định chung"),
    ("h2", "Điều 1. Phạm vi áp dụng"),
    ("p", "Nội quy này áp dụng cho toàn bộ người lao động đang làm việc theo HĐLĐ tại công ty, kể cả nhân viên thử việc."),
    ("h2", "Điều 2. Giờ làm việc"),
    ("p", "Giờ làm việc của công ty từ 08:00 đến 17:30, từ thứ Hai đến thứ Sáu, nghỉ trưa từ 12:00 đến 13:30. "
          "Nhân viên đi muộn quá 15 phút ba lần trong một tháng sẽ bị nhắc nhở bằng văn bản."),
    ("h2", "Điều 3. Chấm công"),
    ("p", "Nhân viên chấm công bằng vân tay khi vào và khi ra. Trường hợp quên chấm công, nhân viên phải báo cho TP "
          "trực tiếp trong vòng 2 ngày làm việc để TP xác nhận; quá hạn thì ngày đó không được tính công."),
    ("h1", "Chương II. Hợp đồng lao động"),
    ("h2", "Điều 4. Hợp đồng thử việc"),
    ("p", "Thời gian thử việc tối đa 60 ngày đối với vị trí chuyên viên trở lên và 30 ngày đối với vị trí nhân viên "
          "hỗ trợ. Lương thử việc bằng 85% mức lương chính thức. Trong thời gian thử việc, hai bên có quyền chấm dứt "
          "hợp đồng mà không cần báo trước."),
    ("h2", "Điều 5. Các loại HĐLĐ"),
    ("p", "Sau thử việc, nhân viên ký HĐLĐ xác định thời hạn 12 tháng, sau đó ký HĐLĐ 36 tháng. Sau hai lần ký liên "
          "tiếp, công ty ký HĐLĐ không xác định thời hạn."),
    ("h2", "Điều 6. Chấm dứt HĐLĐ"),
    ("p", "Nhân viên muốn nghỉ việc phải báo trước 30 ngày đối với HĐLĐ xác định thời hạn và 45 ngày đối với HĐLĐ không "
          "xác định thời hạn. Đơn xin nghỉ việc làm bằng văn bản, gửi TP và phòng Nhân sự."),
    ("h1", "Chương III. Chế độ nghỉ"),
    ("h2", "Điều 7. Nghỉ phép năm"),
    ("p", "Số ngày nghỉ phép năm, cách đăng ký và cách tính phép chưa dùng được quy định trong Quy định nghỉ phép "
          "riêng do phòng Nhân sự ban hành."),
    ("h2", "Điều 8. Nghỉ lễ, Tết"),
    ("p", "Công ty nghỉ các ngày lễ, Tết theo quy định của nhà nước và nghỉ thêm một ngày giáp Tết Nguyên đán do "
          "công ty quyết định hằng năm."),
    ("h2", "Điều 9. Nghỉ ốm và thai sản"),
    ("p", "Nhân viên nghỉ ốm có giấy của cơ sở y tế được hưởng chế độ ốm đau từ quỹ BHXH. Nhân viên nữ nghỉ thai sản "
          "6 tháng, hưởng trợ cấp thai sản từ BHXH; công ty hỗ trợ thêm 5.000.000 đồng khi nhân viên sinh con."),
    ("h1", "Chương IV. Kỷ luật lao động"),
    ("h2", "Điều 10. Hình thức xử lý kỷ luật"),
    ("p", "Công ty áp dụng ba hình thức xử lý kỷ luật theo mức độ vi phạm, nêu ở các mục dưới đây."),
    ("h3", "Khiển trách"),
    ("p", "Áp dụng với vi phạm lần đầu, mức độ nhẹ như đi muộn quá ba lần trong tháng hoặc không tuân thủ quy định "
          "chấm công. Khiển trách được lập thành biên bản và lưu hồ sơ nhân sự."),
    ("h3", "Kéo dài thời hạn nâng lương"),
    ("p", "Áp dụng với nhân viên đã bị khiển trách mà tái phạm trong vòng 6 tháng. Thời gian kéo dài không quá 6 tháng."),
    ("h3", "Sa thải"),
    ("p", "Áp dụng khi nhân viên tự ý bỏ việc 5 ngày cộng dồn trong 30 ngày, hoặc 20 ngày cộng dồn trong 365 ngày mà "
          "không có lý do chính đáng; hoặc khi tiết lộ bí mật kinh doanh của công ty."),
    ("h2", "Điều 11. Bảo mật thông tin"),
    ("p", "Nhân viên không được sao chép, gửi ra ngoài hoặc đăng tải tài liệu nội bộ lên các dịch vụ lưu trữ cá nhân. "
          "Khi nghỉ việc, nhân viên bàn giao toàn bộ tài liệu và tài khoản cho TP."),
    ("h1", "Chương V. Quản lý tài sản"),
    ("h2", "Điều 12. Quản lý và sử dụng tài sản công ty"),
    ("p", "Tài sản của công ty gồm máy tính, màn hình, điện thoại, máy in, nội thất và các thiết bị văn phòng khác được "
          "giao cho nhân viên hoặc phòng ban quản lý. Mỗi tài sản có mã riêng, được ghi vào danh mục tài sản và gắn tem "
          "kiểm kê. Nhân viên không được tự ý bóc tem, thay đổi cấu hình hoặc cho người ngoài công ty sử dụng tài sản "
          "được giao."),
    ("p", "Khi nhận tài sản, nhân viên ký biên bản bàn giao có xác nhận tình trạng ban đầu. Nhân viên chịu trách nhiệm "
          "bảo quản tài sản trong suốt thời gian sử dụng, giữ gìn sạch sẽ, không để chất lỏng gần thiết bị điện tử và "
          "không mang thiết bị ra khỏi văn phòng nếu chưa được TP đồng ý bằng văn bản hoặc email. Thiết bị mang ra ngoài "
          "phải được cài mật khẩu và mã hóa ổ đĩa theo hướng dẫn của phòng Công nghệ."),
    ("p", "Việc sửa chữa, nâng cấp hoặc cài thêm phần mềm do phòng Công nghệ thực hiện. Nhân viên gửi yêu cầu qua hệ "
          "thống hỗ trợ nội bộ, ghi rõ mã tài sản và mô tả sự cố. Phòng Công nghệ phản hồi trong 1 ngày làm việc và hoàn "
          "tất sửa chữa trong 5 ngày làm việc, trừ trường hợp phải gửi hãng bảo hành. Trong thời gian sửa chữa, nhân "
          "viên được mượn thiết bị thay thế nếu còn."),
    ("p", "Hằng năm vào tháng 12, phòng Hành chính phối hợp phòng Kế toán kiểm kê toàn bộ tài sản. Nhân viên có trách "
          "nhiệm có mặt hoặc cử người đại diện để xác nhận tài sản đang giữ. Tài sản không tìm thấy khi kiểm kê mà không "
          "có biên bản báo mất được xem là mất do lỗi của người giữ."),
    ("p", "Trường hợp tài sản bị mất hoặc hư hỏng do lỗi của nhân viên, nhân viên phải báo cho TP và phòng Hành chính "
          "trong vòng 24 giờ kể từ khi phát hiện. Mức bồi thường bằng 50% giá trị còn lại của tài sản theo sổ sách nếu "
          "nhân viên đã báo đúng hạn, và bằng 100% giá trị còn lại nếu báo chậm hoặc cố ý làm hỏng. Khoản bồi thường "
          "được trừ vào lương trong tối đa 3 kỳ lương liên tiếp."),
]

LUONG = [
    ("h1", "1. Nguyên tắc chung"),
    ("p", "Thu nhập của nhân viên gồm lương cơ bản theo bậc, phụ cấp và thưởng. Lương được trả vào ngày 5 hằng tháng. "
          "Mức đóng BHXH tính trên lương cơ bản: người lao động đóng 8%, công ty đóng 17,5%."),
    ("h1", "2. Hệ số lương theo bậc"),
    ("p", "Lương cơ bản bằng hệ số nhân với mức lương cơ sở của công ty là 5.000.000 đồng. Hệ số theo bậc như sau."),
    ("t", [["Bậc", "Hệ số", "Chức danh tương đương"],
           ["Bậc 1", "1,8", "Nhân viên mới"],
           ["Bậc 2", "2,2", "Nhân viên"],
           ["Bậc 3", "2,6", "Chuyên viên"],
           ["Bậc 4", "3,1", "Chuyên viên chính"],
           ["Bậc 5", "3,7", "Trưởng nhóm"],
           ["Bậc 6", "4,5", "Trưởng phòng"]]),
    ("h1", "3. Phụ cấp"),
    ("p", "Phụ cấp được trả cùng kỳ lương, mức theo bảng dưới đây, tính theo tháng."),
    ("t", [["Loại phụ cấp", "Đối tượng", "Mức (đồng/tháng)"],
           ["Ăn trưa", "Khối văn phòng", "730.000"],
           ["Ăn trưa", "Nhân viên kinh doanh", "900.000"],
           ["Điện thoại", "Trưởng phòng trở lên", "500.000"],
           ["Điện thoại", "Nhân viên kinh doanh", "300.000"],
           ["Xăng xe", "Nhân viên kinh doanh", "600.000"],
           ["Trách nhiệm", "Trưởng nhóm", "1.000.000"]]),
    ("h1", "4. Thưởng"),
    ("h2", "4.1. Thưởng hiệu quả quý"),
    ("p", "Thưởng hiệu quả quý tối đa bằng 1 tháng lương cơ bản, chi vào tháng đầu của quý sau. Mức thưởng nhân với "
          "hệ số theo xếp loại ở bảng dưới."),
    ("t", [["Xếp loại", "Hệ số thưởng quý"],
           ["A", "1,0"],
           ["B", "0,7"],
           ["C", "0,4"],
           ["D", "0"]]),
    ("h2", "4.2. Thưởng tháng 13"),
    ("p", "Nhân viên làm đủ 12 tháng trong năm được thưởng tháng 13 bằng 1 tháng lương cơ bản. Nhân viên làm chưa đủ "
          "12 tháng được tính theo tỷ lệ số tháng đã làm việc."),
]

PHEP = {
    "quy-dinh-nghi-phep-2023.docx": ("Quy định nghỉ phép năm (ban hành năm 2023)", [
        ("h1", "1. Số ngày nghỉ phép năm"),
        ("p", "Nhân viên có HĐLĐ chính thức được nghỉ phép năm 12 ngày làm việc. Cứ 5 năm làm việc tại công ty được "
              "cộng thêm 1 ngày."),
        ("h1", "2. Đăng ký nghỉ phép"),
        ("p", "Nhân viên đăng ký nghỉ phép trên hệ thống trước ít nhất 3 ngày làm việc, TP là người duyệt. Nghỉ từ 3 "
              "ngày liên tiếp trở lên phải đăng ký trước 7 ngày."),
        ("h1", "3. Phép chưa dùng hết"),
        ("p", "Phép năm chưa dùng hết được bảo lưu đến hết ngày 31/03 của năm sau. Quá hạn này, số ngày phép còn lại "
              "không được cộng dồn hay quy đổi thành tiền."),
    ]),
    "quy-dinh-nghi-phep-2025.docx": ("Quy định nghỉ phép năm (ban hành năm 2025, thay thế bản 2023)", [
        ("h1", "1. Số ngày nghỉ phép năm"),
        ("p", "Nhân viên có HĐLĐ chính thức được nghỉ phép năm 14 ngày làm việc. Cứ 5 năm làm việc tại công ty được "
              "cộng thêm 1 ngày."),
        ("h1", "2. Đăng ký nghỉ phép"),
        ("p", "Nhân viên đăng ký nghỉ phép trên hệ thống trước ít nhất 2 ngày làm việc, TP là người duyệt. Nghỉ từ 3 "
              "ngày liên tiếp trở lên phải đăng ký trước 5 ngày."),
        ("h1", "3. Phép chưa dùng hết"),
        ("p", "Phép năm chưa dùng hết được bảo lưu đến hết ngày 30/06 của năm sau. Quá hạn này, số ngày phép còn lại "
              "không được cộng dồn hay quy đổi thành tiền."),
        ("h1", "4. Nghỉ nửa ngày"),
        ("p", "Nhân viên được đăng ký nghỉ nửa ngày, buổi sáng hoặc buổi chiều. Mỗi lần nghỉ nửa ngày được trừ 0,5 ngày phép."),
    ]),
}

THANH_TOAN = [
    [[
        "# Quy trình thanh toán",
        "1. Mục đích",
        "Quy trình này quy định các bước đề nghị, kiểm tra, phê duyệt và chi trả các khoản thanh toán của công ty "
        "cho nhà cung cấp và cho nhân viên.",
        "2. Hồ sơ đề nghị thanh toán",
        "Hồ sơ đề nghị thanh toán gồm: giấy đề nghị thanh toán theo mẫu TC-01, hóa đơn VAT hợp lệ, hợp đồng hoặc đơn "
        "đặt hàng, và biên bản nghiệm thu. Hóa đơn phải ghi đúng tên công ty và mã số thuế. Chi phí công tác thanh "
        "toán theo định mức công tác phí hiện hành, kèm giấy đi đường.",
    ]],
    [[
        "3. Hạn mức phê duyệt",
        "Khoản thanh toán dưới 5.000.000 đồng do TP duyệt. Khoản từ 5.000.000 đồng đến dưới 50.000.000 đồng do TP và "
        "Giám đốc tài chính cùng duyệt. Khoản từ 50.000.000 đồng trở lên do Tổng giám đốc phê duyệt.",
        "4. Thời hạn xử lý",
        "Kế toán kiểm tra hồ sơ trong 2 ngày làm việc. Công ty thanh toán trong 5 ngày làm việc kể từ ngày hồ sơ đầy "
        "đủ. Việc chuyển khoản được thực hiện vào thứ Ba và thứ Sáu hằng tuần.",
    ]],
    [[
        "5. Tạm ứng",
        "Mức tạm ứng tối đa bằng 70% dự toán đã được duyệt. Người tạm ứng phải quyết toán trong vòng 10 ngày sau khi "
        "hoàn thành công việc. Người chưa quyết toán khoản tạm ứng trước thì không được tạm ứng lần sau.",
        "6. Hoàn ứng",
        "Số tiền tạm ứng chi không hết phải nộp lại quỹ trong ngày quyết toán. Số tiền chi vượt được thanh toán bổ "
        "sung sau khi TP xác nhận.",
    ]],
    [[
        "7. Chứng từ và hóa đơn",
        "Mọi khoản chi phải có chứng từ gốc. Hóa đơn điện tử được lưu dưới dạng tệp PDF kèm tệp XML và đặt tên theo cú "
        "pháp ngày, số hóa đơn, tên nhà cung cấp. Hóa đơn giấy phải còn nguyên, không tẩy xóa, không rách nát; trường "
        "hợp hóa đơn bị mất, người đề nghị xin bản sao có xác nhận của nhà cung cấp. Hóa đơn xuất sai thông tin phải "
        "được điều chỉnh hoặc xuất lại trong vòng 7 ngày, nếu không kế toán có quyền từ chối thanh toán. Hóa đơn có "
        "ngày lập sau ngày nghiệm thu hàng hóa hoặc dịch vụ phải kèm giải trình bằng văn bản của người đề nghị.",
        "8. Hình thức chi trả",
        "Khoản chi từ 25.000.000 đồng trở lên phải thanh toán bằng chuyển khoản vào tài khoản của nhà cung cấp, không "
        "thanh toán bằng tiền mặt. Khoản chi dưới 25.000.000 đồng được phép thanh toán bằng tiền mặt qua quỹ khi có "
        "phiếu chi do kế toán trưởng ký. Mọi khoản chi bằng ngoại tệ phải được Giám đốc tài chính phê duyệt trước và "
        "quy đổi theo tỷ giá bán của ngân hàng giao dịch tại ngày chi.",
        "9. Chi phí nhỏ lẻ",
        "Chi phí nhỏ lẻ dưới 200.000 đồng mỗi lần mà không có hóa đơn được thanh toán bằng bảng kê tự lập có chữ ký "
        "của TP, tổng cộng tối đa 1.000.000 đồng mỗi người mỗi tháng. Chi phí vượt mức này bắt buộc có hóa đơn hợp lệ.",
    ]],
]

MUA_HANG = [
    [[
        "# Quy trình mua hàng",
        "1. Phạm vi",
        "Quy trình áp dụng cho việc mua sắm thiết bị, vật tư và dịch vụ phục vụ hoạt động của công ty.",
        "2. Đề xuất mua hàng",
        "Phòng có nhu cầu lập phiếu đề xuất mua hàng theo mẫu MH-01, có chữ ký của TP và nêu rõ mục đích, số lượng, "
        "thời điểm cần hàng.",
    ]],
    [[
        "3. Lựa chọn nhà cung cấp",
        "Đơn hàng dưới 10.000.000 đồng chỉ cần một báo giá. Đơn hàng từ 10.000.000 đồng đến 100.000.000 đồng cần ít "
        "nhất ba báo giá cạnh tranh. Đơn hàng trên 100.000.000 đồng phải tổ chức chọn nhà cung cấp theo hình thức "
        "đấu thầu do hội đồng mua sắm thực hiện.",
    ]],
    [[
        "4. Nghiệm thu và nhập kho",
        "Người đề xuất cùng thủ kho kiểm tra số lượng, chủng loại và tình trạng hàng khi nhận, ký biên bản nghiệm "
        "thu trong ngày nhận hàng.",
        "5. Bảo hành",
        "Thiết bị công nghệ thông tin phải được bảo hành tối thiểu 12 tháng. Công ty giữ lại 5% giá trị hợp đồng "
        "cho đến hết thời hạn bảo hành.",
    ]],
]

BAN_TIN = [
    [[
        "# Bản tin nội bộ số 11/2025",
        "Lời chào tháng Mười Một",
        "Cuối năm là lúc cả công ty tăng tốc hoàn thành các mục tiêu. Công ty sẽ chuyển sang văn phòng mới tại tầng 7 "
        "tòa nhà Sao Mai từ ngày 01/12, ban hành chính sẽ gửi sơ đồ chỗ ngồi trước một tuần.",
    ], [
        "# Tin nhân sự",
        "Chào mừng 12 bạn đồng nghiệp mới gia nhập trong tháng này. Chương trình khám sức khỏe định kỳ diễn ra từ ngày "
        "15 đến ngày 17/12 tại phòng khám Hòa Bình. Nhân viên đăng ký khung giờ với phòng Nhân sự trước ngày 05/12.",
    ]],
    [[
        "# Hoạt động đoàn thể",
        "Giải bóng đá nội bộ sẽ khai mạc ngày 20/12 tại sân Thành Công. Nhân viên muốn tham gia đăng ký đội với anh "
        "Hoàng Minh ở bộ phận Hành chính trước ngày 10/12; mỗi đội gồm 7 người.",
    ], [
        "# Góc kỹ thuật",
        "Hệ thống ERP sẽ bảo trì ngày 06/12 từ 22:00 đến 02:00 sáng hôm sau, trong thời gian này nhân viên không thể "
        "truy cập. Phòng Công nghệ nhắc mọi người đổi mật khẩu mỗi 90 ngày.",
    ]],
]

CONG_TAC_PHI = {
    "Định mức 2025": ([
        ["Đối tượng", None, "Ăn ở", None, None, "Đi lại", None, "Ghi chú"],
        ["Địa bàn", "Cấp bậc", "Tiền ăn (đồng/ngày)", "Phụ cấp lưu trú (đồng/ngày)", "Khách sạn tối đa (đồng/đêm)",
         "Vé máy bay", "Taxi nội thành (đồng/ngày)", None],
        ["Hà Nội, TP. HCM", "Nhân viên", 300000, 200000, 1200000, "Hạng phổ thông", 250000, "Có hóa đơn khách sạn"],
        ["Hà Nội, TP. HCM", "Trưởng phòng", 400000, 250000, 1800000, "Hạng phổ thông", 350000, "Có hóa đơn khách sạn"],
        ["Đà Nẵng", "Nhân viên", 250000, 150000, 900000, "Hạng phổ thông", 200000, "Có hóa đơn khách sạn"],
        ["Đà Nẵng", "Trưởng phòng", 350000, 200000, 1400000, "Hạng phổ thông", 300000, "Có hóa đơn khách sạn"],
        ["Tỉnh, thành khác", "Nhân viên", 200000, 150000, 700000, "Không áp dụng", 150000, "Đi xe khách hoặc tàu"],
        ["Tỉnh, thành khác", "Trưởng phòng", 300000, 200000, 1100000, "Không áp dụng", 250000, "Đi xe khách hoặc tàu"],
        ["Nước ngoài", "Mọi cấp bậc", 1200000, 800000, 3000000, "Hạng phổ thông", 600000, "Tổng giám đốc duyệt trước"],
    ], ["A1:B1", "C1:E1", "F1:G1", "H1:H2"]),
    "Ghi chú": ([
        ["Trường hợp", "Quy định"],
        ["Công tác nửa ngày", "Chuyến công tác dưới 4 giờ chỉ được thanh toán 50% tiền ăn."],
        ["Ở nhà người thân", "Không thanh toán tiền khách sạn, vẫn nhận đủ phụ cấp lưu trú."],
        ["Đi công tác bằng xe cá nhân", "Thanh toán xăng theo số km thực tế, 4.000 đồng mỗi km."],
    ], []),
}

TAI_SAN = {
    "Tài sản": ([
        ["Tài sản", None, None, "Mua sắm", None, None, "Sử dụng", None, "Theo dõi", None],
        ["Mã TS", "Tên tài sản", "Loại", "Nhà cung cấp", "Ngày mua", "Nguyên giá (đồng)", "Người sử dụng", "Phòng",
         "Khấu hao (tháng)", "Tình trạng"],
        ["TS-001", "Laptop Dell Latitude 5440", "Thiết bị CNTT", "Công ty Phong Vũ", "15/03/2024", 24500000,
         "Nguyễn Văn An", "Kinh doanh", 36, "Đang dùng tốt"],
        ["TS-002", "Laptop Lenovo ThinkPad E14", "Thiết bị CNTT", "Công ty Phong Vũ", "02/07/2024", 21800000,
         "Trần Thị Bình", "Kế toán", 36, "Đang dùng tốt"],
        ["TS-003", "Màn hình LG 27 inch", "Thiết bị CNTT", "Công ty Hoàng Hà", "20/08/2024", 4900000,
         "Lê Quang Cường", "Công nghệ", 24, "Đang dùng tốt"],
        ["TS-004", "Máy in HP LaserJet Pro M404", "Thiết bị văn phòng", "Công ty Hoàng Hà", "10/01/2023", 8700000,
         "Dùng chung", "Hành chính", 36, "Cần thay mực"],
        ["TS-005", "Máy chiếu Epson EB-X51", "Thiết bị văn phòng", "Công ty Nam Việt", "05/05/2022", 13200000,
         "Dùng chung", "Phòng họp tầng 3", 48, "Đang sửa chữa, hỏng bóng đèn"],
        ["TS-006", "Điều hòa Daikin 18000 BTU", "Thiết bị văn phòng", "Công ty Nam Việt", "18/06/2021", 16400000,
         "Dùng chung", "Phòng họp tầng 5", 60, "Đang dùng tốt"],
        ["TS-007", "Bàn họp 12 chỗ", "Nội thất", "Công ty Hòa Phát", "12/09/2022", 18500000,
         "Dùng chung", "Phòng họp tầng 5", 60, "Đang dùng tốt"],
        ["TS-008", "Ghế công thái học Ergo", "Nội thất", "Công ty Hòa Phát", "25/11/2024", 3600000,
         "Phạm Thu Hà", "Nhân sự", 36, "Đang dùng tốt"],
    ], ["A1:C1", "D1:F1", "G1:H1", "I1:J1"]),
}

FAQ = {
    "Câu hỏi thường gặp": ([
        ["STT", "Chủ đề", "Câu hỏi", "Trả lời", "Đơn vị phụ trách"],
        [1, "Tài khoản", "Quên mật khẩu email công ty thì làm sao?",
         "Vào trang đăng nhập, chọn Quên mật khẩu và nhập số điện thoại đã đăng ký. Nếu không nhận được mã, gọi "
         "phòng Công nghệ số máy lẻ 118.", "Công nghệ"],
        [2, "Hành chính", "Đặt phòng họp ở đâu?",
         "Đặt phòng họp trên lịch chung của hệ thống ERP, mục Tài nguyên. Mỗi lần đặt tối đa 2 giờ, phòng họp "
         "lớn tầng 3 cần TP duyệt.", "Hành chính"],
        [3, "Hành chính", "Quên thẻ ra vào thì làm sao?",
         "Nhận thẻ tạm tại quầy lễ tân tầng 1 bằng cách xuất trình thẻ nhân viên có ảnh hoặc giấy tờ tùy thân, "
         "trả lại thẻ tạm trước 17:30 cùng ngày. Quên thẻ quá 3 lần trong tháng sẽ bị báo cho TP.", "Hành chính"],
        [4, "Nhân sự", "Xin giấy xác nhận đang làm việc ở công ty để vay ngân hàng thì làm thế nào?",
         "Gửi email cho phòng Nhân sự theo mẫu NS-05, ghi rõ tên ngân hàng, mục đích và cho biết có cần ghi "
         "mức lương hay không. Phòng Nhân sự xử lý trong 3 ngày làm việc kể từ khi nhận đủ thông tin và gửi bản "
         "scan qua email, bản gốc có dấu đỏ nhận tại quầy lễ tân tầng 1. Nhân viên đang thử việc chỉ được cấp giấy "
         "xác nhận không ghi mức lương. Trường hợp cần ngay trong ngày, nhân viên liên hệ trực tiếp trưởng phòng "
         "Nhân sự để được ưu tiên, nhưng vẫn phải gửi email theo mẫu để lưu hồ sơ. Giấy xác nhận có hiệu lực 30 ngày "
         "kể từ ngày ký; nếu ngân hàng yêu cầu thời hạn dài hơn thì nhân viên phải xin cấp lại. Nếu ngân hàng cần xác "
         "nhận trực tiếp qua điện thoại, nhân viên nhắn trước cho phòng Nhân sự tên và số điện thoại của cán bộ ngân "
         "hàng để phòng Nhân sự chủ động trả lời, tránh việc ngân hàng gọi vào các số máy lẻ khác. Giấy xác nhận chỉ "
         "cấp cho nhân viên đã ký HĐLĐ chính thức và không có vụ vi phạm kỷ luật đang trong thời gian xem xét. Với "
         "mục đích thuê nhà, xin visa hoặc làm thủ tục cho con đi học, nhân viên dùng cùng mẫu NS-05 nhưng ghi rõ mục "
         "đích tương ứng, và không cần ghi mức lương trừ khi nơi nhận yêu cầu bằng văn bản. Mỗi nhân viên được cấp "
         "miễn phí hai bản gốc trong một năm; từ bản gốc thứ ba trở đi, nhân viên nộp phí 30.000 đồng mỗi bản cho bộ "
         "phận Hành chính. Bản scan gửi qua email không giới hạn số lần và không thu phí.", "Nhân sự"],
        [5, "Hành chính", "Gửi xe máy ở đâu và mất bao nhiêu tiền?",
         "Nhân viên gửi xe tại hầm B1 của tòa nhà, phí 120.000 đồng mỗi tháng, công ty hỗ trợ một nửa.", "Hành chính"],
        [6, "Hành chính", "Muốn đặt thêm văn phòng phẩm thì làm sao?",
         "Điền phiếu yêu cầu văn phòng phẩm trước ngày 25 hằng tháng, bộ phận Hành chính phát vào đầu tháng sau.",
         "Hành chính"],
        [7, "Công nghệ", "Cho khách dùng wifi như thế nào?",
         "Khách kết nối mạng Khach-SaoMai, mật khẩu đổi vào thứ Hai hằng tuần và có tại quầy lễ tân.", "Công nghệ"],
        [8, "Kế toán", "Xuất hóa đơn đỏ cho khách hàng cần những thông tin gì?",
         "Cần tên công ty khách, mã số thuế, địa chỉ và email nhận hóa đơn. Kế toán xuất hóa đơn trong 2 ngày làm việc.",
         "Kế toán"],
    ], []),
}


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--font", required=True, help="TTF with Vietnamese glyphs, e.g. NotoSans-Regular.ttf")
    a = ap.parse_args()
    out = Path(a.out_dir)
    for d in ("nhan-su", "tai-chinh", "hanh-chinh"):
        (out / d).mkdir(parents=True, exist_ok=True)

    write_docx(out / "nhan-su/noi-quy-lao-dong.docx", "Nội quy lao động", NOI_QUY)
    write_docx(out / "nhan-su/quy-che-luong-thuong.docx", "Quy chế lương thưởng", LUONG)
    for name, (title, blocks) in PHEP.items():
        write_docx(out / "nhan-su" / name, title, blocks)
    write_pdf(out / "tai-chinh/quy-trinh-thanh-toan.pdf", a.font, THANH_TOAN)
    write_pdf(out / "tai-chinh/quy-trinh-mua-hang.pdf", a.font, MUA_HANG)
    write_xlsx(out / "tai-chinh/dinh-muc-cong-tac-phi.xlsx", CONG_TAC_PHI)
    write_pdf(out / "hanh-chinh/ban-tin-noi-bo-hai-cot.pdf", a.font, BAN_TIN)
    write_xlsx(out / "hanh-chinh/danh-muc-tai-san.xlsx", TAI_SAN)
    write_xlsx(out / "hanh-chinh/faq-thuong-gap.xlsx", FAQ)


if __name__ == "__main__":
    main()
