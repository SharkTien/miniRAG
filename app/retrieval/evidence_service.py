"""Content-only evidence evaluation for the RAG pipeline.

Document names are deliberately not accepted by this module.  They are
identifiers for citation only; all relevance and coverage decisions are made
from the question and chunk content.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Sequence


_STOPWORDS = {
    "và", "hoặc", "thì", "là", "có", "được", "không", "ko", "k", "về",
    "việc", "sau", "khi", "nhận", "cho", "của", "tại", "ở", "các", "những",
    "đã", "đang", "sẽ", "phải", "cần", "gì", "ai", "đâu", "nào", "sao",
    "thế", "như", "này", "đó", "ra", "vào", "lại", "thực", "hiện", "hãy",
    "xin", "vui", "lòng", "cho", "biết", "tôi", "mình", "bạn", "thì",
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on",
    "for", "from", "with", "by", "is", "are", "was", "were", "be",
    "been", "being", "what", "which", "who", "when", "where", "why",
    "how", "does", "do", "did", "can", "could", "would", "should",
    "please", "tell", "me", "about", "this", "that", "these", "those",
}

_ANSWER_TERMS = {
    "lương", "tiền", "mức", "tính", "trả", "thanh toán", "hưởng", "được hưởng",
    "điều kiện", "thời hạn", "thời gian", "quy trình", "hồ sơ", "phê duyệt",
    "nghỉ", "ngày", "giờ", "tỷ lệ", "phụ cấp", "trợ cấp", "đăng ký",
    "giá", "amount", "price", "cost", "total", "date", "time", "rate", "number",
    "name", "address", "condition", "deadline", "period", "process", "form",
    "approved", "approval", "leave", "hours", "salary", "payment", "paid",
}

_GENERIC_QUERY_TERMS = {
    "giá", "dịch", "vụ", "thông", "tin", "nội", "dung", "như", "nào",
}
_MONEY_PATTERN = re.compile(
    r"\b\d[\d\s.,]*\s*(?:đ|đồng|vnđ|vnd)\b|\btổng\s+cộng\b",
    re.IGNORECASE | re.UNICODE,
)


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "").lower()).strip()


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[\wÀ-ỹ]+", _fold(text), flags=re.UNICODE)
            if len(t) > 1 and t not in _STOPWORDS]


def _phrases(text: str) -> List[str]:
    """Extract small content requirements without using document metadata."""
    folded = _fold(text)
    parts = re.split(r"\s+(?:và|hoặc|nhưng|còn)\s+|[,;?]", folded)
    phrases = []
    for part in parts:
        words = [w for w in _tokens(part) if len(w) > 1]
        if words:
            phrases.append(" ".join(words[-5:]))
    return phrases


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    folded = _fold(text)
    return any(_fold(term) in folded for term in terms)


@dataclass
class EvidenceAssessment:
    """Provide the evidenceassessment application component."""
    relevance: str
    coverage: str
    consistency: str
    answerability: bool
    relevance_score: float
    coverage_score: float
    missing_requirements: List[str]
    selected_chunk_ids: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert the value to dict."""
        return asdict(self)


class EvidenceService:
    """Evaluate whether retrieved *content* can support an answer.

    This is intentionally a conservative baseline.  It is independent from
    the generator so it can later be replaced by a cross-encoder or judge
    model without changing the decision contract.
    """

    def rerank(self, question: str, chunks: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rerank retrieved evidence using grounded signals."""
        q_tokens = set(_tokens(question))
        q_phrases = _phrases(question)
        ranked: List[Dict[str, Any]] = []
        for chunk in chunks:
            content = chunk.get("content") or ""
            c_tokens = set(_tokens(content))
            token_overlap = len(q_tokens & c_tokens) / max(1, len(q_tokens))
            phrase_overlap = sum(1 for p in q_phrases if p and p in _fold(content)) / max(1, len(q_phrases))
            dense = float(chunk.get("similarity_score") or 0.0)
            # Dense retrieval supplies recall; content overlap decides ordering.
            score = min(1.0, 0.50 * token_overlap + 0.25 * phrase_overlap + 0.25 * max(0.0, dense))
            item = dict(chunk)
            item["content_relevance_score"] = round(score, 4)
            ranked.append(item)
        return sorted(ranked, key=lambda x: (x["content_relevance_score"], x.get("similarity_score", 0.0)), reverse=True)

    def assess(self, question: str, chunks: Sequence[Dict[str, Any]]) -> EvidenceAssessment:
        """Assess evidence quality and answerability."""
        if not chunks:
            return EvidenceAssessment("IRRELEVANT", "INSUFFICIENT", "CONSISTENT", False, 0.0, 0.0, _phrases(question), [])

        q_tokens = set(_tokens(question))
        q_phrases = _phrases(question)
        joined = "\n".join(chunk.get("content") or "" for chunk in chunks)
        joined_folded = _fold(joined)
        overlap = len(q_tokens & set(_tokens(joined))) / max(1, len(q_tokens))
        relevant_chunks = [c for c in chunks if c.get("content_relevance_score", 0.0) >= 0.12]

        # A requirement is covered only when its actual phrase or its content
        # terms occur in the evidence.  Similarity alone cannot cover it.
        covered: List[str] = []
        missing: List[str] = []
        for phrase in q_phrases:
            p_tokens = set(_tokens(phrase)) - _GENERIC_QUERY_TERMS
            phrase_hit = phrase in joined_folded
            token_hit = len(p_tokens & set(_tokens(joined))) / max(1, len(p_tokens)) >= 0.6
            (covered if phrase_hit or token_hit else missing).append(phrase)

        asked_answer_dimension = _contains_any(question, _ANSWER_TERMS)
        answer_dimension_present = (
            _contains_any(joined, _ANSWER_TERMS)
            or bool(_MONEY_PATTERN.search(joined))
        )
        coverage_score = len(covered) / max(1, len(q_phrases))
        if asked_answer_dimension and not answer_dimension_present:
            coverage_score *= 0.35
            missing.append("nội dung trả lời trực tiếp cho yêu cầu của câu hỏi")

        if not relevant_chunks or overlap < 0.08:
            relevance = "IRRELEVANT"
        else:
            relevance = "RELEVANT"

        if coverage_score >= 0.70 and (not asked_answer_dimension or answer_dimension_present):
            coverage = "SUFFICIENT"
        elif coverage_score > 0.0:
            coverage = "PARTIAL"
        else:
            coverage = "INSUFFICIENT"

        # Conservative conflict signal: explicit negation/exception in two
        # passages that discuss the same answer terms.  Version-aware conflict
        # resolution remains a decision-layer concern.
        conflict_markers = ("không áp dụng", "không được", "trừ trường hợp", "ngoại trừ", "thay thế")
        consistency = "CONFLICTING" if sum(_contains_any(c.get("content", ""), conflict_markers) for c in chunks) >= 2 else "CONSISTENT"
        answerability = relevance == "RELEVANT" and coverage == "SUFFICIENT" and consistency == "CONSISTENT"
        selected_ids = [str(c.get("chunk_id") or "") for c in relevant_chunks]
        return EvidenceAssessment(
            relevance, coverage, consistency, answerability,
            round(overlap, 4), round(coverage_score, 4),
            list(dict.fromkeys(missing)), selected_ids,
        )
