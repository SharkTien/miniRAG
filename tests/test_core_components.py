import unittest

from app.ingestion.extract_service import ExtractService
from app.ingestion.normalize_service import NormalizeService


class CoreComponentTests(unittest.TestCase):
    def test_clean_text_normalizes_whitespace_and_control_chars(self):
        cleaned = NormalizeService.clean_text("  A\x00  B\n\n\n C  ")
        self.assertEqual(cleaned, "A B\n\nC")

    def test_semantic_chunking_preserves_section_and_page_range(self):
        chunks = NormalizeService().chunk_elements(
            [
                {"element_id": "h", "text": "Section", "page": 2, "element_type": "section_header"},
                {"element_id": "p", "text": "A useful paragraph with enough context.", "page": 2, "element_type": "paragraph"},
            ],
            {"document_id": "doc-1", "filename": "policy.pdf"},
        )
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["metadata"]["document_id"], "doc-1")
        self.assertEqual(chunks[0]["metadata"]["page_start"], 2)
        self.assertEqual(chunks[0]["metadata"]["page_end"], 2)
        self.assertEqual(chunks[0]["metadata"]["section"], "Section")

    def test_docling_bbox_metadata_is_normalized(self):
        images = ExtractService._extract_image_bboxes(
            {
                "pictures": [
                    {"self_ref": "#/pictures/0", "label": "picture", "prov": [
                        {"page_no": 3, "bbox": {"l": 1, "b": 2, "r": 10, "t": 20, "coord_origin": "BOTTOMLEFT"}}
                    ]}
                ]
            }
        )
        self.assertEqual(images[0]["page_no"], 3)
        self.assertEqual(images[0]["bbox"]["right"], 10)
        self.assertEqual(images[0]["coord_origin"], "BOTTOMLEFT")


if __name__ == "__main__":
    unittest.main()
