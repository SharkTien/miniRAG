"""Content-only evidence evaluation for the RAG pipeline.

Document names are deliberately not accepted by this module.  They are
identifiers for citation only; all relevance and coverage decisions are made
from the question and chunk content.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Iterable, List, Sequence


_STOPWORDS = {
    "và", "hoặc", "thì", "là", "có", "được", "không", "ko", "k", "về",
    "việc", "sau", "khi", "nhận", "cho", "của", "tại", "ở", "các", "những",
    "đã", "đang", "sẽ", "phải", "cần", "gì", "ai", "đâu", "nào", "sao",
    "thế", "như", "này", "đó", "ra", "vào", "lại", "thực", "hiện", "hãy",
    "xin", "vui", "lòng", "cho", "biết", "tôi", "mình", "bạn", "thì",
    "anh", "em", "chị", "cô", "chú", "bên", "mới", "được", "giúp",
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on",
    "for", "from", "with", "by", "is", "are", "was", "were", "be",
    "been", "being", "what", "which", "who", "when", "where", "why",
    "how", "does", "do", "did", "can", "could", "would", "should",
    "please", "tell", "me", "about", "this", "that", "these", "those",
}

# Words that are common across policy documents.  They are deliberately kept
# out of the entity/topic signal; otherwise a query containing only ``trả
# hàng`` or ``phí`` would incorrectly anchor on any return policy in the
# corpus.  Short brand and payment tokens (for example ``momo``, ``tiki`` and
# ``napas``) remain eligible.
_GENERIC_ANCHORS = {
    "thông", "tin", "chính", "sách", "phẩm", "hàng", "hành", "khách",
    "người", "trường", "hợp", "phí", "chi", "gửi", "ngày", "tháng",
    "tiền", "hoàn", "điều", "kiện", "dịch", "vụ", "bưu", "cước", "trả",
    "đổi", "sản", "phương", "thức", "thời", "gian", "được", "phải",
    "mấy", "bao", "nhiêu", "hình", "thức", "đơn", "hàng", "yêu", "cầu",
    # Generic warranty/return wording must not become a document identity.
    # For example, a query mentioning "bảo hành trọn đời" is anchored by
    # ``adore``; ``bảo`` and ``trọn`` alone would incorrectly admit every
    # warranty policy in the corpus.
    "bảo", "trọn", "đời", "lỗi", "nhà", "xuất", "phụ", "thời", "trang",
}

_SCOPE_PATTERNS = {
    "pickup": (
        "đơn vị vận chuyển đến lấy hàng", "lấy hàng tại nhà", "shipper đến lấy",
        "bưu tá đến lấy", "đến lấy hàng",
    ),
    "drop_off": (
        "trả hàng tại bưu cục", "gửi hàng tại bưu cục", "gửi tại bưu cục",
        "đem hàng tới bưu cục", "mang hàng đến bưu cục",
    ),
    "self_arranged": (
        "tự sắp xếp", "tự thanh toán", "tự gửi hàng", "tự vận chuyển",
    ),
}

_CLAIM_PATTERNS = {
    ("fee", "free"): ("miễn phí trả hàng", "miễn phí hoàn trả", "miễn phí vận chuyển"),
    ("fee", "pay_first"): ("thanh toán trước phí", "trả trước phí", "thanh toán trước"),
    ("fee", "support_later"): ("hỗ trợ hoàn lại phí", "hỗ trợ phí trả hàng", "hoàn lại phí trả hàng"),
    ("requirement", "accepted_request"): ("yêu cầu trả hàng/hoàn tiền được chấp nhận", "yêu cầu trả hàng được chấp nhận"),
    ("requirement", "delivered_tracking"): ("giao hàng thành công", "mã vận đơn có trạng thái", "mã vận đơn phải tra được"),
    ("requirement", "seller_refund_approval"): ("người bán hoặc shopee đồng ý hoàn tiền", "đồng ý hoàn tiền"),
    ("requirement", "not_seller_shipping"): ("không phải do người bán tự vận chuyển",),
    ("requirement", "return_details"): ("điền đầy đủ thông tin trả hàng", "thông tin trả hàng và mã vận đơn"),
}


def _extract_scoped_claims(content: str) -> List[Dict[str, str]]:
    """Map option-specific claims without merging neighbouring alternatives.

    This is a conservative structure hint, not a replacement for the source
    text.  A chunk may belong to more than one scope when a table row contains
    two explicitly labelled free options (pickup and drop-off).
    """
    folded = _fold(content)
    scopes = [
        scope for scope, patterns in _SCOPE_PATTERNS.items()
        if any(pattern in folded for pattern in patterns)
    ] or ["general"]
    claims = [
        (claim_type, value)
        for (claim_type, value), patterns in _CLAIM_PATTERNS.items()
        if any(pattern in folded for pattern in patterns)
    ]
    return [
        {"scope": scope, "claim_type": claim_type, "value": value}
        for scope in scopes
        for claim_type, value in claims
    ]


def _anchor_terms(text: str) -> List[str]:
    """Extract distinctive product, brand, code, or acronym anchors.

    Generic words such as ``bảo hành`` must not decide the document. A
    visible acronym (AOC, TECNO, INVT) or model code is a stronger signal and
    lets the reranker discard generic warranty passages from other brands.
    """
    values = re.findall(r"\b[A-ZÀ-ỸĐ][A-ZÀ-ỸĐ0-9-]{2,}\b", text or "")
    # Also retain distinctive product/entity terms written in normal title
    # case or lowercase.  The old ``len(token) >= 7`` rule silently dropped
    # common five-letter entities such as ``napas`` and four-letter payment or
    # brand names such as ``momo``/``tiki``.
    values.extend(
        token for token in _tokens(text)
        if len(token) >= 4 and token not in _GENERIC_ANCHORS
    )
    return list(dict.fromkeys(_fold(value) for value in values))

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
    requirement_evidence: Dict[str, List[str]]
    topical_relevance: float = 0.0
    entity_match: float = 0.0
    constraint_match: float = 0.0
    scoped_claims: List[Dict[str, str]] = field(default_factory=list)

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
        anchors = _anchor_terms(question)
        strict_anchors = [_fold(value) for value in re.findall(r"\b[A-ZÀ-ỸĐ][A-ZÀ-ỸĐ0-9-]{2,}\b", question or "")]
        # Named products/brands written in normal casing or lowercase (for
        # example ``shopee``, ``napas`` and ``inverter``) are still useful
        # corpus anchors.  Use only distinctive words and never generic policy
        # vocabulary, so unrelated documents cannot pass on shared words such
        # as "phí" or "trả hàng".
        topic_anchors = [
            _fold(value) for value in anchors
            if len(_fold(value)) >= 4 and _fold(value) not in _GENERIC_ANCHORS
        ]
        generic_signal_terms = {
            "chính", "sách", "trả", "hàng", "đổi", "điều", "kiện", "phí",
            "gửi", "dịch", "vụ", "phương", "thức", "người", "được", "phải",
        }
        signal_terms = {
            term for term in q_tokens
            if len(term) >= 4 and term not in generic_signal_terms
        }
        ranked: List[Dict[str, Any]] = []
        for chunk in chunks:
            content = chunk.get("content") or ""
            # Previous failed answers must never become evidence for a later
            # query. They are system boilerplate, not document facts.
            if (
                "không tìm thấy thông tin hoặc tài liệu nào liên quan" in _fold(content)
                and len(content) < 500
            ):
                continue
            c_tokens = set(_tokens(content))
            token_overlap = len(q_tokens & c_tokens) / max(1, len(q_tokens))
            phrase_overlap = sum(1 for p in q_phrases if p and p in _fold(content)) / max(1, len(q_phrases))
            dense = float(chunk.get("similarity_score") or 0.0)
            anchor_match = bool(anchors and any(anchor in _fold(content) for anchor in anchors))
            entity_terms = set(topic_anchors) | set(strict_anchors)
            entity_match = (
                sum(1 for term in entity_terms if term in _fold(content)) / max(1, len(entity_terms))
                if entity_terms else 1.0
            )
            constraint_match = sum(1 for term in signal_terms if term in c_tokens) / max(1, len(signal_terms))
            # Dense retrieval supplies recall; the answer-bearing entity and
            # constraint coverage decide whether a chunk can answer the query.
            topical_score = min(1.0, 0.45 * token_overlap + 0.25 * phrase_overlap + 0.30 * max(0.0, dense))
            score = min(1.0, 0.35 * topical_score + 0.35 * entity_match + 0.30 * constraint_match)
            if anchor_match:
                score = min(1.0, score + 0.25)
            item = dict(chunk)
            item["content_relevance_score"] = round(score, 4)
            item["query_compatibility_score"] = round(score, 4)
            item["topical_relevance"] = round(topical_score, 4)
            item["entity_match"] = round(entity_match, 4)
            item["constraint_match"] = round(constraint_match, 4)
            item["answerability_score"] = round(0.45 * entity_match + 0.55 * constraint_match, 4)
            item["anchor_match"] = anchor_match
            item["scoped_claims"] = _extract_scoped_claims(content)
            item["evidence_scopes"] = list(dict.fromkeys(
                claim["scope"] for claim in item["scoped_claims"]
            )) or ["general"]
            ranked.append(item)
        # When a query names a distinctive acronym/model, generic passages
        # from other brands are not valid evidence even if they discuss the
        # same broad topic. Keep the fallback only when no anchor-bearing
        # candidate was retrieved.
        if strict_anchors:
            anchored = [item for item in ranked if any(anchor in _fold(item.get("content", "")) for anchor in strict_anchors)]
            if anchored:
                ranked = anchored
        elif topic_anchors:
            anchored = [
                item for item in ranked
                if any(anchor in _fold(item.get("content", "")) for anchor in topic_anchors)
            ]
            # Apply the topic gate only when at least one candidate actually
            # carries the named topic.  Generic questions remain corpus-wide.
            if anchored:
                ranked = anchored
            else:
                # The lexical anchor extractor also sees ordinary verbs and
                # nouns (for example ``tính`` or ``lương``).  If no candidate
                # contains one of those terms, preserve the scored candidates
                # and let the document-level identity gate decide.  Returning
                # an empty set here breaks valid generic-relevance checks and
                # prevents dense retrieval from supplying useful evidence.
                pass
        # Answerability is an explicit ranking signal, rather than metadata
        # calculated and ignored downstream.  This makes a row containing
        # ``NAPAS`` + the refund duration outrank a generic Shopee return
        # paragraph even when both have similar dense scores.
        return sorted(
            ranked,
            key=lambda x: (
                x.get("answerability_score", 0.0),
                x["content_relevance_score"],
                x.get("similarity_score", 0.0),
            ),
            reverse=True,
        )

    def assess(self, question: str, chunks: Sequence[Dict[str, Any]]) -> EvidenceAssessment:
        """Assess evidence quality and answerability."""
        if not chunks:
            return EvidenceAssessment(
                "IRRELEVANT", "INSUFFICIENT", "CONSISTENT", False, 0.0, 0.0,
                _phrases(question), [], {}, 0.0, 0.0, 0.0,
            )

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
        requirement_evidence: Dict[str, List[str]] = {}
        for phrase in q_phrases:
            p_tokens = set(_tokens(phrase))
            phrase_hit = phrase in joined_folded
            token_hit = len(p_tokens & set(_tokens(joined))) / max(1, len(p_tokens)) >= 0.6
            matching_ids = [
                str(chunk.get("chunk_id") or "")
                for chunk in chunks
                if phrase in _fold(chunk.get("content") or "")
                or len(p_tokens & set(_tokens(chunk.get("content") or ""))) / max(1, len(p_tokens)) >= 0.6
            ]
            if phrase_hit or token_hit:
                covered.append(phrase)
                requirement_evidence[phrase] = [value for value in matching_ids if value]
            else:
                missing.append(phrase)
                requirement_evidence[phrase] = []

        coverage_score = len(covered) / max(1, len(q_phrases))

        # Do not maintain a hand-written list of answer concepts (price,
        # service, salary, and so on). Dense retrieval already measures the
        # relationship between the question and the evidence. When the model
        # finds a strong semantic match but the wording differs, use that
        # signal to avoid rejecting a valid answer because of missing literal
        # words.
        best_dense_score = max(
            (float(chunk.get("similarity_score") or 0.0) for chunk in chunks),
            default=0.0,
        )
        lexical_token_overlap = len(q_tokens & set(_tokens(joined))) / max(1, len(q_tokens))
        # A long token shared by the question and evidence is a language-
        # independent anchor (brand, product, code, or named entity). It lets
        # semantic retrieval bridge descriptive wording without a vocabulary
        # list maintained by the application.
        shared_long_anchor = any(
            len(token) >= 5 and token in set(_tokens(joined))
            for token in q_tokens
        )
        if (
            relevant_chunks
            and best_dense_score >= 0.65
            and (lexical_token_overlap >= 0.50 or shared_long_anchor)
        ):
            semantic_coverage = min(1.0, 0.35 + (best_dense_score * 0.65))
            coverage_score = max(coverage_score, semantic_coverage)
            missing = []
            # Semantic support is still tied to the strongest retrieved
            # chunks, rather than being returned as an untraceable score.
            requirement_evidence = {
                phrase: [str(chunk.get("chunk_id") or "") for chunk in relevant_chunks if chunk.get("chunk_id")]
                for phrase in q_phrases
            }

        if not relevant_chunks or overlap < 0.08:
            relevance = "IRRELEVANT"
        else:
            relevance = "RELEVANT"

        if coverage_score >= 0.70:
            coverage = "SUFFICIENT"
        elif coverage_score > 0.0:
            coverage = "PARTIAL"
        else:
            coverage = "INSUFFICIENT"

        # Do not treat ordinary policy wording such as “không được ...” as a
        # contradiction.  OCR chunks from one policy commonly repeat those
        # exception phrases.  Mark a conflict only when opposing applicability
        # statements are actually present in the retrieved evidence.
        contents = [_fold(c.get("content", "")) for c in chunks]
        has_positive_scope = any("áp dụng" in content and "không áp dụng" not in content for content in contents)
        has_negative_scope = any("không áp dụng" in content for content in contents)
        consistency = "CONFLICTING" if has_positive_scope and has_negative_scope else "CONSISTENT"
        answerability = relevance == "RELEVANT" and coverage == "SUFFICIENT" and consistency == "CONSISTENT"
        selected_ids = [str(c.get("chunk_id") or "") for c in relevant_chunks]
        topical_relevance = sum(float(c.get("topical_relevance", 0.0)) for c in relevant_chunks) / max(1, len(relevant_chunks))
        entity_match = sum(float(c.get("entity_match", 0.0)) for c in relevant_chunks) / max(1, len(relevant_chunks))
        constraint_match = sum(float(c.get("constraint_match", 0.0)) for c in relevant_chunks) / max(1, len(relevant_chunks))
        scoped_claims: List[Dict[str, str]] = []
        for chunk in chunks:
            for claim in chunk.get("scoped_claims") or []:
                if claim not in scoped_claims:
                    scoped_claims.append(claim)
        return EvidenceAssessment(
            relevance, coverage, consistency, answerability,
            round(overlap, 4), round(coverage_score, 4),
            list(dict.fromkeys(missing)), selected_ids, requirement_evidence,
            round(topical_relevance, 4), round(entity_match, 4), round(constraint_match, 4),
            scoped_claims,
        )
