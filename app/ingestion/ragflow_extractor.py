"""
RAGFlow / DeepDoc Document Extractor Service
============================================
Integrate RAGFlow (DeepDoc) document extraction:
- Mode 1: deepdoc-lib for in-process extraction.
- Mode 2: ragflow-sdk for remote RAGFlow Server extraction.

The extractor returns clean text, layout elements, tables, and bounding boxes.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.config.settings import (
    RAGFLOW_MODE,
    RAGFLOW_BASE_URL,
    RAGFLOW_API_KEY,
)

logger = logging.getLogger("ragflow_extractor")


class RagflowExtractor:
    """Provide the ragflowextractor application component."""
    def __init__(self, mode: str = RAGFLOW_MODE):
        self.mode = mode.lower()
        self._pdf_parser = None

    def _get_deepdoc_parser(self):
        """Initialize the DeepDoc PDF parser from the supported package variants."""
        if self._pdf_parser is None:
            try:
                # 1. Thử import từ deepdoc-lib
                from deepdoc import PdfParser, PdfModelConfig, TokenizerConfig
                model_cfg = PdfModelConfig()
                tokenizer_cfg = TokenizerConfig()
                self._pdf_parser = PdfParser(model_cfg=model_cfg, tokenizer_cfg=tokenizer_cfg)
                logger.info("DeepDoc PdfParser (deepdoc-lib) initialized successfully")
            except ImportError:
                try:
                    # 2. Thử import từ deepdoc.parser
                    from deepdoc.parser import PdfParser
                    self._pdf_parser = PdfParser()
                    logger.info("DeepDoc PdfParser (deepdoc.parser) initialized successfully")
                except ImportError as exc:
                    raise RuntimeError(
                        "Chưa cài đặt thư viện DeepDoc. Vui lòng cài đặt: pip install deepdoc-lib"
                    ) from exc
        return self._pdf_parser

    def extract(self, file_path: str, filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract a document and return normalized results:
        - clean_text: str containing cleaned document text.
        - normalized_elements: list[dict] containing layout elements.
        - ocr_bboxes: list[dict] containing text-region coordinates.
        - image_bboxes: list[dict] containing image/table coordinates.
        - doc_json: dict containing the raw structured document.
        """
        path_obj = Path(file_path)
        actual_filename = filename or path_obj.name
        if self.mode == "api":
            return self._extract_via_ragflow_api(file_path, actual_filename)
        else:
            return self._extract_via_deepdoc(file_path, actual_filename)

    def _extract_via_deepdoc(self, file_path: str, filename: str) -> Dict[str, Any]:
        """Extract a document with the in-process DeepDoc parser."""
        parser = self._get_deepdoc_parser()
        
        # DeepDoc parse tài liệu
        logger.info("Bắt đầu parse bằng DeepDoc: %s", filename)
        
        # PdfParser trả về sections và tables
        try:
            parse_result = parser(file_path)
        except Exception as exc:
            # Kiểm tra phương thức parse_into_bboxes nếu có
            if hasattr(parser, "parse_into_bboxes"):
                parse_result = parser.parse_into_bboxes(file_path)
            else:
                raise exc

        sections = []
        tables = []
        
        if isinstance(parse_result, tuple) and len(parse_result) == 2:
            sections, tables = parse_result
        elif isinstance(parse_result, list):
            sections = parse_result
        elif isinstance(parse_result, dict):
            sections = parse_result.get("sections", [])
            tables = parse_result.get("tables", [])

        normalized_elements: List[Dict[str, Any]] = []
        ocr_bboxes: List[Dict[str, Any]] = []
        image_bboxes: List[Dict[str, Any]] = []
        text_parts: List[str] = []

        elem_index = 0

        # 1. Xử lý các sections / text blocks từ DeepDoc
        for sec in sections:
            elem_index += 1
            elem_id = f"deepdoc_{elem_index:04d}"
            
            # Trích xuất text và metadata
            sec_text = ""
            page_no = 1
            bbox_coords = None
            sec_type = "paragraph"

            if isinstance(sec, tuple):
                sec_text = str(sec[0]) if len(sec) > 0 else ""
                if len(sec) > 1 and isinstance(sec[1], (int, float)):
                    page_no = int(sec[1])
                elif len(sec) > 1 and isinstance(sec[1], dict):
                    page_no = sec[1].get("page_no", 1)
                    bbox_coords = sec[1].get("bbox")
            elif isinstance(sec, dict):
                sec_text = sec.get("text", "")
                page_no = sec.get("page_no", sec.get("page", 1))
                bbox_coords = sec.get("bbox")
                sec_type = sec.get("type", "paragraph")
            else:
                sec_text = str(sec)

            sec_text = sec_text.strip()
            if not sec_text:
                continue

            # Phân loại sơ bộ nếu chưa có type
            if sec_type == "paragraph":
                first_line = sec_text.split("\n")[0].strip()
                if len(first_line) < 100 and (
                    first_line.isupper()
                    or any(first_line.lower().startswith(k) for k in ["điều ", "chương ", "mục ", "phần ", "quy định ", "kính gửi"])
                ):
                    sec_type = "section_header"

            text_parts.append(sec_text)

            elem_dict = {
                "element_id": elem_id,
                "type": sec_type,
                "element_type": sec_type,
                "text": sec_text,
                "page": page_no,
            }
            if bbox_coords:
                elem_dict["bbox"] = bbox_coords

            normalized_elements.append(elem_dict)

            # Tạo OCR bbox nếu có tọa độ
            if bbox_coords and isinstance(bbox_coords, (list, tuple)) and len(bbox_coords) >= 4:
                ocr_bboxes.append({
                    "id": f"#/texts/{elem_index}",
                    "page_no": page_no,
                    "text": sec_text[:100],
                    "bbox": {
                        "left": bbox_coords[0],
                        "top": bbox_coords[1],
                        "right": bbox_coords[2],
                        "bottom": bbox_coords[3],
                    },
                    "coord_origin": "TOPLEFT",
                })

        # 2. Xử lý các tables từ DeepDoc
        for tbl_idx, tbl in enumerate(tables):
            tbl_page = 1
            tbl_content = ""
            
            if isinstance(tbl, dict):
                tbl_content = tbl.get("content", tbl.get("text", ""))
                tbl_page = tbl.get("page_no", 1)
                tbl_bbox = tbl.get("bbox")
            else:
                tbl_content = str(tbl)
                tbl_bbox = None

            if tbl_content:
                text_parts.append(f"\n[BẢNG {tbl_idx+1}]\n{tbl_content}\n")
                normalized_elements.append({
                    "element_id": f"deepdoc_tbl_{tbl_idx:03d}",
                    "type": "table",
                    "element_type": "table",
                    "text": tbl_content,
                    "page": tbl_page,
                })

            if tbl_bbox and isinstance(tbl_bbox, (list, tuple)) and len(tbl_bbox) >= 4:
                image_bboxes.append({
                    "id": f"#/tables/{tbl_idx}",
                    "page_no": tbl_page,
                    "label": "table",
                    "bbox": {
                        "left": tbl_bbox[0],
                        "top": tbl_bbox[1],
                        "right": tbl_bbox[2],
                        "bottom": tbl_bbox[3],
                    },
                })

        clean_text = "\n\n".join(text_parts).strip()

        doc_json = {
            "source": "ragflow_deepdoc",
            "filename": filename,
            "total_elements": len(normalized_elements),
            "total_tables": len(tables),
            "sections": sections,
            "tables": tables,
        }

        return {
            "clean_text": clean_text,
            "normalized_elements": normalized_elements,
            "ocr_bboxes": ocr_bboxes,
            "image_bboxes": image_bboxes,
            "doc_json": doc_json,
        }

    def _extract_via_ragflow_api(self, file_path: str, filename: str) -> Dict[str, Any]:
        """Extract a document by uploading it to a RAGFlow server over REST."""
        try:
            from ragflow_sdk import RAGFlow
        except ImportError as exc:
            raise RuntimeError("Vui lòng cài đặt ragflow-sdk: pip install ragflow-sdk") from exc

        if not RAGFLOW_API_KEY:
            raise ValueError("Cần cấu hình RAGFLOW_API_KEY trong .env khi dùng RAGFLOW_MODE=api")

        logger.info("Kết nối RAGFlow API tại: %s", RAGFLOW_BASE_URL)
        client = RAGFlow(api_key=RAGFLOW_API_KEY, base_url=RAGFLOW_BASE_URL)

        # Upload tài liệu và lấy parsed chunks từ dataset
        dataset_name = "mini_rag_temp"
        datasets = client.list_datasets(name=dataset_name)
        if not datasets:
            dataset = client.create_dataset(name=dataset_name)
        else:
            dataset = datasets[0]

        # Upload tài liệu
        with open(file_path, "rb") as f:
            docs = dataset.upload_documents([{"display_name": filename, "blob": f.read()}])

        if not docs:
            raise RuntimeError("RAGFlow API không phản hồi sau khi upload tài liệu")

        doc = docs[0]
        # Chờ parse
        doc.parse()

        # Lấy chunks đã parse
        chunks = doc.list_chunks()
        text_parts = []
        normalized_elements = []

        for idx, chunk in enumerate(chunks):
            chunk_text = getattr(chunk, "content", "") or getattr(chunk, "text", "")
            if not chunk_text:
                continue
            text_parts.append(chunk_text)
            normalized_elements.append({
                "element_id": f"ragflow_chunk_{idx+1:04d}",
                "type": "paragraph",
                "text": chunk_text,
                "page": 1,
            })

        clean_text = "\n\n".join(text_parts).strip()
        return {
            "clean_text": clean_text,
            "normalized_elements": normalized_elements,
            "ocr_bboxes": [],
            "image_bboxes": [],
            "doc_json": {"source": "ragflow_api", "filename": filename, "chunks_count": len(chunks)},
        }
