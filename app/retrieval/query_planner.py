"""Lightweight query planning for the production RAG flow.

The planner deliberately stays deterministic.  It does not call an LLM; it
only classifies the request and produces a small number of lexical variants so
that natural questions such as ``giá của dịch vụ ... như nào`` do not depend
on one exact wording being present in the indexed text.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any, List


_POLITE_PREFIX = re.compile(
    r"^\s*(?:cho\s+(?:tôi|mình)\s+biết|xin\s+cho\s+biết|hãy\s+cho\s+biết|"
    r"vui\s+lòng\s+cho\s+biết|giúp\s+(?:tôi|mình)|tôi\s+muốn\s+biết)\s+",
    re.IGNORECASE | re.UNICODE,
)
_QUESTION_TAIL = re.compile(
    r"\s+(?:như\s+thế\s+nào|như\s+nào|thế\s+nào|ra\s+sao)\s*[?!.]*$",
    re.IGNORECASE | re.UNICODE,
)
_EXACT_MARKERS = (
    "nguyên văn", "chính xác", "trích dẫn", "trang", "mục", "điều khoản",
    "section", "heading", "mã tài liệu", "tên file",
)
_STRUCTURED_MARKERS = (
    "giá", "chi phí", "doanh thu", "chiết khấu", "thuế", "tổng", "trung bình",
    "bao nhiêu", "số lượng", "đơn giá", "đơn vị", "tỷ lệ", "phần trăm",
)
_COMPARISON_MARKERS = (
    "so sánh", "khác nhau", "chênh lệch", "tăng hay giảm", "cao hơn", "thấp hơn",
)
_WIDE_SCOPE_MARKERS = (
    "tất cả", "mọi tài liệu", "toàn bộ", "các tài liệu", "trong kho", "không bỏ sót",
)


def _fold(text: str) -> str:
    value = unicodedata.normalize("NFC", text or "")
    return re.sub(r"\s+", " ", value).strip()


@dataclass(frozen=True)
class QueryPlan:
    """Deterministic retrieval instructions derived from one user question."""

    intent: str
    normalized_query: str
    exact_query: str | None
    query_variants: List[str]
    scope_requested: bool
    exact_lookup: bool
    structured_lookup: bool
    comparison: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class QueryPlanner:
    """Classify a query and produce safe retrieval variants."""

    def plan(self, question: str) -> QueryPlan:
        original = _fold(question)
        normalized = _POLITE_PREFIX.sub("", original)
        normalized = _QUESTION_TAIL.sub("", normalized)
        normalized = re.sub(r"[\u2018\u2019]", "'", normalized)
        normalized = _fold(normalized).strip(" ?!.,;:")
        if not normalized:
            normalized = original

        quoted = re.findall(r"['\"]([^'\"]{2,})['\"]", original)
        exact_query = _fold(quoted[0]) if quoted else None

        lowered = normalized.casefold()
        exact_lookup = any(marker in lowered for marker in _EXACT_MARKERS)
        structured_lookup = any(marker in lowered for marker in _STRUCTURED_MARKERS)
        comparison = any(marker in lowered for marker in _COMPARISON_MARKERS)
        scope_requested = any(marker in lowered for marker in _WIDE_SCOPE_MARKERS)

        if comparison:
            intent = "comparison"
        elif exact_lookup:
            intent = "exact"
        elif structured_lookup:
            intent = "structured"
        elif scope_requested:
            intent = "wide_scope"
        else:
            intent = "semantic"

        variants: list[str] = []
        for candidate in (original, normalized):
            candidate = _fold(candidate).strip(" ?!.,;:")
            if candidate and candidate not in variants:
                variants.append(candidate)

        # Do not fan out every query.  A second variant is useful only when the
        # natural wording differs from the normalized lexical form.
        if len(variants) > 2:
            variants = variants[:2]
        return QueryPlan(
            intent=intent,
            normalized_query=normalized,
            exact_query=exact_query,
            query_variants=variants or [original],
            scope_requested=scope_requested,
            exact_lookup=exact_lookup,
            structured_lookup=structured_lookup,
            comparison=comparison,
        )
