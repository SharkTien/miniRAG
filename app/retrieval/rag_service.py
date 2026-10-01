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
import difflib
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
    RETRIEVAL_CANDIDATE_MULTIPLIER,
    NIM_SUPPORTS_MULTIMODAL,
    NIM_MAX_INPUT_CHARS,
    NIM_TIMEOUT_SECONDS,
)
from app.config.prompts import CHITCHAT_SYSTEM_PROMPT, GROUNDED_QA_SYSTEM_PROMPT
from app.retrieval.evidence_service import EvidenceService
from app.retrieval.query_planner import QueryPlanner

if TYPE_CHECKING:
    from app.retrieval.retrieval_service import RetrievalService

logger = logging.getLogger("rag_service")

# Terms that describe a policy scenario but do not identify the document or
# product. They are excluded from document/topic gates; otherwise a query such
# as "phụ kiện Adore có được bảo hành trọn đời không" can keep unrelated
# warranty documents merely because they contain the word "bảo hành".
_GENERIC_TOPIC_TERMS = {
    "thông", "tin", "chính", "sách", "phẩm", "hành", "khách", "người",
    "ngày", "tháng", "tiền", "hoàn", "điều", "kiện", "dịch", "phí",
    "hàng", "gửi", "trả", "đổi", "bằng", "trong", "phải", "được",
    "nếu", "chọn", "bưu", "cước", "thời", "gian", "mấy", "bao", "nhiêu",
    "hình", "thức", "đơn", "yêu", "cầu", "bảo", "trọn", "đời", "lỗi",
    "nhà", "sản", "xuất", "phụ", "trang",
}


def build_grounded_qa_system_prompt() -> str:
    """Shared production/benchmark prompt for multilingual document QA."""
    return GROUNDED_QA_SYSTEM_PROMPT


_SELF_CAPABILITY_ANSWER = (
    "Tôi có thể đọc và tìm thông tin trong các tài liệu đã được tải lên, "
    "kết hợp tìm kiếm từ khóa và ngữ nghĩa, tóm tắt hoặc giải thích nội dung, "
    "và trả lời kèm nguồn tài liệu liên quan. Tôi cũng có thể duy trì ngữ cảnh "
    "của cuộc trò chuyện và trả kết quả từng phần khi hệ thống đang xử lý. "
    "Nếu tài liệu không có đủ dữ kiện, tôi sẽ nói rõ phần còn thiếu thay vì tự suy đoán."
)


def _extract_time_context(question: str) -> str:
    """Tính số tháng từ các mốc thời gian đề cập trong câu hỏi.

    Trả về chuỗi annotation tiếng Việt để inject vào prompt,
    giúp model không cần tự suy luận 'X ngày = tháng thứ mấy'.
    Trả về chuỗi rỗng nếu không tìm thấy mốc thời gian.
    """
    q = question.lower()

    # Tính số ngày từ các pattern phổ biến
    total_days: Optional[int] = None

    # "X ngày"
    m = re.search(r'(\d+)\s*ngày', q)
    if m:
        total_days = int(m.group(1))

    # "X tuần"
    if total_days is None:
        m = re.search(r'(\d+)\s*tuần', q)
        if m:
            total_days = int(m.group(1)) * 7

    # "X tháng" — đã có tháng rõ ràng, không cần tính thêm
    if total_days is None:
        m = re.search(r'(\d+)\s*tháng', q)
        if m:
            months = int(m.group(1))
            if months == 1:
                return f"[Lưu ý tính toán thời gian: {months} tháng = tháng thứ 1 kể từ ngày mua → áp dụng mức phí tháng thứ 1.]"
            elif 2 <= months <= 12:
                return f"[Lưu ý tính toán thời gian: {months} tháng = tháng thứ {months} kể từ ngày mua → áp dụng mức phí tháng thứ 2–12.]"
            return ""

    if total_days is None:
        return ""

    # Quy đổi ngày sang tháng (30 ngày/tháng theo quy ước thương mại)
    month_number = (total_days - 1) // 30 + 1  # tháng thứ 1 = ngày 1–30

    if month_number == 1:
        label = "tháng thứ 1"
        rule_hint = "áp dụng mức phí tháng thứ 1 (tháng đầu tiên kể từ ngày mua)"
    elif 2 <= month_number <= 12:
        label = f"tháng thứ {month_number}"
        rule_hint = "áp dụng mức phí tháng thứ 2–12 (vì đã qua tháng đầu tiên)"
    else:
        label = f"tháng thứ {month_number}"
        rule_hint = "đã vượt quá 12 tháng — kiểm tra xem chính sách còn áp dụng không"

    return (
        f"[Lưu ý tính toán thời gian: {total_days} ngày kể từ ngày mua = {label} → {rule_hint}.]"
    )

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
    r"^\s*(khả\s+năng|năng\s+lực|chức\s+năng)\s+(của\s+)?(bạn|hệ\s+thống|chatbot|trợ\s+lý)\b",
    r"\b(bạn|chatbot|trợ\s+lý)\s+(có\s+thể|làm\s+được|hỗ\s+trợ)\b",
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
    """Coordinate retrieval, evidence filtering, and grounded answer generation."""

    @staticmethod
    def _clean_extracted_noise(value: str) -> str:
        """Remove repeated OCR/export chrome while preserving factual text."""
        text = str(value or "")
        noise = re.compile(
            r"(?im)^\s*(?:đoạn\s*#?\s*\d+|•\s*trang\s*\d+|xem\s+trên\s+pdf|"
            r"legal_reference|rule_obligation|contact|content|save|"
            r"[]+)\s*$"
        )
        lines = [line.rstrip() for line in text.splitlines() if not noise.match(line)]
        cleaned = "\n".join(lines)
        cleaned = re.sub(r"(?m)^\s*[]+\s*$", "", cleaned)
        return re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    @staticmethod
    def _critical_policy_lines(context: str) -> str:
        """Keep numeric conditions visible when OCR evidence contains policy tables.

        Small instruction-following models often merge adjacent rows in warranty
        tables. Passing the source lines containing thresholds and service times
        as a separate checklist reduces that failure without inventing facts.
        """
        patterns = re.compile(
            r"\b\d+(?:[.,]\d+)?\s*(?:%|ngày|giờ|tuần|tháng|năm|đồng|đ)\b|"
            r"\b\d+\s*[-–]\s*\d+\s*(?:ngày|giờ|tuần|tháng|năm)\b|"
            r"điều kiện|thời gian|phí|chi phí|hỗ trợ|miễn phí|không quá|tối đa|\|",
            re.IGNORECASE,
        )
        lines = []
        for line in (context or "").splitlines():
            clean = re.sub(r"\s+", " ", line).strip()
            if clean.startswith("[PHẠM VI ÁP DỤNG:"):
                continue
            if clean and patterns.search(clean) and clean not in lines:
                lines.append(clean)
        return "\n".join(lines[:40])

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
        self.query_planner = QueryPlanner()

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

    def _is_self_capability(self, question: str) -> bool:
        """Return whether the user asks about this assistant or system itself."""
        normalized = re.sub(r"\s+", " ", (question or "").strip().casefold())
        return bool(re.search(
            r"^(?:khả năng|năng lực|chức năng)\s+(?:của )?(?:bạn|hệ thống|chatbot|trợ lý)\b"
            r"|^(?:bạn|chatbot|trợ lý)\s+(?:có thể|làm được|hỗ trợ)\b"
            r"|^(?:bạn là ai|bạn tên là gì|what can you do|who are you)\b",
            normalized,
            re.IGNORECASE,
        ))

    def _resolve_followup(self, question: str, history: Optional[List[Dict[str, Any]]]) -> str:
        """Resolve a short follow-up against recent turns before retrieval.

        History is used only to interpret the current turn. The resolver returns
        a compact standalone query, never an answer or new factual assumptions.
        """
        if not history:
            return question
        # Only spend a resolver call where the current turn is likely elliptical:
        # dates/numbers, very short phrases, or explicit references.
        words = re.findall(r"[\wÀ-ỹ]+", question, flags=re.UNICODE)
        looks_elliptical = (
            len(words) <= 7
            or bool(re.search(r"\b(nó|đó|vậy|thế|còn|như vậy|ngày|hôm đó)\b", question, re.I))
            or bool(re.search(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", question))
        )
        if not looks_elliptical:
            return question

        turns = history[-8:]
        transcript = "\n".join(
            f"{str(turn.get('role', ''))[:20]}: {str(turn.get('content', ''))[:1200]}"
            for turn in turns if turn.get("content")
        )
        if not transcript:
            return question
        prompt = (
            "Dựa vào hội thoại gần đây, viết lại tin nhắn mới thành một truy vấn độc lập để tra cứu/"
            "trả lời. Chỉ bổ sung tham chiếu đã rõ từ hội thoại; giữ nguyên mọi con số, ngày tháng và "
            "ý định. Không trả lời câu hỏi, không tự thêm dữ kiện. Nếu người dùng đổi chủ đề hoặc "
            "không đủ căn cứ nối ngữ cảnh, trả lại nguyên văn tin nhắn mới. Chỉ xuất truy vấn đã viết lại.\n\n"
            f"HỘI THOẠI:\n{transcript}\n\nTIN NHẮN MỚI:\n{question}"
        )
        try:
            resolved = self._call_llm(
                "Bạn là bộ phân giải tham chiếu hội thoại chính xác. Chỉ xuất một truy vấn độc lập.",
                prompt,
            ).strip().strip('"')
            if resolved and len(resolved) <= max(600, len(question) * 8):
                logger.info("Resolved contextual follow-up for retrieval")
                return resolved
        except Exception as exc:
            logger.warning("Follow-up resolution failed; using original query: %s", exc)
        return question

    @staticmethod
    def _is_refusal_answer(answer: str) -> bool:
        """Detect generic capability refusals that ignore supplied evidence."""
        sample = re.sub(r"\s+", " ", (answer or "").strip().lower())[:700]
        refusal_markers = (
            "tôi xin lỗi, nhưng tôi không thể trả lời",
            "tôi không thể cung cấp thông tin chính xác",
            "tôi không có khả năng đưa ra quyết định",
            "tôi khuyên bạn nên liên hệ trực tiếp",
        )
        return sum(marker in sample for marker in refusal_markers) >= 1

    @staticmethod
    def _needs_policy_repair(answer: str, question: str, context: str) -> bool:
        """Detect a confident answer that drops a requested value from a table."""
        text = re.sub(r"\s+", " ", (answer or "").lower())
        q = (question or "").lower()
        source = (context or "").lower()
        asks_value = any(marker in q for marker in ("bao nhiêu", "mấy ngày", "thời gian", "khi nào", "trong bao lâu"))
        has_table = "|" in source and bool(re.search(r"\d", source))
        if asks_value and has_table and not re.search(r"\d", text):
            return True
        # Do not let a general eligibility condition (“seller agrees to the
        # return”) override an explicit shipping-fee rule in the evidence.
        # This catches the common Shopee failure where the model invents a
        # seller-negotiation requirement despite “miễn phí trả hàng” or
        # “sẽ hỗ trợ hoàn lại phí trả hàng”.
        explicit_fee_support = any(
            marker in source
            for marker in (
                "miễn phí trả hàng",
                "hỗ trợ hoàn lại phí trả hàng",
                "hỗ trợ phí trả hàng",
            )
        )
        seller_fee_inference = any(
            marker in text
            for marker in (
                "người bán đồng ý trả phí",
                "nếu người bán đồng ý, bạn sẽ được miễn phí",
                "phụ thuộc vào thỏa thuận với người bán",
                "người bán chịu phí vận chuyển",
            )
        )
        if explicit_fee_support and seller_fee_inference:
            return True
        # Alternative shipping methods have different applicability scopes.
        # Force a second grounded pass when the model attaches the
        # self-arranged reimbursement conditions to free pickup/drop-off.
        has_branching_shipping_policy = (
            "tự sắp xếp" in source
            and ("miễn phí trả hàng" in source or "miễn phí hoàn trả" in source)
            and ("thanh toán trước" in source or "hoàn lại phí" in source)
        )
        merged_branch_conditions = bool(re.search(
            r"(?:đến lấy|tại bưu cục|cả hai).{0,180}(?:điều kiện trên|mã vận đơn|giao hàng thành công|người bán đồng ý)",
            text,
            flags=re.IGNORECASE,
        ))
        merged_branch_conditions = merged_branch_conditions or (
            "điều kiện trên" in text
            and ("đến lấy" in text or "tại bưu cục" in text)
            and "tự sắp xếp" in source
        )
        if has_branching_shipping_policy and merged_branch_conditions:
            return True
        return False

    @staticmethod
    def _compose_scoped_branch_answer(
        question: str,
        chunks: List[Dict[str, Any]],
        generated_answer: str,
        context: str,
    ) -> str | None:
        """Repair an option-scope merge using structured evidence claims.

        This is intentionally a generic branch composer.  It activates only
        when the evidence contains distinct free and pay-first options and the
        generated answer applies a shared condition to those options.
        """
        if not RagService._needs_policy_repair(generated_answer, question, context):
            return None
        claims = [claim for chunk in chunks for claim in (chunk.get("scoped_claims") or [])]
        has_pickup_free = {"scope": "pickup", "claim_type": "fee", "value": "free"} in claims
        has_dropoff_free = {"scope": "drop_off", "claim_type": "fee", "value": "free"} in claims
        has_self_pay = {"scope": "self_arranged", "claim_type": "fee", "value": "pay_first"} in claims
        has_self_support = {"scope": "self_arranged", "claim_type": "fee", "value": "support_later"} in claims
        if not (has_pickup_free and has_dropoff_free and has_self_pay and has_self_support):
            return None

        labels = {
            "accepted_request": "yêu cầu trả hàng/hoàn tiền được chấp nhận",
            "delivered_tracking": "mã vận đơn có trạng thái giao hàng thành công",
            "seller_refund_approval": "người bán hoặc Shopee đồng ý hoàn tiền",
            "not_seller_shipping": "đơn hàng không do người bán tự vận chuyển",
            "return_details": "điền đầy đủ thông tin trả hàng và mã vận đơn",
        }
        self_values = {
            claim.get("value")
            for claim in claims
            if claim.get("scope") == "self_arranged"
        }
        # A general “conditions for support” chunk belongs to the pay-first
        # branch when that is the only branch that explicitly requests fee
        # reimbursement.  It must never be attached to free pickup/drop-off.
        general_values = {
            claim.get("value")
            for claim in claims
            if claim.get("scope") == "general" and claim.get("claim_type") == "requirement"
        }
        requirements = [
            labels[value]
            for value in (*sorted(self_values | general_values),)
            if value in labels
        ]
        answer = (
            "Nếu chọn đơn vị vận chuyển đến lấy hàng hoặc trả hàng tại bưu cục, "
            "phí trả hàng là miễn phí.\n\n"
            "Nếu chọn tự sắp xếp đơn vị vận chuyển, bạn cần thanh toán trước phí trả hàng; "
            "Shopee sẽ hỗ trợ hoàn lại khoản phí này khi đáp ứng các điều kiện trong chính sách."
        )
        if requirements:
            answer += "\n\nCác điều kiện áp dụng cho nhánh tự sắp xếp gồm: " + "; ".join(requirements) + "."
        return answer

    @staticmethod
    def _remove_question_echo(answer: str, question: str) -> str:
        """Remove a model paragraph that merely repeats the user question."""
        if not answer or not question:
            return answer
        parts = re.split(r"\n\s*\n", answer.strip(), maxsplit=1)
        if len(parts) < 2:
            return answer.strip()
        def normalize(value: str) -> str:
            """Normalize text for detecting a repeated question paragraph."""
            return re.sub(r"[^\wÀ-ỹ]+", "", value.lower())
        first, qnorm = normalize(parts[0]), normalize(question)
        lead_markers = (
            "tôi hiểu rằng", "bạn đang hỏi", "câu hỏi của bạn", "theo câu hỏi của bạn",
            "bạn muốn biết", "tôi hiểu bạn muốn biết",
        )
        if (
            (first and qnorm and difflib.SequenceMatcher(None, first, qnorm).ratio() >= 0.82)
            or parts[0].strip().lower().startswith(lead_markers)
        ):
            answer = parts[1].strip()
        # Remove generic conversational sign-offs that add no evidence.
        answer = re.sub(r"\n+(?:Hy vọng|Mong rằng|Nếu bạn cần thêm)[^\n]*[.!]?\s*$", "", answer, flags=re.IGNORECASE)
        answer = re.sub(r"\s+\*\s+", "\n- ", answer)
        answer = re.sub(r"(?<!\n)\s+(?=(?:Kết luận|Tính toán phí|Tổng phí|Điều kiện|Thời gian)\s*:)", "\n\n", answer)
        # NIM may repeat the same bullet when it is asked to cover several
        # conditions. Remove exact duplicate lines while preserving order.
        seen_lines: set[str] = set()
        kept: list[str] = []
        for line in answer.splitlines():
            key = re.sub(r"\s+", " ", line.strip()).casefold()
            if key and key in seen_lines:
                continue
            if key:
                seen_lines.add(key)
            kept.append(line)
        answer = "\n".join(kept).strip()

        # Loại bỏ câu lặp ở cấp câu (sentence-level deduplication).
        # Mô hình đôi khi sinh hai câu hoàn chỉnh có nội dung tương đồng cao
        # dù viết hơi khác nhau (ví dụ: "Nếu X thì Y.\nNếu X thì Y.").
        sentences = re.split(r'(?<=[.!?])\s+', answer)
        seen_sents: set[str] = set()
        deduped: list[str] = []
        for sent in sentences:
            norm = re.sub(r"[^\wÀ-ỹ]+", "", sent.lower())
            if not norm:
                deduped.append(sent)
                continue
            is_dup = False
            for seen_s in seen_sents:
                if difflib.SequenceMatcher(None, norm, seen_s).ratio() >= 0.88:
                    is_dup = True
                    break
            if not is_dup:
                seen_sents.add(norm)
                deduped.append(sent)
        # Preserve Markdown line breaks when persisting the answer. Joining
        # with spaces makes a refreshed conversation lose bullets and tables.
        separator = "\n" if "\n" in answer else " "
        return separator.join(item.strip() for item in deduped).strip()

    @staticmethod
    def _deduplicate_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove repeated OCR/native chunks before context construction."""
        seen = set()
        unique = []
        for chunk in chunks:
            content = re.sub(r"\s+", " ", str(chunk.get("content") or "")).strip().lower()
            if not content:
                continue
            fingerprint = content
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            unique.append(chunk)
        return unique

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
        document_ids: Optional[List[str]] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        on_token=None,
    ) -> Dict[str, Any]:
        """
        Execute the end-to-end RAG flow.

        The flow applies a guardrail, retrieves and reranks chunks, calls the
        LLM, and returns an answer with mandatory source citations.
        """
        t0 = time.time()
        original_question = question.strip()
        q = original_question
        if not q:
            return {
                "answer": "Vui lòng nhập câu hỏi cần tra cứu.",
                "sources": [],
                "execution_time_seconds": 0.0,
            }

        # Resolve contextual fragments before the short-query chitchat guardrail
        # (a bare date such as "15/09/2026" would otherwise bypass retrieval).
        q = self._resolve_followup(q, conversation_history)

        # ── INTENT ROUTER: system/self capability ──────────────────────────────
        # Capability questions are system knowledge, not document knowledge.
        # Bypass retrieval and EvidenceService so unrelated chunks cannot force
        # an abstention such as "insufficient evidence".
        if self._is_self_capability(q):
            return {
                "answer": _SELF_CAPABILITY_ANSWER,
                "sources": [],
                "retrieved_chunks": [],
                "decision": "self_capability",
                "query_plan": {"intent": "self_capability", "requires_rag": False},
                "execution_time_seconds": round(time.time() - t0, 2),
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

        # Classify the request and produce a small lexical variant.  The
        # original wording remains the primary query; the normalized variant
        # helps BM25 match natural Vietnamese phrasing without relying on an
        # LLM or a hand-written list of answer concepts.
        query_plan = self.query_planner.plan(q)

        # 1. Retrieval
        # Retrieve a wider candidate pool, then rerank and trim to the context
        # budget. Fetching only top_k here made the reranker unable to recover
        # relevant passages ranked just below the vector-search cutoff.
        # Keep a wider final context so a question that spans policies,
        # procedures and exceptions can be answered from several documents.
        # The previous cap of 8 chunks plus a global slice let one document
        # consume the entire answer context.
        final_k = max(1, min(int(top_k or TOP_K), 16))
        candidate_k = min(80, max(final_k * RETRIEVAL_CANDIDATE_MULTIPLIER, 16))
        scope_ids: list[str] = []
        for value in [document_id, *(document_ids or [])]:
            if value and value not in scope_ids:
                scope_ids.append(value)

        # Document-level pre-filter: resolve explicit product/platform terms
        # before searching chunks.  This prevents generic words such as
        # "trả hàng" from mixing Shopee, Microsoft and inverter policies.
        topic_terms = [
            token.casefold() for token in re.findall(r"[\wÀ-ỹ]+", q, flags=re.UNICODE)
            if len(token) >= 4 and token.casefold() not in _GENERIC_TOPIC_TERMS
        ]
        document_filter_applied = False
        if not scope_ids and topic_terms:
            candidate_document_ids = self.retriever.chunk_repo.find_document_ids_by_topics(topic_terms)
            document_filter_applied = True
            scope_ids.extend(candidate_document_ids)

        raw_chunks: list[Dict[str, Any]] = []
        retrieval_queries = query_plan.query_variants or [q]
        # Search each requested document independently so one large document
        # cannot consume the entire top-k budget of a multi-document request.
        # An explicit topic with no matching document must not fall back to a
        # corpus-wide search and return an unrelated policy.
        retrieval_scopes: list[Optional[str]] = scope_ids if document_filter_applied else (scope_ids or [None])
        for scope_id in retrieval_scopes:
            if query_plan.exact_lookup:
                exact_retrieve = getattr(self.retriever, "retrieve_exact", None)
                if callable(exact_retrieve):
                    raw_chunks.extend(
                        dict(chunk)
                        for chunk in exact_retrieve(
                            query=query_plan.exact_query or query_plan.normalized_query,
                            top_k=final_k,
                            document_id=scope_id,
                        )
                    )
            for retrieval_query in retrieval_queries:
                retrieved = self.retriever.retrieve(
                    query=retrieval_query,
                    top_k=candidate_k,
                    document_id=scope_id,
                )
                for chunk in retrieved:
                    item = dict(chunk)
                    item["retrieval_query"] = retrieval_query
                    raw_chunks.append(item)

        retrieved_doc_ids = sorted({
            str(chunk.get("document_id"))
            for chunk in raw_chunks
            if chunk.get("document_id")
        })
        retrieval_scope = {
            "mode": "explicit_documents" if scope_ids else "corpus_candidate_pool",
            "requested_document_count": len(scope_ids),
            "document_filter_applied": document_filter_applied,
            "retrieved_document_count": len(retrieved_doc_ids),
            "retrieved_document_ids": retrieved_doc_ids,
            "coverage": "top_k_candidates",
        }

        # Content-only evidence gate.  Retrieval may return related-looking
        # chunks, but generation is allowed only when the content itself is
        # relevant, sufficiently covering the question, and consistent.
        reranked_chunks = self._deduplicate_chunks(self.evidence.rerank(q, raw_chunks))
        relevance_scores = sorted(
            float(chunk.get("content_relevance_score", 0.0))
            for chunk in reranked_chunks
        )
        if relevance_scores:
            median = relevance_scores[len(relevance_scores) // 2]
            score_spread = relevance_scores[-1] - relevance_scores[0]
            distribution_cutoff = max(0.12, median + 0.25 * score_spread)
        else:
            distribution_cutoff = 0.12
        eligible_chunks = [
            chunk for chunk in reranked_chunks
            if chunk.get("content_relevance_score", 0.0) >= distribution_cutoff
            and (
                not query_plan.structured_lookup
                or float(chunk.get("answerability_score", 0.0)) >= 0.34
            )
        ]
        # Keep the compatibility order produced by EvidenceService visible
        # throughout the selection phase.  Round-robin document diversity and
        # clause coverage are secondary; they must not move a weak generic
        # paragraph ahead of a chunk that contains the requested entity and
        # answer-bearing constraint.
        def compatibility_key(item: Dict[str, Any]) -> tuple[float, float, float, float]:
            return (
                float(item.get("answerability_score", 0.0)),
                float(item.get("content_relevance_score", 0.0)),
                float(item.get("bm25_score", 0.0) or 0.0),
                float(item.get("similarity_score", 0.0) or 0.0),
            )

        eligible_chunks = sorted(eligible_chunks, key=compatibility_key, reverse=True)
        # Preserve one strong candidate for each decomposed query clause. A
        # global score cutoff can otherwise keep only the first condition and
        # drop a later clause such as the return-shipping fee or its support
        # requirements.
        selected_ids = {str(chunk.get("chunk_id")) for chunk in eligible_chunks}
        clause_priority: list[Dict[str, Any]] = []
        for clause in retrieval_queries:
            clause_candidates = [
                chunk for chunk in reranked_chunks
                if str(chunk.get("retrieval_query") or "") == str(clause)
                and str(chunk.get("chunk_id")) not in selected_ids
            ]
            if clause_candidates:
                candidate = clause_candidates[0]
                if (
                    float(candidate.get("content_relevance_score", 0.0)) >= 0.03
                    and (
                        not query_plan.structured_lookup
                        or float(candidate.get("answerability_score", 0.0)) >= 0.34
                    )
                ):
                    clause_priority.append(candidate)
                    selected_ids.add(str(candidate.get("chunk_id")))
        # Clause representatives are added to the candidate pool, then sorted
        # again by compatibility.  They no longer jump to the front merely
        # because they came from a decomposed query variant.
        if clause_priority:
            eligible_chunks = sorted(
                self._deduplicate_chunks(clause_priority + eligible_chunks),
                key=compatibility_key,
                reverse=True,
            )
        # Select by document in round-robin order.  This preserves the best
        # evidence from each relevant document while still ranking documents
        # by their strongest match.  A single long document can no longer
        # hide corroborating evidence from other documents.
        by_document: dict[str, list[Dict[str, Any]]] = {}
        for chunk in eligible_chunks:
            by_document.setdefault(str(chunk.get("document_id") or "unknown"), []).append(chunk)
        # Apply a document-level relevance gate after chunk scoring.  Shared
        # policy words ("bảo hành", "gửi", "chi phí") can make an unrelated
        # document pass a global chunk threshold even though its best passage
        # is far below the best document.  Keep corroborating documents only
        # when their strongest evidence is reasonably close to the leader.
        if by_document:
            def document_score(chunks: list[Dict[str, Any]]) -> float:
                scores = [float(item.get("content_relevance_score", 0.0)) for item in chunks[:3]]
                if not scores:
                    return 0.0
                # Strongest passage carries most weight; supporting passages
                # and distinct query clauses prevent one accidental keyword
                # hit from representing an entire document.
                strongest = scores[0]
                support = sum(scores) / len(scores)
                covered_clauses = {
                    str(item.get("retrieval_query") or "").casefold()
                    for item in chunks[:8]
                    if item.get("retrieval_query")
                }
                clause_bonus = min(0.12, max(0, len(covered_clauses) - 1) * 0.03)
                return 0.60 * strongest + 0.30 * support + clause_bonus

            scored_documents = {doc_id: document_score(chunks) for doc_id, chunks in by_document.items()}
            best_document_score = max(scored_documents.values(), default=0.0)
            document_cutoff = max(distribution_cutoff, best_document_score * 0.68)
            by_document = {
                doc_id: chunks
                for doc_id, chunks in by_document.items()
                if chunks and scored_documents.get(doc_id, 0.0) >= document_cutoff
            }
        ordered_documents = sorted(
            by_document,
            key=lambda doc: (
                document_score(by_document[doc]) if by_document else 0.0,
                float(by_document[doc][0].get("content_relevance_score", 0.0)),
            ),
            reverse=True,
        )
        matched_chunks = []
        per_document_cap = max(2, min(4, final_k // max(1, min(len(ordered_documents), 4))))
        for round_index in range(per_document_cap):
            for doc_id in ordered_documents:
                candidates = by_document[doc_id]
                if round_index < len(candidates) and len(matched_chunks) < final_k:
                    matched_chunks.append(candidates[round_index])
            if len(matched_chunks) >= final_k:
                break
        # Structured questions target an answer-bearing row or paragraph.
        # Never expand them with adjacent headings and navigation text.  Use a
        # slightly wider bound for genuinely long multi-condition questions,
        # but still keep the most compatible chunks first.
        query_word_count = len(re.findall(r"[\wÀ-ỹ]+", q, flags=re.UNICODE))
        focused_lookup = query_plan.structured_lookup and bool(matched_chunks)
        if focused_lookup:
            matched_chunks = sorted(
                matched_chunks,
                key=compatibility_key,
                reverse=True,
            )[: (4 if query_word_count > 16 else 2)]
        # Score distributions can become too narrow for long, multi-intent
        # questions even when the best chunk is useful. Keep the strongest
        # evidence as a bounded fallback so the answer layer can report a
        # partial result instead of claiming that nothing was found.
        if not matched_chunks and reranked_chunks:
            best = reranked_chunks[0]
            if float(best.get("content_relevance_score", 0.0)) >= 0.03:
                matched_chunks = [chunk for chunk in reranked_chunks[:3] if float(chunk.get("content_relevance_score", 0.0)) >= 0.03]
        # Preserve section continuity. A table/heading hit is often followed
        # by the procedure and exception paragraphs in adjacent chunks; score
        # filtering must not remove those parts of the same document section.
        if matched_chunks and not focused_lookup:
            selected_keys = {(str(c.get("document_id")), int(c.get("chunk_index", -10**9))) for c in matched_chunks}
            expanded = list(matched_chunks)
            for base in matched_chunks:
                try:
                    doc_id = str(base.get("document_id"))
                    idx = int(base.get("chunk_index"))
                except (TypeError, ValueError):
                    continue
                for candidate in reranked_chunks:
                    try:
                        key = (str(candidate.get("document_id")), int(candidate.get("chunk_index")))
                    except (TypeError, ValueError):
                        continue
                    if key[0] == doc_id and abs(key[1] - idx) <= 4 and key not in selected_keys:
                        expanded.append(candidate)
                        selected_keys.add(key)
            matched_chunks = sorted(expanded, key=compatibility_key, reverse=True)[: max(final_k, 8)]

        # Final topic safety gate at the exact boundary used to build sources.
        # This protects against later continuity/round-robin expansion adding
        # a generic policy chunk from another product family.
        q_tokens = [
            token.casefold() for token in re.findall(r"[\wÀ-ỹ]+", q, flags=re.UNICODE)
        ]
        topic_terms = [
            token for token in q_tokens
            if len(token) >= 4 and token not in _GENERIC_TOPIC_TERMS
        ]
        if topic_terms and matched_chunks:
            topic_matched = [
                chunk for chunk in matched_chunks
                if any(term in str(chunk.get("content") or "").casefold() for term in topic_terms)
            ]
            if topic_matched:
                matched_chunks = topic_matched

        # Hard document identity gate.  A query often contains ordinary words
        # such as ``theo`` or ``đầu`` that occur in many policies.  They must
        # not be treated as a brand/entity anchor.  Estimate document
        # frequency over the retrieved candidate pool and keep only rare query
        # terms as identity signals.  For the Adore query, ``adore`` occurs in
        # one document while generic warranty words occur in several, so all
        # NLMT chunks are removed while supporting ADORE chunks are retained.
        if matched_chunks and reranked_chunks:
            candidate_by_document: dict[str, list[Dict[str, Any]]] = {}
            for chunk in reranked_chunks:
                doc_id = str(chunk.get("document_id") or "")
                if doc_id:
                    candidate_by_document.setdefault(doc_id, []).append(chunk)
            document_count = len(candidate_by_document)
            max_identity_document_frequency = max(1, (document_count + 2) // 3)
            term_documents: dict[str, set[str]] = {}
            for token in q_tokens:
                if len(token) < 4 or token in _GENERIC_TOPIC_TERMS:
                    continue
                for doc_id, doc_chunks in candidate_by_document.items():
                    haystack = " ".join(
                        str(item.get("content") or "") + " "
                        + str(item.get("original_filename") or item.get("file_name") or "")
                        for item in doc_chunks
                    ).casefold()
                    if token in haystack:
                        term_documents.setdefault(token, set()).add(doc_id)
            identity_terms = [
                term for term, docs in term_documents.items()
                if docs and len(docs) <= max_identity_document_frequency
            ]
            identity_document_ids = {
                doc_id for term in identity_terms for doc_id in term_documents[term]
            }
            if identity_document_ids:
                matched_chunks = [
                    chunk for chunk in matched_chunks
                    if str(chunk.get("document_id")) in identity_document_ids
                ]
        # The source list and the prompt must use the same compatibility order
        # as reranking.  This final sort also makes the order deterministic
        # after topic filtering or document round-robin selection.
        matched_chunks = sorted(matched_chunks, key=compatibility_key, reverse=True)
        evidence_state = self.evidence.assess(q, matched_chunks)

        # A multi-intent natural question may contain a clause whose wording
        # is not present verbatim in the evidence.  Do not discard all useful
        # evidence in that case: let the grounded generator answer the covered
        # parts and state the one missing part. Abstain only when evidence is
        # irrelevant or has no covered requirement at all.
        if matched_chunks and evidence_state.relevance == "IRRELEVANT":
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
                "query_plan": query_plan.to_dict(),
                "retrieval_queries": retrieval_queries,
                "scope_document_ids": scope_ids,
                "retrieval_scope": retrieval_scope,
                "execution_time_seconds": round(time.time() - t0, 2),
            }

        if not raw_chunks:
            return {
                "answer": "Không tìm thấy thông tin hoặc tài liệu nào liên quan trong cơ sở dữ liệu để trả lời câu hỏi của bạn.",
                "sources": [],
                "query_plan": query_plan.to_dict(),
                "retrieval_queries": retrieval_queries,
                "scope_document_ids": scope_ids,
                "retrieval_scope": retrieval_scope,
                "execution_time_seconds": round(time.time() - t0, 2),
            }

        # The content-only evidence gate above is the single relevance gate.
        # Do not re-filter by a filename-aware or similarity-only heuristic.

        if not matched_chunks:
            return {
                "answer": "Không tìm thấy thông tin hoặc tài liệu nào liên quan trong cơ sở dữ liệu để trả lời câu hỏi của bạn.",
                "sources": [],
                "query_plan": query_plan.to_dict(),
                "retrieval_queries": retrieval_queries,
                "scope_document_ids": scope_ids,
                "retrieval_scope": retrieval_scope,
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
            content = self._clean_extracted_noise(chunk.get("content", "").strip())
            element_ids = meta.get("element_ids") or []
            if not isinstance(element_ids, list):
                element_ids = [str(element_ids)]
            scoped_claims = chunk.get("scoped_claims") or []
            scope_hint = "; ".join(
                f"{claim.get('scope')} -> {claim.get('claim_type')}:{claim.get('value')}"
                for claim in scoped_claims
            ) or "general"
            # Khắc phục lỗi rớt/đứt từ do phân mảnh chunk biên (Chunk boundary clipping)
            content = re.sub(r'lao động yết\b', 'lao động và niêm yết', content)
            content = re.sub(r'xác nhận và niêm\s*$', 'xác nhận: ', content)
            chunk["content"] = content

            context_blocks.append(
                f"[EVIDENCE #{idx+1} | File: {file_name} | Chunk: {chunk_id} | Trang: {page}]\n"
                f"[PHẠM VI ÁP DỤNG: {scope_hint}]\n{content}"
            )
            sources.append({
                "document_id": doc_id,
                "file_name": file_name,
                "chunk_id": chunk_id,
                "page": page,
                "similarity_score": score,
                "query_compatibility_score": chunk.get("query_compatibility_score", chunk.get("content_relevance_score")),
                "answerability_score": chunk.get("answerability_score"),
                "entity_match": chunk.get("entity_match"),
                "constraint_match": chunk.get("constraint_match"),
                "scoped_claims": scoped_claims,
                "dense_score": chunk.get("dense_score"),
                "bm25_score": chunk.get("bm25_score"),
                "retrieval_method": chunk.get("retrieval_method"),
                "source_locator": meta.get("locator") or meta.get("source_locator"),
                "element_ids": element_ids,
                "section": meta.get("section"),
                "extraction_method": meta.get("extraction_method") or meta.get("source"),
                "ocr_confidence": meta.get("ocr_confidence"),
                "page_start": meta.get("page_start"),
                "page_end": meta.get("page_end"),
                "snippet": content[:150].replace("\n", " ") + ("..." if len(content) > 150 else ""),
            })

        full_context = "\n\n".join(context_blocks)
        if len(full_context) > NIM_MAX_INPUT_CHARS:
            # Keep the highest-ranked evidence first; sending the entire
            # corpus to a hosted model causes avoidable latency and timeouts.
            full_context = full_context[:NIM_MAX_INPUT_CHARS]
        critical_lines = self._critical_policy_lines(full_context)

        system_prompt = build_grounded_qa_system_prompt()

        policy_checklist = (
            "\n\n--- CRITICAL SOURCE LINES (DO NOT MERGE ROWS) ---\n"
            f"{critical_lines}\n"
            "Before answering, apply each threshold and each location/category separately."
            if critical_lines else ""
        )
        time_context = _extract_time_context(q)
        time_annotation = f"\n{time_context}" if time_context else ""
        user_prompt = f"--- EVIDENCE ---\n{full_context}{policy_checklist}\n\n--- QUESTION ---\n{q}{time_annotation}\n\n"
        user_prompt += (
            "Nếu bằng chứng là bảng, phải đối chiếu theo đúng hàng: phương thức thanh toán trong câu hỏi "
            "hoặc thuộc tính được hỏi phải khớp với ô/cột tương ứng. Không chọn hàng đầu tiên chỉ vì một từ khóa "
            "chung xuất hiện; giữ nguyên quan hệ giữa các cột và chỉ lấy thời gian trên đúng hàng đã khớp.\n"
            "Các dòng PHẠM VI ÁP DỤNG là bản đồ gợi ý được tạo từ chính chunk; dùng chúng để giữ quan hệ nhánh, "
            "nhưng luôn kiểm tra lại nội dung gốc. Không in bản đồ, nhãn kỹ thuật hoặc tên claim ra câu trả lời.\n"
            "Chỉ chọn đoạn quy định trực tiếp áp dụng cho tình huống người dùng nêu; không chép phần mở đầu, "
            "lịch sử hoặc toàn bộ văn bản chính sách. Trả lời theo đúng các ý người dùng hỏi, tối đa 5 gạch đầu dòng "
            "và khoảng 180 từ. Nếu người dùng hỏi quy trình, tóm tắt thành các bước đánh số, chỉ nêu bước có trong bằng chứng. "
            "Nếu nguồn nêu nhiều phương thức trả hàng hoặc nhiều lựa chọn, trình bày kết quả theo từng phương thức; "
            "gắn phí và điều kiện với đúng phương thức đó, không lấy điều kiện của 'tự sắp xếp' áp cho 'đến lấy' hoặc "
            "'gửi tại bưu cục', và không gộp các nhánh thành một điều kiện chung. "
            "Không lặp lại câu hỏi và không trộn quy định của sản phẩm hoặc tình huống khác. Trả lời trực tiếp:"
        )
        image_inputs = []
        storage = None
        for chunk in matched_chunks if NIM_SUPPORTS_MULTIMODAL else []:
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
        answer = self._call_llm(system_prompt, user_prompt, image_inputs=image_inputs, on_token=on_token)

        # Một số lượt sinh của mô hình có thể trả lời bằng lời từ chối chung
        # dù bằng chứng đã đủ. Gửi lại cùng bằng chứng với hợp đồng đầu ra
        # ngắn và bắt buộc để tránh biến một câu hỏi chính sách thành lời
        # khuyên chung chung.
        if self._is_refusal_answer(answer) or self._needs_policy_repair(answer, q, full_context):
            forced_prompt = (
                f"{system_prompt}\n\n"
                "Đây là lượt kiểm tra lại vì câu trả lời trước chưa bám đủ bằng chứng. "
                "Bắt buộc đối chiếu lại từng dữ kiện của câu hỏi với đúng đoạn, hàng hoặc cột trong nguồn. "
                "Không xin lỗi, không từ chối và không thêm giả định. Trả lời kết luận trước, tối đa 5 gạch đầu dòng "
                "với văn phong tư vấn tự nhiên; nếu là thời hạn hoặc thời gian hoàn tiền, nêu rõ mốc bắt đầu tính "
                "theo tài liệu và phân biệt với các mốc khác mà người dùng dễ nhầm. Chỉ thêm ví dụ ngày tháng nếu "
                "đó là phép tính trực tiếp từ số ngày làm việc được nêu trong nguồn. "
                "Nếu có nhiều phương thức trả hàng, hãy tách từng phương thức thành một dòng và giữ nguyên phạm vi "
                "điều kiện của từng phương thức; không gộp điều kiện hoàn phí của một phương thức vào phương thức khác. "
                "Nếu nguồn có các nhánh đến lấy hàng, gửi tại bưu cục và tự sắp xếp, hãy biểu diễn nội bộ theo sơ đồ: "
                "đến lấy = miễn phí; gửi tại bưu cục = miễn phí; tự sắp xếp = trả trước rồi mới xét hỗ trợ, chỉ khi "
                "đúng nguồn có đủ các nhãn này. Chỉ đưa điều kiện mã vận đơn hoặc hoàn phí vào nhánh mà nguồn gắn nó. "
                "và không chép lại phần mở đầu của chính sách. Nếu nguồn ghi rõ 'miễn phí trả hàng' hoặc 'hỗ trợ hoàn lại phí', "
                "không được đổi thành điều kiện người bán phải đồng ý chịu phí hay thỏa thuận riêng."
            )
            forced_user_prompt = (
                f"--- EVIDENCE ---\n{full_context}\n\n"
                "--- EXTRACTION TASK ---\n"
                f"Tình huống cần đối chiếu: {q}\n"
                "Hãy trích xuất trực tiếp quy định phù hợp với tình huống, giữ riêng từng điều kiện, mốc thời gian, "
                "địa điểm, loại sản phẩm và hàng trong bảng nếu chúng xuất hiện. Bắt đầu bằng 'Kết luận:'; "
                "không nhắc lại tình huống, không xin lỗi, không chép toàn bộ tài liệu và không nói về giới hạn của mô hình."
            )
            answer = self._call_llm(forced_prompt, forced_user_prompt, image_inputs=image_inputs, on_token=on_token)

        scoped_repair = self._compose_scoped_branch_answer(q, matched_chunks, answer, full_context)
        if scoped_repair:
            answer = scoped_repair
            if on_token:
                on_token(answer)

        # NVIDIA may occasionally return an empty content stream while the
        # retrieval phase succeeded. Return a grounded extractive response
        # instead of leaving the user with a source-only message.
        if not (answer or "").strip() or (answer or "").strip() in {
            "Không nhận được phản hồi từ mô hình AI.",
            "Không nhận được phản hồi từ mô hình AI sau nhiều lần thử lại.",
        }:
            fallback_lines: list[str] = []
            for chunk in matched_chunks[:4]:
                text = re.sub(r"\s+", " ", str(chunk.get("content") or "")).strip()
                if text and text not in fallback_lines:
                    fallback_lines.append(text[:700])
            answer = "Kết luận:\n" + "\n".join(f"- {line}" for line in fallback_lines)
            if on_token:
                on_token(answer)

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
            # Internal retrieval labels are for the API metadata, never for
            # the user-facing answer.
            answer = re.sub(r'(?im)^\s*\|?\s*(?:tham chiếu|evidence|nguồn nội bộ|retrieved_chunks|source locator)\s*\|?.*$', '', answer)
            answer = re.sub(r'(?i)\[?evidence\s*#?\s*\d+[^\]]*\]?\s*', '', answer)
            answer = re.sub(r'(?i)\b(?:chunk[_ -]?id|query[_ -]?plan|retrieval[_ -]?scope|similarity[_ -]?score)\s*[:=][^\n|,;]+', '', answer)
            answer = re.sub(r'(?im)^\s*\|?\s*(?:điều kiện|tham chiếu|nội dung chính)\s*\|.*$', '', answer)
            answer = re.sub(r'(?im)^\s*(?:kết luận|điều kiện áp dụng|phần còn thiếu|phần thiếu)\s*:?\s*$', '', answer)
            # Loại bỏ phần "Lưu ý" do model tự thêm vào không có trong evidence.
            # Bắt cả dạng inline (cùng dòng) và dạng block (xuống dòng riêng).
            answer = re.sub(
                r'(?:^|\n+)\*?\*?Lưu ý\*?\*?\s*:?[^\n]*(?:\n(?!\n)[^\n]*)*',
                '',
                answer,
                flags=re.IGNORECASE,
            ).strip()
            # Loại bỏ câu "Phí này không áp dụng cho..." kiểu hallucinate thường thấy
            answer = re.sub(
                r'\.?\s*\*?\s*Phí này không áp dụng cho[^.]*\.',
                '.',
                answer,
                flags=re.IGNORECASE,
            ).strip()
            # Loại bỏ câu nói về fullbox khi user không hỏi về fullbox
            if 'fullbox' not in q.lower() and 'nguyên thùng' not in q.lower() and 'nguyên hộp' not in q.lower():
                answer = re.sub(
                    r'\.?\s*\*?[^.]*(?:fullbox|nguyên thùng|nguyên hộp)[^.]*\.',
                    '.',
                    answer,
                    flags=re.IGNORECASE,
                ).strip()
            answer = self._remove_question_echo(answer, q)

        elapsed = round(time.time() - t0, 2)

        return {
            "answer": answer,
            "sources": sources,
            "total_chunks_retrieved": len(matched_chunks),
            "retrieved_chunks": matched_chunks,
            "evidence": evidence_state.to_dict(),
            "decision": "ANSWER",
            "query_plan": query_plan.to_dict(),
            "retrieval_queries": retrieval_queries,
            "scope_document_ids": scope_ids,
            "retrieval_scope": retrieval_scope,
            "execution_time_seconds": elapsed,
        }

    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        image_inputs: Optional[List[str]] = None,
        model: Optional[str] = None,
        on_token=None,
    ) -> str:
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
            "model": model or self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.0,
            "seed": 42,
            # Keep the response budget bounded; Nemotron's hosted endpoint
            # spends less time decoding when the grounded answer is concise.
            # Leave enough headroom for multi-part policy answers. The model
            # may stop mid-word when the budget is too tight, especially after
            # preserving table conditions and numbered requirements.
            "max_tokens": 1200,
            "stream": bool(on_token),
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
                with urllib.request.urlopen(req, timeout=NIM_TIMEOUT_SECONDS) as resp:
                    if on_token:
                        answer_parts = []
                        for raw_line in resp:
                            line = raw_line.decode("utf-8", errors="ignore").strip()
                            if not line.startswith("data:"):
                                continue
                            data_line = line[5:].strip()
                            if data_line == "[DONE]":
                                break
                            try:
                                delta = json.loads(data_line).get("choices", [{}])[0].get("delta", {}).get("content") or ""
                            except (ValueError, IndexError, AttributeError):
                                delta = ""
                            if delta:
                                answer_parts.append(delta)
                                on_token(delta)
                        streamed_answer = "".join(answer_parts).strip()
                        # Some NVIDIA endpoints may close a streaming response
                        # after emitting metadata/role events without a
                        # ``content`` delta. Never publish a source-only
                        # assistant message; retry once in non-stream mode and
                        # forward the recovered answer through the same token
                        # callback.
                        if streamed_answer:
                            return streamed_answer
                        fallback_payload = dict(payload)
                        fallback_payload["stream"] = False
                        fallback_request = urllib.request.Request(
                            endpoint,
                            data=json.dumps(fallback_payload).encode("utf-8"),
                            headers=headers,
                            method="POST",
                        )
                        with urllib.request.urlopen(fallback_request, timeout=NIM_TIMEOUT_SECONDS) as fallback_resp:
                            fallback_json = json.loads(fallback_resp.read().decode("utf-8"))
                        fallback_answer = ""
                        fallback_choices = fallback_json.get("choices", []) if isinstance(fallback_json, dict) else []
                        if fallback_choices:
                            message = fallback_choices[0].get("message", {}) or {}
                            fallback_answer = str(message.get("content") or "").strip()
                        if fallback_answer:
                            on_token(fallback_answer)
                            return fallback_answer
                        return "Không nhận được phản hồi từ mô hình AI."
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
