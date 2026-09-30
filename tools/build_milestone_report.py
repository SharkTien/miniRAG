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
        rich("BÁO CÁO BÀN GIAO", styles["CoverSub"]),
        Spacer(1, 7 * mm),
        rich("Mini RAG Service", styles["CoverTitle"]),
        rich("Các mốc, tiêu chí nghiệm thu, tiêu chí đánh giá và nghiên cứu xử lý dữ liệu", styles["CoverSub"]),
        Spacer(1, 15 * mm),
        HRFlowable(width="65%", thickness=2, color=colors.HexColor("#F59E0B"), hAlign="CENTER"),
        Spacer(1, 15 * mm),
        rich("Vai trò trình bày: kỹ sư dữ liệu / nhà khoa học dữ liệu", styles["CoverSub"]),
        rich("Ngày cập nhật: 30/09/2026", styles["CoverSub"]),
        rich("Mã commit: 05185d9", styles["CoverSub"]),
        rich('<link href="https://github.com/SharkTien/miniRAG" color="#176B87">Kho mã nguồn trên GitHub: github.com/SharkTien/miniRAG</link>', styles["CoverSub"]),
        Spacer(1, 25 * mm),
        rich("Tài liệu này nhấn mạnh cách dữ liệu được khảo sát, đo lường, chuẩn hóa và đưa vào quyết định kỹ thuật của hệ thống RAG.", styles["Callout"]),
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

    h1("1. Tóm tắt điều hành")
    body("Báo cáo đối chiếu mã commit 05185d9 với bốn mốc trong SUBJECT.md. Trọng tâm là nghiên cứu dữ liệu: phân loại nội dung, kiểm tra chất lượng sau trích xuất/OCR, đánh giá theo loại dữ liệu và truy vết quyết định đưa vào hệ thống.")
    body("Trên bộ 5 PDF SynthDocQA với 877 câu hỏi, cấu hình tốt nhất tìm đúng tài liệu 90,65%, tìm đúng nội dung 41,33% và đạt đúng mệnh đề 23,72%. Đây là số liệu của bộ đánh giá chuyên biệt, không phải cam kết cho mọi tài liệu thực tế.")
    story.append(rich("Điểm cần xem trong báo cáo: dữ liệu được khảo sát trước khi chọn cách xử lý; lỗi trích xuất, lỗi lập chỉ mục và lỗi truy xuất được tách riêng; kết quả theo bảng, biểu mẫu, hình, chú thích và văn bản được dùng để thay đổi luồng xử lý.", styles["Callout"]))

    h1("2. Sơ đồ luồng dữ liệu")
    story.append(pipeline_diagram(regular))
    body("Khi tải tài liệu, hệ thống lưu file gốc, trích xuất bố cục, nhận dạng phần chữ trên bản quét, làm sạch và chia thành các đoạn có nguồn gốc. Mỗi đoạn được tạo vector và lưu cùng metadata trong PostgreSQL. Khi đặt câu hỏi, hệ thống kết hợp tìm kiếm từ khóa và vector, lọc bằng chứng rồi mới gửi phần ngữ cảnh đã chọn tới mô hình sinh.")

    h1("3. Các mốc thực hiện")
    h2("Mốc 1 — Luồng dữ liệu")
    body("Đã hoàn thành tải tài liệu, kiểm tra định dạng, lưu MinIO, trích xuất PDF/TXT/DOCX và định dạng mở rộng, OCR NVIDIA cho bản quét/ảnh, làm sạch, chuẩn hóa ngữ nghĩa có giới hạn thời gian, chia đoạn, tạo vector theo lô, lưu pgvector và xử lý nền.")
    bullet("Hồ sơ nghiên cứu dữ liệu nằm tại docs/report.md.")
    bullet("877 câu hỏi được phân loại theo bảng, biểu mẫu, hình, chú thích và văn bản.")
    bullet("Các phương án OCR, mở rộng tập ứng viên, tìm kiếm kết hợp, xử lý bảng, hình và chú thích được chạy trên cùng bộ câu hỏi.")
    h2("Mốc 2 — API hỏi đáp")
    body("API hỏi đáp, lập kế hoạch truy vấn, tìm kiếm toàn văn kết hợp vector, mở rộng tập ứng viên, lọc danh tính tài liệu, xếp hạng bằng chứng, lời nhắc bám nguồn, trích dẫn nguồn và trả kết quả từng phần đã có trong mã nguồn.")
    h2("Mốc 3 — Đóng gói và kiểm tra tự động")
    body("Dockerfile, Docker Compose cho API, tiến trình nền, PostgreSQL + pgvector, MinIO và giao diện, tệp .env.example và quy trình GitHub Actions đã có. Cổng chất lượng trên máy phát triển đạt 98,8/100; ảnh chụp quy trình nằm ở phần bằng chứng.")
    h2("Mốc 4 — Tài liệu và trình diễn")
    body("README, tài liệu kiến trúc, ví dụ API, kịch bản trình diễn, truy vết yêu cầu, bảng kiểm tra truy xuất và báo cáo PDF này được bàn giao.")

    h1("4. Bằng chứng trực quan từ hệ thống")
    body("Các ảnh dưới đây được lấy từ quá trình chạy thật trong repository. Chúng minh họa đường đi của dữ liệu và cấu trúc lưu trữ, không chỉ là sơ đồ khái niệm.")
    story.append(evidence_image(ROOT / "output/images/docker_CICD.png", "Hình 1. Quy trình kiểm tra tự động sau lần đẩy mã 975ec77: hai nhánh quality và frontend hoàn tất trước bước docker; toàn bộ quy trình có trạng thái Success và thời lượng 7 phút 10 giây.", regular))
    story.append(evidence_image(ROOT / "output/images/pgvector.png", "Hình 2. Cấu trúc PostgreSQL/pgvector: bảng document_chunks có content dạng text, metadata dạng jsonb, embedding vector(2048), khóa liên kết document_id và chỉ mục theo tài liệu.", regular))
    story.append(evidence_image(ROOT / "output/images/upload.png", "Hình 3. Giao diện kho tài liệu sau khi tải lên: sáu tài liệu đã xuất hiện, tài liệu Shopee được chọn, bản xem trước PDF và phần văn bản đã định dạng được hiển thị cùng số lượng chunk.", regular, width=166 * mm))
    story.append(evidence_image(ROOT / "output/images/chunk.png", "Hình 4. Màn hình xem chunk: nội dung được chia thành các đoạn có thứ tự, giữ tiêu đề, trang và văn bản liên quan để bước truy xuất có thể chọn đúng phần.", regular, width=130 * mm))

    h1("5. Nghiên cứu và xử lý dữ liệu")
    h2("3.1 Hồ sơ dữ liệu")
    body("Benchmark gồm 877 câu hỏi trên 5 PDF. Bảng chiếm 299 câu, biểu mẫu 107, hình 159, chú thích/đánh dấu 285 và văn bản thường 27. Việc phân loại giúp không dùng một chiến lược chunk/OCR cho mọi loại nội dung.")
    story.append(table([
        ["Loại dữ liệu", "Số câu", "Rủi ro cần kiểm soát"],
        ["Bảng", "299", "Mất quan hệ hàng, cột và tiêu đề"],
        ["Biểu mẫu", "107", "Nhãn và giá trị bị tách rời"],
        ["Hình", "159", "Dữ kiện nằm trong sơ đồ/hình"],
        ["Chú thích", "285", "Callout, tô màu, vùng đánh dấu"],
        ["Văn bản", "27", "Header/footer và chunk quá ngắn"],
    ], [35 * mm, 20 * mm, 105 * mm], regular, small=True))
    h2("3.2 Thiết kế phép đo")
    bullet("Document hit: tài liệu đúng xuất hiện trong kết quả.")
    bullet("Content hit: kết quả có đoạn chứa dữ kiện trả lời.")
    bullet("Assertion pass: câu trả lời đúng mệnh đề được kiểm tra.")
    body("Ba chỉ số được đọc cùng nhau. Document hit cao nhưng content hit thấp nghĩa là hệ thống biết tên tài liệu nhưng chưa tìm được bằng chứng; content hit có nhưng assertion pass thấp chỉ ra vấn đề ở bước tổng hợp hoặc diễn đạt.")
    h2("3.3 So sánh phương án")
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
    h2("3.4 Quyết định kỹ thuật từ dữ liệu")
    bullet("Tài liệu quét: OCR toàn trang NVIDIA có timeout và fallback để không treo job.")
    bullet("Bảng: giữ quan hệ tiêu đề–hàng–cột, thêm chunk cha và điều hướng theo câu hỏi.")
    bullet("Hình: lưu crop, page, bbox và metadata; benchmark cho thấy chỉ mục phần tử riêng tốt hơn gắn ảnh vào chunk trang.")
    bullet("Chú thích: không mặc định dùng OCR lát cắt cố định; cần detector theo hình học và quan hệ vùng đánh dấu.")
    bullet("Truy xuất: kết hợp dense và lexical, mở rộng tập ứng viên rồi mới rerank theo khả năng trả lời.")

    h1("6. Kiểm thử đơn vị và kiểm thử API")
    body("Lệnh kiểm tra chính là ruff check app tests, python -m compileall -q app tests và python -m pytest -q tests. Kết quả gần nhất: 22 kiểm thử đạt; kiểm thử gọi dịch vụ NVIDIA trực tiếp được bỏ qua khi môi trường không có khóa API, còn các kiểm thử ngoại tuyến vẫn chạy bình thường.")
    story.append(table([
        ["Tệp kiểm thử", "Nội dung kiểm tra", "Bằng chứng"],
        ["test_core_components.py", "Cấu hình, làm sạch ký tự, chia đoạn giữ trang/section, chuẩn hóa bbox", "4 kiểm thử"],
        ["test_api.py", "Đường dẫn sức khỏe, hỏi đáp có nguồn, câu hỏi rỗng, không có bằng chứng, định dạng file và trạng thái queued", "6 kiểm thử"],
        ["test_evidence_service.py", "Loại đoạn chỉ giống chủ đề, giữ đoạn đủ dữ kiện và bảo đảm tên file không làm đổi điểm nội dung", "3 kiểm thử"],
        ["test_ocr_routing.py", "Đường tắt PDF có lớp chữ, sửa dấu tiếng Việt, chống mở rộng bịa đặt, giữ bbox và chính sách nhà cung cấp", "5 kiểm thử"],
        ["test_nim_parallel.py", "Đọc cấu hình, chia trang, kiểm tra chống bịa đặt; gọi NVIDIA trực tiếp là phần tùy chọn", "3 kiểm thử ngoại tuyến + 1 tùy chọn"],
        ["test_query_rag.py", "Bộ kiểm tra truy xuất cục bộ và tạo vector phục vụ kiểm chứng thủ công", "Tập kiểm tra bổ sung"],
    ], [42 * mm, 100 * mm, 34 * mm], regular, small=True))
    body("Kiểm thử API dùng dịch vụ giả lập để kiểm tra hợp đồng phản hồi: câu trả lời phải đi kèm sources; câu hỏi rỗng phải bị từ chối; truy vấn không có bằng chứng không được sinh nguồn giả; file không hỗ trợ phải trả lỗi; upload hợp lệ phải trả trạng thái queued.")

    h1("7. Cấu hình và nguồn sự thật")
    body("Cấu hình được tách khỏi mã nghiệp vụ. Tệp .env.example chỉ chứa giá trị mẫu; giá trị thật nằm trong .env và không được đưa vào mã commit. app/config/settings.py đọc biến môi trường, kiểm tra kiểu dữ liệu và cung cấp giá trị mặc định cho máy phát triển.")
    story.append(table([
        ["Nhóm", "Biến cấu hình", "Tác dụng"],
        ["Kết nối", "DATABASE_URL, POSTGRES_DB, POSTGRES_USER", "Kết nối PostgreSQL/pgvector và tên cơ sở dữ liệu"],
        ["Mô hình", "EMBEDDING_MODEL, EMBEDDING_DIM, LLM_MODEL", "Mô hình tạo vector, số chiều và mô hình sinh"],
        ["Chia đoạn", "CHUNK_SIZE, CHUNK_OVERLAP", "Kích thước đoạn và phần chồng lấn"],
        ["Truy xuất", "TOP_K, RETRIEVAL_CANDIDATE_MULTIPLIER, SIMILARITY_THRESHOLD", "Số bằng chứng, tập ứng viên và ngưỡng lọc"],
        ["OCR", "NVIDIA_OCR_MODEL, NVIDIA_OCR_TIMEOUT_SECONDS, NVIDIA_OCR_BATCH_SIZE", "Mô hình, thời gian chờ và kích thước lô OCR"],
        ["Chuẩn hóa", "NIM_MODEL, NIM_REQUEST_TIMEOUT_SECONDS, NIM_MAX_RETRIES", "Mô hình ngữ nghĩa, thời gian chờ và số lần thử lại"],
    ], [35 * mm, 78 * mm, 63 * mm], regular, small=True))
    body("Khi triển khai, chỉ cần thay .env và khởi động lại dịch vụ. Luồng xử lý không cần sửa mã nguồn để đổi mô hình, kích thước đoạn, số lượng kết quả hay thời gian chờ.")

    h1("8. Đánh giá từng trường hợp kiểm tra truy xuất")
    body("Bảng tính output/retrieval_verification.xlsx có 8 câu hỏi có dữ liệu; hai dòng cuối để trống nên không được tính là trường hợp kiểm tra. Cách đánh giá: Đạt khi câu trả lời chứa đủ ý chính và không mâu thuẫn; Đạt một phần khi có ý chính nhưng thiếu điều kiện hoặc thêm thông tin chưa có căn cứ; Chưa đạt khi mâu thuẫn với đáp án hoặc bỏ sót dữ kiện quyết định.")
    retrieval_cases = [
        ("1. Hoàn tiền bằng thẻ NAPAS", "Đạt một phần", "Đã trả đúng mốc 2–5 ngày làm việc và đúng phương thức hoàn về thẻ NAPAS. Còn thiếu điều kiện mốc tính từ lúc Shopee xác nhận đã hoàn tiền và phần minh họa ngày làm việc."),
        ("2. Shop giao sai hàng và phí trả hàng", "Đạt", "Đã phân biệt lấy tại nhà, gửi tại bưu cục và tự sắp xếp; nêu điều kiện chấp nhận và mã vận đơn. Đây là câu trả lời đáp ứng các ý chính trong đáp án kiểm tra."),
        ("3. Đổi riêng áo lỗi trong một bộ", "Chưa đạt", "Câu trả lời khẳng định được gửi riêng áo và hoàn tiền toàn bộ, trong khi bằng chứng không đủ để kết luận có tách bộ hay không. Đây là lỗi suy diễn vượt nguồn."),
        ("4. Phụ kiện Adore có được đổi không", "Chưa đạt", "Câu trả lời khẳng định chắc chắn được đổi trong 7 ngày, trong khi đáp án yêu cầu nêu rõ phần chính sách cung cấp chưa xác định được trường hợp phụ kiện. Đây là lỗi trộn bảo hành với đổi hàng."),
        ("5. Bảo hành biến tần GD100-PV", "Đạt một phần", "Đã nêu đúng thời hạn 1,5 năm và mốc tính từ ngày giao hàng. Phần điều kiện, địa điểm và mô tả phụ thêm không có căn cứ nên cần loại bỏ khi trả lời người dùng."),
        ("6. Inverter gửi tới Nguyễn Văn Quá", "Chưa đạt", "Chưa trả đúng thời gian 24 giờ làm việc, chưa nêu quy trình báo giá khi máy nứt vỡ và chỉ trả một phần thông tin cước. Đây là thiếu dữ kiện quyết định."),
        ("7. Hotline khiếu nại Kamereo", "Đạt một phần", "Đã trả đúng số 0812 46 37 27. Các mốc 4 giờ, 8 giờ và yêu cầu bổ sung cần được giữ lại chỉ khi có đúng chunk chính sách làm căn cứ."),
        ("8. Rau củ dập úng sau 14 giờ", "Đạt", "Đã trả đúng nguyên tắc không trừ tiền ngay, chỉ đổi hoặc bù ở đơn tiếp theo và yêu cầu gửi thông tin, hình ảnh để xác minh."),
    ]
    for title, verdict, explanation in retrieval_cases:
        story.append(KeepTogether([
            Paragraph(escape(title), styles["ReportH2"]),
            rich(f"<b>Kết luận kiểm tra:</b> {escape(verdict)}", styles["BodyVi"]),
            p(explanation, styles["BodyVi"]),
        ]))
    body("Kết quả tổng hợp: 2/8 câu đạt đầy đủ, 3/8 câu đạt một phần và 3/8 câu chưa đạt. Các trường hợp chưa đạt đều liên quan đến việc mô hình suy diễn khi bằng chứng thiếu hoặc trộn hai chính sách khác nhau; đây là lý do hệ thống phải giữ lọc tài liệu, chấm khả năng trả lời và bắt buộc trích nguồn.")

    h1("9. Cách tạo source trong câu trả lời")
    body("Source không do mô hình sinh tự đặt ra. RagService lấy source từ những chunk đã vượt qua truy xuất kết hợp, lọc danh tính tài liệu, phân bố điểm và xếp hạng bằng chứng. Với mỗi chunk được chọn, hệ thống tạo một khối bằng chứng có tên file, mã chunk và trang trước khi gọi mô hình.")
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
    body("Dockerfile và docker-compose.yml mô tả API, tiến trình nền, PostgreSQL + pgvector, MinIO và giao diện. Lệnh docker compose config --quiet kiểm tra cú pháp trước khi chạy; ảnh Hình 1 cho thấy quy trình quality, frontend và docker đã chạy thành công trên GitHub Actions ở commit 975ec77.")
    h2("Tải và xử lý tài liệu")
    body("POST /documents nhận PDF, TXT và DOCX, ghi bản ghi queued rồi để tiến trình nền trích xuất, làm sạch, chia đoạn, tạo vector và lưu metadata. Hình 3 cho thấy tài liệu xuất hiện trong kho; Hình 4 cho thấy đoạn văn sau khi chia. Kiểm thử API xác nhận file không hỗ trợ bị từ chối và file hợp lệ trả queued.")
    h2("Lưu vector và metadata")
    body("Hình 2 là bằng chứng trực tiếp từ PostgreSQL: document_chunks có content, metadata jsonb và embedding vector(2048), cùng khóa ngoại về documents. File gốc nằm ở MinIO; object_key trong documents liên kết bản ghi với file.")
    h2("API hỏi đáp và nguồn")
    body("POST /query trả answer cùng sources; POST /query/stream gửi token trước rồi gửi metadata nguồn. Kiểm thử API bao phủ câu hỏi hợp lệ, câu hỏi rỗng và câu hỏi không có bằng chứng. Nguồn được tạo từ chunk đã chọn, không phải văn bản do mô hình tự đặt.")
    h2("Kiểm tra tự động và tài liệu")
    body("Ruff, biên dịch, 22 kiểm thử, bản dựng giao diện và kiểm tra Docker là các bằng chứng có thể chạy lại. README, tài liệu kiến trúc, hồ sơ nghiên cứu dữ liệu và bảng kiểm tra truy xuất liên kết trực tiếp tới mã nguồn hoặc tệp kết quả. Quy trình CI của commit mới nhất cần được xác nhận lại sau khi đẩy thay đổi hiện tại.")

    h1("11. Tiêu chí đánh giá")
    story.append(table([
        ["Hạng mục", "Trọng số", "Tự đánh giá", "Căn cứ"],
        ["Trích xuất và xử lý dữ liệu", "20%", "19/20", "Hồ sơ docs/report.md, ảnh upload/chunk, so sánh OCR và xử lý theo loại dữ liệu"],
        ["Cơ sở dữ liệu vector và truy xuất", "20%", "19/20", "Ảnh pgvector, tìm kiếm từ khóa + vector, tập ứng viên và xếp hạng bằng chứng"],
        ["Tích hợp AI/RAG", "15%", "14/15", "OCR NVIDIA, tạo vector, lời nhắc bám nguồn, trả kết quả từng phần và nguồn"],
        ["Docker và môi trường", "15%", "15/15", "Dockerfile, Compose, biến môi trường và ảnh quy trình chạy"],
        ["Quy trình kiểm tra tự động", "10%", "9/10", "Ảnh GitHub Actions; cần xác nhận lần chạy của mã hiện tại"],
        ["Kiểm thử", "10%", "10/10", "22 kiểm thử đơn vị/API và kiểm tra chống bịa đặt"],
        ["Tài liệu và trình diễn", "10%", "10/10", "README, kiến trúc, hồ sơ nghiên cứu, PDF và bảng truy xuất"],
        ["Tổng tự đánh giá", "100%", "96/100", "Điểm tham khảo, cần reviewer xác nhận"],
    ], [47 * mm, 18 * mm, 22 * mm, 73 * mm], regular, small=True))
    story.append(rich("Phần nghiên cứu dữ liệu nằm trong 20% trích xuất và xử lý dữ liệu: khảo sát loại dữ liệu, thiết kế tập đánh giá, so sánh phương án, phân tích lỗi, ghi quyết định và đưa kết quả trở lại cấu hình vận hành.", styles["Callout"]))

    h1("12. Điểm cộng")
    story.append(table([
        ["Nội dung mở rộng", "Bằng chứng trong mã nguồn"],
        ["Tìm kiếm kết hợp và xếp hạng lại", "PostgreSQL toàn văn, pgvector và EvidenceService"],
        ["Hỗ trợ CSV/XLSX", "Bộ định tuyến trích xuất theo phần mở rộng"],
        ["Tiến trình nền, thử lại và khôi phục", "Hàng đợi PostgreSQL, thử lại NIM và đưa job lỗi về hàng đợi"],
        ["API xóa, danh sách, đổi tên và hủy", "Các đường dẫn tài liệu trong app/api/routers/documents.py"],
        ["Trả kết quả từng phần", "Các đường dẫn /query/stream"],
        ["Nghiên cứu dữ liệu theo loại", "docs/report.md, ảnh minh chứng và bảng đánh giá"],
    ], [75 * mm, 85 * mm], regular, small=True))
    body("Các nội dung mở rộng chỉ có ý nghĩa khi luồng cơ bản đã ổn định. Những phần gọi dịch vụ trực tuyến cần được xác nhận lại trong môi trường triển khai thật.")

    h1("13. Hạn chế và kế hoạch tiếp theo")
    bullet("Bộ đánh giá hiện tập trung 5 PDF SynthDocQA; cần thêm bộ tài liệu thực tế cân bằng theo loại dữ liệu.")
    bullet("Chỉ mục phần tử hình và OCR vùng chú thích chưa bật cho mọi tài liệu vận hành.")
    bullet("Bộ xếp hạng hiện dựa trên luật; chưa có mô hình xếp hạng học từ phản hồi người dùng.")
    bullet("Cần nạp lại tài liệu, chạy đánh giá hồi quy và theo dõi độ trễ, tỷ lệ OCR dự phòng, tỷ lệ không có bằng chứng theo loại dữ liệu.")
    body("Chi tiết phương pháp, phân tích lỗi, bảng kết quả đầy đủ và quy trình tái lập nằm trong docs/report.md. File PDF này là bản trình bày có dẫn chứng; hồ sơ nghiên cứu là nơi lưu giải thích đầy đủ.")

    document.multiBuild(story)
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
