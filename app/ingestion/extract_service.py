import uuid
import tempfile
import os
import time
import io
from pathlib import Path
from app.config.storage import StorageManager
from app.repositories.document_repo import DocumentRepository
from app.config.settings import (
    DOCLING_DEVICE, DOCLING_DO_OCR, DOCLING_DO_TABLE_STRUCTURE,
    DOCLING_NUM_THREADS, DOCLING_OCR_BATCH_SIZE, DOCLING_FORCE_FULL_PAGE_OCR,
    DOCLING_OCR_ENGINE, DOCLING_OCR_LANG,
    DOCLING_TESSERACT_PSM,
    DOCLING_TESSERACT_OSD,
    SEMANTIC_NORMALIZER, SEMANTIC_NORMALIZE_OCR_ONLY,
    SEMANTIC_OCR_CONFIDENCE_GATE,
    PERSIST_PAGE_VISUALS,
    PAGE_VISUAL_SCALE,
    EMBEDDING_MODEL,
)
import threading
from app.ingestion.normalize_service import NormalizeService
from app.ingestion.semantic_normalizer import normalize_document
from app.retrieval.embedding_service import EmbeddingService
from app.repositories.chunk_repo import ChunkRepository

# ─── PROGRESS TRACKING HOOK CHO DOCLING PIPELINE ────────────────────────────
_docling_progress_local = threading.local()


class DocumentCancelledError(Exception):
    """Raised when a document is deleted while extraction is running."""

def set_page_progress_callback(cb, total_pages=1):
    """Set page progress callback."""
    _docling_progress_local.cb = cb
    _docling_progress_local.total_pages = max(1, total_pages)

def get_page_progress_callback():
    """Return page progress callback."""
    return getattr(_docling_progress_local, "cb", None)

def get_page_progress_total():
    """Return page progress total."""
    return getattr(_docling_progress_local, "total_pages", 1)

class TrackedDoclingQueue:
    """Wrap a Docling queue and report completed-page progress."""
    def __init__(self, real_q, callback, total_pages):
        self._real_q = real_q
        self._callback = callback
        self._total_pages = max(1, total_pages)
        self._completed = 0

    def get_batch(self, batch_size, timeout=0.05):
        """Return batch."""
        batch = self._real_q.get_batch(batch_size, timeout)
        if batch:
            self._completed += len(batch)
            if self._callback:
                try:
                    self._callback(self._completed, self._total_pages)
                except Exception as exc:
                    if isinstance(exc, DocumentCancelledError):
                        raise
                    print(f"TrackedDoclingQueue callback error: {exc}", flush=True)
        return batch

    def __getattr__(self, name):
        return getattr(self._real_q, name)

# Cài đặt hook vào Docling StandardPdfPipeline._create_run_ctx
try:
    from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
    if not hasattr(StandardPdfPipeline, "_orig_create_run_ctx_ntc"):
        StandardPdfPipeline._orig_create_run_ctx_ntc = StandardPdfPipeline._create_run_ctx

        def _patched_create_run_ctx(self):
            ctx = self._orig_create_run_ctx_ntc()
            cb = get_page_progress_callback()
            if cb and hasattr(ctx, "output_queue"):
                total = get_page_progress_total()
                ctx.output_queue = TrackedDoclingQueue(ctx.output_queue, cb, total)
            return ctx

        StandardPdfPipeline._create_run_ctx = _patched_create_run_ctx
        print("[ExtractService] Docling StandardPdfPipeline page-tracking hook installed", flush=True)
except Exception as patch_err:
    print(f"[ExtractService] Could not hook Docling StandardPdfPipeline: {patch_err}", flush=True)


class ExtractService:
    """Provide the extractservice application component."""
    def __init__(self, repo: DocumentRepository, storage: StorageManager):
        self.repo = repo
        self.storage = storage
        self._converters = {}
        self._normalizer = NormalizeService()
        self._embedder = EmbeddingService()
        self._chunk_repo = ChunkRepository(repo.db)

    def _persist_visual_crops(self, pdf_path: str, doc_id: uuid.UUID, image_bboxes: list[dict]) -> list[dict]:
        """Render Docling picture regions and persist compact visual evidence in object storage."""
        if not image_bboxes or Path(pdf_path).suffix.lower() != ".pdf":
            return image_bboxes
        try:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(pdf_path)
            for index, item in enumerate(image_bboxes):
                page_no = int(item.get("page_no") or 1)
                if page_no < 1 or page_no > len(pdf):
                    continue
                page = pdf[page_no - 1]
                width, height = page.get_size()
                scale = 2.0
                bitmap = page.render(scale=scale)
                image = bitmap.to_pil().convert("RGB")
                box = item.get("bbox") or {}
                left = max(0, int(float(box.get("left", 0)) * scale))
                right = min(image.width, int(float(box.get("right", width)) * scale))
                # Docling PDF coordinates use bottom-left origin.
                top = max(0, int((height - float(box.get("top", height))) * scale))
                bottom = min(image.height, int((height - float(box.get("bottom", 0))) * scale))
                if right <= left or bottom <= top:
                    continue
                crop = image.crop((left, top, right, bottom))
                payload = io.BytesIO()
                crop.save(payload, format="PNG", optimize=True)
                payload.seek(0)
                key = f"visual_crops/{doc_id}/page_{page_no}_{index}.png"
                self.storage.upload_fileobj(payload, key, "image/png")
                item["image_object_key"] = key
                item["image_mime_type"] = "image/png"
            pdf.close()
            return image_bboxes
        except Exception as exc:
            print(f"[{doc_id}] visual crop persistence skipped: {exc}", flush=True)
            return image_bboxes

    def _persist_page_visuals(self, pdf_path: str, doc_id: uuid.UUID, page_count: int) -> list[dict]:
        """Persist one compressed page snapshot for visual QA and annotations.

        Text chunks keep only the object key and page number.  The image is
        fetched lazily by ``RagService`` when a visual answer needs it, so
        ordinary text queries do not pay the download or prompt cost.
        """
        if not PERSIST_PAGE_VISUALS or Path(pdf_path).suffix.lower() != ".pdf":
            return []
        visuals: list[dict] = []
        pdf = None
        try:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(pdf_path)
            total = min(max(1, int(page_count or len(pdf))), len(pdf))
            for page_index in range(total):
                try:
                    bitmap = pdf[page_index].render(scale=PAGE_VISUAL_SCALE)
                    image = bitmap.to_pil().convert("RGB")
                    payload = io.BytesIO()
                    image.save(payload, format="JPEG", quality=84, optimize=True)
                    payload.seek(0)
                    page_no = page_index + 1
                    key = f"page_visuals/{doc_id}/page_{page_no}.jpg"
                    self.storage.upload_fileobj(payload, key, "image/jpeg")
                    visuals.append({
                        "image_object_key": key,
                        "image_mime_type": "image/jpeg",
                        "page": page_no,
                    })
                except Exception as page_exc:
                    print(f"[{doc_id}] page visual {page_index + 1} skipped: {page_exc}", flush=True)
        except Exception as exc:
            print(f"[{doc_id}] page visual persistence skipped: {exc}", flush=True)
        finally:
            if pdf is not None:
                try:
                    pdf.close()
                except Exception:
                    pass
        return visuals
    @staticmethod
    def _pdf_has_text(path: str) -> bool:
        """Sample a few pages so digital PDFs can skip the OCR stage."""
        if Path(path).suffix.lower() != ".pdf":
            return False
        try:
            from pypdf import PdfReader
            reader = PdfReader(path, strict=False)
            page_count = len(reader.pages)
            if not page_count:
                return False
            # Sample across the entire file: covers commonly mixed PDFs where
            # the first pages are digital text but later pages are scans/forms.
            sample_count = min(7, page_count)
            sample_indexes = sorted({
                round(i * (page_count - 1) / max(1, sample_count - 1))
                for i in range(sample_count)
            })
            page_lengths = [
                len((reader.pages[index].extract_text() or "").strip())
                for index in sample_indexes
            ]
            # OCR the whole PDF if even one sampled page lacks a usable text
            # layer. Hybrid files often place scans/forms in later sections.
            return bool(page_lengths) and all(length >= 100 for length in page_lengths)
        except Exception as exc:
            print(f"Could not inspect PDF text layer: {exc}", flush=True)
            return False

    @staticmethod
    def _pdf_has_embedded_images(path: str) -> bool:
        """Detect image-heavy PDFs whose visible text is absent from the text layer."""
        if Path(path).suffix.lower() != ".pdf":
            return False
        try:
            from pypdf import PdfReader
            reader = PdfReader(path, strict=False)
            page_count = len(reader.pages)
            if not page_count:
                return False
            sample_count = min(7, page_count)
            sample_indexes = sorted({
                round(i * (page_count - 1) / max(1, sample_count - 1))
                for i in range(sample_count)
            })
            image_pages = 0
            for index in sample_indexes:
                try:
                    image_pages += bool(reader.pages[index].images)
                except Exception:
                    continue
            # Require recurring images so a one-off logo does not send every
            # otherwise-native PDF through the OCR pipeline.
            return image_pages >= max(2, (len(sample_indexes) + 1) // 2)
        except Exception as exc:
            print(f"Could not inspect PDF images: {exc}", flush=True)
            return False

    @staticmethod
    def _merge_semantic_elements(
        source_elements: list[dict], semantic_elements: list[dict]
    ) -> list[dict]:
        """Apply validated text/type patches while preserving source geometry/order."""
        patches = {
            str(item.get("element_id")): item
            for item in semantic_elements
            if item.get("element_id") is not None
        }
        for source in source_elements:
            patch = patches.get(str(source.get("element_id")))
            if not patch:
                continue
            if patch.get("text") is not None:
                source["text"] = str(patch["text"])
            semantic_type = patch.get("type", "text")
            source["semantic_type"] = semantic_type
            # Normalize the provider schema to the chunker's boundary types.
            if semantic_type == "heading":
                source["element_type"] = "section_header"
            elif semantic_type in {"title", "paragraph", "list", "table", "caption", "footer"}:
                source["element_type"] = semantic_type
        return source_elements

    def _get_converter(self, do_ocr: bool):
        if do_ocr not in self._converters:
            from docling.datamodel.accelerator_options import AcceleratorOptions
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, InputFormat, PdfFormatOption

            device = DOCLING_DEVICE
            if str(device).startswith("cuda"):
                try:
                    import torch
                    if not torch.cuda.is_available():
                        print("CUDA is unavailable; falling back to CPU", flush=True)
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
                            return pd.DataFrame({
                                "key": ["Orientation in degrees"],
                                "value": ["0"],
                            })

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
                accelerator_options=AcceleratorOptions(
                    num_threads=DOCLING_NUM_THREADS,
                    device=device,
                ),
            )
            if ocr_options is not None:
                pipeline_kwargs["ocr_options"] = ocr_options
            options = PdfPipelineOptions(**pipeline_kwargs)
            self._converters[do_ocr] = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
            )
        return self._converters[do_ocr]

    @staticmethod
    def _extract_image_bboxes(doc_json: dict) -> list[dict]:
        """Return one normalized record for every Docling picture provenance."""
        images = []
        for index, picture in enumerate(doc_json.get("pictures", [])):
            for provenance in picture.get("prov", []):
                bbox = provenance.get("bbox") or {}
                if not {"l", "b", "r", "t"}.issubset(bbox):
                    continue
                images.append({
                    "id": picture.get("self_ref", f"#/pictures/{index}"),
                    "page_no": provenance.get("page_no"),
                    "bbox": {
                        "left": bbox["l"],
                        "bottom": bbox["b"],
                        "right": bbox["r"],
                        "top": bbox["t"],
                    },
                    "coord_origin": bbox.get("coord_origin", "BOTTOMLEFT"),
                    "label": picture.get("label", "picture"),
                })
        return images

    @staticmethod
    def _extract_ocr_bboxes(doc_json: dict) -> list[dict]:
        """Return OCR/text provenance boxes, useful for scanned documents."""
        boxes = []
        for index, item in enumerate(doc_json.get("texts", [])):
            for provenance in item.get("prov", []):
                bbox = provenance.get("bbox") or {}
                if not {"l", "b", "r", "t"}.issubset(bbox):
                    continue
                boxes.append({
                    "id": item.get("self_ref", f"#/texts/{index}"),
                    "page_no": provenance.get("page_no"),
                    "text": item.get("text", ""),
                    "bbox": {
                        "left": bbox["l"],
                        "bottom": bbox["b"],
                        "right": bbox["r"],
                        "top": bbox["t"],
                    },
                    "coord_origin": bbox.get("coord_origin", "BOTTOMLEFT"),
                })
        return boxes

    @staticmethod
    def _normalize_office_bboxes(records: list[dict], suffix: str) -> list[dict]:
        """Convert PowerPoint EMU coordinates to PDF points for the viewer."""
        if suffix.lower() != ".pptx":
            return records
        # PowerPoint uses English Metric Units: 914400 EMU per inch;
        # PDF coordinates use 72 points per inch.
        factor = 72.0 / 914400.0
        for record in records:
            record["bbox_unit"] = "pt"
            for key, value in record.get("bbox", {}).items():
                if value is not None:
                    record["bbox"][key] = value * factor
        return records

    def extract_document_background(self, doc_id: uuid.UUID):
        """Extract document background."""
        try:
            if not self.repo.is_document_active(doc_id):
                return
            row = self.repo.get_document(doc_id)
            if not row:
                return
            
            # row indexes based on SELECT *: 0=id, 1=original_filename, 2=object_key
            original_filename = row[1]
            object_key = row[2]
                
            with tempfile.NamedTemporaryFile(suffix=Path(original_filename).suffix, delete=False) as tmp:
                tmp_name = tmp.name
                
            self.storage.download_file(object_key, tmp_name)
            print(f"[{doc_id}] stage=download_done", flush=True)
            self.repo.update_progress(doc_id, 10, 'Tải tệp về máy chủ')
            
            from app.config.settings import DOCUMENT_PARSER_ENGINE, RAGFLOW_MODE

            extraction_started = time.monotonic()
            source_suffix = Path(original_filename).suffix.lower()
            native_pdf_text = self._pdf_has_text(tmp_name)
            pdf_has_embedded_images = self._pdf_has_embedded_images(tmp_name)
            extraction_complete = False
            parser_used = None
            do_ocr = False
            page_count = 1
            ocr_confidence = None
            image_bboxes = []
            ocr_bboxes = []

            # Plain-text uploads do not need a PDF layout engine. Reading them
            # directly preserves the original line order and avoids sending a
            # TXT/CSV/Markdown file through Docling's PDF converter.
            if source_suffix in {".txt", ".csv", ".markdown"}:
                raw_text = Path(tmp_name).read_text(encoding="utf-8", errors="replace")
                clean_text = self._normalizer.clean_text(raw_text)
                normalized_elements = []
                for index, line in enumerate(clean_text.splitlines()):
                    line = line.strip()
                    if not line:
                        continue
                    normalized_elements.append({
                        "element_id": f"#/text/{index}",
                        "text": line,
                        "page": 1,
                        "bbox": None,
                        "coord_origin": None,
                        "element_type": "paragraph",
                        "metadata": {},
                    })
                doc_json = {"texts": [], "tables": []}
                parser_used = "plain_text"
                extraction_complete = True
                self.repo.update_progress(doc_id, 68, "Đã đọc xong tệp văn bản")

            # Auto mode mirrors the upstream parser guidance: do not OCR a PDF
            # that already has a usable text layer; use the Vietnamese GPU OCR
            # service for scans/images; keep DeepDoc opt-in for complex layouts.
            use_ragflow = DOCUMENT_PARSER_ENGINE == "ragflow"
            use_tesseract_direct = DOCUMENT_PARSER_ENGINE == "tesseract" or (
                DOCUMENT_PARSER_ENGINE == "auto"
                and (source_suffix != ".pdf" or not native_pdf_text)
                and source_suffix in {".pdf", ".png", ".jpg", ".jpeg"}
            )
            use_local_ocr = DOCUMENT_PARSER_ENGINE == "ppocr"

            if use_ragflow:
                try:
                    print(f"[{doc_id}] stage=ragflow_extract_start mode={RAGFLOW_MODE}", flush=True)
                    self.repo.update_progress(doc_id, 15, 'Đọc nội dung tài liệu')
                    from app.ingestion.ragflow_extractor import RagflowExtractor
                    ragflow_result = RagflowExtractor().extract(tmp_name, original_filename)
                    clean_text = ragflow_result["clean_text"]
                    normalized_elements = ragflow_result["normalized_elements"]
                    ocr_bboxes = ragflow_result["ocr_bboxes"]
                    image_bboxes = ragflow_result["image_bboxes"]
                    doc_json = ragflow_result["doc_json"]
                    page_count = max(
                        [int(item.get("page") or 1) for item in normalized_elements] or [1]
                    )
                    do_ocr = True
                    parser_used = f"ragflow_{RAGFLOW_MODE}"
                    extraction_complete = True
                    print(f"[{doc_id}] stage=ragflow_extract_done chars={len(clean_text)} elements={len(normalized_elements)}", flush=True)
                    self.repo.update_progress(doc_id, 70, 'Phân tích cấu trúc văn bản')
                except Exception as rf_err:
                    print(f"[{doc_id}] ragflow extraction unavailable ({rf_err}), falling back to Docling OCR", flush=True)
                    extraction_complete = False

            if use_tesseract_direct and not extraction_complete:
                try:
                    from app.ingestion.tesseract_extractor import TesseractExtractor

                    print(f"[{doc_id}] stage=tesseract_direct_start", flush=True)
                    self.repo.update_progress(doc_id, 15, 'OCR tiếng Việt theo trang')
                    tesseract_result = TesseractExtractor().extract(tmp_name, original_filename)
                    clean_text = tesseract_result["clean_text"]
                    normalized_elements = tesseract_result["normalized_elements"]
                    ocr_bboxes = tesseract_result["ocr_bboxes"]
                    image_bboxes = tesseract_result["image_bboxes"]
                    doc_json = tesseract_result["doc_json"]
                    page_count = tesseract_result["page_count"]
                    ocr_confidence = tesseract_result.get("confidence")
                    do_ocr = True
                    parser_used = "tesseract_direct"
                    extraction_complete = True
                    print(
                        f"[{doc_id}] stage=tesseract_direct_done pages={page_count} "
                        f"chars={len(clean_text)} elements={len(normalized_elements)}",
                        flush=True,
                    )
                    self.repo.update_progress(doc_id, 68, 'Hoàn tất OCR tiếng Việt')
                except Exception as tess_err:
                    print(
                        f"[{doc_id}] direct Tesseract unavailable ({tess_err}), "
                        "trying local PP-OCRv6",
                        flush=True,
                    )
                    use_local_ocr = True

            if use_local_ocr and not extraction_complete:
                try:
                    from app.ingestion.ppocr_extractor import PpOcrExtractor

                    print(f"[{doc_id}] stage=ppocr_extract_start", flush=True)
                    self.repo.update_progress(doc_id, 15, 'OCR tiếng Việt bằng GPU local')
                    ppocr_result = PpOcrExtractor().extract(tmp_name, original_filename)
                    clean_text = ppocr_result["clean_text"]
                    normalized_elements = ppocr_result["normalized_elements"]
                    ocr_bboxes = ppocr_result["ocr_bboxes"]
                    image_bboxes = ppocr_result["image_bboxes"]
                    doc_json = ppocr_result["doc_json"]
                    page_count = ppocr_result["page_count"]
                    ocr_confidence = ppocr_result.get("confidence")
                    do_ocr = True
                    parser_used = "local_ppocrv6"
                    extraction_complete = True
                    print(
                        f"[{doc_id}] stage=ppocr_extract_done pages={page_count} "
                        f"chars={len(clean_text)} elements={len(normalized_elements)}",
                        flush=True,
                    )
                    self.repo.update_progress(doc_id, 68, 'Hoàn tất OCR tiếng Việt')
                except Exception as ppocr_err:
                    print(
                        f"[{doc_id}] local PP-OCRv6 unavailable ({ppocr_err}), "
                        "falling back to Docling/Tesseract",
                        flush=True,
                    )
                    extraction_complete = False

            if not extraction_complete:
                # Đếm trước tổng số trang nếu là PDF
                total_pages = 1
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(tmp_name, strict=False)
                    total_pages = max(1, len(reader.pages))
                except Exception:
                    pass

                if DOCLING_DO_OCR == "true":
                    do_ocr = True
                elif DOCLING_DO_OCR == "false":
                    do_ocr = False
                else:
                    do_ocr = source_suffix in {".png", ".jpg", ".jpeg"} or (
                        source_suffix == ".pdf" and (
                            not native_pdf_text or pdf_has_embedded_images
                        )
                    )
                print(
                    f"Processing {original_filename}: total_pages={total_pages}, do_ocr={do_ocr}, "
                    f"ocr_engine={DOCLING_OCR_ENGINE}, ocr_lang={DOCLING_OCR_LANG}, "
                    f"device={DOCLING_DEVICE}",
                    flush=True,
                )
                # Reuse one converter per pipeline configuration in this worker.
                converter = self._get_converter(do_ocr)
                print(f"[{doc_id}] stage=docling_start total_pages={total_pages}", flush=True)

                def on_docling_page(done_pages, total):
                    """Run the on docling page operation."""
                    if not self.repo.is_document_active(doc_id):
                        raise DocumentCancelledError(f"Document {doc_id} was cancelled")
                    done = min(done_pages, total)
                    ratio = done / max(1, total)
                    # Tiến trình tăng dần từ 15% đến 60%
                    pct = int(15 + ratio * 45)
                    if done < total:
                        stage = f"Đang đọc nội dung trang {done + 1}/{total} (đã xong {done}/{total})"
                    else:
                        stage = f"Đã đọc xong toàn bộ {total}/{total} trang"
                    print(f"[{doc_id}] progress={pct}% stage={stage}", flush=True)
                    self.repo.update_progress(doc_id, pct, stage)

                set_page_progress_callback(on_docling_page, total_pages)
                self.repo.update_progress(doc_id, 15, f"Đang đọc nội dung trang 1/{total_pages} (0/{total_pages})")
                try:
                    result = converter.convert(tmp_name)
                finally:
                    set_page_progress_callback(None)

                print(f"[{doc_id}] stage=docling_done", flush=True)
                self.repo.update_progress(doc_id, 60, f"Đã đọc xong toàn bộ {total_pages}/{total_pages} trang")
                if not self.repo.is_document_active(doc_id):
                    return
                
                # Extract markdown and structured JSON
                doc_json = result.document.export_to_dict()
                print(f"[{doc_id}] stage=export_done pages={len(result.pages) if hasattr(result, 'pages') else 'unknown'}", flush=True)
                image_bboxes = self._extract_image_bboxes(doc_json)
                ocr_bboxes = self._extract_ocr_bboxes(doc_json)
                source_suffix = Path(original_filename).suffix.lower()
                self._normalize_office_bboxes(image_bboxes, source_suffix)
                self._normalize_office_bboxes(ocr_bboxes, source_suffix)
                image_bboxes = self._persist_visual_crops(tmp_name, doc_id, image_bboxes)
                clean_text, normalized_elements = self._normalizer.normalize(
                    doc_json,
                    {"document_id": str(doc_id), "filename": original_filename},
                )
                print(f"[{doc_id}] stage=rule_clean_done chars={len(clean_text)} elements={len(normalized_elements)}", flush=True)
                self.repo.update_progress(doc_id, 68, 'Phân tích cấu trúc văn bản')
                page_count = total_pages
                parser_used = "docling_tesseract" if do_ocr else "docling_native_text"
                extraction_complete = True

            extraction_elapsed = round(time.monotonic() - extraction_started, 3)
            page_visuals = self._persist_page_visuals(tmp_name, doc_id, page_count)
            should_semantic_normalize = (
                SEMANTIC_NORMALIZER not in {"none", "off", "false"}
                and (do_ocr or not SEMANTIC_NORMALIZE_OCR_ONLY)
                and not (
                    parser_used == "tesseract_direct"
                    and ocr_confidence is not None
                    and ocr_confidence >= SEMANTIC_OCR_CONFIDENCE_GATE
                )
            )
            if should_semantic_normalize:
                print(
                    f"[{doc_id}] stage=semantic_normalize_start policy={SEMANTIC_NORMALIZER}",
                    flush=True,
                )
                self.repo.update_progress(doc_id, 70, 'Phân tích ngữ nghĩa AI')

                def on_semantic_progress(done_win, total_win):
                    # Tiến trình tăng dần từ 70% đến 85%
                    """Run the on semantic progress operation."""
                    ratio = done_win / max(1, total_win)
                    pct = int(70 + ratio * 15)
                    stage = f"Phân tích ngữ nghĩa AI: trang {done_win}/{total_win}"
                    print(f"[{doc_id}] progress={pct}% stage={stage}", flush=True)
                    self.repo.update_progress(doc_id, pct, stage)

                semantic_structure, semantic_error, semantic_meta = normalize_document(
                    clean_text,
                    normalized_elements,
                    policy=SEMANTIC_NORMALIZER,
                    progress_callback=on_semantic_progress,
                )
                print(
                    f"[{doc_id}] stage=semantic_normalize_done "
                    f"provider={semantic_meta.get('provider')} "
                    f"status={semantic_meta.get('status')}",
                    flush=True,
                )
                self.repo.update_progress(doc_id, 85, 'Phân tích ngữ nghĩa xong')
                if semantic_structure and semantic_structure.get("elements"):
                    normalized_elements = self._merge_semantic_elements(
                        normalized_elements, semantic_structure["elements"]
                    )
                    semantic_text = "\n\n".join(
                        item["text"] for item in normalized_elements if item.get("text")
                    )
                else:
                    semantic_text = clean_text
                    semantic_structure = {"title": None, "sections": [], "elements": [], "warnings": [semantic_error] if semantic_error else []}
            else:
                if not do_ocr:
                    reason = "native_text_fast_path"
                elif (
                    parser_used == "tesseract_direct"
                    and ocr_confidence is not None
                    and ocr_confidence >= SEMANTIC_OCR_CONFIDENCE_GATE
                ):
                    reason = "high_confidence_ocr"
                else:
                    reason = "provider_disabled"
                print(f"[{doc_id}] stage=semantic_normalize_skipped reason={reason}", flush=True)
                self.repo.update_progress(doc_id, 85, 'Hoàn tất phân tích cấu trúc')
                semantic_text = clean_text
                semantic_structure = {"title": None, "sections": [], "elements": normalized_elements, "warnings": []}
                semantic_error = None
                semantic_meta = {"provider": "none", "status": "skipped", "reason": reason}
            # Chunk using structure-aware semantic chunker (preferred)
            # Falls back to plain-text SentenceSplitter if no elements
            # Keep the minimum retrieval metadata explicit and stable.  The
            # legacy ``filename`` key is retained for compatibility with old
            # chunks, while ``file_name`` is the canonical public key.
            doc_meta = {
                "document_id": str(doc_id),
                "file_name": original_filename,
                "filename": original_filename,
                "embedding_model": self._embedder.model or EMBEDDING_MODEL,
            }
            if normalized_elements:
                chunks = self._normalizer.chunk_elements(normalized_elements, doc_meta)
            else:
                chunks = self._normalizer.chunk_text(semantic_text, doc_meta)

            # Attach at most two visual crops from the same page range to each
            # text chunk. The image is fetched lazily only if that chunk wins
            # retrieval, so ordinary text-only queries pay no image cost.
            for chunk in chunks:
                meta = chunk.get("metadata") or {}
                start = meta.get("page_start")
                end = meta.get("page_end") or start
                visuals = [
                    item for item in image_bboxes
                    if item.get("image_object_key")
                    and start is not None
                    and item.get("page_no") is not None
                    and int(start) <= int(item["page_no"]) <= int(end)
                ][:2]
                if visuals:
                    meta["visual_evidence"] = [
                        {"image_object_key": item["image_object_key"], "image_mime_type": item.get("image_mime_type", "image/png"), "page": item.get("page_no"), "bbox": item.get("bbox")}
                        for item in visuals
                    ]
                if page_visuals:
                    page_start = int(start) if start is not None else None
                    page_end = int(end) if end is not None else page_start
                    page_evidence = [
                        item for item in page_visuals
                        if page_start is not None and page_start <= int(item["page"]) <= int(page_end)
                    ][:2]
                    if page_evidence:
                        meta["page_visual_evidence"] = page_evidence
                if visuals or page_visuals:
                    chunk["metadata"] = meta

            print(f"[{doc_id}] stage=chunk_done chunks={len(chunks)} chars={len(semantic_text)}", flush=True)
            self.repo.update_progress(doc_id, 88, 'Cắt nhỏ thành các đoạn tìm kiếm')

            # Phase 2: Vectorize & Lưu Chunks vào PostgreSQL pgvector
            print(f"[{doc_id}] stage=embedding_start chunks={len(chunks)}", flush=True)
            try:
                chunk_texts = [c.get("text", "") for c in chunks]
                embeddings = self._embedder.embed_texts(chunk_texts, input_type="passage")
                chunks_with_vecs = []
                for idx, c in enumerate(chunks):
                    vec = embeddings[idx] if idx < len(embeddings) else []
                    chunk_meta = c.get("metadata") or {}
                    chunk_id = uuid.uuid4()
                    chunks_with_vecs.append({
                        "id": chunk_id,
                        "chunk_index": chunk_meta.get("chunk_index", idx),
                        "content": c.get("text", ""),
                        "metadata": {
                            **chunk_meta,
                            "document_id": str(doc_id),
                            "chunk_id": str(chunk_id),
                            "file_name": original_filename,
                            "filename": original_filename,
                            "embedding_model": self._embedder.model or EMBEDDING_MODEL,
                            # Semantic chunker fields (may already be in chunk_meta)
                            "chunk_type": chunk_meta.get("chunk_type", "content"),
                            "section": chunk_meta.get("section", ""),
                            "page_start": chunk_meta.get("page_start"),
                            "page_end": chunk_meta.get("page_end"),
                            "extraction_method": parser_used,
                            "ocr_confidence": (
                                round(float(ocr_confidence), 4)
                                if ocr_confidence is not None else None
                            ),
                            "source_locator": (
                                f"{original_filename}#page={chunk_meta.get('page_start')}"
                                if chunk_meta.get("page_start") is not None
                                else original_filename
                            ),
                        },
                        "embedding": vec,
                    })
                saved_chunks = self._chunk_repo.save_chunks_batch(doc_id, chunks_with_vecs)
                print(f"[{doc_id}] stage=embedding_done saved_chunks={saved_chunks}", flush=True)
                self.repo.update_progress(doc_id, 95, 'Lưu vào cơ sở dữ liệu')

            except Exception as emb_exc:
                # Never report a document as searchable when its vectors were
                # not created. A retry after the embedding service is restored
                # is safer than a silent processed-but-unretrievable document.
                print(f"[{doc_id}] stage=embedding_failed error={emb_exc}", flush=True)
                raise RuntimeError(f"Embedding failed; document was not indexed: {emb_exc}") from emb_exc

            if not self.repo.is_document_active(doc_id):
                return
            
            # Prepare extracted data
            extracted_data = {
                # The user-facing OCR result is the cleaned/normalized text.
                "ocr_text": semantic_text,
                "raw_ocr_text": clean_text,
                "text": semantic_text,
                "chunks": chunks,
                "normalized_elements": normalized_elements,
                "semantic_structure": semantic_structure,
                "semantic_normalization": semantic_meta,
                "metadata": {
                    "page_count": page_count,
                    "language": "vie+eng",
                    "parser": parser_used,
                    "ocr_applied": do_ocr,
                    "extraction_elapsed_seconds": extraction_elapsed,
                    "confidence_score": (
                        round(ocr_confidence, 4)
                        if ocr_confidence is not None
                        else (0.995 if not do_ocr else None)
                    ),
                    "ocr_percent": (
                        round(ocr_confidence * 100, 2)
                        if ocr_confidence is not None
                        else (99.5 if not do_ocr else None)
                    ),
                },
                "entities": [], # Phase 2: VLM / Quality Checker
                "images": image_bboxes,
                "page_visuals": page_visuals,
                "ocr_bboxes": ocr_bboxes,
                "raw_docling": doc_json # Structured document
            }
            
            self.repo.update_document_status(doc_id, "processed", extracted_data=extracted_data)
            print(f"[{doc_id}] stage=persist_done", flush=True)
                
            os.remove(tmp_name)
        except Exception as e:
            if isinstance(e, DocumentCancelledError):
                print(f"[{doc_id}] extraction cancelled", flush=True)
                try:
                    if 'tmp_name' in locals() and os.path.exists(tmp_name):
                        os.remove(tmp_name)
                except OSError:
                    pass
                return
            print(f"Error extracting {doc_id}: {e}")
            try:
                if 'tmp_name' in locals() and os.path.exists(tmp_name):
                    os.remove(tmp_name)
            except OSError:
                pass
            self.repo.update_document_status(doc_id, "failed", error_message=str(e))
