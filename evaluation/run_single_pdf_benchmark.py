"""Run a small, reproducible RAG evaluation against one arbitrary PDF.

The runner uses the production embedding service, EvidenceService, grounded
prompt, and RagService generation path. Retrieval is held in memory so the
evaluation does not require PostgreSQL or MinIO.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
from pathlib import Path
from typing import Any

from app.retrieval.embedding_service import EmbeddingService
from app.retrieval.evidence_service import EvidenceService
from app.retrieval.rag_service import RagService


QUESTIONS = [
    {
        "id": "Q01",
        "question": "Tôi vừa đủ 18 tuổi và đang tìm hiểu khoản vay MBSLink. Trước khi đăng ký, giới hạn tuổi tối đa có khác nhau giữa khách hàng nữ và nam không, cụ thể là bao nhiêu?",
        "required": [["18 tuổi"], ["60 tuổi"], ["65 tuổi"]],
    },
    {
        "id": "Q02",
        "question": "Tôi là người Việt Nam đang cư trú trong nước và muốn đăng ký MBSLink. Hồ sơ có yêu cầu tôi phải có đầy đủ năng lực pháp luật và năng lực hành vi dân sự hay điều kiện tương tự nào không?",
        "required": [["cá nhân người Việt Nam cư trú"], ["năng lực pháp luật"], ["năng lực hành vi dân sự"]],
    },
    {
        "id": "Q03",
        "question": "Tôi đang có tài khoản chứng khoán ở nơi khác nhưng chưa giao dịch qua MBS. Để dùng được MBSLink thì tôi có bắt buộc phải đứng tên một tài khoản giao dịch chứng khoán mở tại MBS không?",
        "required": [["chủ tài khoản giao dịch chứng khoán"], ["MBS"]],
    },
    {
        "id": "Q04",
        "question": "Ứng dụng báo tôi chưa đủ điều kiện đăng ký dịch vụ. Tôi cần chuyển sang gói nào trên MBBank, và việc định danh với ngân hàng phải được thực hiện ra sao?",
        "required": [["gói nâng cao"], ["định danh trực tiếp"], ["CBNV MB"]],
    },
    {
        "id": "Q05",
        "question": "Tôi muốn kiểm tra trước xem lịch sử tín dụng có ảnh hưởng đến việc được cấp hạn mức MBSLink hay không. Trong 12 tháng gần đây và tại thời điểm vay, những khoản nợ nào sẽ khiến tôi không đủ điều kiện?",
        "required": [["nhóm 2"], ["nhóm 5"], ["12 tháng"], ["nợ quá hạn"]],
    },
    {
        "id": "Q06",
        "question": "Tôi đã đăng nhập app MBBank nhưng chưa tìm thấy chỗ đăng ký hạn mức cho nhu cầu đầu tư. Có thể hướng dẫn tôi đi từ màn hình đầu tiên đến đúng chức năng cần chọn không?",
        "required": [["đăng nhập"], ["vay online"], ["SXKD và đầu tư"], ["đăng ký cấp hạn mức"]],
    },
    {
        "id": "Q07",
        "question": "Tôi chưa từng mở tài khoản chứng khoán tại MBS. Khi bắt đầu đăng ký MBSLink trên app, hệ thống sẽ đưa tôi đi đâu và tôi cần thực hiện việc mở tài khoản ở đâu?",
        "required": [["chưa có"], ["điều hướng"], ["mở TK chứng khoán"], ["ứng dụng MBBank"]],
    },
    {
        "id": "Q08",
        "question": "Tôi đã có tài khoản tại MBS và muốn hoàn tất hồ sơ ngay trên ứng dụng. Sau khi chọn chi nhánh hỗ trợ, tôi cần chuẩn bị giấy tờ, đăng ký chữ ký số và xác thực bằng cách nào?",
        "required": [["chọn CN MB hỗ trợ"], ["chữ ký CA"], ["chụp ảnh giấy tờ tùy thân"], ["DOTP"]],
    },
    {
        "id": "Q09",
        "question": "Tôi đã kiểm tra xong thông tin cấp hạn mức trên ứng dụng và muốn hoàn tất đăng ký. Ở màn hình cuối tôi cần xác nhận và xác thực thêm thao tác gì?",
        "required": [["kiểm tra"], ["xác nhận"], ["nhập DOTP"]],
    },
    {
        "id": "Q10",
        "question": "Tôi đang dùng một gói MBBank khác và muốn đổi sang gói phù hợp để đăng ký MBSLink. Tôi phải vào khu vực nào, chọn những mục nào, và việc đổi gói có bị tính thêm phí không?",
        "required": [["tiện ích"], ["thay đổi hạn mức chuyển tiền"], ["gói nâng cao"], ["chọn gói này"], ["không phát sinh thêm chi phí"]],
    },
]


def normalize(text: str) -> str:
    text = (text or "").lower().replace("đ", "đ")
    return re.sub(r"\s+", " ", text).strip()


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def extract_chunks(pdf_path: Path) -> list[dict[str, Any]]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    chunks = []
    for page_no, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if text:
            chunks.append(
                {
                    "chunk_id": f"{pdf_path.stem}_p{page_no}",
                    "file_name": pdf_path.name,
                    "original_filename": pdf_path.name,
                    "content": text,
                    "metadata": {"page": page_no, "page_start": page_no, "page_end": page_no},
                }
            )
    return chunks


class InMemoryRetriever:
    def __init__(self, chunks: list[dict[str, Any]], embedder: EmbeddingService):
        self.chunks = chunks
        self.embedder = embedder
        self.vectors = embedder.embed_texts([c["content"] for c in chunks], input_type="passage")
        self.query_vectors: dict[str, list[float]] = {}

    def retrieve(self, query: str, top_k: int = 16, document_id: str | None = None):
        vector = self.query_vectors.get(query)
        if vector is None:
            vector = self.embedder.embed_query(query)
            self.query_vectors[query] = vector
        q_words = set(re.findall(r"[\wÀ-ỹ]+", normalize(query)))
        scored = []
        for chunk, cvec in zip(self.chunks, self.vectors):
            c_words = set(re.findall(r"[\wÀ-ỹ]+", normalize(chunk["content"])))
            lexical = len(q_words & c_words) / max(1, len(q_words))
            item = dict(chunk)
            item["similarity_score"] = round(0.75 * cosine(vector, cvec) + 0.25 * lexical, 6)
            scored.append(item)
        return sorted(scored, key=lambda item: item["similarity_score"], reverse=True)[:top_k]


def score_answer(answer: str, required: list[list[str]]) -> tuple[int, int, list[list[str]]]:
    folded = normalize(answer)
    hits = []
    for group in required:
        group_hit = any(normalize(term) in folded for term in group)
        hits.append(group_hit)
    return sum(hits), len(required), [group for group, hit in zip(required, hits) if not hit]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, default=Path("evaluation/single_pdf_benchmark.json"))
    args = parser.parse_args()

    chunks = extract_chunks(args.pdf)
    embedder = EmbeddingService(fallback_to_mock=False)
    retriever = InMemoryRetriever(chunks, embedder)
    rag = RagService(retriever)
    evidence = EvidenceService()
    records = []

    for item in QUESTIONS:
        started = time.time()
        try:
            result = rag.answer_question(item["question"], top_k=3)
            answer = result.get("answer", "")
            hit, total, missing = score_answer(answer, item["required"])
            sources = result.get("sources", [])
            records.append(
                {
                    "id": item["id"],
                    "question": item["question"],
                    "answer": answer,
                    "required": item["required"],
                    "required_hit": hit,
                    "required_total": total,
                    "pass": hit == total,
                    "missing": missing,
                    "sources": sources,
                    "evidence": result.get("evidence", {}),
                    "decision": result.get("decision"),
                    "latency_seconds": round(result.get("execution_time_seconds", time.time() - started), 2),
                }
            )
        except Exception as exc:  # preserve partial benchmark evidence
            records.append(
                {
                    "id": item["id"],
                    "question": item["question"],
                    "answer": "",
                    "required": item["required"],
                    "required_hit": 0,
                    "required_total": len(item["required"]),
                    "pass": False,
                    "missing": item["required"],
                    "sources": [],
                    "evidence": {},
                    "decision": "ERROR",
                    "error": f"{type(exc).__name__}: {exc}",
                    "latency_seconds": round(time.time() - started, 2),
                }
            )

    total_groups = sum(r["required_total"] for r in records)
    hit_groups = sum(r["required_hit"] for r in records)
    summary = {
        "pdf": str(args.pdf),
        "filename": args.pdf.name,
        "pages": len(chunks),
        "questions": len(records),
        "question_pass": sum(1 for r in records if r["pass"]),
        "question_pass_rate_pct": round(100 * sum(1 for r in records if r["pass"]) / max(1, len(records)), 2),
        "required_point_hit": hit_groups,
        "required_point_total": total_groups,
        "required_point_hit_rate_pct": round(100 * hit_groups / max(1, total_groups), 2),
        "retrieval_source": "in-memory PDF page chunks + production EmbeddingService",
        "generation_source": "production RagService grounded prompt and NVIDIA-compatible LLM",
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in summary if k != "records"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
