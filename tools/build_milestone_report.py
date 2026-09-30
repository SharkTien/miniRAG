"""Build the Vietnamese milestone and data-research report as a PDF."""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "milestones_bonus_ec.pdf"


def register_fonts() -> tuple[str, str]:
    """Register a Unicode font available on the build host."""
    candidates = (
        (
            "/home/ntcai/rag-blueprint/parse-nemotron/NeMo-Retriever/cache/vietnamese-ocr/site/matplotlib/mpl-data/fonts/ttf/DejaVuSans.ttf",
            "/home/ntcai/rag-blueprint/parse-nemotron/NeMo-Retriever/cache/vietnamese-ocr/site/matplotlib/mpl-data/fonts/ttf/DejaVuSans-Bold.ttf",
        ),
        (
            "/home/ntcai/face-reconizer/face-recognition/.venv311/lib/python3.11/site-packages/matplotlib/mpl-data/fonts/ttf/DejaVuSans.ttf",
            "/home/ntcai/face-reconizer/face-recognition/.venv311/lib/python3.11/site-packages/matplotlib/mpl-data/fonts/ttf/DejaVuSans-Bold.ttf",
        ),
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ),
        (
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ),
    )
    for regular, bold in candidates:
        if Path(regular).exists() and Path(bold).exists():
            pdfmetrics.registerFont(TTFont("ReportSans", regular))
            pdfmetrics.registerFont(TTFont("ReportSans-Bold", bold))
            return "ReportSans", "ReportSans-Bold"
    raise FileNotFoundError("No Unicode TrueType font was found")


class ReportDocument(BaseDocTemplate):
    """Document template with page numbers and an automatic table of contents."""

    def __init__(self, filename: str, regular: str, **kwargs):
        super().__init__(filename, **kwargs)
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="normal",
        )
        self.addPageTemplates(
            [PageTemplate(id="main", frames=frame, onPage=self._draw_page)]
        )
        self.regular = regular

    def _draw_page(self, canvas, document):
        canvas.saveState()
        canvas.setFont(self.regular, 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        if document.page > 1:
            canvas.drawString(18 * mm, 12 * mm, "Mini RAG Service | Hồ sơ bàn giao")
            canvas.drawRightString(
                A4[0] - 18 * mm, 12 * mm, f"Trang {document.page}"
            )
            canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
            canvas.line(18 * mm, 16 * mm, A4[0] - 18 * mm, 16 * mm)
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph):
            return
        level = {"ReportH1": 0, "ReportH2": 1, "ReportH3": 2}.get(
            flowable.style.name
        )
        if level is not None:
            text = flowable.getPlainText()
            key = f"h{level}-{self.page}-{id(flowable)}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=False)
            self.notify("TOCEntry", (level, text, self.page))


def p(text: str, style: ParagraphStyle) -> Paragraph:
    """Create a paragraph with safe XML text."""
    return Paragraph(escape(text).replace("\n", "<br/>").replace("  ", "&nbsp; "), style)


def rich(text: str, style: ParagraphStyle) -> Paragraph:
    """Create a paragraph for intentionally limited inline markup."""
    return Paragraph(text, style)


def evidence_image(path: Path, caption: str, regular: str, width: float = 166 * mm):
    """Return a bounded screenshot with a Vietnamese caption."""
    reader = ImageReader(str(path))
    image_width, image_height = reader.getSize()
    height = width * image_height / image_width
    image = Image(str(path), width=width, height=height)
    image.hAlign = "CENTER"
    caption_style = ParagraphStyle(
        "ImageCaption",
        fontName=regular,
        fontSize=8,
        leading=10.5,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#475569"),
        spaceBefore=3,
        spaceAfter=9,
    )
    return KeepTogether([image, Paragraph(escape(caption), caption_style)])


def pipeline_diagram(regular: str) -> Drawing:
    """Draw the end-to-end data and retrieval flow as a clean vector diagram."""
    drawing = Drawing(510, 172)
    labels = [
        ("Tài liệu", "PDF / DOCX / TXT"),
        ("Trích xuất", "Docling + OCR"),
        ("Chuẩn hóa", "làm sạch + chia đoạn"),
        ("Lưu trữ", "vector + metadata"),
        ("Truy xuất", "từ khóa + ngữ nghĩa"),
        ("Trả lời", "bằng chứng + mô hình"),
    ]
    colors_fill = ["#E0F2FE", "#DBEAFE", "#DCFCE7", "#FEF3C7", "#FCE7F3", "#EDE9FE"]
    box_w, box_h, gap = 76, 48, 9
    start_x = 4
    y = 92
    for idx, ((title, subtitle), fill) in enumerate(zip(labels, colors_fill)):
        x = start_x + idx * (box_w + gap)
        drawing.add(Rect(x, y, box_w, box_h, rx=7, ry=7, fillColor=colors.HexColor(fill), strokeColor=colors.HexColor("#64748B"), strokeWidth=0.8))
        drawing.add(String(x + box_w / 2, y + 29, title, fontName="ReportSans-Bold", fontSize=8.2, fillColor=colors.HexColor("#0F172A"), textAnchor="middle"))
        drawing.add(String(x + box_w / 2, y + 14, subtitle, fontName=regular, fontSize=6.4, fillColor=colors.HexColor("#334155"), textAnchor="middle"))
        if idx < len(labels) - 1:
            next_x = x + box_w + 1
            arrow_x = x + box_w + gap - 1
            drawing.add(Line(next_x, y + box_h / 2, arrow_x, y + box_h / 2, strokeColor=colors.HexColor("#0F3D5E"), strokeWidth=1.2))
            drawing.add(Polygon([arrow_x, y + box_h / 2, arrow_x - 5, y + box_h / 2 + 3, arrow_x - 5, y + box_h / 2 - 3], fillColor=colors.HexColor("#0F3D5E"), strokeColor=None))
    drawing.add(String(255, 58, "Mỗi đoạn giữ mã tài liệu, số trang, loại dữ liệu và thông tin nguồn để truy ngược", fontName=regular, fontSize=7.4, fillColor=colors.HexColor("#475569"), textAnchor="middle"))
    drawing.add(Line(4, 45, 506, 45, strokeColor=colors.HexColor("#CBD5E1"), strokeWidth=0.6))
    drawing.add(String(255, 27, "Luồng tải tài liệu và luồng hỏi đáp dùng chung lớp metadata và bằng chứng", fontName="ReportSans-Bold", fontSize=8, fillColor=colors.HexColor("#176B87"), textAnchor="middle"))
    return drawing


def table(data, widths, regular, header=True, small=False):
    font_size = 7.3 if small else 8.1
    leading = 9.2 if small else 10.2
    converted = []
    for row_index, row in enumerate(data):
        converted.append(
            [
                Paragraph(
                    escape(str(value)),
                    ParagraphStyle(
                        "Cell",
                        fontName="ReportSans-Bold" if header and row_index == 0 else regular,
                        fontSize=font_size,
                        leading=leading,
                        textColor=colors.HexColor("#0F172A"),
                    ),
                )
                for value in row
            ]
        )
    result = Table(converted, colWidths=widths, repeatRows=1 if header else 0)
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
    ]
    if header:
        commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F3D5E")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ]
        )
    for row_index in range(1 if header else 0, len(data)):
        if row_index % 2:
            commands.append(
                ("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#F8FAFC"))
            )
    result.setStyle(TableStyle(commands))
    return result


def build():
    regular, _ = register_fonts()
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CoverTitle",
            parent=styles["Title"],
            fontName="ReportSans-Bold",
            fontSize=25,
            leading=31,
            textColor=colors.HexColor("#0F3D5E"),
            alignment=TA_CENTER,
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverSub",
            parent=styles["Normal"],
            fontName=regular,
            fontSize=12,
            leading=17,
            textColor=colors.HexColor("#475569"),
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportH1",
            parent=styles["Heading1"],
            fontName="ReportSans-Bold",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#0F3D5E"),
            spaceBefore=13,
            spaceAfter=8,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ContentsTitle",
            parent=styles["ReportH1"],
            fontName="ReportSans-Bold",
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportH2",
            parent=styles["Heading2"],
            fontName="ReportSans-Bold",
            fontSize=11.5,
            leading=15,
            textColor=colors.HexColor("#176B87"),
            spaceBefore=9,
            spaceAfter=5,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportH3",
            parent=styles["Heading3"],
            fontName="ReportSans-Bold",
            fontSize=9.5,
            leading=12,
            textColor=colors.HexColor("#334155"),
            spaceBefore=7,
            spaceAfter=3,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodyVi",
            parent=styles["BodyText"],
            fontName=regular,
            fontSize=9.2,
            leading=13.2,
            textColor=colors.HexColor("#1E293B"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BulletVi",
            parent=styles["BodyText"],
            fontName=regular,
            fontSize=8.9,
            leading=12.2,
            leftIndent=13,
            firstLineIndent=-8,
            bulletIndent=0,
            textColor=colors.HexColor("#1E293B"),
            spaceAfter=3,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TOCVi",
            parent=styles["Normal"],
            fontName=regular,
            fontSize=10,
            leading=14,
            leftIndent=14,
            firstLineIndent=-14,
            textColor=colors.HexColor("#1E293B"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="Callout",
            parent=styles["BodyText"],
            fontName=regular,
            fontSize=9.2,
            leading=13,
            borderColor=colors.HexColor("#93C5FD"),
            borderWidth=0.6,
            borderPadding=8,
            backColor=colors.HexColor("#EFF6FF"),
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=5,
            spaceAfter=8,
        )
    )

    document = ReportDocument(
        str(OUTPUT),
        regular,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=23 * mm,
        title="Báo cáo milestone và nghiên cứu dữ liệu Mini RAG Service",
        author="Mini RAG Service",
    )
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("TOC0", parent=styles["TOCVi"], leftIndent=0, fontName="ReportSans-Bold"),
        ParagraphStyle("TOC1", parent=styles["TOCVi"], leftIndent=12, fontSize=9),
        ParagraphStyle("TOC2", parent=styles["TOCVi"], leftIndent=24, fontSize=8.5),
    ]

    story = [
        Spacer(1, 32 * mm),
        rich("MINI RAG / HỒ SƠ KỸ THUẬT", styles["CoverSub"]),
        Spacer(1, 7 * mm),
        rich("Luồng dữ liệu và truy xuất tài liệu", styles["CoverTitle"]),
        rich("Các mốc triển khai, bằng chứng kiểm thử và kết quả đánh giá", styles["CoverSub"]),
        Spacer(1, 15 * mm),
        HRFlowable(width="65%", thickness=2, color=colors.HexColor("#F59E0B"), hAlign="CENTER"),
        Spacer(1, 15 * mm),
        rich("Ngày cập nhật: 30/09/2026", styles["CoverSub"]),
        rich('<link href="https://github.com/SharkTien/miniRAG" color="#176B87">Kho mã nguồn trên GitHub: github.com/SharkTien/miniRAG</link>', styles["CoverSub"]),
        Spacer(1, 30 * mm),
        PageBreak(),
        rich("Mục lục", styles["ContentsTitle"]),
        toc,
        PageBreak(),
    ]

    def h1(text):
        story.append(Paragraph(escape(text), styles["ReportH1"]))

    def h2(text):
        story.append(Paragraph(escape(text), styles["ReportH2"]))

    def body(text):
        story.append(p(text, styles["BodyVi"]))

    def bullet(text):
        story.append(Paragraph("• " + escape(text), styles["BulletVi"]))

    h1("3. Các mốc thực hiện")
    h2("Mốc 1 — Luồng dữ liệu")
    body("Đã hoàn thành tải tài liệu, kiểm tra định dạng, lưu kho đối tượng, trích xuất PDF/TXT/DOCX và định dạng mở rộng, nhận dạng ký tự NVIDIA cho bản quét và ảnh, làm sạch, chuẩn hóa ngữ nghĩa có giới hạn thời gian, chia đoạn, tạo vector theo lô, lưu pgvector và xử lý nền.")
    story.append(pipeline_diagram(regular))
    body("Sơ đồ trên là luồng xử lý dữ liệu cuối cùng: tài liệu được trích xuất trước, làm sạch và chia đoạn theo cấu trúc, sau đó mới tạo vector và lưu cùng metadata. Khi hỏi, hệ thống dùng đồng thời điểm từ khóa và điểm ngữ nghĩa, lọc theo tài liệu, xếp hạng bằng chứng rồi mới gửi ngữ cảnh phù hợp cho mô hình trả lời.")
    h3 = lambda text: story.append(Paragraph(escape(text), styles["ReportH3"]))
    h3("Các mô hình và vai trò trong luồng")
    story.append(table([
        ["Thành phần", "Mô hình/công nghệ", "Vai trò"],
        ["Nhận dạng ký tự", "NVIDIA NeMo Retriever OCR v2", "Đọc chữ trong PDF quét, ảnh và vùng bảng khi tài liệu không có lớp chữ."],
        ["Tạo vector", "NVIDIA NeMo Retriever Embed 1B", "Biến câu hỏi và từng đoạn thành vector cùng không gian để tìm kiếm ngữ nghĩa."],
        ["Chuẩn hóa ngữ nghĩa", "Mô hình ngôn ngữ qua NVIDIA NIM", "Chuẩn hóa tiêu đề, quan hệ bảng và tín hiệu truy vấn khi cần; có giới hạn thời gian và thử lại."],
        ["Sinh câu trả lời", "Mô hình ngôn ngữ qua NVIDIA NIM", "Tổng hợp câu trả lời chỉ từ các bằng chứng đã được chọn và trả kèm nguồn."],
        ["Lưu trữ và tìm kiếm", "PostgreSQL + pgvector + toàn văn", "Lưu vector/metadata và kết hợp tìm kiếm ngữ nghĩa với từ khóa."],
    ], [38 * mm, 57 * mm, 83 * mm], regular, small=True))
    bullet("Hồ sơ nghiên cứu dữ liệu được bàn giao kèm báo cáo và dùng làm căn cứ cho các quyết định kỹ thuật.")
    bullet("877 câu hỏi được phân loại theo bảng, biểu mẫu, hình, chú thích và văn bản.")
    bullet("Các phương án OCR, mở rộng tập ứng viên, tìm kiếm kết hợp, xử lý bảng, hình và chú thích được chạy trên cùng bộ câu hỏi.")
    h2("Mốc 2 — API hỏi đáp")
    body("API hỏi đáp, lập kế hoạch truy vấn, tìm kiếm toàn văn kết hợp vector, mở rộng tập ứng viên, lọc danh tính tài liệu, xếp hạng bằng chứng, lời nhắc bám nguồn, trích dẫn nguồn và trả kết quả từng phần đã có trong mã nguồn.")
    h2("Mốc 3 — Đóng gói và kiểm tra tự động")
    body("Dockerfile, Docker Compose cho API, tiến trình nền, PostgreSQL + pgvector, MinIO và giao diện, tệp cấu hình mẫu và quy trình GitHub Actions đã có. Cổng chất lượng đạt 98,8/100; ảnh chụp quy trình nằm ở phần bằng chứng.")
    h2("Mốc 4 — Tài liệu và trình diễn")
    body("README, tài liệu kiến trúc, ví dụ API, kịch bản trình diễn, truy vết yêu cầu, bảng kiểm tra truy xuất và báo cáo PDF này được bàn giao.")

    h1("4. Bằng chứng trực quan từ hệ thống")
    body("Các ảnh dưới đây được lấy từ quá trình chạy thật của hệ thống. Chúng minh họa đường đi của dữ liệu và cấu trúc lưu trữ, không chỉ là sơ đồ khái niệm.")
    story.append(evidence_image(ROOT / "output/images/docker_CICD.png", "Hình 1. Quy trình kiểm tra tự động: các bước chất lượng, giao diện và dựng Docker hoàn tất với trạng thái thành công trong cùng một lần chạy.", regular))
    story.append(evidence_image(ROOT / "output/images/pgvector.png", "Hình 2. Cấu trúc PostgreSQL/pgvector: bảng document_chunks có content dạng text, metadata dạng jsonb, embedding vector(2048), khóa liên kết document_id và chỉ mục theo tài liệu.", regular))
    story.append(evidence_image(ROOT / "output/images/upload.png", "Hình 3. Giao diện kho tài liệu sau khi tải lên: sáu tài liệu đã xuất hiện, tài liệu Shopee được chọn, bản xem trước PDF và phần văn bản đã định dạng được hiển thị cùng số lượng chunk.", regular, width=166 * mm))
    story.append(evidence_image(ROOT / "output/images/chunk.png", "Hình 4. Màn hình xem chunk: nội dung được chia thành các đoạn có thứ tự, giữ tiêu đề, trang và văn bản liên quan để bước truy xuất có thể chọn đúng phần.", regular, width=130 * mm))

    h1("5. Nghiên cứu và xử lý dữ liệu")
    h2("5.1 Hồ sơ dữ liệu")
    body("Benchmark gồm 877 câu hỏi trên 5 PDF. Bảng chiếm 299 câu, biểu mẫu 107, hình 159, chú thích/đánh dấu 285 và văn bản thường 27. Việc phân loại giúp không dùng một chiến lược chunk/OCR cho mọi loại nội dung.")
    story.append(table([
        ["Loại dữ liệu", "Số câu", "Rủi ro cần kiểm soát"],
        ["Bảng", "299", "Mất quan hệ hàng, cột và tiêu đề"],
        ["Biểu mẫu", "107", "Nhãn và giá trị bị tách rời"],
        ["Hình", "159", "Dữ kiện nằm trong sơ đồ/hình"],
        ["Chú thích", "285", "Callout, tô màu, vùng đánh dấu"],
        ["Văn bản", "27", "Header/footer và chunk quá ngắn"],
    ], [35 * mm, 20 * mm, 105 * mm], regular, small=True))
    h2("5.2 Thiết kế phép đo")
    bullet("Document hit: tài liệu đúng xuất hiện trong kết quả.")
    bullet("Content hit: kết quả có đoạn chứa dữ kiện trả lời.")
    bullet("Assertion pass: câu trả lời đúng mệnh đề được kiểm tra.")
    body("Ba chỉ số được đọc cùng nhau. Document hit cao nhưng content hit thấp nghĩa là hệ thống biết tên tài liệu nhưng chưa tìm được bằng chứng; content hit có nhưng assertion pass thấp chỉ ra vấn đề ở bước tổng hợp hoặc diễn đạt.")
    h2("5.3 So sánh phương án")
    story.append(table([
        ["Phương án", "Kết quả", "Quyết định"],
        ["Ban đầu", "85,52% document; 33,52% content; 18,59% pass", "Mốc"],
        ["OCR toàn trang", "34,44% content; 19,73% pass", "Giữ"],
        ["OCR + ứng viên x8", "88,26% document; 37,66% content", "Giữ"],
        ["Hybrid dense + lexical", "90,65% document; 41,33% content; 23,72% pass", "Baseline"],
        ["Structured table toàn cục", "Content còn 36,85%", "Loại"],
        ["Visual element + region OCR", "Figure 34/159 hit; 19/159 pass", "Giữ cho hình"],
        ["OCR tile cố định", "Annotation 92/285 hit, thấp hơn tuyến ngữ cảnh", "Loại"],
    ], [53 * mm, 72 * mm, 35 * mm], regular, small=True))
    h2("5.4 Quyết định kỹ thuật từ dữ liệu")
    bullet("Tài liệu quét: OCR toàn trang NVIDIA có timeout và fallback để không treo job.")
    bullet("Bảng: giữ quan hệ tiêu đề–hàng–cột, thêm chunk cha và điều hướng theo câu hỏi.")
    bullet("Hình: lưu crop, page, bbox và metadata; benchmark cho thấy chỉ mục phần tử riêng tốt hơn gắn ảnh vào chunk trang.")
    bullet("Chú thích: không mặc định dùng OCR lát cắt cố định; cần detector theo hình học và quan hệ vùng đánh dấu.")
    bullet("Truy xuất: kết hợp dense và lexical, mở rộng tập ứng viên rồi mới rerank theo khả năng trả lời.")

    h1("6. Kiểm thử đơn vị và kiểm thử API")
    body("Lệnh kiểm tra chính là ruff check app tests, python -m compileall -q app tests và python -m pytest -q tests. Kết quả gần nhất: 22 kiểm thử đạt; kiểm thử gọi dịch vụ NVIDIA trực tiếp được bỏ qua khi môi trường không có khóa API, còn các kiểm thử ngoại tuyến vẫn chạy bình thường.")
    h2("6.1 Kiểm thử thành phần lõi")
    body("Mục tiêu: bảo đảm dữ liệu đầu vào được làm sạch và chia đúng trước khi tạo vector. Mẫu kiểm tra: chuỗi có khoảng trắng thừa, ba dòng xuống dòng liên tiếp và một ký tự điều khiển phải trở thành một dòng trống đúng chuẩn; đoạn văn có số trang và tiêu đề phải giữ lại trang/phần; hộp giới hạn phải được chuẩn hóa về cùng hệ tọa độ. Nếu một ký tự điều khiển làm thay đổi nội dung hoặc mất số trang, kiểm thử thất bại.")
    h2("6.2 Kiểm thử hợp đồng API")
    body("Mục tiêu: xác nhận dịch vụ phản hồi đúng khi người dùng gọi API. Mẫu kiểm tra trạng thái hoạt động: gửi GET /health và yêu cầu mã phản hồi thành công cùng trạng thái dịch vụ cơ sở dữ liệu. Mẫu hỏi đáp: gửi POST /query với câu hỏi hợp lệ và kiểm tra có câu trả lời cùng nguồn. Mẫu lỗi: câu hỏi rỗng phải trả lỗi 400; tệp ngoài PDF/TXT/DOCX phải bị từ chối; tệp hợp lệ phải trả trạng thái queued và mã tài liệu; truy vấn không có bằng chứng phải trả sources rỗng, không dựng nguồn giả.")
    h2("6.3 Kiểm thử xếp hạng bằng chứng")
    body("Mục tiêu: đoạn chứa dữ kiện quyết định phải đứng trên đoạn chỉ trùng chủ đề. Mẫu kiểm tra: với câu hỏi về thời gian hoàn tiền thẻ NAPAS, đoạn có “2–5 ngày làm việc” phải vượt đoạn chỉ nói thời hạn trả hàng; đổi tên tệp nhưng giữ nguyên nội dung không được làm thay đổi điểm nội dung. Kiểm thử cũng xác nhận đoạn Kamereo, Microsoft hoặc chính sách bảo hành khác không lọt vào khi câu hỏi chỉ hỏi Shopee.")
    h2("6.4 Kiểm thử nhận dạng ký tự và định tuyến")
    body("Mục tiêu: chọn đúng cách đọc theo loại tài liệu. Mẫu kiểm tra: PDF đã có lớp chữ phải đi đường tắt, PDF quét phải chuyển sang OCR NVIDIA, dấu tiếng Việt phải được sửa khi OCR trả ký tự lỗi, vùng bảng phải giữ hộp giới hạn và hệ thống phải dừng đúng thời gian khi mô hình OCR chậm. Văn bản sau OCR phải được đánh dấu phương pháp trích xuất và độ tin cậy để có thể kiểm tra lại.")
    h2("6.5 Kiểm thử kết nối mô hình NVIDIA")
    body("Mục tiêu: kiểm tra cấu hình, chia lô và khả năng thử lại mà không bắt buộc gọi dịch vụ trực tuyến trong mọi lần chạy. Mẫu kiểm tra: đọc đúng mô hình, chia trang thành các lô có kích thước giới hạn, giữ thứ tự trang sau khi xử lý song song, và từ chối câu trả lời không có bằng chứng. Khi thiếu khóa truy cập, phần gọi trực tuyến được bỏ qua có chủ đích; các kiểm thử ngoại tuyến vẫn phải đạt.")
    h2("6.6 Kiểm chứng truy xuất")
    body("Mục tiêu: kiểm tra độc lập việc tạo vector và tìm đúng đoạn. Mẫu kiểm tra gồm các câu hỏi về thời hạn hoàn tiền, phí trả hàng, chính sách bảo hành, hotline và xử lý hàng lỗi; mỗi câu lưu lại tài liệu mong đợi, tài liệu nhận được, câu trả lời mong đợi và câu trả lời thực tế để đánh giá ở mục 8.")
    body("Kiểm thử API dùng dịch vụ giả lập để kiểm tra hợp đồng phản hồi: câu trả lời phải đi kèm sources; câu hỏi rỗng phải bị từ chối; truy vấn không có bằng chứng không được sinh nguồn giả; file không hỗ trợ phải trả lỗi; upload hợp lệ phải trả trạng thái queued.")

    h1("7. Cấu hình và nguồn sự thật")
    body("Cấu hình được tách khỏi mã nghiệp vụ. Tệp cấu hình mẫu chỉ chứa giá trị mẫu; giá trị thật được nạp từ môi trường và không đưa vào mã nguồn. Bộ đọc cấu hình kiểm tra kiểu dữ liệu và cung cấp giá trị mặc định cho máy phát triển.")
    story.append(table([
        ["Nhóm", "Biến cấu hình", "Tác dụng"],
        ["Kết nối", "DATABASE_URL, POSTGRES_DB, POSTGRES_USER", "Kết nối PostgreSQL/pgvector và tên cơ sở dữ liệu"],
        ["Mô hình", "EMBEDDING_MODEL, EMBEDDING_DIM, LLM_MODEL", "Mô hình tạo vector, số chiều và mô hình sinh"],
        ["Chia đoạn", "CHUNK_SIZE, CHUNK_OVERLAP", "Kích thước đoạn và phần chồng lấn"],
        ["Truy xuất", "TOP_K, RETRIEVAL_CANDIDATE_MULTIPLIER, SIMILARITY_THRESHOLD", "Số bằng chứng, tập ứng viên và ngưỡng lọc"],
        ["OCR", "NVIDIA_OCR_MODEL, NVIDIA_OCR_TIMEOUT_SECONDS, NVIDIA_OCR_BATCH_SIZE", "Mô hình, thời gian chờ và kích thước lô OCR"],
        ["Chuẩn hóa", "NIM_MODEL, NIM_REQUEST_TIMEOUT_SECONDS, NIM_MAX_RETRIES", "Mô hình ngữ nghĩa, thời gian chờ và số lần thử lại"],
    ], [35 * mm, 78 * mm, 63 * mm], regular, small=True))
    body("Khi triển khai, chỉ cần thay các biến môi trường và khởi động lại dịch vụ. Luồng xử lý không cần sửa mã nguồn để đổi mô hình, kích thước đoạn, số lượng kết quả hay thời gian chờ.")

    h1("8. Đánh giá từng trường hợp kiểm tra truy xuất")
    body("Bảng kiểm tra truy xuất có 8 câu hỏi có dữ liệu; hai dòng cuối để trống nên không được tính là trường hợp kiểm tra. Cách đánh giá: Đạt khi câu trả lời chứa đủ ý chính và không mâu thuẫn; Đạt một phần khi có ý chính nhưng thiếu điều kiện hoặc thêm thông tin chưa có căn cứ; Chưa đạt khi mâu thuẫn với đáp án hoặc bỏ sót dữ kiện quyết định.")
    retrieval_cases = [
        ("1. Hoàn tiền bằng thẻ NAPAS", "shopee trả hàng thẻ napas mấy ngày tiền về ví vậy", "Sau khi Shopee xác nhận hoàn tiền, tiền về thẻ hoặc tài khoản liên kết trong 2–5 ngày làm việc; thứ bảy, chủ nhật và ngày lễ không tính.", "Hệ thống trả đúng 2–5 ngày và đúng thẻ NAPAS, nhưng chưa nói rõ mốc tính từ lúc xác nhận đã hoàn tiền và chưa có ví dụ ngày làm việc.", "Đạt một phần"),
        ("2. Shop giao sai hàng và phí trả hàng", "Shop giao sai đồ, chọn bưu tá hay bưu cục có mất phí không và điều kiện được hỗ trợ cước là gì?", "Lấy hàng tại nhà và gửi tại bưu cục được miễn phí; tự sắp xếp thì trả trước rồi được hỗ trợ khi đủ điều kiện. Cần yêu cầu được chấp nhận, mã vận đơn hợp lệ và thông tin trả hàng đầy đủ.", "Hệ thống đã phân biệt ba cách gửi, nêu điều kiện chấp nhận, mã vận đơn và thời hạn yêu cầu.", "Đạt"),
        ("3. Đổi riêng áo lỗi trong một bộ", "Mua bộ áo quần, áo lỗi sau 5 ngày; có đổi hoặc hoàn riêng áo không?", "Được báo lỗi trong 7 ngày, nhưng chính sách chưa nói rõ có tách riêng áo khỏi bộ hay phải gửi cả bộ.", "Hệ thống khẳng định được gửi riêng áo và hoàn tiền toàn bộ, vượt quá bằng chứng.", "Chưa đạt"),
        ("4. Phụ kiện Adore", "Phụ kiện không được bảo hành trọn đời thì lỗi do nhà sản xuất trong 7 ngày có được đổi không?", "Phụ kiện không thuộc bảo hành trọn đời; chính sách cung cấp chưa đủ để kết luận chắc chắn nhánh đổi hàng lỗi có áp dụng cho phụ kiện.", "Hệ thống khẳng định chắc chắn được đổi trong 7 ngày, đồng thời trộn điều kiện bảo hành với đổi hàng.", "Chưa đạt"),
        ("5. Bảo hành biến tần GD100-PV", "Biến tần bơm năng lượng mặt trời GD100-PV được bảo hành bao lâu và tính từ ngày nào?", "Thời hạn 1,5 năm, tính từ ngày giao hàng ghi trên hóa đơn hoặc phiếu giao hàng.", "Hệ thống trả đúng thời hạn và mốc bắt đầu, nhưng thêm các điều kiện phụ không cần thiết.", "Đạt một phần"),
        ("6. Inverter gửi tới Nguyễn Văn Quá", "Gửi inverter hòa lưới tới trạm Nguyễn Văn Quá mất bao lâu, ai chịu cước và máy nứt vỡ xử lý thế nào?", "Hoàn tất sửa chữa trong 24 giờ làm việc từ lúc nhận thiết bị; khách chịu cước gửi đến trung tâm; nếu không đủ điều kiện bảo hành thì báo giá, khách đồng ý mới sửa và chịu cước gửi về; nếu đủ điều kiện thì trung tâm chịu cước gửi trả.", "Hệ thống thiếu mốc 24 giờ, thiếu quy trình báo giá khi nứt vỡ và chỉ trả một phần cước.", "Chưa đạt"),
        ("7. Hotline Kamereo", "Cho xin số hotline khiếu nại và đổi hàng Kamereo.", "Hotline 0812 46 37 27.", "Hệ thống trả đúng số hotline nhưng thêm các mốc xử lý chỉ nên nêu khi có bằng chứng tương ứng.", "Đạt một phần"),
        ("8. Rau củ dập úng sau 14 giờ", "Nhận rau lúc 15 giờ 30, hàng dập úng; có được trừ ngay công nợ hay phải xử lý thế nào?", "Không trừ ngay công nợ; sau 14 giờ chỉ đổi hoặc bù ở đơn kế tiếp sau khi gửi thông tin và hình ảnh để xác minh.", "Hệ thống trả đúng nguyên tắc không trừ tiền ngay, đổi/bù ở đơn kế tiếp và yêu cầu cung cấp bằng chứng.", "Đạt"),
    ]
    for title, question, expected, observed, verdict in retrieval_cases:
        story.append(Paragraph(escape(title), styles["ReportH2"]))
        story.append(rich(f"<b>Câu hỏi:</b> {escape(question)}", styles["BodyVi"]))
        story.append(rich(f"<b>Đáp án chuẩn:</b> {escape(expected)}", styles["BodyVi"]))
        story.append(rich(f"<b>Kết quả hệ thống:</b> {escape(observed)}", styles["BodyVi"]))
        story.append(rich(f"<b>Đánh giá:</b> {escape(verdict)}", styles["BodyVi"]))
    body("Kết quả tổng hợp: 2/8 câu đạt đầy đủ, 3/8 câu đạt một phần và 3/8 câu chưa đạt. Các lỗi chính là bỏ sót đoạn chứa dữ kiện quyết định, trộn hai chính sách khác nhau và suy diễn khi tài liệu chưa đủ căn cứ.")

    h1("9. Cách tạo source trong câu trả lời")
    body("Source không do mô hình sinh tự đặt ra. Dịch vụ hỏi đáp lấy source từ những chunk đã vượt qua truy xuất kết hợp, lọc danh tính tài liệu, phân bố điểm và xếp hạng bằng chứng. Với mỗi chunk được chọn, hệ thống tạo một khối bằng chứng có tên file, mã chunk và trang trước khi gọi mô hình.")
    story.append(table([
        ["Trường trong source", "Ý nghĩa"],
        ["file_name, document_id", "Tài liệu và bản ghi tài liệu gốc"],
        ["chunk_id, page, page_start, page_end", "Đoạn và vị trí có thể mở lại để kiểm tra"],
        ["dense_score, bm25_score, similarity_score", "Điểm vector, điểm từ khóa và điểm tương đồng"],
        ["query_compatibility_score, answerability_score", "Mức phù hợp với câu hỏi và khả năng chứa dữ kiện trả lời"],
        ["source_locator, element_ids, section", "Vị trí, phần tử bố cục và mục nội dung"],
        ["extraction_method, ocr_confidence, snippet", "Cách lấy dữ liệu, độ tin cậy OCR và đoạn xem nhanh"],
    ], [62 * mm, 116 * mm], regular, small=True))
    body("Trong prompt, bằng chứng được đánh dấu dạng [EVIDENCE #... | File... | Chunk... | Trang...]. Sau khi mô hình sinh câu trả lời, API trả lại answer cùng mảng sources; nếu không có bằng chứng thì sources rỗng và hệ thống không dựng nguồn giả.")

    h1("10. Bằng chứng nghiệm thu")
    h2("Mã nguồn và đóng gói")
    body("Các tệp đóng gói Docker mô tả API, tiến trình nền, PostgreSQL + pgvector, kho đối tượng và giao diện. Lệnh docker compose config --quiet kiểm tra cú pháp trước khi chạy; ảnh Hình 1 cho thấy các bước chất lượng, giao diện và Docker đã chạy thành công trên GitHub Actions.")
    h2("Tải và xử lý tài liệu")
    body("POST /documents nhận PDF, TXT và DOCX, ghi bản ghi queued rồi để tiến trình nền trích xuất, làm sạch, chia đoạn, tạo vector và lưu metadata. Hình 3 cho thấy tài liệu xuất hiện trong kho; Hình 4 cho thấy đoạn văn sau khi chia. Kiểm thử API xác nhận file không hỗ trợ bị từ chối và file hợp lệ trả queued.")
    h2("Lưu vector và metadata")
    body("Hình 2 là bằng chứng trực tiếp từ PostgreSQL: document_chunks có content, metadata jsonb và embedding vector(2048), cùng khóa ngoại về documents. File gốc nằm ở MinIO; object_key trong documents liên kết bản ghi với file.")
    h2("API hỏi đáp và nguồn")
    body("POST /query trả answer cùng sources; POST /query/stream gửi token trước rồi gửi metadata nguồn. Kiểm thử API bao phủ câu hỏi hợp lệ, câu hỏi rỗng và câu hỏi không có bằng chứng. Nguồn được tạo từ chunk đã chọn, không phải văn bản do mô hình tự đặt.")
    h2("Kiểm tra tự động và tài liệu")
    body("Ruff, biên dịch, 22 kiểm thử, bản dựng giao diện và kiểm tra Docker là các bằng chứng có thể chạy lại. README, tài liệu kiến trúc, hồ sơ nghiên cứu dữ liệu và bảng kiểm tra truy xuất được bàn giao cùng mã nguồn. Quy trình CI cần được xác nhận lại sau mỗi lần thay đổi.")

    h1("11. Hạn chế và kế hoạch tiếp theo")
    bullet("Bộ đánh giá hiện tập trung 5 PDF SynthDocQA; cần thêm bộ tài liệu thực tế cân bằng theo loại dữ liệu.")
    bullet("Chỉ mục phần tử hình và OCR vùng chú thích chưa bật cho mọi tài liệu vận hành.")
    bullet("Bộ xếp hạng hiện dựa trên luật; chưa có mô hình xếp hạng học từ phản hồi người dùng.")
    bullet("Cần nạp lại tài liệu, chạy đánh giá hồi quy và theo dõi độ trễ, tỷ lệ OCR dự phòng, tỷ lệ không có bằng chứng theo loại dữ liệu.")
    body("Chi tiết phương pháp, phân tích lỗi, bảng kết quả đầy đủ và quy trình tái lập nằm trong hồ sơ nghiên cứu dữ liệu. File PDF này là bản trình bày có dẫn chứng; hồ sơ nghiên cứu là nơi lưu giải thích đầy đủ.")

    document.multiBuild(story)
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
