"""Semantic document normalization through the existing OpenAI-compatible Qwen service."""

import json
import re
import time
import unicodedata
from difflib import SequenceMatcher
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from app.config.prompts import QWEN_NORMALIZATION_SYSTEM_PROMPT
from app.config.constants import (
    QWEN_FUZZY_LENGTH_DELTA,
    QWEN_FUZZY_MATCH_THRESHOLD,
    QWEN_MAX_EXPANSION_CHARS,
    QWEN_MAX_EXPANSION_RATIO,
    QWEN_MAX_NOVEL_TOKEN_RATIO,
    QWEN_MAX_OUTPUT_TOKENS,
    QWEN_MAX_RETRIES,
    QWEN_RETRY_DELAY_SECONDS,
    QWEN_TEMPERATURE,
)
from app.config.settings import (
    QWEN_BASE_URL,
    QWEN_MAX_INPUT_CHARS,
    QWEN_MODEL,
    QWEN_TIMEOUT_SECONDS,
)

def _fold_ocr_token(value: str) -> str:
    value = value.casefold().replace("đ", "d")
    return "".join(
        char for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def _is_source_like(token: str, source_tokens: set[str]) -> bool:
    folded = _fold_ocr_token(token)
    if folded in source_tokens:
        return True
    # OCR commonly drops one Vietnamese vowel/diacritic.  A bounded fuzzy
    # comparison permits that repair without allowing wholesale rewriting.
    return any(
        abs(len(folded) - len(source)) <= QWEN_FUZZY_LENGTH_DELTA
        and SequenceMatcher(None, folded, source).ratio() >= QWEN_FUZZY_MATCH_THRESHOLD
        for source in source_tokens
    )


def _json_from_response(content: str) -> dict:
    content = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
    if fenced:
        content = fenced.group(1).strip()
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Qwen output không chứa JSON object")
    json_text = content[start:end + 1]
    try:
        value = json.loads(json_text)
    except json.JSONDecodeError:
        # Qwen/vLLM occasionally emits valid objects but misses a comma between
        # adjacent array items or top-level fields. Repair only structural
        # newlines; JSON string newlines are escaped and cannot match these.
        repaired = re.sub(r"}\s*\n\s*{", "},\n{", json_text)
        repaired = re.sub(r'([}\]])\s*\n(\s*)"([A-Za-z_][A-Za-z0-9_]*)"\s*:', r'\1,\n\2"\3":', repaired)
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        value = json.loads(repaired)
    if not isinstance(value, dict):
        raise ValueError("Qwen output không phải JSON object")
    return value


def _validate(value: dict, source_elements: list[dict]) -> dict:
    if not {"sections", "corrections", "types", "warnings"}.issubset(value):
        raise ValueError("Thiếu trường bắt buộc trong semantic normalization")
    if not all(isinstance(value[key], list) for key in ("sections", "corrections", "types", "warnings")):
        raise ValueError("Schema semantic normalization không hợp lệ")
    source_ids = {str(item.get("element_id")) for item in source_elements}
    corrections = {
        str(item.get("element_id")): str(item.get("text", ""))
        for item in value["corrections"]
        if isinstance(item, dict) and str(item.get("element_id")) in source_ids
    }
    allowed_types = {"title", "heading", "paragraph", "list", "table", "caption", "footer", "unknown"}
    type_updates = {
        str(item.get("element_id")): item.get("type")
        for item in value["types"]
        if isinstance(item, dict)
        and str(item.get("element_id")) in source_ids
        and item.get("type") in allowed_types
    }
    normalized = []
    for item in source_elements:
        element_id = str(item.get("element_id"))
        source_type = item.get("element_type", "unknown")
        normalized.append({
            "element_id": element_id,
            "type": type_updates.get(element_id, source_type if source_type in allowed_types else "unknown"),
            "text": corrections.get(element_id, str(item.get("text", ""))),
            "page": item.get("page"),
        })
    source_text = "\n".join(str(item.get("text", "")) for item in source_elements)
    normalized_text = "\n".join(item["text"] for item in normalized)
    if len(normalized_text) > max(
        len(source_text) * QWEN_MAX_EXPANSION_RATIO,
        len(source_text) + QWEN_MAX_EXPANSION_CHARS,
    ):
        raise ValueError("Qwen output dài bất thường so với raw input; từ chối kết quả mở rộng tài liệu")
    source_tokens = {
        _fold_ocr_token(token)
        for token in re.findall(r"[\wÀ-ỹ]+", source_text.casefold())
    }
    normalized_tokens = re.findall(r"[\wÀ-ỹ]+", normalized_text.casefold())
    if normalized_tokens:
        novel_ratio = sum(
            not _is_source_like(token, source_tokens) for token in normalized_tokens
        ) / len(normalized_tokens)
        if novel_ratio > QWEN_MAX_NOVEL_TOKEN_RATIO:
            raise ValueError("Qwen output chứa quá nhiều nội dung không có trong raw input")
    return {
        "title": value.get("title"),
        "sections": value["sections"],
        "elements": normalized,
        "warnings": [str(item) for item in value["warnings"]],
    }


def _normalize_window(clean_text: str, source_elements: list[dict]) -> tuple[dict | None, str | None]:
    """Normalize one bounded source window."""
    selected_elements = []
    element_chars = 0
    for item in source_elements:
        compact = {
            "element_id": item.get("element_id"),
            "text": item.get("text", ""),
            "page": item.get("page"),
            "element_type": item.get("element_type"),
        }
        item_chars = len(json.dumps(compact, ensure_ascii=False))
        if element_chars + item_chars > QWEN_MAX_INPUT_CHARS:
            break
        selected_elements.append(compact)
        element_chars += item_chars
    payload = {
        "document": {
            "text": clean_text[:QWEN_MAX_INPUT_CHARS],
            "truncated": len(clean_text) > QWEN_MAX_INPUT_CHARS,
            "elements": selected_elements,
            "elements_truncated": len(selected_elements) < len(source_elements),
        }
    }
    request_payload = {
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": QWEN_NORMALIZATION_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        "temperature": QWEN_TEMPERATURE,
        "max_tokens": QWEN_MAX_OUTPUT_TOKENS,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    try:
        last_error = None
        for attempt in range(QWEN_MAX_RETRIES):
            request_body = json.dumps(request_payload).encode("utf-8")
            request = Request(f"{QWEN_BASE_URL}/chat/completions", data=request_body, headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=QWEN_TIMEOUT_SECONDS) as response:
                result = json.loads(response.read().decode("utf-8"))
            choice = result["choices"][0]
            content = choice["message"]["content"]
            finish_reason = choice.get("finish_reason")
            try:
                if finish_reason == "length":
                    raise ValueError("Qwen output bị cắt do chạm giới hạn output token")
                return _validate(_json_from_response(content), selected_elements), None
            except (ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < QWEN_MAX_RETRIES - 1:
                    request_payload["messages"].append({"role": "user", "content": "Your previous output was invalid JSON. Return the PATCH JSON object again. Keep corrections and types minimal; do not repeat unchanged elements."})
                    time.sleep(QWEN_RETRY_DELAY_SECONDS)
        raise ValueError(str(last_error))
    except HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
        except Exception:
            detail = str(exc)
        return None, f"Qwen semantic normalization failed: HTTP {exc.code}: {detail}"
    except (URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as exc:
        return None, f"Qwen semantic normalization failed: {exc}"


def normalize(clean_text: str, source_elements: list[dict]) -> tuple[dict | None, str | None]:
    """Normalize all source elements in bounded windows without dropping the tail."""
    if not source_elements:
        return None, "Qwen semantic normalization failed: không có source element"

    windows = []
    current = []
    current_chars = 0
    for item in source_elements:
        compact_size = len(json.dumps({
            "element_id": item.get("element_id"),
            "text": item.get("text", ""),
            "page": item.get("page"),
            "element_type": item.get("element_type"),
        }, ensure_ascii=False))
        if current and current_chars + compact_size > QWEN_MAX_INPUT_CHARS:
            windows.append(current)
            current = []
            current_chars = 0
        current.append(item)
        current_chars += compact_size
    if current:
        windows.append(current)

    merged_elements = []
    merged_sections = []
    warnings = []
    title = None
    print(f"Qwen normalization windows={len(windows)} elements={len(source_elements)} max_input_chars={QWEN_MAX_INPUT_CHARS}", flush=True)
    for index, window in enumerate(windows, start=1):
        window_text = "\n\n".join(str(item.get("text", "")) for item in window)
        print(f"Qwen batch {index}/{len(windows)} start elements={len(window)} chars={len(window_text)}", flush=True)
        result, error = _normalize_window(window_text, window)
        if error or not result:
            print(f"Qwen batch {index}/{len(windows)} failed: {error}", flush=True)
            return None, error or "Qwen semantic normalization failed: empty result"
        print(f"Qwen batch {index}/{len(windows)} done output_elements={len(result.get('elements', []))}", flush=True)
        title = title or result.get("title")
        merged_elements.extend(result.get("elements", []))
        merged_sections.extend(result.get("sections", []))
        warnings.extend(result.get("warnings", []))

    # Restore source order even if a model reorders elements inside a window.
    order = {str(item.get("element_id")): index for index, item in enumerate(source_elements)}
    merged_elements.sort(key=lambda item: order.get(str(item.get("element_id")), 10**9))
    return {
        "title": title,
        "sections": merged_sections,
        "elements": merged_elements,
        "warnings": warnings,
    }, None
