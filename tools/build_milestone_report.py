"""Build the Vietnamese milestone and data-research report as a PDF."""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
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
        rich("Milestone, acceptance criteria, evaluation và nghiên cứu xử lý dữ liệu", styles["CoverSub"]),
        Spacer(1, 15 * mm),
        HRFlowable(width="65%", thickness=2, color=colors.HexColor("#F59E0B"), hAlign="CENTER"),
        Spacer(1, 15 * mm),
        rich("Vai trò trình bày: Data Engineer / Data Scientist", styles["CoverSub"]),
        rich("Ngày cập nhật: 30/09/2026", styles["CoverSub"]),
        rich("Source commit: 05185d9", styles["CoverSub"]),
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
    body("Báo cáo đối chiếu source commit 05185d9 với bốn milestone trong SUBJECT.md. Điểm nhấn được bổ sung là nghiên cứu dữ liệu: phân loại nội dung, kiểm tra chất lượng sau extract/OCR, benchmark theo loại dữ liệu và truy vết quyết định đưa vào production.")
    body("Trên bộ 5 PDF SynthDocQA với 877 câu hỏi, cấu hình tốt nhất đạt document hit 90,65%, content hit 41,33% và assertion pass 23,72%. Đây là số liệu benchmark chuyên biệt, không phải cam kết cho mọi tài liệu production.")
    story.append(rich("Điểm cần reviewer quan sát: hệ thống không chỉ chọn mô hình rồi đo điểm tổng. Quy trình đã tách lỗi trích xuất, lỗi lập chỉ mục và lỗi truy xuất; sau đó dùng kết quả theo Table, Form, Figure, Annotation và Text để thay đổi pipeline.", styles["Callout"]))

    h1("2. Milestones")
    h2("Milestone 1 — Data Pipeline")
    body("Đã hoàn thành upload, kiểm tra định dạng, lưu MinIO, extract PDF/TXT/DOCX và định dạng mở rộng, OCR NVIDIA cho scan/ảnh, làm sạch, semantic normalization có timeout/fallback, chunking, embedding theo batch, lưu pgvector và worker nền.")
    bullet("Bổ sung hồ sơ nghiên cứu dữ liệu tại docs/report.md.")
    bullet("Phân loại 877 câu hỏi theo Table 299, Form 107, Figure 159, Annotation 285 và Text 27.")
    bullet("So sánh OCR, candidate multiplier, hybrid retrieval, xử lý bảng, hình và annotation bằng cùng một bộ câu hỏi.")
    bullet("Đưa kết quả vào các quyết định: OCR toàn trang, chunk bảng có cấu trúc, provenance theo trang, hybrid retrieval và evidence filtering.")
    h2("Milestone 2 — RAG API")
    body("Query API, query planning, full-text/BM25 kết hợp dense vector, mở rộng tập ứng viên, lọc danh tính tài liệu, xếp hạng evidence, prompt có grounding, source citation và streaming đã có trong source.")
    h2("Milestone 3 — Docker & CI")
    body("Dockerfile, Compose cho API/worker/PostgreSQL + pgvector/MinIO/frontend, .env.example và GitHub Actions đã có. Local quality gate đạt 98,8/100; workflow commit 05185d9 đang chờ runner hoàn tất tại thời điểm lập báo cáo.")
    h2("Milestone 4 — Documentation & Demo")
    body("README, architecture, API examples, demo script, traceability, retrieval verification và báo cáo PDF này đã được bàn giao.")

    h1("3. Nghiên cứu và xử lý dữ liệu")
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

    h1("4. Acceptance criteria")
    story.append(table([
        ["Tiêu chí", "Trạng thái", "Bằng chứng"],
        ["Docker Compose chạy được", "Đạt", "docker-compose.yml; local stack"],
        ["Upload PDF, TXT, DOCX", "Đạt", "Upload API và allowed extensions"],
        ["Extract, chunk, embedding", "Đạt", "Ingestion worker"],
        ["Vector + metadata", "Đạt", "PostgreSQL + pgvector"],
        ["Query có source", "Đạt", "QueryResponse.sources"],
        ["Config tách business logic", "Đạt", ".env.example và settings"],
        ["Unit/API test", "Đạt", "22 test local"],
        ["CI pipeline", "Chờ xác nhận", "Commit mới nhất đang in_progress"],
        ["Retrieval verification", "Đạt", "10 câu trong output"],
        ["README + architecture", "Đạt", "root docs và output"],
    ], [65 * mm, 30 * mm, 65 * mm], regular, small=True))
    body("Acceptance chỉ đóng hoàn toàn sau khi GitHub Actions của commit hiện tại kết thúc thành công. Các kiểm tra local đã pass.")

    h1("5. Evaluation criteria")
    story.append(table([
        ["Hạng mục", "Trọng số", "Tự đánh giá", "Căn cứ"],
        ["Data ingestion & processing", "20%", "19/20", "12 điểm ingestion + 8 điểm nghiên cứu/chuẩn hóa trong docs/report.md"],
        ["Vector Database & Retrieval", "20%", "19/20", "pgvector, BM25, dense, candidate pool, evidence"],
        ["AI / RAG Integration", "15%", "14/15", "NVIDIA OCR/NIM, grounding, streaming, source"],
        ["Docker & Environment", "15%", "15/15", "Dockerfile, Compose, env, stack local"],
        ["CI", "10%", "9/10", "Workflow có đủ bước, chờ runner mới"],
        ["Testing", "10%", "10/10", "22 test và quality gate"],
        ["Documentation & Demo", "10%", "10/10", "README, architecture, demo, PDF"],
        ["Tổng", "100%", "96/100", "Điểm tự đánh giá, chờ reviewer"],
    ], [47 * mm, 18 * mm, 22 * mm, 73 * mm], regular, small=True))
    story.append(rich("Phần nghiên cứu dữ liệu nằm trong 20% Data ingestion & processing: khảo sát loại dữ liệu, thiết kế tập đánh giá, so sánh phương án, phân tích lỗi, ghi quyết định và tái đưa kết quả vào cấu hình production.", styles["Callout"]))

    h1("6. Bonus")
    story.append(table([
        ["Bonus", "Trạng thái", "Bằng chứng"],
        ["Hybrid Search / full-text + vector", "Đạt", "PostgreSQL full-text + pgvector"],
        ["Reranking và tối ưu retrieval", "Đạt", "EvidenceService, planner, candidate multiplier"],
        ["CSV/XLSX", "Đạt", "Extraction routing"],
        ["Background worker và retry", "Đạt", "PostgreSQL queue, retry/fallback"],
        ["API xóa và danh sách tài liệu", "Đạt", "DELETE/GET documents"],
        ["Đổi tên, hủy job, streaming", "Đạt", "API và frontend"],
        ["Data research dossier", "Đạt", "docs/report.md và evaluation artifacts"],
    ], [58 * mm, 28 * mm, 74 * mm], regular, small=True))
    body("Bonus chỉ có giá trị sau khi yêu cầu cơ bản ổn định. Với OCR, embedding và LLM hosted, cần xác nhận thêm trong môi trường triển khai thật.")

    h1("7. Hạn chế và kế hoạch tiếp theo")
    bullet("Benchmark hiện tập trung 5 PDF SynthDocQA; cần thêm bộ production cân bằng theo loại dữ liệu.")
    bullet("Visual-element index và OCR vùng annotation chưa bật cho mọi tài liệu production.")
    bullet("Reranker hiện deterministic; chưa có cross-encoder học từ phản hồi người dùng.")
    bullet("Cần re-ingest, chạy benchmark regression và theo dõi độ trễ, fallback OCR, no-evidence rate theo loại dữ liệu.")
    body("Chi tiết phương pháp, failure analysis, bảng kết quả đầy đủ và quy trình tái lập nằm trong docs/report.md. File này là bản tóm tắt để reviewer đọc nhanh; không thay thế hồ sơ nghiên cứu chi tiết.")

    document.multiBuild(story)
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
