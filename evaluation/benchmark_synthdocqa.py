"""
Benchmark Suite: Mini RAG with SynthDocQA Dataset
=================================================
Evaluate RAG accuracy and performance on the SynthDocQA dataset:
- evaluate five local PDF files from grounding_pdfs_v2;
- report retrieval and generation metrics independently;
- break results down by table, form, figure, annotation, and text block;
- cache chunks and vectors for reproducible reruns.
"""

import sys
import os
import json
import time
import re
import argparse
import concurrent.futures
import hashlib
import math
import base64
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

# UTF-8 stdout trên Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Thêm project root vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import (
    NGC_API_KEY,
    NIM_BASE_URL,
    NIM_MODEL,
    LLM_RAG_MODEL,
    EMBEDDING_MODEL,
    TOP_K,
)
from app.retrieval.embedding_service import EmbeddingService
from app.retrieval.evidence_service import EvidenceService
from app.retrieval.rag_service import build_grounded_qa_system_prompt

# Đường dẫn mặc định tới dataset
DEFAULT_DATASET_DIR = Path(__file__).resolve().parent.parent / "datasets" / "synthdocqa"
CACHE_DIR = Path(__file__).resolve().parent / "benchmark_cache"
RESULTS_FILE = Path(__file__).resolve().parent / "benchmark_results.json"
REPORT_FILE = Path(__file__).resolve().parent / "benchmark_report.md"

# Danh sách 5 PDF có sẵn trong grounding_pdfs_v2
VALID_PDF_FILES = {
    "doc_0000_s1131058660.pdf",
    "doc_0000_s71722309.pdf",
    "doc_0000_s39946201.pdf",
    "doc_0000_s341236940.pdf",
    "doc_0000_s1045958549.pdf",
}

# ─── ANSI COLORS ───────────────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
CYAN    = "\033[36m"
RED     = "\033[31m"
MAGENTA = "\033[35m"
WHITE   = "\033[97m"


def log_header(text: str):
    bar = "═" * 68
    print(f"\n{BOLD}{CYAN}{bar}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{bar}{RESET}")


def log_info(label: str, value: Any = ""):
    print(f"  {DIM}•{RESET} {BOLD}{label}:{RESET} {CYAN}{value}{RESET}")


def log_success(text: str):
    print(f"  {GREEN}✔{RESET} {text}")


def log_warn(text: str):
    print(f"  {YELLOW}⚠{RESET} {text}")


# ─── EXTRACTOR & CHUNKER ───────────────────────────────────────────────────────

def extract_pdf_chunks(pdf_path: Path, manifest_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Extract PDF text and split it into structured chunks.
    """
    import pypdf

    reader = pypdf.PdfReader(str(pdf_path))
    chunks = []
    chunk_counter = 0

    # Nạp manifest để lấy thêm metadata cấu trúc nếu có
    manifest_elements = {}
    if manifest_path and manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
                for el in manifest_data.get("structure", []):
                    art_id = el.get("Artifact_ID") or el.get("variant_id")
                    if art_id:
                        manifest_elements[art_id] = el
        except Exception:
            pass

    for page_idx, page in enumerate(reader.pages, start=1):
        raw_text = (page.extract_text() or "").strip()
        if not raw_text:
            continue

        # Chuẩn hóa khoảng trắng
        clean_text = re.sub(r"[ \t]+", " ", raw_text)
        clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()

        # Nếu trang ngắn (< 1500 ký tự), giữ nguyên 1 chunk
        # Nếu trang dài, chia đoạn 1000 ký tự với gối đầu 150 ký tự
        max_chunk_size = 1200
        overlap = 150

        if len(clean_text) <= max_chunk_size:
            chunk_counter += 1
            chunks.append({
                "chunk_id": f"{pdf_path.stem}_p{page_idx}_c1",
                "file_name": pdf_path.name,
                "page": page_idx,
                "content": clean_text,
                "char_count": len(clean_text),
            })
        else:
            paragraphs = clean_text.split("\n\n")
            current_buffer = []
            curr_len = 0
            sub_idx = 1

            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                if curr_len + len(para) > max_chunk_size and current_buffer:
                    chunk_text = "\n\n".join(current_buffer)
                    chunk_counter += 1
                    chunks.append({
                        "chunk_id": f"{pdf_path.stem}_p{page_idx}_c{sub_idx}",
                        "file_name": pdf_path.name,
                        "page": page_idx,
                        "content": chunk_text,
                        "char_count": len(chunk_text),
                    })
                    sub_idx += 1
                    # Giữ lại đoạn cuối làm overlap
                    current_buffer = [current_buffer[-1]] if len(current_buffer[-1]) < overlap else []
                    curr_len = sum(len(p) for p in current_buffer)

                current_buffer.append(para)
                curr_len += len(para)

            if current_buffer:
                chunk_text = "\n\n".join(current_buffer)
                chunk_counter += 1
                chunks.append({
                    "chunk_id": f"{pdf_path.stem}_p{page_idx}_c{sub_idx}",
                    "file_name": pdf_path.name,
                    "page": page_idx,
                    "content": chunk_text,
                    "char_count": len(chunk_text),
                })

    return chunks


# ─── INDEX MANAGER (WITH DISK CACHE) ──────────────────────────────────────────

class SynthDocIndexManager:
    """Manage the SynthDocQA index and vector cache."""

    def __init__(
        self,
        dataset_dir: Path,
        embedder: EmbeddingService,
        cache_dir: Path = CACHE_DIR,
        ocr_cache_dir: Optional[Path] = None,
        table_cache_dir: Optional[Path] = None,
        visual_cache_dir: Optional[Path] = None,
        page_visual_cache_dir: Optional[Path] = None,
        annotation_cache_dir: Optional[Path] = None,
    ):
        self.dataset_dir = dataset_dir
        self.pdf_dir = dataset_dir / "grounding_pdfs_v2"
        self.manifest_dir = dataset_dir / "manifest_files"
        self.embedder = embedder
        self.cache_dir = cache_dir
        self.ocr_cache_dir = ocr_cache_dir
        self.table_cache_dir = table_cache_dir
        self.visual_cache_dir = visual_cache_dir
        self.page_visual_cache_dir = page_visual_cache_dir
        self.annotation_cache_dir = annotation_cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.all_chunks: List[Dict[str, Any]] = []
        self.all_embeddings: List[List[float]] = []
        self.file_to_chunks: Dict[str, List[Dict[str, Any]]] = {}

    def build_or_load_index(self, target_files: Optional[set] = None):
        """Build or load an index for the selected files."""
        target_files = target_files or VALID_PDF_FILES
        log_header(f"NẠP / XÂY DỰNG INDEX CHO {len(target_files)} TÀI LIỆU SYNTHDOCQA")

        for fname in sorted(target_files):
            pdf_path = self.pdf_dir / fname
            if not pdf_path.exists():
                log_warn(f"Tệp không tồn tại: {pdf_path}")
                continue

            cache_file = self.cache_dir / f"{fname}.json"
            manifest_file = self.manifest_dir / f"{pdf_path.stem}.json"
            ocr_file = (self.ocr_cache_dir / f"{fname}_tesseract.json") if self.ocr_cache_dir else None
            table_file = (self.table_cache_dir / f"{fname}.json") if self.table_cache_dir else None
            visual_file = (self.visual_cache_dir / f"{fname}.json") if self.visual_cache_dir else None
            page_visual_file = (self.page_visual_cache_dir / f"{fname}.json") if self.page_visual_cache_dir else None
            annotation_file = (self.annotation_cache_dir / f"{fname}.json") if self.annotation_cache_dir else None
            ocr_digest = hashlib.sha256(ocr_file.read_bytes()).hexdigest() if ocr_file and ocr_file.exists() else ""
            table_digest = hashlib.sha256(table_file.read_bytes()).hexdigest() if table_file and table_file.exists() else ""
            visual_digest = hashlib.sha256(visual_file.read_bytes()).hexdigest() if visual_file and visual_file.exists() else ""
            page_visual_digest = hashlib.sha256(page_visual_file.read_bytes()).hexdigest() if page_visual_file and page_visual_file.exists() else ""
            annotation_digest = hashlib.sha256(annotation_file.read_bytes()).hexdigest() if annotation_file and annotation_file.exists() else ""
            cache_key = hashlib.sha256(
                f"{hashlib.sha256(pdf_path.read_bytes()).hexdigest()}|{self.embedder.model}|page-chunk-v6-native-visual-metadata|{ocr_digest}|{table_digest}|{visual_digest}|{page_visual_digest}|{annotation_digest}".encode()
            ).hexdigest()

            if cache_file.exists():
                # Nạp từ cache
                t0 = time.time()
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                if cached_data.get("cache_key") == cache_key:
                    chunks = cached_data["chunks"]
                    embeddings = cached_data["embeddings"]
                    log_success(f"[Cache Hit] {fname}: {len(chunks)} chunks ({time.time() - t0:.2f}s)")
                else:
                    cached_data = None
            else:
                cached_data = None

            if cached_data is None:
                # Trích xuất và vector hóa mới khi file/model/chunker thay đổi.
                t0 = time.time()
                print(f"  {DIM}[Trích xuất]{RESET} Đang parse {CYAN}{fname}{RESET}...")
                chunks = extract_pdf_chunks(pdf_path, manifest_file)
                native_chunks = list(chunks)
                if ocr_file and ocr_file.exists():
                    with open(ocr_file, "r", encoding="utf-8") as f:
                        ocr_chunks = json.load(f).get("chunks", [])
                    for idx, chunk in enumerate(ocr_chunks):
                        item = dict(chunk)
                        item["chunk_id"] = f"{item.get('chunk_id', fname + '_ocr')}_{idx}"
                        item["retrieval_source"] = "tesseract_ocr"
                        chunks.append(item)
                    log_info(f"OCR chunks bổ sung {fname}", len(ocr_chunks))
                if table_file and table_file.exists():
                    table_data = json.loads(table_file.read_text(encoding="utf-8"))
                    for table in table_data.get("tables", []):
                        header = " | ".join(table.get("columns", []))
                        for row_idx, row in enumerate(table.get("rows", [])):
                            content = f"TABLE {table.get('table_id')}\nHEADER: {header}\nROW {row_idx}: " + " | ".join(str(v) for v in row)
                            chunks.append({"chunk_id": f"{table.get('table_id')}:r{row_idx}", "file_name": fname,
                                           "page": (table.get("pages") or [None])[0], "content": content,
                                           "retrieval_source": "table_structured", "table_id": table.get("table_id"),
                                           "row_index": row_idx, "table_header": header})
                    log_info(f"Structured table chunks bổ sung {fname}", len(chunks))
                if visual_file and visual_file.exists():
                    visual_data = json.loads(visual_file.read_text(encoding="utf-8"))
                    by_page = {}
                    for item in visual_data.get("items", []):
                        by_page.setdefault(int(item.get("page") or 0), []).append(item)
                    for visual_idx, item in enumerate(visual_data.get("items", [])):
                        page = int(item.get("page") or 0)
                        page_context = " ".join(
                            str(c.get("content", ""))
                            for c in native_chunks
                            if int(c.get("page") or 0) == page
                        )[:1600]
                        ocr_text = str(item.get("ocr_text") or "").strip()
                        content = (
                            f"VISUAL ELEMENT page {page}\n"
                            f"REGION OCR: {ocr_text}\n"
                            f"PAGE CONTEXT: {page_context}"
                        ).strip()
                        chunks.append({
                            "chunk_id": f"{fname}:visual:{visual_idx}",
                            "file_name": fname,
                            "page": page,
                            "content": content,
                            "retrieval_source": "visual_element",
                            "metadata": {"visual_evidence": [item]},
                        })
                    # Keep the crop available when a native page chunk wins
                    # retrieval. This does not add visual elements to the
                    # ranking pool; it only supplies the matching page crop
                    # during generation (especially useful for annotations).
                    for chunk in native_chunks:
                        page = int(chunk.get("page") or 0)
                        items = by_page.get(page, [])[:2]
                        if items:
                            chunk["metadata"] = {
                                **(chunk.get("metadata") or {}),
                                "visual_evidence": items,
                            }
                    log_info(f"Visual crops gắn vào {fname}", sum(len(v) for v in by_page.values()))
                if page_visual_file and page_visual_file.exists():
                    page_visual_data = json.loads(page_visual_file.read_text(encoding="utf-8"))
                    page_items = {
                        int(item.get("page") or 0): item
                        for item in page_visual_data.get("pages", [])
                    }
                    for chunk in chunks:
                        page = int(chunk.get("page") or 0)
                        page_item = page_items.get(page)
                        if page_item:
                            chunk["metadata"] = {
                                **(chunk.get("metadata") or {}),
                                "page_visual_evidence": [page_item],
                            }
                    log_info(f"Page snapshots gắn vào {fname}", len(page_items))
                if annotation_file and annotation_file.exists():
                    annotation_data = json.loads(annotation_file.read_text(encoding="utf-8"))
                    for region_idx, item in enumerate(annotation_data.get("items", [])):
                        page = int(item.get("page") or 0)
                        text = str(item.get("ocr_text") or "").strip()
                        if not text:
                            continue
                        chunks.append({
                            "chunk_id": f"{fname}:annotation:{region_idx}",
                            "file_name": fname,
                            "page": page,
                            "content": f"ANNOTATION REGION page {page}\n{text}",
                            "retrieval_source": "annotation_region",
                            "metadata": {"visual_evidence": [item]},
                        })
                    log_info(f"Annotation regions gắn vào {fname}", len(annotation_data.get("items", [])))
                print(f"    -> Đã tạo {len(chunks)} chunks. Đang tạo vector embedding...")

                texts = [c["content"] for c in chunks]
                embeddings = self.embedder.embed_texts(texts, input_type="passage")

                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump({"cache_key": cache_key, "embedding_model": self.embedder.model,
                               "chunks": chunks, "embeddings": embeddings}, f, ensure_ascii=False)
                log_success(f"[Cache Saved] {fname}: {len(chunks)} chunks trong {time.time() - t0:.2f}s")

            # Lưu vào bộ nhớ chung
            self.file_to_chunks[fname] = chunks
            for c, emb in zip(chunks, embeddings):
                self.all_chunks.append(c)
                self.all_embeddings.append(emb)

        log_info("Tổng số chunks trong toàn bộ index", len(self.all_chunks))
        log_info("Tổng số vector embeddings", len(self.all_embeddings))

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        target_file: Optional[str] = None,
        retrieval_source: Optional[str] = None,
        query_vector: Optional[List[float]] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve the most similar top-k chunks for a query."""
        if not self.all_chunks:
            return []

        q_vec = query_vector if query_vector is not None else self.embedder.embed_query(query)
        q_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        scored = []

        for idx, (chunk, emb) in enumerate(zip(self.all_chunks, self.all_embeddings)):
            if target_file and chunk["file_name"] != target_file:
                continue
            chunk_source = chunk.get("retrieval_source", "native")
            if retrieval_source and chunk_source != retrieval_source:
                continue
            # Cosine similarity (vectors từ NIM embedder đã được L2 normalized)
            score = sum(a * b for a, b in zip(q_vec, emb))
            content_terms = set(re.findall(r"[a-z0-9]+", (chunk.get("content") or "").lower()))
            lexical = len(q_terms & content_terms) / max(1, len(q_terms))
            hybrid = 0.65 * max(0.0, score) + 0.35 * lexical
            scored.append({
                **chunk,
                "similarity_score": round(score, 4),
                "lexical_score": round(lexical, 4),
                "hybrid_score": round(hybrid, 4),
            })

        scored.sort(key=lambda x: x["hybrid_score"], reverse=True)
        return scored[:top_k]


# ─── ASSERTION EVALUATION ──────────────────────────────────────────────────────

def extract_expected_value(assertion_text: str) -> Optional[str]:
    """Extract the expected value from an assertion string."""
    # Pattern 1: Giữa dấu ngoặc đơn: The response must state 'ABC'.
    m = re.search(r"['\"]([^'\"]+)['\"]", assertion_text)
    if m:
        return m.group(1).strip()

    # Pattern 2: Sau cụm "must state ": The response must state 123.
    m = re.search(r"(?:must state|mention|state)\s+([^\.]+)", assertion_text, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    return None


def assertion_texts(assertions: Any) -> List[str]:
    """Normalize SynthDocQA assertions (stored as strings or objects)."""
    if not isinstance(assertions, list):
        return []
    return [
        str(item.get("text", "")) if isinstance(item, dict) else str(item)
        for item in assertions
        if (item.get("text") if isinstance(item, dict) else item)
    ]


def normalize_answer_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().replace(",", "").replace("$", "")).strip()


def span_coverage(spans: List[str], text: str) -> int:
    """Approximate character span length supported by exact normalized substrings."""
    normalized = normalize_answer_text(text)
    intervals = []
    for span in spans:
        needle = normalize_answer_text(span)
        if not needle:
            continue
        start = 0
        while True:
            start = normalized.find(needle, start)
            if start < 0:
                break
            intervals.append((start, start + len(needle)))
            start += max(1, len(needle))
    if not intervals:
        return 0
    intervals.sort()
    total = 0
    left, right = intervals[0]
    for start, end in intervals[1:]:
        if start <= right:
            right = max(right, end)
        else:
            total += right - left
            left, right = start, end
    return total + right - left


def trace_retrieval_metrics(chunks: List[Dict[str, Any]], expected_values: List[str]) -> Dict[str, Optional[float]]:
    """Compute relevance proxy and completeness against available answer spans.

    RAGBench TRACe requires annotated relevant/utilized spans. Here the dataset
    only provides answer assertions, so this reports an explicitly labeled
    answer-span proxy, not the paper's human/LLM span annotations.
    """
    context_chars = sum(len(c.get("content", "")) for c in chunks)
    relevant_chars = sum(span_coverage(expected_values, c.get("content", "")) for c in chunks)
    relevance = relevant_chars / context_chars if context_chars else 0.0
    completeness = min(1.0, relevant_chars / max(1, sum(len(normalize_answer_text(v)) for v in expected_values))) if expected_values else None
    return {"context_relevance_answer_span_proxy": relevance,
            "answer_span_coverage_proxy": completeness,
            "context_utilization": None,
            "answer_adherence": None}


def evaluate_assertion(assertion_text: str, answer: str) -> Tuple[bool, str]:
    """
    Check whether an answer satisfies an assertion and return pass status/reason.
    """
    if not answer or "không tìm thấy" in answer.lower():
        return False, "Answer refused or missing content"

    expected = extract_expected_value(assertion_text)
    if not expected:
        # Fallback: kiểm tra xem các từ khóa dài trong assertion có trong answer không
        words = [w for w in re.findall(r"\w+", assertion_text) if len(w) > 4]
        match_count = sum(1 for w in words if w.lower() in answer.lower())
        if match_count >= max(1, len(words) // 2):
            return True, "Keyword match fallback"
        return False, "No explicit expected value extracted"

    # Chuẩn hóa so khớp
    norm_expected = expected.lower().replace(",", "").replace("$", "").strip()
    norm_answer = answer.lower().replace(",", "").replace("$", "").strip()

    # So khớp trực tiếp chuỗi
    if norm_expected in norm_answer:
        return True, f"Exact match on '{expected}'"

    # So khớp số học nếu là số
    try:
        exp_num = float(norm_expected)
        # Tìm các số trong answer
        numbers = [float(n) for n in re.findall(r"[-+]?\d*\.\d+|\d+", norm_answer)]
        if exp_num in numbers:
            return True, f"Numeric match on {exp_num}"
    except ValueError:
        pass

    return False, f"Expected '{expected}' not found in answer"


# ─── BENCHMARK RUNNER ─────────────────────────────────────────────────────────

class SynthDocBenchmark:
    """Coordinate the complete SynthDocQA benchmark."""

    def __init__(
        self,
        dataset_dir: Path = DEFAULT_DATASET_DIR,
        ocr_cache_dir: Optional[Path] = None,
        table_cache_dir: Optional[Path] = None,
        visual_cache_dir: Optional[Path] = None,
        page_visual_cache_dir: Optional[Path] = None,
        annotation_cache_dir: Optional[Path] = None,
        results_file: Path = RESULTS_FILE,
        report_file: Path = REPORT_FILE,
    ):
        self.dataset_dir = dataset_dir
        self.results_file = results_file
        self.report_file = report_file
        self.embedder = EmbeddingService(fallback_to_mock=False)
        self.evidence = EvidenceService()
        self.rag_service = None
        cache_dir = CACHE_DIR if ocr_cache_dir is None else CACHE_DIR.parent / "benchmark_cache_ocr"
        self.index_mgr = SynthDocIndexManager(dataset_dir, self.embedder, cache_dir=cache_dir,
            ocr_cache_dir=ocr_cache_dir, table_cache_dir=table_cache_dir,
            visual_cache_dir=visual_cache_dir, page_visual_cache_dir=page_visual_cache_dir,
            annotation_cache_dir=annotation_cache_dir)

    def load_valid_queries(self, doc_filter: Optional[str] = None, element_type_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Load ALL_queries.json and retain only queries targeting valid local PDFs.
        """
        queries_path = self.dataset_dir / "ALL_queries.json"
        if not queries_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file {queries_path}")

        with open(queries_path, "r", encoding="utf-8") as f:
            all_queries = json.load(f)

        target_files = {doc_filter} if doc_filter else VALID_PDF_FILES

        filtered = []
        for q in all_queries:
            refs = q.get("refs", [])
            # Query hợp lệ khi có ít nhất 1 ref nằm trong target_files
            valid_refs = [r for r in refs if r.get("filePath") in target_files]
            if valid_refs:
                primary_ref = valid_refs[0]
                target_pages = []
                for ref in valid_refs:
                    page_value = ref.get("page")
                    if isinstance(page_value, int):
                        target_pages.append(page_value)
                    for key in ("page", "page_num", "page_number", "pageIndex"):
                        nested_page = ref.get(key)
                        if isinstance(nested_page, int):
                            target_pages.append(nested_page)
                filtered.append({
                    **q,
                    "target_files": list(dict.fromkeys(r.get("filePath") for r in valid_refs)),
                    "target_pages": list(dict.fromkeys(target_pages)),
                    "element_type": primary_ref.get("element_type", "unknown"),
                    "artifact_id": primary_ref.get("Artifact_ID", ""),
                })

        if element_type_filter:
            filtered = [q for q in filtered if q.get("element_type") == element_type_filter]
        return filtered

    def run(
        self,
        doc_filter: Optional[str] = None,
        sample_size: int = -1,
        top_k: int = 5,
        skip_generation: bool = False,
        ocr_penalty: float = 0.8,
        candidate_multiplier: int = 4,
        element_type_filter: Optional[str] = None,
        concurrency: int = 4,
    ) -> Dict[str, Any]:
        target_files = {doc_filter} if doc_filter else VALID_PDF_FILES
        self.index_mgr.build_or_load_index(target_files)

        queries = self.load_valid_queries(doc_filter, element_type_filter)
        log_header(f"BẮT ĐẦU BENCHMARK — {len(queries)} CÂU HỎI TRONG PHẠM VI 5 FILE")

        if sample_size > 0 and sample_size < len(queries):
            # Lấy mẫu phân bố đều theo từng tài liệu
            from collections import defaultdict
            by_doc = defaultdict(list)
            for q in queries:
                for doc in q["target_files"]:
                    by_doc[doc].append(q)
            sampled = []
            per_doc = max(1, sample_size // len(by_doc))
            for doc, q_list in by_doc.items():
                sampled.extend(q_list[:per_doc])
            queries = sampled[:sample_size]
            log_warn(f"Đã lấy mẫu {len(queries)} câu hỏi (sample_size={sample_size})")

        # Embed each query once in batches. The retrieval experiment uses
        # several source channels, so embedding inside each channel caused up
        # to five network calls per question and made the full 877-query run
        # needlessly slow.
        query_texts = [q.get("query", "") for q in queries]
        if query_texts:
            print(f"  {DIM}Đang batch-embed {len(query_texts)} câu hỏi...{RESET}")
            query_vectors = self.embedder.embed_texts(query_texts, input_type="query")
            for query_obj, query_vector in zip(queries, query_vectors):
                query_obj["_query_vector"] = query_vector

        total_queries = len(queries)
        results = []

        # Thống kê
        hit_count_at_k = 0
        answer_span_eligible_count = 0
        doc_match_count = 0
        doc_hit_by_file = {f: 0 for f in target_files}
        page_match_count = 0
        assertion_pass_count = 0
        total_assertions = 0

        element_stats = {
            "table": {"total": 0, "hits": 0, "eligible": 0, "passed": 0},
            "form": {"total": 0, "hits": 0, "eligible": 0, "passed": 0},
            "figure": {"total": 0, "hits": 0, "eligible": 0, "passed": 0},
            "annotation": {"total": 0, "hits": 0, "eligible": 0, "passed": 0},
            "text_block": {"total": 0, "hits": 0, "eligible": 0, "passed": 0},
            "unknown": {"total": 0, "hits": 0, "eligible": 0, "passed": 0},
        }

        doc_stats = {f: {"total": 0, "hits": 0, "passed": 0, "page_hits": 0} for f in target_files}

        t_start = time.time()

        def process_single_query(idx: int, q_obj: Dict[str, Any]) -> Dict[str, Any]:
            qid = q_obj.get("Id", f"Q{idx+1}")
            query_text = q_obj.get("query", "")
            target_files = q_obj.get("target_files", [])
            elem_type = q_obj.get("element_type", "unknown")
            assertions = q_obj.get("assertions", [])

            t0 = time.time()
            # 1. Retrieval
            final_k = max(1, min(int(top_k), 8))
            candidate_k = min(40, max(final_k * max(1, int(candidate_multiplier)), 16))
            query_vector = q_obj.get("_query_vector")
            if query_vector is None:
                query_vector = self.embedder.embed_query(query_text)
            native_candidates = self.index_mgr.retrieve(
                query_text, top_k=candidate_k, retrieval_source="native", query_vector=query_vector
            )
            ocr_candidates = self.index_mgr.retrieve(
                query_text, top_k=candidate_k, retrieval_source="tesseract_ocr", query_vector=query_vector
            )
            visual_candidates = self.index_mgr.retrieve(
                query_text, top_k=candidate_k, retrieval_source="visual_element", query_vector=query_vector
            )
            annotation_candidates = self.index_mgr.retrieve(
                query_text, top_k=candidate_k, retrieval_source="annotation_region", query_vector=query_vector
            )
            table_candidates = self.index_mgr.retrieve(
                query_text, top_k=candidate_k, retrieval_source="table_structured", query_vector=query_vector
            )
            # Keep OCR as a supplemental recall channel. Its recognition errors
            # make it less reliable than the native text layer, so apply a
            # modest score penalty after content-based reranking.
            table_query = elem_type == "table" or bool(re.search(
                r"\b(table|row|column|cell|year|amount|total|percent|percentage|value|fiscal|revenue|cost|rate)\b",
                query_text.lower(),
            ))
            # The current visual cache is built from Docling picture regions.
            # They are valid figure candidates, but they do not represent
            # SynthDocQA callouts/highlights/colored-table annotations. Do not
            # let those unrelated crops displace the OCR/page channel for
            # annotation queries until annotation-specific regions are indexed.
            visual_query = elem_type == "figure"
            annotation_query = elem_type == "annotation"
            if table_query:
                # Route table-like questions through the structured branch first;
                # retain a smaller native/OCR fallback for captions and context.
                raw_retrieved = table_candidates + native_candidates[: candidate_k // 2] + ocr_candidates[: candidate_k // 2]
            elif visual_query:
                # Visual elements are first-class retrieval units. Native/OCR
                # page chunks remain as context, but cannot displace a crop
                # when the question explicitly targets a figure/annotation.
                raw_retrieved = visual_candidates + native_candidates[: candidate_k // 2] + ocr_candidates[: candidate_k // 2]
            elif annotation_query:
                raw_retrieved = annotation_candidates + native_candidates[: candidate_k // 2] + ocr_candidates[: candidate_k // 2]
            else:
                raw_retrieved = native_candidates + ocr_candidates
            ranked_retrieved = self.evidence.rerank(query_text, raw_retrieved)
            for chunk in ranked_retrieved:
                if chunk.get("retrieval_source") == "tesseract_ocr" and not visual_query:
                    chunk["content_relevance_score"] = round(
                        chunk.get("content_relevance_score", 0.0) * float(ocr_penalty), 4
                    )
            ranked_retrieved.sort(
                key=lambda x: (
                    x.get("content_relevance_score", 0.0)
                    * (1.08 if table_query and x.get("retrieval_source") == "table_structured" else 1.0)
                    * (1.25 if visual_query and x.get("retrieval_source") == "visual_element" else 1.0)
                    * (1.15 if annotation_query and x.get("retrieval_source") == "annotation_region" else 1.0)
                    * (1.15 if visual_query and x.get("retrieval_source") == "tesseract_ocr" else 1.0),
                    x.get("similarity_score", 0.0),
                ),
                reverse=True,
            )
            retrieved = [
                c for c in ranked_retrieved
                if c.get("content_relevance_score", 0.0) >= 0.12
            ][:final_k]
            if table_query:
                # Parent expansion: a matching row is insufficient without its
                # table context. Add the nearest row from the same structured
                # table while keeping the original ranked evidence first.
                selected_ids = {
                    c.get("table_id") for c in retrieved
                    if c.get("retrieval_source") == "table_structured" and c.get("table_id")
                }
                if selected_ids:
                    neighbors = [
                        c for c in self.index_mgr.all_chunks
                        if c.get("retrieval_source") == "table_structured"
                        and c.get("table_id") in selected_ids
                        and c not in retrieved
                    ]
                    neighbors.sort(key=lambda c: (c.get("table_id", ""), c.get("row_index", 0)))
                    retrieved.extend(neighbors[: max(0, 8 - len(retrieved))])
            retrieval_time = round(time.time() - t0, 3)

            # Đánh giá Retrieval: có lấy đúng tài liệu không?
            doc_hit = any(c["file_name"] in target_files for c in retrieved)
            target_pages = q_obj.get("target_pages", [])
            page_hit = (
                any(c["file_name"] in target_files and c.get("page") in target_pages for c in retrieved)
                if target_pages else None
            )

            # Assertion answer spans are used only as a lexical retrieval proxy.
            content_hit = False
            texts = assertion_texts(assertions)
            expected_vals = [extract_expected_value(a) for a in texts]
            expected_vals = [v for v in expected_vals if v]

            for val in expected_vals:
                norm_v = normalize_answer_text(val)
                if any(
                    norm_v in normalize_answer_text(c["content"])
                    for c in retrieved if c["file_name"] in target_files
                ):
                    content_hit = True
                    break
            target_retrieved = [c for c in retrieved if c["file_name"] in target_files]
            trace_metrics = trace_retrieval_metrics(target_retrieved, expected_vals)

            # 2. Generation & Answer Evaluation
            answer = ""
            generation_time = 0.0
            assertion_results = []
            all_passed = False

            if not skip_generation:
                if self.rag_service is None:
                    from app.retrieval.rag_service import RagService
                    self.rag_service = RagService(retriever="mock")
                # In document-scoped QA, do not let equally similar chunks
                # from another uploaded PDF override the selected document's
                # callout/highlight/table evidence. Retrieval metrics still
                # use the complete candidate set; only generation context is
                # scoped here.
                generation_retrieved = [
                    c for c in retrieved if c.get("file_name", c.get("file")) in target_files
                ] or retrieved
                # Tạo prompt context
                context_blocks = [
                    f"[CHUNK #{i+1} | File: {c.get('file_name', c.get('file', ''))} | Trang: {c['page']}]\n{c['content']}"
                    for i, c in enumerate(generation_retrieved)
                ]
                full_context = "\n\n".join(context_blocks)
                sys_prompt = build_grounded_qa_system_prompt()
                usr_prompt = f"--- EVIDENCE ---\n{full_context}\n\n--- QUESTION ---\n{query_text}\n\nAnswer directly:"

                # Forward attached visual evidence to the vision-capable LLM.
                # The text benchmark still works when no crop is attached, but
                # figure/annotation questions must include the rendered crop
                # or the run silently degrades to text-only QA.
                image_inputs = []
                seen_image_paths = set()
                image_chunks = generation_retrieved
                if elem_type == "annotation":
                    # Annotation pages often carry visual markers that are
                    # absent from the question text. Prefer the candidate
                    # containing those markers when the endpoint accepts only
                    # one image per request.
                    marker_re = re.compile(
                        r"\b(warning|approved|highlight|callout|status|archived|subject to change)\b|■",
                        re.IGNORECASE,
                    )
                    image_chunks = sorted(
                        retrieved,
                        key=lambda c: len(marker_re.findall(c.get("content", ""))),
                        reverse=True,
                    )
                for chunk in image_chunks:
                    chunk_metadata = chunk.get("metadata") or {}
                    visual_items = (
                        chunk_metadata.get("visual_evidence", [])
                        + chunk_metadata.get("page_visual_evidence", [])
                    )
                    for visual in visual_items:
                        image_path = visual.get("path")
                        if not image_path or image_path in seen_image_paths:
                            continue
                        image_file = Path(image_path)
                        if not image_file.exists():
                            continue
                        seen_image_paths.add(image_path)
                        try:
                            encoded = base64.b64encode(image_file.read_bytes()).decode("ascii")
                            mime = "image/jpeg" if image_file.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
                            image_inputs.append(f"data:{mime};base64,{encoded}")
                        except OSError:
                            continue
                        if len(image_inputs) >= 1:
                            break
                    if len(image_inputs) >= 1:
                        break

                t_gen = time.time()
                try:
                    answer = self.rag_service._call_llm(
                        sys_prompt,
                        usr_prompt,
                        image_inputs=image_inputs or None,
                    )
                except Exception as exc:
                    answer = f"[LLM ERROR: {exc}]"
                generation_time = round(time.time() - t_gen, 3)

                # Đánh giá assertions
                passed_for_q = True
                for atext in texts:
                    passed, reason = evaluate_assertion(atext, answer)
                    assertion_results.append({
                        "assertion": atext,
                        "passed": passed,
                        "reason": reason,
                    })
                    if not passed:
                        passed_for_q = False

                all_passed = passed_for_q if assertions else False

            return {
                "id": qid,
                "query": query_text,
                "target_files": target_files,
                "target_pages": q_obj.get("target_pages", []),
                "element_type": elem_type,
                "doc_hit": doc_hit,
                "page_hit": page_hit,
                "content_hit": content_hit,
                "answer_span_eligible": bool(expected_vals),
                "trace_metrics": trace_metrics,
                "retrieval_time": retrieval_time,
                "generation_time": generation_time,
                "answer": answer,
                "assertions": assertion_results,
                "all_passed": all_passed,
                "retrieved_chunks": [
                    {"page": c["page"], "chunk_id": c["chunk_id"], "score": c["similarity_score"], "file": c["file_name"], "content": c["content"]}
                    for c in retrieved
                ],
            }

        print(f"\n  {DIM}Đang thực thi benchmark với concurrency={concurrency}...{RESET}\n")

        # Chạy song song hoặc tuần tự
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            future_to_idx = {
                executor.submit(process_single_query, i, q): i
                for i, q in enumerate(queries)
            }
            completed = 0
            for future in concurrent.futures.as_completed(future_to_idx):
                res = future.result()
                results.append(res)
                completed += 1

                # Cập nhật số liệu
                if res["doc_hit"]:
                    doc_match_count += 1
                    for fname in res["target_files"]:
                        if fname in doc_hit_by_file:
                            doc_hit_by_file[fname] += 1
                if res["page_hit"]:
                    page_match_count += 1
                if res["answer_span_eligible"]:
                    answer_span_eligible_count += 1
                if res["content_hit"]:
                    hit_count_at_k += 1
                if res["all_passed"]:
                    assertion_pass_count += 1

                el = res["element_type"] if res["element_type"] in element_stats else "unknown"
                element_stats[el]["total"] += 1
                if res["content_hit"]:
                    element_stats[el]["hits"] += 1
                if res["answer_span_eligible"]:
                    element_stats[el]["eligible"] += 1
                if res["all_passed"]:
                    element_stats[el]["passed"] += 1

                for df in res["target_files"]:
                    if df in doc_stats:
                        doc_stats[df]["total"] += 1
                        if res["content_hit"]:
                            doc_stats[df]["hits"] += 1
                        if res["answer_span_eligible"]:
                            doc_stats[df]["eligible"] = doc_stats[df].get("eligible", 0) + 1
                        if res["page_hit"]:
                            doc_stats[df]["page_hits"] += 1
                        if res["all_passed"]:
                            doc_stats[df]["passed"] += 1

                # Tiến trình
                pass_icon = f"{GREEN}✔ PASS{RESET}" if res["all_passed"] else f"{RED}✖ FAIL{RESET}"
                hit_icon = f"{GREEN}HIT{RESET}" if res["content_hit"] else f"{YELLOW}MISS{RESET}"
                sys.stdout.write(
                    f"\r  [{completed}/{total_queries}] {res['id']} | [{res['element_type']}] | Retrieval: {hit_icon} | Gen: {pass_icon} "
                )
                sys.stdout.flush()

        total_elapsed = round(time.time() - t_start, 2)
        print("\n")

        # Tính tỷ lệ phần trăm
        hit_rate = round((hit_count_at_k / answer_span_eligible_count) * 100, 2) if answer_span_eligible_count else 0
        doc_hit_rate = round((doc_match_count / total_queries) * 100, 2) if total_queries else 0
        page_total = sum(bool(r.get("target_pages")) for r in results)
        page_hit_rate = round((page_match_count / page_total) * 100, 2) if page_total else None
        pass_rate = None if skip_generation else (round((assertion_pass_count / total_queries) * 100, 2) if total_queries else 0)
        trace_values = [r["trace_metrics"] for r in results]
        relevance_values = [v["context_relevance_answer_span_proxy"] for v in trace_values if v["context_relevance_answer_span_proxy"] is not None]
        completeness_values = [v["answer_span_coverage_proxy"] for v in trace_values if v["answer_span_coverage_proxy"] is not None]
        mean_relevance = round(sum(relevance_values) / len(relevance_values), 4) if relevance_values else None
        mean_completeness = round(sum(completeness_values) / len(completeness_values), 4) if completeness_values else None

        # Explain whether failures came from missing text in the target PDF or
        # from answer generation after retrieval. This is an association, not a
        # causal estimate.
        span_groups = {True: [], False: []}
        for item in results:
            if item.get("answer_span_eligible"):
                span_groups[bool(item.get("content_hit"))].append(item)

        def _pass_pct(items):
            return round(100 * sum(bool(x.get("all_passed")) for x in items) / len(items), 2) if items else None

        diagnostics = {
            "answer_span_hit_count": len(span_groups[True]),
            "answer_span_miss_count": len(span_groups[False]),
            "assertion_pass_rate_given_answer_span_hit_pct": _pass_pct(span_groups[True]) if not skip_generation else None,
            "assertion_pass_rate_given_answer_span_miss_pct": _pass_pct(span_groups[False]) if not skip_generation else None,
        }

        pipeline_diagnostics = None
        if not skip_generation:
            from pypdf import PdfReader
            target_text = {}
            for fname in target_files:
                pdf_path = self.dataset_dir / "grounding_pdfs_v2" / fname
                if pdf_path.exists():
                    reader = PdfReader(str(pdf_path), strict=False)
                    target_text[fname] = normalize_answer_text("\n".join(p.extract_text() or "" for p in reader.pages))
            by_type = {}
            eligible_queries = found_queries = off_target_only_hits = 0
            for item in results:
                expected = [
                    extract_expected_value(a.get("assertion", ""))
                    for a in item.get("assertions", [])
                ]
                expected = [normalize_answer_text(x) for x in expected if x]
                if not expected:
                    continue
                eligible_queries += 1
                element_type = item.get("element_type", "unknown")
                stat = by_type.setdefault(element_type, {"eligible": 0, "found": 0})
                stat["eligible"] += 1
                target_files_for_query = item.get("target_files", [])
                in_target = any(
                    val in target_text.get(fname, "")
                    for fname in target_files_for_query for val in expected
                )
                if in_target:
                    found_queries += 1
                    stat["found"] += 1
                retrieved = item.get("retrieved_chunks", [])
                in_any_chunk = any(
                    val in normalize_answer_text(chunk.get("content", ""))
                    for val in expected for chunk in retrieved
                )
                if in_any_chunk and not in_target:
                    off_target_only_hits += 1
            pipeline_diagnostics = {
                "eligible_queries": eligible_queries,
                "expected_span_found_in_target_text": found_queries,
                "expected_span_found_in_target_text_pct": round(100 * found_queries / eligible_queries, 2) if eligible_queries else None,
                "off_target_only_hits": off_target_only_hits,
                "by_element_type": by_type,
            }

        # Tổng hợp kết quả
        benchmark_summary = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "scope": "5 Grounding PDFs (Exclusive)",
            "total_queries": total_queries,
            "top_k": top_k,
            "candidate_top_k": min(40, max(max(1, min(int(top_k), 8)) * 4, 16)),
            "retrieval_reranker": "EvidenceService token/phrase/dense rerank; relevance cutoff 0.12",
            "generation_prompt": "shared production grounded multilingual document QA prompt",
            "ocr_augmented": self.index_mgr.ocr_cache_dir is not None,
            "skip_generation": skip_generation,
            "embedding_model": self.embedder.model,
            "generation_model": LLM_RAG_MODEL,
            "dataset_dir": str(self.dataset_dir),
            "trace_note": "Answer-span proxies use SynthDocQA assertions and exact span matching; TRACe utilization/adherence require span labels and generated responses.",
            "diagnostics": diagnostics,
            "pipeline_diagnostics": pipeline_diagnostics,
            "total_time_seconds": total_elapsed,
            "metrics": {
                "document_hit_rate_pct": doc_hit_rate,
                "target_page_hit_rate_pct": page_hit_rate,
                "content_hit_rate_pct": hit_rate,
                "assertion_pass_rate_pct": pass_rate,
                "assertion_pass_count": assertion_pass_count if not skip_generation else None,
                "context_relevance_answer_span_proxy_mean": mean_relevance,
                "answer_span_coverage_proxy_mean": mean_completeness,
                "context_utilization_mean": None,
                "answer_adherence_pct": None,
            },
            "by_element_type": element_stats,
            "by_document": {f: {**s, "doc_hits": doc_hit_by_file.get(f, 0)} for f, s in doc_stats.items()},
            "details": results,
        }

        # Lưu kết quả JSON
        with open(self.results_file, "w", encoding="utf-8") as f:
            json.dump(benchmark_summary, f, ensure_ascii=False, indent=2)
        log_success(f"Đã lưu kết quả chi tiết vào: {self.results_file}")

        # Tạo báo cáo Markdown
        self.generate_markdown_report(benchmark_summary)

        return benchmark_summary

    def generate_markdown_report(self, data: Dict[str, Any]):
        """Write the benchmark report as a Markdown table and summary."""
        m = data["metrics"]
        lines = [
            "# Báo cáo Benchmark Hệ thống RAG — SynthDocQA (5 File Cục bộ)",
            f"\n- **Thời gian thực hiện**: `{data['timestamp']}`",
            f"- **Phạm vi đánh giá**: Chỉ tính trên **5 tệp PDF có sẵn** (loại bỏ mọi query ngoài phạm vi)",
            f"- **Tổng số câu hỏi đánh giá**: `{data['total_queries']}` câu hỏi",
            f"- **Tham số Retrieval Top-K**: `{data['top_k']}`",
            f"- **Candidate retrieval trước rerank**: `{data.get('candidate_top_k', data['top_k'])}` chunks; rerank bằng token/phrase/dense score, cutoff 0.12",
            f"- **OCR augmentation**: `{'Tesseract, giữ riêng nhánh OCR và giảm trọng số 20%' if data.get('ocr_augmented') else 'tắt; chỉ dùng text layer'} (retrieval benchmark)",
            f"- **Embedding model**: `{data.get('embedding_model', 'unknown')}`",
            f"- **Generation model**: `{data.get('generation_model', 'unknown')}`",
            f"- **Tổng thời gian chạy**: `{data['total_time_seconds']:.1f}` giây",
            "\n## 1. Kết quả Tổng quan",
            "\n| Chỉ số Đánh giá | Giá trị (%) | Mô tả |",
            "| :--- | :--- | :--- |",
            f"| **Document Hit Rate** | **{m['document_hit_rate_pct']}%** | Top-K chunks chứa đúng tài liệu mục tiêu |",
            f"| **Assertion Answer-Span Hit (proxy)** | **{m['content_hit_rate_pct']}%** | Top-K chứa literal từ assertions có thể trích xuất |",
            f"| **Target Page Hit Rate** | **{m['target_page_hit_rate_pct'] if m['target_page_hit_rate_pct'] is not None else 'N/A'}** | Dataset không cung cấp page ground truth |",
            f"| **Assertion Pass Rate** | **{str(m['assertion_pass_rate_pct']) + '%' if m['assertion_pass_rate_pct'] is not None else 'N/A (generation skipped)'}** | Câu trả lời AI đạt mọi assertion của query |",
            "\n## 2. TRACe-inspired metrics",
            "\nRAGBench TRACe gốc cần nhãn span relevant/utilized và câu trả lời. SynthDocQA chỉ có assertions; hai proxy dưới đây dùng exact answer spans, không tương đương nhãn span TRACe.",
            f"\n- **Context relevance (answer-span proxy)**: {m['context_relevance_answer_span_proxy_mean']}",
            f"- **Completeness (answer-span coverage proxy)**: {m['answer_span_coverage_proxy_mean']}",
            "- **Context utilization / adherence**: N/A — cần annotation span và câu trả lời để chấm theo TRACe.",
            "\n## 3. Phân tích theo Loại Phần tử (Element Type Breakdown)",
            "\n| Loại Phần tử | Số câu hỏi | Answer-Span Hit (%) | Assertion Pass Rate (%) |",
            "| :--- | :--- | :--- | :--- |",
        ]

        for el, s in data["by_element_type"].items():
            if s["total"] == 0:
                continue
            hr = round((s["hits"] / s["eligible"]) * 100, 1) if s.get("eligible") else "N/A"
            pr = f"{round((s['passed'] / s['total']) * 100, 1)}%" if not data.get("skip_generation") else "N/A"
            lines.append(f"| `{el}` | {s['total']} | {hr}% | {pr} |")

        lines.extend([
            "\n## 4. Phân tích theo Từng Tài liệu",
            "\n| Tên Tệp PDF | Số câu hỏi | Answer-Span Hit (%) | Document Hit (%) | Assertion Pass (%) |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ])

        for doc, s in data["by_document"].items():
            if s["total"] == 0:
                continue
            hr = round((s["hits"] / s["eligible"]) * 100, 1) if s.get("eligible") else "N/A"
            dh = round((s.get("doc_hits", 0) / s["total"]) * 100, 1)
            pr = f"{round((s['passed'] / s['total']) * 100, 1)}%" if not data.get("skip_generation") else "N/A"
            lines.append(f"| `{doc}` | {s['total']} | {hr}% | {dh}% | {pr} |")

        lines.extend([
            "\n## Ghi chú cách chấm",
            "\n- Chỉ query có ít nhất một ref tới đúng 5 PDF được đưa vào benchmark.",
            "- Document Hit chỉ xác nhận có chunk từ file tham chiếu trong Top-K; không xác nhận đúng artifact/page.",
            "- Answer-span hit là exact substring từ assertion trích xuất được, chỉ tính khi xuất hiện trong chunk thuộc PDF ref của query.",
            "- Điểm này không thể so trực tiếp với RAGBench paper do corpus và nhãn khác nhau.",
            "- Tham chiếu phương pháp: [RAGBench / TRACe](https://arxiv.org/abs/2407.11005).",
        ])

        diagnostics = data.get("diagnostics")
        if diagnostics:
            lines.extend([
                "\n## 5. Đọc kết quả để tinh chỉnh",
                f"\n- Assertion pass khi answer span có trong Top-K: **{diagnostics['assertion_pass_rate_given_answer_span_hit_pct']}%**.",
                f"- Assertion pass khi answer span không có trong Top-K: **{diagnostics['assertion_pass_rate_given_answer_span_miss_pct']}%**.",
                "- Đây là tương quan quan sát được, không chứng minh quan hệ nhân quả.",
            ])

        extraction = data.get("pipeline_diagnostics")
        if extraction:
            figure = extraction["by_element_type"].get("figure", {"found": 0, "eligible": 0})
            lines.extend([
                "\n## 6. Nút thắt trong pipeline",
                f"\n- Expected literal có trong text đã trích từ PDF đích ở **{extraction['expected_span_found_in_target_text']}/{extraction['eligible_queries']}** query ({extraction['expected_span_found_in_target_text_pct']}%).",
                f"- Với `figure`, chỉ **{figure['found']}/{figure['eligible']}** expected literal xuất hiện trong text layer PDF. Benchmark extractor dùng `pypdf.page.extract_text()` và không OCR/render ảnh.",
                f"- Trong metric cũ, **{extraction['off_target_only_hits']}** query chỉ hit answer literal trong chunk từ PDF khác; metric đã sửa để chỉ chấm PDF ref của query.",
                "- Query có `Artifact_ID`, nhưng benchmark không dùng ID này để định vị element/page; document-level hit có thể trúng form/table khác cùng PDF.",
                "- Benchmark dùng chung reranker và prompt với production, nhưng gọi `_call_llm` trực tiếp; chưa chạy DB hybrid retrieval, extraction/OCR hoặc evidence coverage gate của `RagService.answer_question`.",
            ])

        sweep = data.get("top_k_sweep")
        if sweep:
            lines.extend([
                "\n## 7. Tuning sweep: Top-K",
                "\nSweep retrieval-only trên toàn bộ 877 query thuộc phạm vi; answer-span denominator gồm các query có assertion value trích xuất được. Generation chỉ được chạy ở K=5.",
                "\n| K | Document Hit (%) | Answer-Span Hit (%) |",
                "| :--- | :--- | :--- |",
            ])
            for item in sweep:
                lines.append(f"| {item['top_k']} | {item['document_hit_rate_pct']}% | {item['answer_span_hit_rate_pct']}% |")
            lines.append("\nK=10 tăng document hit và answer-span hit so với K=5. Dùng K=10 làm candidate retrieval để thử bước rerank/cắt context; chưa kết luận đây là K tốt nhất cho generation nếu chưa đo assertion pass và context cost ở K=10.")

        with open(self.report_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        log_success(f"Đã xuất báo cáo Markdown vào: {self.report_file}")


# ─── MAIN CLI ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Benchmark RAG on SynthDocQA (5 PDFs only)")
    parser.add_argument("--doc", type=str, default="", help="Chỉ benchmark 1 file cụ thể (vd: doc_0000_s1131058660.pdf)")
    parser.add_argument("--sample", type=int, default=-1, help="Giới hạn số câu hỏi mẫu (vd: 20 để test nhanh, -1 là chạy hết)")
    parser.add_argument("--top-k", type=int, default=5, help="Số lượng Top-K chunks (mặc định: 5)")
    parser.add_argument("--skip-generation", action="store_true", help="Chỉ đánh giá Retrieval, bỏ qua LLM Generation")
    parser.add_argument("--concurrency", type=int, default=4, help="Số luồng gọi API LLM song song")
    parser.add_argument("--ocr-cache-dir", type=Path, default=None, help="Thêm OCR chunks Tesseract vào text layer")
    parser.add_argument("--table-cache-dir", type=Path, default=None, help="Thêm chunks bảng đã khôi phục cấu trúc")
    parser.add_argument("--visual-cache-dir", type=Path, default=None, help="Thêm visual crop theo trang")
    parser.add_argument("--page-visual-cache-dir", type=Path, default=None, help="Ảnh snapshot toàn trang cho annotation")
    parser.add_argument("--annotation-cache-dir", type=Path, default=None, help="OCR tile riêng cho callout/highlight/colored table")
    parser.add_argument("--ocr-penalty", type=float, default=0.8, help="Hệ số điểm OCR sau rerank (mặc định 0.8)")
    parser.add_argument("--candidate-multiplier", type=int, default=4, help="Số candidate theo top-k trước rerank (mặc định 4)")
    parser.add_argument("--element-type", type=str, default="", help="Chỉ benchmark loại phần tử, vd table")
    parser.add_argument("--results-file", type=Path, default=RESULTS_FILE, help="Đường dẫn JSON kết quả")
    parser.add_argument("--report-file", type=Path, default=REPORT_FILE, help="Đường dẫn Markdown báo cáo")
    args = parser.parse_args()

    bench = SynthDocBenchmark(
        ocr_cache_dir=args.ocr_cache_dir,
        table_cache_dir=args.table_cache_dir,
        visual_cache_dir=args.visual_cache_dir,
        page_visual_cache_dir=args.page_visual_cache_dir,
        annotation_cache_dir=args.annotation_cache_dir,
        results_file=args.results_file,
        report_file=args.report_file,
    )
    bench.run(
        doc_filter=args.doc if args.doc else None,
        sample_size=args.sample,
        top_k=args.top_k,
        skip_generation=args.skip_generation,
        ocr_penalty=args.ocr_penalty,
        candidate_multiplier=args.candidate_multiplier,
        element_type_filter=args.element_type or None,
        concurrency=args.concurrency,
    )


if __name__ == "__main__":
    main()
