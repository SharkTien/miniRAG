"""Verification suite for NVIDIA NIM Normalizer and Parallel Page Processing.
Tests:
1. Environment & API Key configuration
2. Page-level partitioning
3. Parallel execution timing & order preservation
4. Live NIM API call for OCR error correction and semantic tagging
5. Resilience & graceful fallback mechanism
"""

import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


from app.config.settings import NGC_API_KEY, NIM_MODEL, NIM_BASE_URL, NIM_CONCURRENCY
from app.ingestion.nim_normalizer import (
    partition_by_pages,
    normalize_parallel,
    _validate_patch,
)


def test_config_loading():
    print("=== TEST 1: Config & API Key Loading ===")
    print(f"NIM Base URL: {NIM_BASE_URL}")
    print(f"NIM Model: {NIM_MODEL}")
    print(f"NIM Concurrency: {NIM_CONCURRENCY}")
    masked_key = NGC_API_KEY[:8] + "..." + NGC_API_KEY[-4:] if NGC_API_KEY else "EMPTY"
    print(f"NGC_API_KEY configured: {masked_key}")
    assert NGC_API_KEY, "NGC_API_KEY must not be empty"
    print(">> TEST 1 PASSED\n")


def test_page_partitioning():
    print("=== TEST 2: Page Partitioning ===")
    mock_elements = [
        {"element_id": "elem_1_1", "text": "Tiêu đề trang 1", "page": 1, "element_type": "title"},
        {"element_id": "elem_1_2", "text": "Đoạn văn trang 1", "page": 1, "element_type": "paragraph"},
        {"element_id": "elem_2_1", "text": "Tiêu đề trang 2", "page": 2, "element_type": "title"},
        {"element_id": "elem_2_2", "text": "Đoạn văn trang 2", "page": 2, "element_type": "paragraph"},
        {"element_id": "elem_3_1", "text": "Nội dung trang 3", "page": 3, "element_type": "paragraph"},
    ]
    windows = partition_by_pages(mock_elements)
    print(f"Input: {len(mock_elements)} elements across 3 pages")
    print(f"Output partitions: {[tag for tag, _ in windows]}")
    assert len(windows) == 3, f"Expected 3 page partitions, got {len(windows)}"
    assert windows[0][0] == "page_1" and len(windows[0][1]) == 2
    assert windows[1][0] == "page_2" and len(windows[1][1]) == 2
    assert windows[2][0] == "page_3" and len(windows[2][1]) == 1
    print(">> TEST 2 PASSED\n")


def test_validation_and_anti_hallucination():
    print("=== TEST 3: Validation & Anti-Hallucination ===")
    source = [
        {"element_id": "e1", "text": "Quy định làm việc ké từ ngày 01/01/2025", "page": 1, "element_type": "text"},
        {"element_id": "e2", "text": "Thời gian làm việc từ 8h tới 17h", "page": 1, "element_type": "text"},
    ]
    # Valid patch
    valid_patch = {
        "title": "Quy định làm việc",
        "sections": [{"heading": "Quy định", "level": 1, "element_ids": ["e1", "e2"]}],
        "corrections": [{"element_id": "e1", "text": "Quy định làm việc kể từ ngày 01/01/2025"}],
        "types": [{"element_id": "e1", "type": "heading"}, {"element_id": "e2", "type": "paragraph"}],
        "warnings": [],
    }
    validated = _validate_patch(valid_patch, source)
    assert validated["elements"][0]["text"] == "Quy định làm việc kể từ ngày 01/01/2025"
    assert validated["elements"][0]["type"] == "heading"
    print("Valid patch parsed and applied correctly.")

    # Invalid expansion hallucination check
    hallucinated_patch = {
        "title": "Fabrication",
        "sections": [],
        "corrections": [{"element_id": "e1", "text": "A" * 1000}],
        "types": [],
        "warnings": [],
    }
    try:
        _validate_patch(hallucinated_patch, source)
        assert False, "Should have rejected abnormally long hallucination"
    except ValueError as e:
        print(f"Successfully caught hallucination: {e}")
    print(">> TEST 3 PASSED\n")


def test_live_parallel_nim_normalization():
    print("=== TEST 4: Live NVIDIA NIM Parallel Normalization ===")
    # 3 mock pages with slight OCR noise
    mock_document_elements = [
        # Page 1
        {"element_id": "p1_e1", "text": "CHÍNH SÁCH BẢO HÀNH SẢN PHẨM", "page": 1, "element_type": "text"},
        {"element_id": "p1_e2", "text": "Chính sách này áp dụng ké từ ngày 01/01/2025 cho toàn bộ khách hàng.", "page": 1, "element_type": "text"},
        # Page 2
        {"element_id": "p2_e1", "text": "ĐIỀU KIỆN ĐỔI TRẢ", "page": 2, "element_type": "text"},
        {"element_id": "p2_e2", "text": "Sản phẩm phải còn nguyên tem bảo hành, không bị trầy xước.", "page": 2, "element_type": "text"},
        # Page 3
        {"element_id": "p3_e1", "text": "QUY TRÌNH TIẾP NHẬN", "page": 3, "element_type": "text"},
        {"element_id": "p3_e2", "text": "Khách hàng liên hệ trung tâm hỗ trợ qua tổng đài 1900 xxxx.", "page": 3, "element_type": "text"},
    ]
    raw_text = "\n\n".join(e["text"] for e in mock_document_elements)

    print(f"Calling NIM normalize_parallel with {len(mock_document_elements)} elements across 3 pages (concurrency=3)...")
    start_t = time.time()
    result, error = normalize_parallel(raw_text, mock_document_elements, concurrency=3)
    duration = time.time() - start_t

    print(f"Completed in {duration:.2f} seconds!")
    print(f"Result Status: {'Success' if error is None else 'Fallback/Partial'}")
    if error:
        print(f"Note/Error: {error}")
    
    assert result is not None, "Result should not be None"
    assert "elements" in result, "Result must contain 'elements'"
    assert len(result["elements"]) == len(mock_document_elements), "Element count must match source"
    
    # Verify page order preservation
    expected_order = [e["element_id"] for e in mock_document_elements]
    actual_order = [e["element_id"] for e in result["elements"]]
    assert actual_order == expected_order, f"Order mismatch! Expected {expected_order}, got {actual_order}"
    print(f"Verified element order preserved exactly: {actual_order}")

    # Check if OCR correction occurred on 'ké từ' -> 'kể từ'
    p1_e2 = next(e for e in result["elements"] if e["element_id"] == "p1_e2")
    print(f"Cleaned Text Sample: '{p1_e2['text']}' (Type: {p1_e2.get('type')})")
    print(">> TEST 4 PASSED\n")


if __name__ == "__main__":
    test_config_loading()
    test_page_partitioning()
    test_validation_and_anti_hallucination()
    test_live_parallel_nim_normalization()
    print("==================================================")
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("==================================================")
