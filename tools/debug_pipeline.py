"""
Debug Terminal Script - Mini RAG Pipeline
==========================================
Run the OCR and NIM normalization pipeline on a real PDF.
Display detailed stage progress, colors, and timings.

Usage:
    python tools/debug_pipeline.py
    python tools/debug_pipeline.py "path/to/your.pdf"
"""

import sys
import time
import os
import tempfile
from pathlib import Path

# UTF-8 stdout trên Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Thêm project root vào sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ─── ANSI Colors ───────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
RED    = "\033[31m"
BLUE   = "\033[34m"
MAGENTA= "\033[35m"
WHITE  = "\033[97m"


def header(text: str):
    bar = "═" * 60
    print(f"\n{BOLD}{CYAN}{bar}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{bar}{RESET}")


def step(icon: str, label: str, detail: str = ""):
    ts = time.strftime("%H:%M:%S")
    print(f"  {DIM}[{ts}]{RESET} {icon}  {BOLD}{label}{RESET}", end="")
    if detail:
        print(f"  {DIM}{detail}{RESET}", end="")
    print()


def ok(label: str, detail: str = ""):
    ts = time.strftime("%H:%M:%S")
    print(f"  {DIM}[{ts}]{RESET} {GREEN}✔{RESET}  {label}", end="")
    if detail:
        print(f"  {DIM}{detail}{RESET}", end="")
    print()


def warn(label: str):
    print(f"  {YELLOW}⚠{RESET}  {label}")


def err(label: str):
    print(f"  {RED}✖{RESET}  {BOLD}{RED}{label}{RESET}")


def info(label: str, value=""):
    if value:
        print(f"     {DIM}↳{RESET} {label}: {CYAN}{value}{RESET}")
    else:
        print(f"     {DIM}↳{RESET} {label}")


def progress_bar(done: int, total: int, width: int = 30, label: str = "") -> str:
    pct = done / max(total, 1)
    filled = int(pct * width)
    bar = GREEN + "█" * filled + RESET + DIM + "░" * (width - filled) + RESET
    return f"[{bar}] {pct*100:.0f}%  {label}"


# ─── STAGE 0: Config ────────────────────────────────────────────────────────────
def stage_config():
    header("STAGE 0 — Cấu hình & API Key")
    from app.config.settings import (
        NGC_API_KEY, NIM_MODEL, NIM_BASE_URL, NIM_CONCURRENCY,
        DOCLING_OCR_ENGINE, DOCLING_OCR_LANG, DOCLING_DO_OCR,
        DOCLING_DEVICE, DOCLING_NUM_THREADS, DOCLING_FORCE_FULL_PAGE_OCR,
        HF_TOKEN,
        DOCUMENT_PARSER_ENGINE, RAGFLOW_MODE,
        NVIDIA_OCR_BASE_URL, NVIDIA_OCR_MODEL,
    )
    masked_key = NGC_API_KEY[:8] + "..." + NGC_API_KEY[-4:] if NGC_API_KEY else "❌ EMPTY"
    masked_hf = HF_TOKEN[:6] + "..." + HF_TOKEN[-4:] if HF_TOKEN else "❌ EMPTY"
    ok("Cấu hình được nạp từ .env")
    info("Parser Engine",     DOCUMENT_PARSER_ENGINE.upper())
    if DOCUMENT_PARSER_ENGINE == "ragflow":
        info("RAGFlow Mode",     RAGFLOW_MODE)
    info("NGC_API_KEY",       masked_key)
    info("HF_TOKEN",          masked_hf)
    info("NIM Model",         NIM_MODEL)
    info("NVIDIA OCR Model",   NVIDIA_OCR_MODEL)
    info("NVIDIA OCR Endpoint", NVIDIA_OCR_BASE_URL)
    info("NIM Concurrency",   str(NIM_CONCURRENCY))
    if DOCUMENT_PARSER_ENGINE == "docling":
        info("Docling OCR Engine", DOCLING_OCR_ENGINE)
        info("Docling OCR Lang",   ",".join(DOCLING_OCR_LANG) if isinstance(DOCLING_OCR_LANG, list) else DOCLING_OCR_LANG)
        info("Docling Device",     DOCLING_DEVICE)
        info("Docling Threads",    str(DOCLING_NUM_THREADS))
        info("Force Full Page OCR", str(DOCLING_FORCE_FULL_PAGE_OCR))
        info("do_ocr mode",        DOCLING_DO_OCR)

    if not NGC_API_KEY:
        warn("NGC_API_KEY không được cấu hình - NIM Normalize sẽ dùng fallback rule-based")
    return NGC_API_KEY


# ─── STAGE 1: Docling OCR ───────────────────────────────────────────────────────
def _pdf_has_text(path: str) -> bool:
    """Use a local copy to avoid importing ExtractService and boto3."""
    from pathlib import Path as _Path
    if _Path(path).suffix.lower() != ".pdf":
        return False
    try:
        from pypdf import PdfReader
        reader = PdfReader(path, strict=False)
        pages = reader.pages[:min(3, len(reader.pages))]
        page_lengths = [len((page.extract_text() or "").strip()) for page in pages]
        return bool(page_lengths) and sum(length >= 100 for length in page_lengths) == len(page_lengths)
    except Exception as exc:
        print(f"Could not inspect PDF text layer: {exc}", flush=True)
        return False


def _get_converter_direct(do_ocr: bool):
    """Build a Docling converter without importing storage-heavy ExtractService."""
    from app.config.settings import (
        DOCLING_DEVICE, DOCLING_DO_TABLE_STRUCTURE, DOCLING_NUM_THREADS,
        DOCLING_OCR_BATCH_SIZE, DOCLING_FORCE_FULL_PAGE_OCR,
        DOCLING_OCR_ENGINE, DOCLING_OCR_LANG,
        DOCLING_TESSERACT_PSM, DOCLING_TESSERACT_OSD,
    )
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, InputFormat, PdfFormatOption

    device = DOCLING_DEVICE
    if str(device).startswith("cuda"):
        try:
            import torch
            if not torch.cuda.is_available():
                print("CUDA unavailable — falling back to CPU", flush=True)
                device = "cpu"
        except Exception:
            device = "cpu"

    ocr_options = None
    if do_ocr:
        if DOCLING_OCR_ENGINE == "tesseract":
            from docling.datamodel.pipeline_options import TesseractCliOcrOptions
            if not DOCLING_TESSERACT_OSD:
                import pandas as pd
                from docling.models.stages.ocr.tesseract_ocr_cli_model import TesseractOcrCliModel
                def _skip_osd(_model, _filename):
                    return pd.DataFrame({"key": ["Orientation in degrees"], "value": ["0"]})
                TesseractOcrCliModel._perform_osd = _skip_osd
            ocr_options = TesseractCliOcrOptions(
                lang=DOCLING_OCR_LANG,
                force_full_page_ocr=DOCLING_FORCE_FULL_PAGE_OCR,
                psm=DOCLING_TESSERACT_PSM,
            )
        else:
            from docling.datamodel.pipeline_options import RapidOcrOptions
            ocr_options = RapidOcrOptions(
                lang=DOCLING_OCR_LANG,
                force_full_page_ocr=DOCLING_FORCE_FULL_PAGE_OCR,
            )

    pipeline_kwargs = dict(
        do_ocr=do_ocr,
        do_table_structure=DOCLING_DO_TABLE_STRUCTURE,
        ocr_batch_size=DOCLING_OCR_BATCH_SIZE,
        accelerator_options=AcceleratorOptions(num_threads=DOCLING_NUM_THREADS, device=device),
    )
    if ocr_options is not None:
        pipeline_kwargs["ocr_options"] = ocr_options

    options = PdfPipelineOptions(**pipeline_kwargs)
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def stage_docling(pdf_path: str):
    header("STAGE 1 — Docling OCR (Trích xuất tài liệu)")
    step("🔍", "Kiểm tra loại tài liệu")

    has_text = _pdf_has_text(pdf_path)
    info("Phát hiện text layer gốc (native)", str(has_text))

    from app.config.settings import DOCLING_DO_OCR
    if DOCLING_DO_OCR == "true":
        do_ocr = True
    elif DOCLING_DO_OCR == "false":
        do_ocr = False
    else:
        do_ocr = not has_text

    info("do_ocr", f"{'Bật (scanned)' if do_ocr else 'Tắt (native text)'}")

    step("📦", "Khởi động Docling converter", f"(OCR={'ON' if do_ocr else 'OFF'})")
    t0 = time.time()

    converter = _get_converter_direct(do_ocr)
    ok(f"Converter sẵn sàng", f"({time.time() - t0:.1f}s)")

    step("⚙", "Bắt đầu chuyển đổi PDF → Docling Document")
    t1 = time.time()
    result = converter.convert(pdf_path)
    elapsed_docling = time.time() - t1

    pages = result.pages if hasattr(result, "pages") else []
    ok(f"Docling xử lý xong", f"{len(pages)} trang | {elapsed_docling:.1f}s")

    # In tóm tắt tiến trình từng trang
    print()
    for i, page in enumerate(pages[:10]):  # Hiện tối đa 10 trang đầu
        page_bar = progress_bar(i + 1, len(pages), width=20, label=f"Trang {i+1}/{len(pages)}")
        print(f"     {page_bar}")
    if len(pages) > 10:
        print(f"     {DIM}... và {len(pages) - 10} trang khác{RESET}")

    return result, do_ocr, elapsed_docling


# ─── STAGE 1 (RAGFlow Alternative): DeepDoc Extraction ─────────────────────────
def stage_ragflow(pdf_path: str):
    header("STAGE 1 — RAGFlow DeepDoc (Bóc Tách & Phân Tích Layout)")
    step("🚀", "Khởi động RAGFlow DeepDoc extractor")
    from app.ingestion.ragflow_extractor import RagflowExtractor
    t0 = time.time()
    extractor = RagflowExtractor()
    ok("RAGFlow Extractor sẵn sàng", f"({time.time() - t0:.2f}s)")

    step("⚙", "Tiến hành bóc tách tài liệu (Layout Recognition, OCR, TSR)")
    t1 = time.time()
    try:
        ragflow_data = extractor.extract(pdf_path)
        elapsed = time.time() - t1

        clean_text = ragflow_data["clean_text"]
        normalized_elements = ragflow_data["normalized_elements"]
        ocr_bboxes = ragflow_data["ocr_bboxes"]
        image_bboxes = ragflow_data["image_bboxes"]
        doc_json = ragflow_data["doc_json"]

        ok(f"RAGFlow xử lý xong", f"{len(normalized_elements)} elements | {len(clean_text)} ký tự | {elapsed:.1f}s")
        info("Số OCR BBoxes", str(len(ocr_bboxes)))
        info("Số Image/Table BBoxes", str(len(image_bboxes)))
    except Exception as exc:
        warn(f"RAGFlow DeepDoc chưa sẵn sàng trong image ({exc})")
        info("Gợi ý", "Chạy '.\\scripts\\run_debug.ps1 -Rebuild' nếu muốn cài đặt deepdoc-lib vào image")
        warn("Đang tự động chuyển sang Docling Engine để tiếp tục pipeline...")
        result, do_ocr, elapsed = stage_docling(pdf_path)
        clean_text, normalized_elements, image_bboxes, ocr_bboxes, doc_json = stage_clean(result, pdf_path)

    return clean_text, normalized_elements, image_bboxes, ocr_bboxes, doc_json, elapsed


# ─── STAGE 1 (NVIDIA OCR): NeMo Retriever OCR v2 ─────────────────────────────
def stage_nvidia_ocr(pdf_path: str):
    """Run the same NVIDIA OCR adapter used by the background worker."""
    header("STAGE 1 — NVIDIA NeMo Retriever OCR v2")
    step("🚀", "Gửi ảnh theo trang tới NVIDIA OCR NIM")
    from app.ingestion.nvidia_ocr_extractor import NvidiaOcrExtractor

    t0 = time.time()
    result = NvidiaOcrExtractor().extract(pdf_path, Path(pdf_path).name)
    elapsed = time.time() - t0
    clean_text = result["clean_text"]
    normalized_elements = result["normalized_elements"]
    image_bboxes = result["image_bboxes"]
    ocr_bboxes = result["ocr_bboxes"]
    doc_json = result["doc_json"]
    ok(
        "NVIDIA OCR xử lý xong",
        f"{result['page_count']} trang | {len(normalized_elements)} elements | {elapsed:.1f}s",
    )
    info("Mô hình", doc_json.get("model", "nvidia/nemotron-ocr-v2"))
    info("Confidence trung bình", str(result.get("confidence")))
    return clean_text, normalized_elements, image_bboxes, ocr_bboxes, doc_json, elapsed


# ─── STAGE 2: Export & Rule-based Clean ─────────────────────────────────────────
def stage_clean(result, pdf_path: str):
    header("STAGE 2 — Rule-based Clean & Normalize")
    step("📄", "Xuất Docling Document sang dict JSON")
    t0 = time.time()
    doc_json = result.document.export_to_dict()
    ok("Export xong", f"({time.time() - t0:.2f}s)")

    step("🖼", "Trích xuất Image BBoxes")
    from app.ingestion.normalize_service import NormalizeService as _NS
    # Inline bbox extraction to avoid boto3 dependency from extract_service
    def _extract_image_bboxes(doc_json):
        images = []
        for index, picture in enumerate(doc_json.get("pictures", [])):
            for provenance in picture.get("prov", []):
                bbox = provenance.get("bbox") or {}
                if not {"l", "b", "r", "t"}.issubset(bbox):
                    continue
                images.append({"id": picture.get("self_ref", f"#/pictures/{index}"), "page_no": provenance.get("page_no"), "bbox": {"left": bbox["l"], "bottom": bbox["b"], "right": bbox["r"], "top": bbox["t"]}, "label": picture.get("label", "picture")})
        return images
    def _extract_ocr_bboxes(doc_json):
        boxes = []
        for index, item in enumerate(doc_json.get("texts", [])):
            for provenance in item.get("prov", []):
                bbox = provenance.get("bbox") or {}
                if not {"l", "b", "r", "t"}.issubset(bbox):
                    continue
                boxes.append({"id": item.get("self_ref", f"#/texts/{index}"), "page_no": provenance.get("page_no"), "text": item.get("text", ""), "bbox": {"left": bbox["l"], "bottom": bbox["b"], "right": bbox["r"], "top": bbox["t"]}})
        return boxes

    image_bboxes = _extract_image_bboxes(doc_json)
    ok(f"Hình ảnh", f"{len(image_bboxes)} vùng ảnh")

    step("🔲", "Trích xuất OCR Text BBoxes")
    ocr_bboxes = _extract_ocr_bboxes(doc_json)
    ok(f"Khung chữ OCR", f"{len(ocr_bboxes)} bboxes trên {len(result.pages) if hasattr(result, 'pages') else 1} trang")

    step("🧹", "Rule-based Clean & Normalize")
    from app.ingestion.normalize_service import NormalizeService
    normalizer = NormalizeService()
    doc_id_mock = "debug-test-0000"
    filename = Path(pdf_path).name

    t0 = time.time()
    clean_text, normalized_elements = normalizer.normalize(
        doc_json,
        {"document_id": doc_id_mock, "filename": filename},
    )
    ok("Clean xong", f"{len(clean_text)} ký tự | {len(normalized_elements)} phần tử | ({time.time() - t0:.2f}s)")

    # Phân bố trang
    pages_with_elements = {}
    for elem in normalized_elements:
        p = elem.get("page") or "?"
        pages_with_elements[p] = pages_with_elements.get(p, 0) + 1
    info("Phân bố phần tử theo trang", str(dict(sorted(pages_with_elements.items(), key=lambda x: str(x[0])))))

    # Thống kê các loại element
    elem_types = {}
    for elem in normalized_elements:
        t = elem.get("element_type", "text")
        elem_types[t] = elem_types.get(t, 0) + 1
    info("Loại element", str(elem_types))

    # In 3 phần tử đầu làm mẫu
    print()
    print(f"  {DIM}Mẫu 3 phần tử đầu:{RESET}")
    for elem in normalized_elements[:3]:
        snippet = (elem.get("text") or "")[:80].replace("\n", " ")
        print(f"  {DIM}  [{elem.get('element_type','?')}][trang {elem.get('page','?')}]{RESET} {snippet}...")

    return clean_text, normalized_elements, image_bboxes, ocr_bboxes, doc_json


# ─── STAGE 3: NIM Parallel Normalize ──────────────────────────────────────────
def stage_nim(clean_text: str, normalized_elements: list, has_api_key: bool):
    header("STAGE 3 — NIM Parallel Normalize (NVIDIA API)")

    if not has_api_key:
        warn("Bỏ qua NIM vì NGC_API_KEY không có — trả về fallback rule-based")
        return None, None

    step("🚀", "Bắt đầu NIM Parallel Normalize")
    from app.ingestion.nim_normalizer import normalize_parallel, partition_by_pages
    from app.config.settings import NIM_CONCURRENCY

    page_windows = partition_by_pages(normalized_elements)
    info("Số page windows", str(len(page_windows)))
    info("NIM Concurrency", str(NIM_CONCURRENCY))

    print()
    for i, (tag, elems) in enumerate(page_windows):
        bar = progress_bar(0, 1, width=15, label=f"Window {tag} ({len(elems)} elems) → Đang đợi...")
        print(f"  {DIM}  {bar}{RESET}")

    print()
    step("⚡", "Gửi parallel requests...")

    t0 = time.time()
    semantic_structure, semantic_error = normalize_parallel(clean_text, normalized_elements)
    elapsed = time.time() - t0

    if semantic_error:
        warn(f"NIM hoàn thành với lỗi/fallback một số trang: {semantic_error[:120]}")
    else:
        ok("NIM Normalize hoàn thành!", f"{elapsed:.1f}s | {len(page_windows)} windows song song")

    if semantic_structure:
        elements = semantic_structure.get("elements", [])
        warnings = semantic_structure.get("warnings", [])
        sections = semantic_structure.get("sections", [])
        info("Tổng elements đã normalize", str(len(elements)))
        info("Sections phát hiện", str(len(sections)))
        info("Thời gian NIM", f"{elapsed:.2f}s")
        if semantic_structure.get("title"):
            info("Title phát hiện", semantic_structure["title"])
        if warnings:
            for w in warnings[:3]:
                warn(f"Warning: {w}")

        # Hiển thị một số corrections
        print()
        print(f"  {DIM}Mẫu elements đã clean (3 phần tử):{RESET}")
        for elem in elements[:3]:
            snippet = (elem.get("text") or "")[:80].replace("\n", " ")
            print(f"  {DIM}  [{elem.get('type','?')}][trang {elem.get('page','?')}]{RESET} {snippet}...")

    return semantic_structure, semantic_error


# ─── STAGE 4: Chunking ─────────────────────────────────────────────────────────
def stage_chunk(semantic_text: str, semantic_structure, pdf_path: str):
    header("STAGE 4 — Text Chunking (LlamaIndex)")
    from app.ingestion.normalize_service import NormalizeService
    normalizer = NormalizeService()
    doc_id_mock = "debug-test-0000"
    filename = Path(pdf_path).name

    step("✂", "Chia nhỏ văn bản thành chunks")
    t0 = time.time()
    chunks = normalizer.chunk_text(semantic_text, {"document_id": doc_id_mock, "filename": filename})
    ok(f"Chunking xong", f"{len(chunks)} chunks | ({time.time() - t0:.2f}s)")

    info("Tổng ký tự input", str(len(semantic_text)))
    info("Số chunks", str(len(chunks)))
    if chunks:
        avg_len = sum(len(c["text"]) for c in chunks) / len(chunks)
        info("Độ dài trung bình / chunk", f"{avg_len:.0f} ký tự")

    # Mẫu 2 chunks
    print()
    print(f"  {DIM}Mẫu 2 chunks:{RESET}")
    for i, chunk in enumerate(chunks[:2]):
        snippet = chunk["text"][:100].replace("\n", " ")
        print(f"  {DIM}  [Chunk {i+1}]{RESET} {snippet}...")

    return chunks


# ─── SUMMARY ──────────────────────────────────────────────────────────────────
def summary(pdf_path, elapsed_docling, do_ocr, clean_text, normalized_elements,
            image_bboxes, ocr_bboxes, semantic_structure, semantic_error, chunks):
    header("TÓM TẮT KẾT QUẢ PIPELINE")

    pages = len({e.get("page") for e in normalized_elements if e.get("page") is not None})
    nim_status = "processed" if (semantic_structure and not semantic_error) else "fallback_rule_based"

    rows = [
        ("File",               Path(pdf_path).name),
        ("OCR mode",           "Scanned (OCR ON)" if do_ocr else "Native Text (OCR OFF)"),
        ("Thời gian Docling",  f"{elapsed_docling:.1f}s"),
        ("Số trang",           str(pages)),
        ("Ký tự sau clean",    str(len(clean_text))),
        ("Phần tử normalize",  str(len(normalized_elements))),
        ("OCR BBoxes",         str(len(ocr_bboxes))),
        ("Image BBoxes",       str(len(image_bboxes))),
        ("NIM Status",         nim_status),
        ("Số chunks (RAG)",    str(len(chunks))),
    ]

    max_label = max(len(r[0]) for r in rows)
    for label, value in rows:
        pad = " " * (max_label - len(label))
        print(f"  {BOLD}{label}{pad}{RESET}  →  {CYAN}{value}{RESET}")

    print()
    if nim_status == "processed":
        print(f"  {GREEN}{BOLD}✔ Pipeline hoàn thành THÀNH CÔNG với NIM Semantic Normalization!{RESET}")
    else:
        print(f"  {YELLOW}{BOLD}⚠ Pipeline hoàn thành với Rule-based fallback (NIM không sẵn sàng hoặc gặp lỗi){RESET}")

    print(f"\n  {DIM}Ghi chú: Dữ liệu này đã sẵn sàng để lưu vào DB và đưa vào RAG pipeline.{RESET}\n")


def save_output(
    pdf_path: str,
    elapsed_docling: float,
    do_ocr: bool,
    clean_text: str,
    normalized_elements: list,
    image_bboxes: list,
    ocr_bboxes: list,
    semantic_structure: dict,
    semantic_error: str,
    chunks: list,
    total_elapsed: float,
):
    import json
    from datetime import datetime

    output_dir = Path(__file__).resolve().parent.parent / "evaluation" / "artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_json_path = output_dir / "debug_output.json"
    output_md_path = output_dir / "debug_output.md"

    # 1. Xuất file JSON chi tiết đầy đủ
    output_data = {
        "metadata": {
            "file_name": Path(pdf_path).name,
            "file_size_bytes": os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0,
            "generated_at": datetime.now().isoformat(),
            "total_elapsed_seconds": round(total_elapsed, 2),
            "docling_elapsed_seconds": round(elapsed_docling, 2),
            "do_ocr": do_ocr,
            "total_chunks": len(chunks),
            "total_normalized_elements": len(normalized_elements),
            "total_ocr_bboxes": len(ocr_bboxes),
            "total_image_bboxes": len(image_bboxes),
            "nim_status": "error" if semantic_error else ("processed" if semantic_structure else "skipped"),
        },
        "semantic_structure": semantic_structure or {},
        "semantic_error": semantic_error or "",
        "clean_text": clean_text,
        "chunks": chunks,
        "ocr_bboxes_count": len(ocr_bboxes),
        "ocr_bboxes_sample": ocr_bboxes[:30],
        "image_bboxes": image_bboxes,
    }

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    # 2. Xuất file Markdown báo cáo trực quan
    title = (semantic_structure or {}).get("title") or Path(pdf_path).name
    sections = (semantic_structure or {}).get("sections", [])

    md_lines = [
        f"# Báo Cáo Kết Quả Debug Pipeline: {title}",
        f"",
        f"- **File nguồn:** `{Path(pdf_path).name}`",
        f"- **Thời gian chạy tổng:** `{round(total_elapsed, 2)}s` (Docling OCR: `{round(elapsed_docling, 2)}s`)",
        f"- **OCR Mode:** `{'ON (Scanned PDF)' if do_ocr else 'OFF (Native Text PDF)'}`",
        f"- **Số lượng Elements:** `{len(normalized_elements)}`",
        f"- **Số OCR Bounding Boxes:** `{len(ocr_bboxes)}`",
        f"- **Số Image Bounding Boxes:** `{len(image_bboxes)}`",
        f"- **Số Chunks tạo ra cho RAG:** `{len(chunks)}`",
        f"- **Trạng thái NIM Normalization:** `{'Thành công (meta/llama-3.2-11b-vision-instruct)' if not semantic_error and semantic_structure else 'Fallback / Lỗi: ' + str(semantic_error)}`",
        f"",
        f"---",
        f"",
        f"## 1. Mục Lục & Sections Phát Hiện",
        f"",
    ]

    if sections:
        for s in sections:
            md_lines.append(f"- **{s.get('heading', 'Section')}** (Trang {s.get('page', '?')})")
    else:
        md_lines.append("_Không phát hiện tiêu đề phân mục đặc biệt._")

    md_lines.extend([
        f"",
        f"---",
        f"",
        f"## 2. Toàn Bộ Nội Dung Đã Normalize & Clean ({len(clean_text)} ký tự)",
        f"",
        f"```text",
        clean_text[:6000] + ("\n\n... [Đã cắt bớt để xem nhanh, xem toàn bộ văn bản trong debug_output.json] ..." if len(clean_text) > 6000 else ""),
        f"```",
        f"",
        f"---",
        f"",
        f"## 3. Danh Sách Chunks Cho RAG ({len(chunks)} Chunks)",
        f"",
    ])

    for i, c in enumerate(chunks):
        chunk_idx = c.get("index", i + 1)
        chunk_page = c.get("metadata", {}).get("page", "?")
        words_count = len(c.get("text", "").split())
        md_lines.append(f"### Chunk #{chunk_idx} (Trang {chunk_page} | ~{words_count} từ)")
        md_lines.append(f"```text\n{c.get('text', '')}\n```\n")

    with open(output_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    header("XUẤT FILE KẾT QUẢ OUTPUT")
    ok("Đã xuất kết quả debug ra các file sau:")
    info("Báo cáo trực quan Markdown", str(output_md_path))
    info("Dữ liệu đầy đủ JSON", str(output_json_path))
    print()


# ─── MAIN ────────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{BOLD}{MAGENTA}{'='*64}{RESET}")
    print(f"{BOLD}{MAGENTA}  Mini RAG — Debug Pipeline Terminal{RESET}")
    print(f"{BOLD}{MAGENTA}  NIM Parallel Normalize | Docling OCR | BBox Extract{RESET}")
    print(f"{BOLD}{MAGENTA}{'='*64}{RESET}")

    # Xác định file PDF cần test
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        # Default: dùng file PDF mặc định trong project root
        default = Path(__file__).resolve().parent.parent / "QĐ.NTC.HR-01-QUY TRÌNH, QUY ĐỊNH QUẢN LÝ NGHỈ PHÉP.pdf"
        pdf_path = str(default)

    # Nếu truyền vào là một thư mục, tự động quét tìm file PDF
    if os.path.isdir(pdf_path):
        pdf_candidates = [os.path.join(pdf_path, f) for f in os.listdir(pdf_path) if f.lower().endswith(".pdf")]
        # Ưu tiên file có chứa HR-01
        hr01_match = [f for f in pdf_candidates if "HR-01" in os.path.basename(f)]
        if hr01_match:
            pdf_path = hr01_match[0]
        elif pdf_candidates:
            pdf_path = pdf_candidates[0]

    print(f"\n  {BOLD}File:{RESET} {CYAN}{pdf_path}{RESET}")

    if not os.path.exists(pdf_path):
        # Tự động khắc phục khi Windows CMD làm hỏng font tiếng Việt
        parent_dir = Path(pdf_path).parent if pdf_path else Path("/debug_pdf_dir")
        candidates = []
        if parent_dir.exists():
            candidates = list(parent_dir.glob("*HR-01*.pdf")) or list(parent_dir.glob("*.pdf"))
        if not candidates and Path("/debug_pdf_dir").exists():
            candidates = list(Path("/debug_pdf_dir").glob("*HR-01*.pdf")) or list(Path("/debug_pdf_dir").glob("*.pdf"))
        if not candidates:
            root_dir = Path(__file__).resolve().parent.parent
            candidates = list(root_dir.glob("*HR-01*.pdf")) or list(root_dir.glob("*.pdf"))

        if candidates:
            pdf_path = str(candidates[0])
            warn(f"Khắc phục mã hóa ký tự CMD -> Đã tự động khớp file: {pdf_path}")
        else:
            err(f"File không tồn tại: {pdf_path}")
            print(f"\n  Cách dùng:\n    python tools/debug_pipeline.py\n    python tools/debug_pipeline.py \"path/to/your.pdf\"\n")
            sys.exit(1)

    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    print(f"  {DIM}Kích thước: {file_size_mb:.2f} MB{RESET}")

    t_total = time.time()

    # Chạy từng stage
    has_api_key = stage_config()

    from app.config.settings import DOCUMENT_PARSER_ENGINE

    if DOCUMENT_PARSER_ENGINE == "ragflow":
        clean_text, normalized_elements, image_bboxes, ocr_bboxes, doc_json, elapsed_extract = stage_ragflow(pdf_path)
        do_ocr = True
    elif not _pdf_has_text(pdf_path):
        clean_text, normalized_elements, image_bboxes, ocr_bboxes, doc_json, elapsed_extract = stage_nvidia_ocr(pdf_path)
        do_ocr = True
    else:
        result, do_ocr, elapsed_extract = stage_docling(pdf_path)
        clean_text, normalized_elements, image_bboxes, ocr_bboxes, doc_json = stage_clean(result, pdf_path)

    semantic_structure, semantic_error = stage_nim(clean_text, normalized_elements, bool(has_api_key))

    # Xác định văn bản cuối để chunk
    if semantic_structure and semantic_structure.get("elements"):
        semantic_text = "\n\n".join(
            item["text"] for item in semantic_structure["elements"] if item.get("text")
        )
    else:
        semantic_text = clean_text

    chunks = stage_chunk(semantic_text, semantic_structure, pdf_path)

    total_elapsed = time.time() - t_total
    print(f"\n  {DIM}Tổng thời gian pipeline: {total_elapsed:.1f}s{RESET}")

    summary(
        pdf_path, elapsed_extract, do_ocr,
        clean_text, normalized_elements,
        image_bboxes, ocr_bboxes,
        semantic_structure, semantic_error,
        chunks
    )

    save_output(
        pdf_path, elapsed_extract, do_ocr,
        clean_text, normalized_elements,
        image_bboxes, ocr_bboxes,
        semantic_structure, semantic_error,
        chunks, total_elapsed
    )


if __name__ == "__main__":
    main()
