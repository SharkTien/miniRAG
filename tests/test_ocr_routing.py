"""Offline regression tests for OCR correction/provider routing."""

import unittest
from unittest.mock import patch

from app.ingestion.extract_service import ExtractService
from app.ingestion.qwen_normalizer import _validate
from app.ingestion.semantic_normalizer import _providers


class OcrRoutingTests(unittest.TestCase):
    def test_native_pdf_fast_path_detection(self):
        class Page:
            def extract_text(self):
                return "Văn bản có lớp text. " * 10

        with patch("pypdf.PdfReader") as reader:
            reader.return_value.pages = [Page(), Page()]
            self.assertTrue(ExtractService._pdf_has_text("native.pdf"))
        self.assertFalse(ExtractService._pdf_has_text("image.png"))

    def test_vietnamese_diacritic_repair_is_not_hallucination(self):
        source = [
            {
                "element_id": "e1",
                "text": "Cng hòa xã hi ch nghĩa Vit Nam",
                "page": 1,
                "element_type": "paragraph",
            }
        ]
        patch = {
            "title": None,
            "sections": [],
            "corrections": [
                {
                    "element_id": "e1",
                    "text": "Cộng hòa xã hội chủ nghĩa Việt Nam",
                }
            ],
            "types": [],
            "warnings": [],
        }
        result = _validate(patch, source)
        self.assertEqual(
            result["elements"][0]["text"],
            "Cộng hòa xã hội chủ nghĩa Việt Nam",
        )

    def test_expansion_is_rejected(self):
        source = [{"element_id": "e1", "text": "Văn bản", "page": 1}]
        patch = {
            "title": None,
            "sections": [],
            "corrections": [{"element_id": "e1", "text": "Nội dung bịa đặt " * 100}],
            "types": [],
            "warnings": [],
        }
        with self.assertRaises(ValueError):
            _validate(patch, source)

    def test_semantic_patch_preserves_bbox_and_changes_chunk_boundary(self):
        source = [
            {
                "element_id": "e1",
                "text": "CHNG I",
                "element_type": "paragraph",
                "bbox": {"left": 1, "top": 2, "right": 3, "bottom": 4},
            }
        ]
        merged = ExtractService._merge_semantic_elements(
            source,
            [{"element_id": "e1", "text": "CHƯƠNG I", "type": "heading"}],
        )
        self.assertEqual(merged[0]["text"], "CHƯƠNG I")
        self.assertEqual(merged[0]["element_type"], "section_header")
        self.assertEqual(merged[0]["bbox"]["right"], 3)

    def test_explicit_provider_policies(self):
        self.assertEqual(_providers("none"), [])
        self.assertEqual(_providers("local"), ["local_qwen"])
        self.assertEqual(_providers("nvidia"), ["nvidia_nim"])


if __name__ == "__main__":
    unittest.main()
