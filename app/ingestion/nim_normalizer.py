"""Semantic document normalization and OCR post-processing via NVIDIA NIM API.

Follows principles from ``docs/design_rules.md`` and ``docs/architecture.md``:
- Rule 1: Clear Prompt Boundaries (System instructions != Contract != Source data)
- Rule 2: Token Budget & Context Rot avoidance via page-bounded processing
- Rule 5 & 6: Schema Contract validation, untrusted input sanitation, hallucination defense
- Rule 10: Failure mode handling (FM-004 Timeout, FM-005 Rate limit HTTP 429 retry with backoff, Graceful Fallback)
- Performance: Concurrent per-page processing via ThreadPoolExecutor
"""

import concurrent.futures
import json
import logging
import random
import re
import time
import unicodedata
from difflib import SequenceMatcher
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config.settings import (
    NGC_API_KEY,
    NIM_BASE_URL,
    NIM_MODEL,
    NIM_CONCURRENCY,
    NIM_TIMEOUT_SECONDS,
    NIM_REQUEST_TIMEOUT_SECONDS,
    NIM_MAX_RETRIES,
    NIM_NORMALIZATION_DEADLINE_SECONDS,
    NIM_MAX_INPUT_CHARS,
)
from app.config.prompts import NIM_NORMALIZATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

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
    return any(
        abs(len(folded) - len(source)) <= 2
        and SequenceMatcher(None, folded, source).ratio() >= 0.72
        for source in source_tokens
    )


def _clean_json_response(content: str) -> dict:
    """Extract and parse JSON safely from LLM output."""
    content = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
    if fenced:
        content = fenced.group(1).strip()
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("NIM output did not contain a valid JSON object")
    json_text = content[start:end + 1]
    try:
        value = json.loads(json_text)
    except json.JSONDecodeError:
        # Common LLM format glitch: missing comma between objects or fields
        repaired = re.sub(r"}\s*\n\s*{", "},\n{", json_text)
        repaired = re.sub(r'([}\]])\s*\n(\s*)"([A-Za-z_][A-Za-z0-9_]*)"\s*:', r'\1,\n\2"\3":', repaired)
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        value = json.loads(repaired)
    if not isinstance(value, dict):
        raise ValueError("NIM output is not a JSON dictionary")
    return value


def _validate_patch(value: dict, source_elements: list[dict]) -> dict:
    """Validate JSON output schema and guard against hallucination (Rule 5 & 6)."""
    required_keys = {"sections", "corrections", "types", "warnings"}
    if not required_keys.issubset(value.keys()):
        raise ValueError(f"Missing required keys in NIM response: {required_keys - set(value.keys())}")
    
    source_ids = {str(item.get("element_id")) for item in source_elements}
    
    corrections = {
        str(item.get("element_id")): str(item.get("text", ""))
        for item in value.get("corrections", [])
        if isinstance(item, dict) and str(item.get("element_id")) in source_ids
    }
    
    allowed_types = {"title", "heading", "paragraph", "list", "table", "caption", "footer", "unknown"}
    type_updates = {
        str(item.get("element_id")): item.get("type")
        for item in value.get("types", [])
        if isinstance(item, dict)
        and str(item.get("element_id")) in source_ids
        and item.get("type") in allowed_types
    }
    
    normalized = []
    for item in source_elements:
        eid = str(item.get("element_id"))
        source_type = item.get("element_type", "unknown")
        assigned_type = type_updates.get(eid, source_type if source_type in allowed_types else "unknown")
        cleaned_text = corrections.get(eid, str(item.get("text", "")))
        normalized.append({
            "element_id": eid,
            "type": assigned_type,
            "text": cleaned_text,
            "page": item.get("page"),
            "bbox": item.get("bbox"),
        })
        
    # Anti-hallucination check 1: Length ratio check
    source_text = "\n".join(str(item.get("text", "")) for item in source_elements)
    normalized_text = "\n".join(item["text"] for item in normalized)
    if len(normalized_text) > max(len(source_text) * 1.25, len(source_text) + 250):
        raise ValueError("NIM output length is abnormally larger than source text; rejecting hallucinated expansion")
        
    # Anti-hallucination check 2: Novel token ratio check
    source_tokens = {
        _fold_ocr_token(token)
        for token in re.findall(r"[\wÀ-ỹ]+", source_text.casefold())
    }
    normalized_tokens = re.findall(r"[\wÀ-ỹ]+", normalized_text.casefold())
    if normalized_tokens:
        novel_ratio = sum(
            not _is_source_like(token, source_tokens) for token in normalized_tokens
        ) / len(normalized_tokens)
        if novel_ratio > 0.35:
            raise ValueError(f"NIM output contains {novel_ratio:.1%} novel tokens not present in source text")
            
    return {
        "title": value.get("title"),
        "sections": value.get("sections", []),
        "elements": normalized,
        "warnings": [str(w) for w in value.get("warnings", [])],
    }


def _call_nim_api(
    payload_dict: dict,
    max_retries: int = NIM_MAX_RETRIES,
) -> tuple[dict | None, str | None]:
    """Execute HTTP call to NVIDIA NIM API with backoff on rate-limits/network errors (Rule 10)."""
    api_key = NGC_API_KEY
    if not api_key:
        return None, "NGC_API_KEY / NVIDIA_API_KEY is not configured in .env"
        
    endpoint = f"{NIM_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "NTC-MiniRAG-Normalizer/1.0",
    }
    
    body = json.dumps(payload_dict, ensure_ascii=False).encode("utf-8")
    
    delay = 1.5
    last_error = None
    
    for attempt in range(1, max_retries + 1):
        req = Request(endpoint, data=body, headers=headers, method="POST")
        try:
            # Use a short, explicit socket timeout for this enrichment call.
            # NIM_TIMEOUT_SECONDS is kept for backwards compatibility, but a
            # slow normalizer must not block the document worker indefinitely.
            request_timeout = min(NIM_TIMEOUT_SECONDS, NIM_REQUEST_TIMEOUT_SECONDS)
            with urlopen(req, timeout=request_timeout) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
            choice = resp_data["choices"][0]
            content = choice["message"]["content"]
            if choice.get("finish_reason") == "length":
                raise ValueError("NIM output truncated due to max_tokens limit")
            return _clean_json_response(content), None
        except HTTPError as exc:
            # Handle rate limit (429) and transient server errors (500, 502, 503, 504)
            status = exc.code
            try:
                err_detail = exc.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                err_detail = str(exc)
                
            last_error = f"HTTP {status}: {err_detail}"
            if status in (429, 500, 502, 503, 504) and attempt < max_retries:
                sleep_time = delay + random.uniform(0.2, 0.8)
                print(f"[NIM Normalizer] Rate limit/transient error ({status}). Retrying in {sleep_time:.2f}s (attempt {attempt}/{max_retries})...", flush=True)
                time.sleep(sleep_time)
                delay *= 2.0
                continue
            return None, last_error
        except (URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            if attempt < max_retries:
                time.sleep(delay)
                delay *= 1.5
                continue
            return None, last_error
            
    return None, last_error or "Exceeded maximum retry attempts"


def _normalize_single_page_window(
    page_identifier: str,
    page_text: str,
    source_elements: list[dict],
) -> tuple[dict, str | None]:
    """Process elements belonging to one page window.
    
    Returns:
        (result_dict, error_message_or_None)
        If an error occurs, returns a safe fallback dictionary built from source_elements.
    """
    selected_elements = [
        {
            "element_id": item.get("element_id"),
            "text": item.get("text", ""),
            "page": item.get("page"),
            "element_type": item.get("element_type", "text"),
        }
        for item in source_elements
    ]
    
    # Prompt boundary structuring (Rule 1)
    prompt_payload = {
        "page_id": page_identifier,
        "page_text": page_text[:NIM_MAX_INPUT_CHARS],
        "elements": selected_elements,
    }
    
    request_payload = {
        "model": NIM_MODEL,
        "messages": [
            {"role": "system", "content": NIM_NORMALIZATION_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)},
        ],
        "temperature": 0.1,
        # The normalizer returns a minimal patch, not a copy of the page.
        # Keeping this bounded prevents a large OCR page from waiting for a
        # long, truncated JSON response.
        "max_tokens": 2048,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    
    raw_json, error = _call_nim_api(request_payload)
    if error or not raw_json:
        # Fallback to source elements as rule-based fallback
        fallback_elements = [
            {
                "element_id": str(item.get("element_id")),
                "type": item.get("element_type", "text"),
                "text": str(item.get("text", "")),
                "page": item.get("page"),
                "bbox": item.get("bbox"),
            }
            for item in source_elements
        ]
        return {
            "title": None,
            "sections": [],
            "elements": fallback_elements,
            "warnings": [f"Page {page_identifier} fallback due to: {error}"],
        }, error

    try:
        validated = _validate_patch(raw_json, source_elements)
        return validated, None
    except Exception as val_err:
        # Fallback on validation error
        fallback_elements = [
            {
                "element_id": str(item.get("element_id")),
                "type": item.get("element_type", "text"),
                "text": str(item.get("text", "")),
                "page": item.get("page"),
                "bbox": item.get("bbox"),
            }
            for item in source_elements
        ]
        return {
            "title": None,
            "sections": [],
            "elements": fallback_elements,
            "warnings": [f"Page {page_identifier} validation fallback: {val_err}"],
        }, str(val_err)


def partition_by_pages(source_elements: list[dict], max_chars_per_window: int = NIM_MAX_INPUT_CHARS) -> list[tuple[str, list[dict]]]:
    """Group elements by page number. If a single page exceeds max_chars, subdivide it."""
    pages_map: dict[str, list[dict]] = {}
    for item in source_elements:
        page_val = item.get("page")
        key = f"page_{page_val}" if page_val is not None else "page_unknown"
        pages_map.setdefault(key, []).append(item)
        
    windows: list[tuple[str, list[dict]]] = []
    for page_key, elements in pages_map.items():
        # Check size of elements on this page
        current_chunk = []
        current_chars = 0
        sub_index = 1
        for elem in elements:
            elem_len = len(str(elem.get("text", "")))
            if current_chunk and (current_chars + elem_len > max_chars_per_window):
                windows.append((f"{page_key}_part{sub_index}", current_chunk))
                sub_index += 1
                current_chunk = []
                current_chars = 0
            current_chunk.append(elem)
            current_chars += elem_len
        if current_chunk:
            tag = f"{page_key}_part{sub_index}" if sub_index > 1 else page_key
            windows.append((tag, current_chunk))
            
    return windows


def normalize_parallel(
    clean_text: str,
    source_elements: list[dict],
    concurrency: int = NIM_CONCURRENCY,
    progress_callback = None,
) -> tuple[dict | None, str | None]:
    """Normalize all document elements in parallel across pages using NVIDIA NIM.
    
    Guarantees:
    - Parallel execution via ThreadPoolExecutor(max_workers=concurrency).
    - Preserves original element sequence and document page order.
    - Rate limit protection and graceful fallback on failures.
    """
    if not source_elements:
        return None, "NIM normalizer: Không có source elements"
        
    # Check if API key exists; if not, return early fallback
    if not NGC_API_KEY:
        print("[NIM Normalizer] Cảnh báo: NGC_API_KEY chưa cấu hình. Fallback về Rule-based cleaning.", flush=True)
        fallback_elements = [
            {
                "element_id": str(item.get("element_id")),
                "type": item.get("element_type", "text"),
                "text": str(item.get("text", "")),
                "page": item.get("page"),
                "bbox": item.get("bbox"),
            }
            for item in source_elements
        ]
        return {
            "title": None,
            "sections": [],
            "elements": fallback_elements,
            "warnings": ["NGC_API_KEY is not set; used rule-based fallback"],
        }, "NGC_API_KEY not configured"

    page_windows = partition_by_pages(source_elements)
    total_pages = len(page_windows)
    actual_concurrency = max(1, min(concurrency, total_pages))
    
    print(
        f"[NIM Normalizer] Starting parallel normalization: {total_pages} page windows, "
        f"{len(source_elements)} elements, concurrency={actual_concurrency}, model={NIM_MODEL}",
        flush=True,
    )
    
    start_time = time.time()
    results_indexed: dict[int, dict] = {}
    errors_recorded: list[str] = []
    completed_windows = 0
    
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=actual_concurrency)
    future_to_index = {}
    try:
        for idx, (page_tag, window_elements) in enumerate(page_windows):
            window_text = "\n\n".join(str(item.get("text", "")) for item in window_elements)
            print(f"[NIM Normalizer] Dispatching window {idx + 1}/{total_pages} ({page_tag}, {len(window_elements)} elements)...", flush=True)
            future = executor.submit(
                _normalize_single_page_window,
                page_tag,
                window_text,
                window_elements,
            )
            future_to_index[future] = (idx, page_tag)

        done, pending = concurrent.futures.wait(
            future_to_index,
            timeout=NIM_NORMALIZATION_DEADLINE_SECONDS,
        )

        def fallback_for(idx: int, warning: str) -> dict:
            return {
                "title": None,
                "sections": [],
                "elements": [
                    {
                        "element_id": str(item.get("element_id")),
                        "type": item.get("element_type", "text"),
                        "text": str(item.get("text", "")),
                        "page": item.get("page"),
                        "bbox": item.get("bbox"),
                    }
                    for item in page_windows[idx][1]
                ],
                "warnings": [warning],
            }

        for future in done:
            idx, page_tag = future_to_index[future]
            completed_windows += 1
            try:
                res_dict, err = future.result()
                results_indexed[idx] = res_dict
                if err:
                    errors_recorded.append(f"[{page_tag}] {err}")
                    print(f"[NIM Normalizer] Window {page_tag} completed with fallback: {err}", flush=True)
                else:
                    print(f"[NIM Normalizer] Window {page_tag} finished successfully ({completed_windows}/{total_pages})", flush=True)
            except Exception as exc:
                errors_recorded.append(f"[{page_tag}] Exception: {exc}")
                results_indexed[idx] = fallback_for(idx, str(exc))
                print(f"[NIM Normalizer] Window {page_tag} exception: {exc}", flush=True)
            if progress_callback:
                try:
                    progress_callback(completed_windows, total_pages)
                except Exception as cb_err:
                    print(f"[NIM Normalizer] Callback error: {cb_err}", flush=True)

        if pending:
            timeout_message = (
                f"NIM normalization deadline exceeded ({NIM_NORMALIZATION_DEADLINE_SECONDS}s)"
            )
            print(
                f"[NIM Normalizer] {len(pending)} window(s) exceeded deadline; "
                "using OCR text fallback.",
                flush=True,
            )
            for future in pending:
                idx, page_tag = future_to_index[future]
                future.cancel()
                results_indexed[idx] = fallback_for(idx, timeout_message)
                errors_recorded.append(f"[{page_tag}] {timeout_message}")
                completed_windows += 1
                if progress_callback:
                    try:
                        progress_callback(completed_windows, total_pages)
                    except Exception as cb_err:
                        print(f"[NIM Normalizer] Callback error: {cb_err}", flush=True)
    finally:
        # Do not wait for a stuck network thread after the deadline. The
        # request itself has a bounded socket timeout and will exit shortly;
        # ingestion can continue with the deterministic OCR fallback now.
        executor.shutdown(wait=False, cancel_futures=True)
                
    elapsed = time.time() - start_time
    print(f"[NIM Normalizer] Completed {total_pages} page windows in {elapsed:.2f}s (parallel speedup achieved)", flush=True)
    
    # Assemble in original page order
    merged_elements = []
    merged_sections = []
    all_warnings = []
    overall_title = None
    
    for idx in range(total_pages):
        res = results_indexed.get(idx, {})
        if not overall_title and res.get("title"):
            overall_title = res.get("title")
        merged_sections.extend(res.get("sections", []))
        merged_elements.extend(res.get("elements", []))
        all_warnings.extend(res.get("warnings", []))
        
    # Re-verify original sequence order by element_id
    order_map = {str(item.get("element_id")): i for i, item in enumerate(source_elements)}
    merged_elements.sort(key=lambda item: order_map.get(str(item.get("element_id")), 10**9))
    
    composite_error = "; ".join(errors_recorded) if errors_recorded else None
    
    return {
        "title": overall_title,
        "sections": merged_sections,
        "elements": merged_elements,
        "warnings": all_warnings,
        "elapsed_seconds": round(elapsed, 2),
        "parallel_windows": total_pages,
        "model": NIM_MODEL,
    }, composite_error
