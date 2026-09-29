"""
Terminal Testing Script - Phase 2: AI / RAG Query Test
======================================================
Exercise the RAG flow directly from a terminal:
1. Embed a question with the NVIDIA NIM Embedding API.
2. Retrieve relevant top-k chunks from extracted data.
3. Send evidence and the question to the NVIDIA-compatible LLM.
4. Print the answer with source citations.

Usage:
    python tests/test_query_rag.py
    python tests/test_query_rag.py "How many paid days are granted for marriage leave?"
"""

import sys
import time
import json
from pathlib import Path

# UTF-8 stdout trên Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Thêm project root vào sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import (
    NGC_API_KEY,
    EMBEDDING_MODEL,
    TOP_K,
)
from app.retrieval.embedding_service import EmbeddingService
from app.retrieval.rag_service import RagService

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
    bar = "═" * 64
    print(f"\n{BOLD}{CYAN}{bar}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{bar}{RESET}")


class LocalJsonRetriever:
    """
    Retrieve chunks from evaluation/artifacts/debug_output.json and use NVIDIA
    NIM embeddings for terminal-based vector search without PostgreSQL.
    """
    def __init__(self, json_path: Path, embedder: EmbeddingService):
        self.embedder = embedder
        self.chunks = []
        self.chunk_embeddings = []
        self._load_and_embed_chunks(json_path)

    def _load_and_embed_chunks(self, json_path: Path):
        if not json_path.exists():
            print(f"  {YELLOW}⚠ Không tìm thấy {json_path}. Chạy scripts/run_debug.bat trước để trích xuất chunks.{RESET}")
            return

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_chunks = data.get("chunks", [])
        file_name = data.get("metadata", {}).get("file_name", "document.pdf")

        for idx, c in enumerate(raw_chunks):
            self.chunks.append({
                "chunk_id": f"chunk_{idx+1:03d}",
                "file_name": file_name,
                "content": c.get("text", ""),
                "metadata": c.get("metadata", {}),
            })

        print(f"  {DIM}[Nạp chunks]{RESET} Đã nạp {CYAN}{len(self.chunks)}{RESET} chunks từ {json_path.name}")
        
        # Tạo vector embedding cho các chunks nếu chưa có
        texts = [c["content"] for c in self.chunks]
        t0 = time.time()
        print(f"  {DIM}[Embedding]{RESET} Đang vector hóa {len(texts)} chunks bằng {CYAN}{self.embedder.model}{RESET}...")
        self.chunk_embeddings = self.embedder.embed_texts(texts, input_type="passage")
        print(f"  {GREEN}✔{RESET} Vector hóa hoàn thành trong {time.time() - t0:.2f}s ({len(self.chunk_embeddings)} vectors)")

    def retrieve(self, query: str, top_k: int = TOP_K, document_id=None, min_score=0.1):
        if not self.chunks or not self.chunk_embeddings:
            return []

        query_vec = self.embedder.embed_query(query)
        
        # Tính Cosine Similarity thủ công
        scored_chunks = []
        for chunk, emb in zip(self.chunks, self.chunk_embeddings):
            score = self._cosine_similarity(query_vec, emb)
            if score >= min_score:
                scored_chunks.append({
                    **chunk,
                    "similarity_score": round(score, 4),
                })

        # Sắp xếp giảm dần theo điểm tương đồng
        scored_chunks.sort(key=lambda x: x["similarity_score"], reverse=True)
        return scored_chunks[:top_k]

    @staticmethod
    def _cosine_similarity(v1, v2):
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = sum(a * a for a in v1) ** 0.5 or 1.0
        norm2 = sum(b * b for b in v2) ** 0.5 or 1.0
        return dot / (norm1 * norm2)


def run_rag_test(question: str, rag_service: RagService):
    header("TRUY VẤN HỎI ĐÁP — RAG PIPELINE")
    print(f"  {BOLD}Câu hỏi:{RESET} {YELLOW}{question}{RESET}")
    print(f"  {DIM}Model LLM:{RESET} {CYAN}{rag_service.model}{RESET}")
    print(f"  {DIM}Model Embedding:{RESET} {CYAN}{EMBEDDING_MODEL}{RESET}")
    print()

    t0 = time.time()
    result = rag_service.answer_question(question=question, top_k=TOP_K)
    elapsed = time.time() - t0

    answer = result.get("answer", "")
    sources = result.get("sources", [])

    print(f"  {BOLD}{GREEN}Câu trả lời từ AI:{RESET}")
    print(f"  {WHITE}{answer}{RESET}\n")

    print(f"  {BOLD}{CYAN}Nguồn trích dẫn (Sources - {len(sources)} tài liệu liên quan):{RESET}")
    for idx, src in enumerate(sources):
        fname = src.get("file_name", "")
        cid = src.get("chunk_id", "")
        page = src.get("page", "?")
        score = src.get("similarity_score", 0.0)
        snippet = src.get("snippet", "")
        print(f"    {BOLD}#{idx+1}{RESET} [{CYAN}{fname}{RESET} | {cid} | Trang {page}] — Độ khớp: {GREEN}{score*100:.1f}%{RESET}")
        print(f"       {DIM}Trích đoạn: \"{snippet}\"{RESET}")

    print(f"\n  {DIM}Thời gian phản hồi tổng: {elapsed:.2f}s{RESET}")


def main():
    print(f"\n{BOLD}{MAGENTA}{'='*64}{RESET}")
    print(f"{BOLD}{MAGENTA}  Mini RAG — Phase 2: RAG & Vector Retrieval Test{RESET}")
    print(f"{BOLD}{MAGENTA}{'='*64}{RESET}")

    masked_key = NGC_API_KEY[:8] + "..." + NGC_API_KEY[-4:] if NGC_API_KEY else "❌ EMPTY"
    print(f"  {DIM}NGC_API_KEY:{RESET} {CYAN}{masked_key}{RESET}")

    # Khởi tạo embedding và retriever
    embedder = EmbeddingService()
    json_path = Path(__file__).resolve().parent.parent / "evaluation" / "artifacts" / "debug_output.json"

    retriever = LocalJsonRetriever(json_path, embedder)
    rag_service = RagService(retriever=retriever)

    # Các câu hỏi mẫu trong quy định nghỉ phép
    default_questions = [
        "Quy trình xin nghỉ phép gồm những bước nào và ai là người phê duyệt?",
        "Thời gian báo trước khi xin nghỉ phép từ 7 ngày trở lên là bao nhiêu ngày?",
        "Nghỉ kết hôn được hưởng lương bao nhiêu ngày theo quy định?",
    ]

    if len(sys.argv) > 1:
        custom_q = " ".join(sys.argv[1:])
        run_rag_test(custom_q, rag_service)
    else:
        # Chạy câu hỏi mẫu đầu tiên
        print(f"\n  {DIM}Gợi ý: Bạn có thể đặt câu hỏi tùy ý bằng cách gõ:{RESET}")
        print(f"    {CYAN}python tests/test_query_rag.py \"Câu hỏi của bạn ở đây\"{RESET}\n")
        
        for q in default_questions[:1]:
            run_rag_test(q, rag_service)


if __name__ == "__main__":
    main()
