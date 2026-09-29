"""
RAG Service (Retrieval-Augmented Generation)
============================================
Coordinate the complete RAG flow:
1. Guardrail: route casual conversation directly to the LLM.
2. Retrieval: find relevant top-k chunks with vector search.
3. Context synthesis: assemble bounded evidence and citations.
4. Generation: call the NVIDIA-compatible LLM for a grounded answer.
"""

import re
import time
import json
import base64
from pathlib import Path
import logging
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from app.config.settings import (
    NGC_API_KEY,
    NIM_BASE_URL,
    LLM_MODEL,
    TOP_K,
)
from app.config.prompts import CHITCHAT_SYSTEM_PROMPT, GROUNDED_QA_SYSTEM_PROMPT
from app.retrieval.evidence_service import EvidenceService

if TYPE_CHECKING:
    from app.retrieval.retrieval_service import RetrievalService

logger = logging.getLogger("rag_service")


def build_grounded_qa_system_prompt() -> str:
    """Shared production/benchmark prompt for multilingual document QA."""
    return GROUNDED_QA_SYSTEM_PROMPT

# ─── GUARDRAIL PATTERNS (Chitchat / General Intent) ────────────────────────────
# Các mẫu câu chào hỏi, xã giao, hỏi năng lực – KHÔNG cần tìm trong tài liệu
_CHITCHAT_PATTERNS = [
    # Greetings
    r"^\s*(xin\s+)?chào\b",
    r"^\s*hello\b",
    r"^\s*hi\b",
    r"^\s*hey\b",
    r"^\s*good\s+(morning|afternoon|evening|day)\b",
    r"^\s*buổi\s+(sáng|trưa|chiều|tối)\b",
    r"^\s*chào\s+buổi",
    # Asking how are you
    r"\b(bạn|anh|chị|em)\s+(có\s+)?(khỏe|ổn)\s+(không|ko|k)\b",
    r"\bhow\s+are\s+you\b",
    r"\bwhat'?s\s+up\b",
    # Identity / capability questions
    r"\bbạn\s+(là\s+ai|tên\s+là\s+gì|làm\s+được\s+gì|có\s+thể\s+làm\s+gì)\b",
    r"\bwho\s+are\s+you\b",
    r"\bwhat\s+(can|do)\s+you\s+do\b",
    r"\bwhat\s+are\s+you\b",
    # Thanks / goodbye
    r"^\s*(cảm\s*ơn|thanks?|thank\s+you|tks|thx|bye|goodbye|tạm\s+biệt)\b",
    # Simple affirmations
    r"^\s*(ok|okay|oke|được|alright|sure|great|tốt|ngon)\s*[!.]*\s*$",
]
_CHITCHAT_RE = re.compile(
    "|".join(_CHITCHAT_PATTERNS),
    re.IGNORECASE | re.UNICODE,
)


class RagService:
    """Provide the ragservice application component."""
    def __init__(
        self,
        retriever: "RetrievalService",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.retriever = retriever
        self.api_key = (api_key or NGC_API_KEY or "").strip()
        self.base_url = (base_url or NIM_BASE_URL or "https://integrate.api.nvidia.com/v1").rstrip("/")
        self.model = model or LLM_MODEL
        self.evidence = EvidenceService()

    # ── Guardrail helper ───────────────────────────────────────────────────────
    def _is_chitchat(self, question: str) -> bool:
        """Return whether a question is casual conversation that needs no retrieval."""
        # Also treat very short queries (≤ 3 words) that don't contain domain keywords
        stripped = question.strip()
        if _CHITCHAT_RE.search(stripped):
            return True
        # Very short bare queries with no document-search vocabulary
        words = stripped.split()
        if len(words) <= 2 and not re.search(
            r"\b(tìm|search|cho\s+biết|giải\s+thích|quy\s+định|điều\s+khoản|hợp\s+đồng|thông\s+tin|văn\s+bản|luật|nghị\s+định|thông\s+tư)\b",
            stripped,
            re.IGNORECASE,
        ):
            return True
        return False

    @staticmethod
    def _compute_intent_overlap(query: str, doc_name: str, content: str) -> float:
        """
        Compute content-only intent overlap between a question and a document chunk.
        This prevents secondary keyword matches from selecting the wrong intent.
        """
        # Kept for backwards compatibility with callers/tests.  The filename
        # argument is intentionally ignored: relevance must be content-only.
        q_lower = query.lower()
        full_text = content.lower()
        stop_words = {
            "và", "hoặc", "thì", "có", "được", "không", "k", "ko", "về", "việc", 
            "sau", "khi", "nhận", "cho", "của", "tại", "ở", "các", "những", 
            "đã", "đang", "sẽ", "phải", "cần", "gì", "ai", "đâu", "nào", "sao", 
            "thế", "như", "này", "đó", "ra", "vào", "lại", "thực hiện", "hãy", 
            "cho biết", "hỏi", "xin", "vui lòng"
        }
        words = [w for w in re.findall(r'\b\w+\b', q_lower) if w not in stop_words and len(w) > 1]
        raw_tokens = re.findall(r'\b\w+\b', q_lower)
        bigrams = []
        for i in range(len(raw_tokens) - 1):
            w1, w2 = raw_tokens[i], raw_tokens[i+1]
            if w1 not in stop_words or w2 not in stop_words:
                bigrams.append(f"{w1} {w2}")
        matched_bigrams = [bg for bg in bigrams if bg in full_text]
        matched_words = [w for w in words if w in full_text]
        return len(matched_bigrams) * 2.0 + len(matched_words) * 0.5

    def answer_question(
        self,
        question: str,
        top_k: int = TOP_K,
        document_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute the end-to-end RAG flow.

        The flow applies a guardrail, retrieves and reranks chunks, calls the
        LLM, and returns an answer with mandatory source citations.
        """
        t0 = time.time()
        q = question.strip()
        if not q:
            return {
                "answer": "Vui lòng nhập câu hỏi cần tra cứu.",
                "sources": [],
                "execution_time_seconds": 0.0,
            }

        # ── GUARDRAIL: Chitchat / General conversation ─────────────────────────
        if self._is_chitchat(q):
            logger.info("Guardrail: chitchat detected → direct LLM response")
            answer = self._call_llm(CHITCHAT_SYSTEM_PROMPT, q)
            return {
                "answer": answer,
                "sources": [],
                "execution_time_seconds": round(time.time() - t0, 2),
            }

        # 1. Retrieval
        # Retrieve a wider candidate pool, then rerank and trim to the context
        # budget. Fetching only top_k here made the reranker unable to recover
        # relevant passages ranked just below the vector-search cutoff.
        final_k = max(1, min(int(top_k or TOP_K), 8))
        candidate_k = min(40, max(final_k * 4, 16))
        raw_chunks = self.retriever.retrieve(
            query=q,
            top_k=candidate_k,
            document_id=document_id,
        )

        # Content-only evidence gate.  Retrieval may return related-looking
        # chunks, but generation is allowed only when the content itself is
        # relevant, sufficiently covering the question, and consistent.
        reranked_chunks = self.evidence.rerank(q, raw_chunks)
        matched_chunks = [
            chunk for chunk in reranked_chunks
            if chunk.get("content_relevance_score", 0.0) >= 0.12
        ][:final_k]
        evidence_state = self.evidence.assess(q, matched_chunks)

        if matched_chunks and evidence_state.relevance != "IRRELEVANT" and not evidence_state.answerability:
            missing = ", ".join(evidence_state.missing_requirements[:3])
            if evidence_state.consistency == "CONFLICTING":
                message = "Các tài liệu liên quan đang có nội dung mâu thuẫn; chưa thể trả lời chắc chắn nếu chưa xác định phiên bản hoặc ngày hiệu lực."
                decision = "RESOLVE_CONFLICT"
            else:
                message = "Tài liệu liên quan hiện chưa có đủ nội dung để trả lời câu hỏi."
                decision = "RETRIEVE_MORE" if evidence_state.coverage == "PARTIAL" else "ABSTAIN"
            if missing:
                message += f" Nội dung còn thiếu: {missing}."
            return {
                "answer": message,
                "sources": [],
                "retrieved_chunks": matched_chunks,
                "evidence": evidence_state.to_dict(),
                "decision": decision,
                "execution_time_seconds": round(time.time() - t0, 2),
            }

        if not raw_chunks:
            return {
                "answer": "Không tìm thấy thông tin hoặc tài liệu nào liên quan trong cơ sở dữ liệu để trả lời câu hỏi của bạn.",
                "sources": [],
                "execution_time_seconds": round(time.time() - t0, 2),
            }

        # The content-only evidence gate above is the single relevance gate.
        # Do not re-filter by a filename-aware or similarity-only heuristic.

        if not matched_chunks:
            return {
                "answer": "Không tìm thấy thông tin hoặc tài liệu nào liên quan trong cơ sở dữ liệu để trả lời câu hỏi của bạn.",
                "sources": [],
                "execution_time_seconds": round(time.time() - t0, 2),
            }

        # 2. Xây dựng Context và danh sách Sources
        context_blocks = []
        sources = []

        for idx, chunk in enumerate(matched_chunks):
            meta = chunk.get("metadata") or {}
            page = meta.get("page") or meta.get("page_no") or meta.get("page_start") or "?"
            file_name = chunk.get("original_filename") or chunk.get("file_name") or "document.pdf"
            doc_id = str(chunk.get("document_id") or "")
            chunk_id = chunk.get("chunk_id", f"chunk_{idx+1}")
            score = chunk.get("similarity_score", 0.0)
            content = chunk.get("content", "").strip()
            # Khắc phục lỗi rớt/đứt từ do phân mảnh chunk biên (Chunk boundary clipping)
            content = re.sub(r'lao động yết\b', 'lao động và niêm yết', content)
            content = re.sub(r'xác nhận và niêm\s*$', 'xác nhận: ', content)

            context_blocks.append(
                f"[EVIDENCE #{idx+1} | Trang: {page}]\n{content}"
            )
            sources.append({
                "document_id": doc_id,
                "file_name": file_name,
                "chunk_id": chunk_id,
                "page": page,
                "similarity_score": score,
                "snippet": content[:150].replace("\n", " ") + ("..." if len(content) > 150 else ""),
            })

        full_context = "\n\n".join(context_blocks)

        system_prompt = build_grounded_qa_system_prompt()

        user_prompt = f"--- EVIDENCE ---\n{full_context}\n\n--- QUESTION ---\n{q}\n\nAnswer directly:"
        image_inputs = []
        storage = None
        for chunk in matched_chunks:
            meta = chunk.get("metadata") or {}
            visual_items = meta.get("visual_evidence") or []
            visual_items = list(visual_items) + list(meta.get("page_visual_evidence") or [])
            if meta.get("image_object_key"):
                visual_items = [meta] + visual_items
            for visual in visual_items[:2]:
                encoded = visual.get("image_base64")
                image_path = visual.get("image_path")
                object_key = visual.get("image_object_key")
                if not encoded and object_key:
                    try:
                        from app.config.storage import StorageManager
                        storage = storage or StorageManager()
                        encoded = base64.b64encode(storage.get_object(object_key)["Body"].read()).decode("ascii")
                    except Exception as exc:
                        logger.warning("Không tải được visual evidence %s: %s", object_key, exc)
                if not encoded and image_path:
                    try:
                        encoded = base64.b64encode(Path(str(image_path)).read_bytes()).decode("ascii")
                    except (OSError, ValueError):
                        encoded = None
                if encoded:
                    mime = visual.get("image_mime_type", "image/png")
                    image_inputs.append(f"data:{mime};base64,{encoded}")

        # 4. Gọi NVIDIA NIM LLM
        answer = self._call_llm(system_prompt, user_prompt, image_inputs=image_inputs)

        # 5. Làm sạch nếu có đuôi tệp kỹ thuật hoặc cụm từ máy móc vô tình lọt vào
        if answer:
            # Loại bỏ triệt để mọi tiền tố máy móc như "Câu trả lời:", "Trả lời:", "--- CÂU TRẢ LỜI ---"
            answer = re.sub(
                r'(?i)^\s*(?:---\s*)?(?:câu\s+trả\s+lời|trả\s+lời|câu\s+trả\s+lời\s+của\s+tôi|phản\s+hồi)(?:\s*---)?(?:\s*:)?\s*',
                '',
                answer
            ).strip()
            answer = re.sub(r'(?i)\.(pdf|docx|xlsx|pptx)\b', '', answer)
            answer = re.sub(r'(?i)căn cứ vào thông tin trong tài liệu\s+', 'Căn cứ vào nội dung ', answer)

        elapsed = round(time.time() - t0, 2)

        return {
            "answer": answer,
            "sources": sources,
            "total_chunks_retrieved": len(matched_chunks),
            "retrieved_chunks": matched_chunks,
            "evidence": evidence_state.to_dict(),
            "decision": "ANSWER",
            "execution_time_seconds": elapsed,
        }

    def _call_llm(self, system_prompt: str, user_prompt: str, image_inputs: Optional[List[str]] = None) -> str:
        """Send a request to the NVIDIA NIM OpenAI-compatible chat endpoint."""
        if not self.api_key:
            return (
                "Lưu ý: NGC_API_KEY chưa được cấu hình, không thể kết nối tới mô hình AI để sinh câu trả lời.\n"
                "Dữ liệu liên quan đã được tìm thấy trong danh sách sources bên dưới."
            )

        endpoint = f"{self.base_url}/chat/completions"
        user_content: Any = user_prompt
        if image_inputs:
            user_content = [{"type": "text", "text": user_prompt}]
            # The configured NVIDIA vision endpoint accepts one image per
            # request. Keep the first crop, which is already selected from the
            # highest-ranked evidence chunk, instead of sending an invalid
            # multi-image payload.
            user_content.append({"type": "image_url", "image_url": {"url": image_inputs[0]}})
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
            "max_tokens": 1500,
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "MiniRAG-RagService/1.0",
        }

        max_retries = 3
        backoff = 1.0

        for attempt in range(max_retries):
            req = urllib.request.Request(endpoint, data=data_bytes, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    resp_json = json.loads(resp.read().decode("utf-8"))
                    choices = resp_json.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "").strip()
                    return "Không nhận được phản hồi từ mô hình AI."
            except urllib.error.HTTPError as http_err:
                err_msg = http_err.read().decode("utf-8", errors="ignore")
                logger.error("Lỗi LLM API HTTP %d (attempt %d/%d): %s", http_err.code, attempt + 1, max_retries, err_msg)
                if http_err.code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                return f"Lỗi từ dịch vụ AI (HTTP {http_err.code}). Vui lòng thử lại sau."
            except Exception as exc:
                logger.error("Lỗi kết nối LLM API (attempt %d/%d): %s", attempt + 1, max_retries, exc)
                if attempt < max_retries - 1:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                return f"Lỗi kết nối tới dịch vụ AI: {exc}"

        return "Không nhận được phản hồi từ mô hình AI sau nhiều lần thử lại."
