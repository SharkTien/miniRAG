import html
import re
import unicodedata
from typing import Optional


class NormalizeService:
    """Structure-aware cleaning and semantic chunking for Docling elements."""

    _control_chars = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    _spaces = re.compile(r"[ \t]+")
    _blank_lines = re.compile(r"\n{3,}")
    _image_marker = re.compile(r"<!--\s*image\s*-->", re.IGNORECASE)
    _page_number = re.compile(r"^(?:page|trang)\s+\d{1,4}(?:\s+(?:of|trên)\s+\d{1,4})?$", re.IGNORECASE)

    def __init__(self):
        self._pipeline = None

    # ─────────────────────────── TEXT CLEANING ───────────────────────────────

    @classmethod
    def clean_text(cls, text: str) -> str:
        """Run the clean text operation."""
        text = html.unescape(text or "")
        text = unicodedata.normalize("NFKC", text)
        text = cls._control_chars.sub("", text)
        text = cls._image_marker.sub("\n[IMAGE]\n", text)
        text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text, flags=re.UNICODE)
        lines = [cls._spaces.sub(" ", line).strip() for line in text.splitlines()]
        return cls._blank_lines.sub("\n\n", "\n".join(lines)).strip()

    @staticmethod
    def _signature(text: str) -> str:
        """Diacritics-insensitive fingerprint for dedup comparison."""
        decomposed = unicodedata.normalize("NFKD", text)
        ascii_like = "".join(char for char in decomposed if not unicodedata.combining(char))
        return re.sub(r"[^a-zA-Z0-9]+", "", ascii_like).lower()

    # ─────────────────────────── DEDUPLICATION ───────────────────────────────

    @staticmethod
    def _trigrams(text: str) -> set:
        """Character-level trigrams for Jaccard similarity."""
        s = re.sub(r"\s+", " ", text.lower().strip())
        if len(s) < 3:
            return {s}
        return {s[i:i+3] for i in range(len(s) - 2)}

    @classmethod
    def _jaccard(cls, a: str, b: str) -> float:
        ta, tb = cls._trigrams(a), cls._trigrams(b)
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)

    @classmethod
    def _deduplicate_elements(cls, elements: list, threshold: float = 0.85) -> list:
        """
        Remove near-duplicate elements within a document using sliding window.

        Compares each element against the last WINDOW elements.
        Jaccard similarity >= threshold on trigrams -> element is dropped.
        Works on documents of ANY length (unlike _remove_structural_noise
        which requires >= 3 pages).
        """
        if not elements:
            return elements
        window_size = 8
        kept = []
        recent_texts = []
        for elem in elements:
            text = elem.get("text", "").strip()
            if not text:
                continue
            is_dup = any(
                cls._jaccard(text, prev) >= threshold
                for prev in recent_texts[-window_size:]
            )
            if not is_dup:
                kept.append(elem)
                recent_texts.append(text)
        return kept

    @classmethod
    def _remove_structural_noise(cls, elements: list) -> list:
        """Remove repeating headers/footers spanning many pages."""
        page_count = len({e["page"] for e in elements if e.get("page") is not None})
        if page_count < 3:
            return elements
        signatures_by_page: dict = {}
        for element in elements:
            signature = cls._signature(element["text"])
            page = element.get("page")
            if signature and page is not None:
                signatures_by_page.setdefault(signature, set()).add(page)
        repeated_signatures = {
            signature for signature, pages in signatures_by_page.items()
            if len(signature) <= 180
            and len(pages) >= max(3, int(page_count * 0.6))
        }
        return [
            element for element in elements
            if cls._signature(element["text"]) not in repeated_signatures
            and not cls._page_number.fullmatch(element["text"])
            and not (
                len(element["text"]) <= 4
                and not re.search(r"[\wÀ-ỹĐđ]", element["text"], re.UNICODE)
            )
        ]

    # ─────────────────────────── DOCLING EXTRACTION ──────────────────────────

    @classmethod
    def _elements_from_docling(cls, doc_json: dict) -> list:
        elements = []
        for index, item in enumerate(doc_json.get("texts", [])):
            text = cls.clean_text(item.get("text", ""))
            if not text:
                continue
            provenance = item.get("prov", []) or [{}]
            for prov_index, prov in enumerate(provenance):
                bbox = prov.get("bbox") or {}
                elements.append({
                    "element_id": item.get("self_ref", f"#/texts/{index}"),
                    "text": text,
                    "page": prov.get("page_no"),
                    "bbox": {
                        "left": bbox.get("l"), "bottom": bbox.get("b"),
                        "right": bbox.get("r"), "top": bbox.get("t"),
                    } if bbox else None,
                    "coord_origin": bbox.get("coord_origin") if bbox else None,
                    "element_type": item.get("label", "text"),
                    "provenance_index": prov_index,
                })
        return sorted(
            elements,
            key=lambda element: (
                element["page"] if element.get("page") is not None else 0,
                -(element.get("bbox") or {}).get("top", 0),
                (element.get("bbox") or {}).get("left", 0),
            ),
        )

    # ─────────────────────────── CHUNK TYPE DETECTION ────────────────────────

    _CHUNK_TYPE_PATTERNS = [
        ("contact", re.compile(
            r"(liên hệ|điện thoại|email|fax|số (?:đt|tel)|thắc mắc|trao đổi)",
            re.IGNORECASE | re.UNICODE,
        )),
        ("legal_reference", re.compile(
            r"^(căn cứ|theo |thực hiện|chiếu theo|dựa theo|quy định tại)",
            re.IGNORECASE | re.UNICODE | re.MULTILINE,
        )),
        ("administrative_result", re.compile(
            r"(xác nhận|tiếp nhận|chấp thuận|hồ sơ.*đã|ngày\s+\d{1,2}\s+tháng)",
            re.IGNORECASE | re.UNICODE,
        )),
        ("rule_obligation", re.compile(
            r"(trường hợp|có trách nhiệm|chịu trách nhiệm|không được|bắt buộc|nghĩa vụ)",
            re.IGNORECASE | re.UNICODE,
        )),
        ("document_metadata", re.compile(
            r"(ủy ban nhân dân|cộng hòa xã hội|độc lập|tự do|hạnh phúc|số:\s*/|ngày\s+tháng\s+năm)",
            re.IGNORECASE | re.UNICODE,
        )),
    ]

    @classmethod
    def _detect_chunk_type(cls, text: str) -> str:
        for chunk_type, pattern in cls._CHUNK_TYPE_PATTERNS:
            if pattern.search(text):
                return chunk_type
        return "content"

    # ─────────────────────────── SEMANTIC CHUNKER ────────────────────────────

    _BOUNDARY_TYPES = {"section_header", "title", "page_header"}

    @classmethod
    def _semantic_chunk_elements(
        cls,
        elements: list,
        document_metadata: dict,
        max_chars: int = 1200,
        min_chars: int = 60,
    ) -> list:
        """
        Group normalized elements into semantic chunks.

        Rules:
        1. section_header / title / page_header -> flush current group, start new.
        2. Current group > max_chars -> flush before adding the next element.
        3. Tiny orphan chunks (< min_chars) -> merge into the previous chunk.
        4. Each chunk receives section, type, page range, and element IDs.
        """
        if not elements:
            return []

        chunks = []
        current_texts: list = []
        current_ids: list = []
        current_pages: list = []
        current_section: Optional[str] = None
        chunk_index = 0

        def _flush(texts, ids, pages, section):
            nonlocal chunk_index
            if not texts:
                return
            combined = "\n\n".join(t for t in texts if t.strip())
            if not combined.strip():
                return
            page_start = min((p for p in pages if p is not None), default=None)
            page_end = max((p for p in pages if p is not None), default=None)
            chunks.append({
                "id": None,
                "text": combined,
                "metadata": {
                    **document_metadata,
                    "chunk_index": chunk_index,
                    "section": section or "",
                    "chunk_type": cls._detect_chunk_type(combined),
                    "page_start": page_start,
                    "page_end": page_end,
                    "element_ids": list(ids),
                    "char_count": len(combined),
                },
            })
            chunk_index += 1

        for elem in elements:
            etype = elem.get("element_type", "text")
            text = elem.get("text", "").strip()
            page = elem.get("page")
            eid = elem.get("element_id", "")

            if not text:
                continue

            is_boundary = etype in cls._BOUNDARY_TYPES
            current_len = sum(len(t) for t in current_texts)
            would_exceed = (current_len + len(text)) > max_chars

            if is_boundary:
                _flush(current_texts, current_ids, current_pages, current_section)
                current_texts = [text]
                current_ids = [eid]
                current_pages = [page] if page is not None else []
                current_section = text
            elif would_exceed and current_texts:
                _flush(current_texts, current_ids, current_pages, current_section)
                current_texts = [text]
                current_ids = [eid]
                current_pages = [page] if page is not None else []
            else:
                current_texts.append(text)
                current_ids.append(eid)
                if page is not None:
                    current_pages.append(page)

        _flush(current_texts, current_ids, current_pages, current_section)

        # Merge tiny orphan chunks into previous
        merged: list = []
        for chunk in chunks:
            if merged and len(chunk["text"]) < min_chars:
                prev = merged[-1]
                prev["text"] = prev["text"] + "\n\n" + chunk["text"]
                prev["metadata"]["element_ids"].extend(chunk["metadata"]["element_ids"])
                prev["metadata"]["char_count"] = len(prev["text"])
                if chunk["metadata"].get("page_end") is not None:
                    prev["metadata"]["page_end"] = chunk["metadata"]["page_end"]
                if chunk["metadata"]["chunk_type"] != "content":
                    prev["metadata"]["chunk_type"] = chunk["metadata"]["chunk_type"]
            else:
                merged.append(chunk)

        for i, chunk in enumerate(merged):
            chunk["metadata"]["chunk_index"] = i

        return merged

    # ─────────────────────────── PUBLIC API ──────────────────────────────────

    def normalize(self, doc_json: dict, document_metadata: dict) -> tuple:
        """
        Clean Docling output while preserving element-level provenance.

        Pipeline:
            raw Docling elements
                -> sort by page and bounding-box reading order
                -> remove repeated cross-page structural noise
                -> deduplicate near-identical elements within the document
        """
        elements = self._elements_from_docling(doc_json)
        elements = self._remove_structural_noise(elements)
        elements = self._deduplicate_elements(elements)

        if not elements:
            return "", []

        normalized_elements = [
            {**element, "metadata": {**document_metadata, **{
                "element_id": element["element_id"],
                "page": element["page"],
                "bbox": element["bbox"],
                "coord_origin": element["coord_origin"],
                "element_type": element["element_type"],
            }}}
            for element in elements
        ]
        return "\n\n".join(element["text"] for element in elements), normalized_elements

    def chunk_elements(self, normalized_elements: list, document_metadata: dict) -> list:
        """
        Semantic chunking using Docling element structure.
        Preferred when normalized_elements are available.
        """
        return self._semantic_chunk_elements(normalized_elements, document_metadata)

    def chunk_text(self, text: str, document_metadata: dict) -> list:
        """Fallback chunker for plain text (no element structure)."""
        if not text.strip():
            return []
        from llama_index.core import Document
        nodes = self._get_pipeline().run(
            documents=[Document(text=text, metadata=document_metadata)],
            show_progress=False,
        )
        return [
            {
                "id": node.node_id,
                "text": node.get_content(),
                "metadata": {**document_metadata, "chunk_type": "content"},
            }
            for node in nodes
        ]

    def ingest(self, doc_json: dict, document_metadata: dict) -> tuple:
        """Legacy entry point kept for backward compatibility."""
        clean_text, elements = self.normalize(doc_json, document_metadata)
        if not elements:
            return clean_text, []
        return clean_text, self.chunk_elements(elements, document_metadata)

    def _get_pipeline(self):
        if self._pipeline is None:
            from app.config.settings import CHUNK_OVERLAP, CHUNK_SIZE
            from llama_index.core.ingestion import IngestionPipeline
            from llama_index.core.node_parser import SentenceSplitter
            self._pipeline = IngestionPipeline(
                transformations=[SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)]
            )
        return self._pipeline
