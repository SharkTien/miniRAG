"""Fast page-parallel OCR using the local Tesseract CLI.

This bypasses Docling's layout pipeline for image-only PDFs.  It keeps word
geometry through TSV output and uses the Vietnamese language pack explicitly.
"""

from __future__ import annotations

import concurrent.futures
import csv
import io
import subprocess
from pathlib import Path

from PIL import Image

from app.config.settings import (
    DOCLING_OCR_LANG,
    DOCLING_TESSERACT_PSM,
    LOCAL_OCR_DPI,
    TESSERACT_PAGE_CONCURRENCY,
    TESSERACT_PAGE_TIMEOUT_SECONDS,
)
from app.ingestion.normalize_service import NormalizeService


class TesseractExtractor:
    """Provide the tesseractextractor application component."""
    def __init__(
        self,
        *,
        languages: list[str] = DOCLING_OCR_LANG,
        psm: int = DOCLING_TESSERACT_PSM,
        dpi: int = LOCAL_OCR_DPI,
        concurrency: int = TESSERACT_PAGE_CONCURRENCY,
        timeout: int = TESSERACT_PAGE_TIMEOUT_SECONDS,
    ) -> None:
        self.languages = "+".join(languages) or "vie+eng"
        self.psm = psm
        self.dpi = max(96, min(dpi, 300))
        self.concurrency = max(1, concurrency)
        self.timeout = timeout

    @staticmethod
    def _image_bytes(image: Image.Image) -> bytes:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG", optimize=False)
        return buffer.getvalue()

    def _ocr_page(self, page: tuple[int, Image.Image, float, float]) -> dict:
        page_index, image, page_width, page_height = page
        command = [
            "tesseract",
            "stdin",
            "stdout",
            "-l",
            self.languages,
            "--psm",
            str(self.psm),
            "-c",
            "preserve_interword_spaces=1",
            "tsv",
        ]
        completed = subprocess.run(
            command,
            input=self._image_bytes(image),
            capture_output=True,
            timeout=self.timeout,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Tesseract page {page_index} failed: {stderr}")

        rows = csv.DictReader(
            completed.stdout.decode("utf-8", errors="replace").splitlines(),
            delimiter="\t",
        )
        line_words: dict[tuple[str, str, str], list[dict]] = {}
        for row in rows:
            text = NormalizeService.clean_text(row.get("text", ""))
            if not text or row.get("level") != "5":
                continue
            key = (row.get("block_num", "0"), row.get("par_num", "0"), row.get("line_num", "0"))
            try:
                word = {
                    "text": text,
                    "left": int(row["left"]),
                    "top": int(row["top"]),
                    "width": int(row["width"]),
                    "height": int(row["height"]),
                    "confidence": float(row.get("conf", "-1")) / 100.0,
                }
            except (KeyError, TypeError, ValueError):
                continue
            line_words.setdefault(key, []).append(word)

        x_scale = page_width / max(image.width, 1)
        y_scale = page_height / max(image.height, 1)
        lines = []
        for words in line_words.values():
            words.sort(key=lambda word: word["left"])
            text = " ".join(word["text"] for word in words)
            left_px = min(word["left"] for word in words)
            top_px = min(word["top"] for word in words)
            right_px = max(word["left"] + word["width"] for word in words)
            bottom_px = max(word["top"] + word["height"] for word in words)
            valid_scores = [word["confidence"] for word in words if word["confidence"] >= 0]
            lines.append(
                {
                    "text": text,
                    "bbox": {
                        "left": left_px * x_scale,
                        "top": top_px * y_scale,
                        "right": right_px * x_scale,
                        "bottom": bottom_px * y_scale,
                    },
                    "confidence": sum(valid_scores) / len(valid_scores) if valid_scores else None,
                }
            )
        lines.sort(key=lambda line: (line["bbox"]["top"], line["bbox"]["left"]))
        return {"page": page_index, "lines": lines}

    def extract(self, file_path: str, filename: str | None = None) -> dict:
        """Run the extract operation."""
        suffix = Path(file_path).suffix.lower()
        results = []
        if suffix != ".pdf":
            with Image.open(file_path) as source:
                image = source.convert("RGB")
            page_count = 1
            results = [self._ocr_page((1, image, float(image.width), float(image.height)))]
        else:
            import pypdfium2 as pdfium

            document = pdfium.PdfDocument(file_path)
            page_count = len(document)
            scale = self.dpi / 72.0
            # Render/OCR bounded batches so a long PDF cannot retain every page
            # bitmap in memory at once.
            try:
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=min(self.concurrency, max(1, page_count))
                ) as executor:
                    for start in range(0, page_count, self.concurrency):
                        rendered = []
                        for page_offset in range(start, min(start + self.concurrency, page_count)):
                            page = document[page_offset]
                            width, height = page.get_size()
                            image = page.render(
                                scale=scale, rev_byteorder=True
                            ).to_pil().convert("RGB")
                            rendered.append(
                                (page_offset + 1, image, float(width), float(height))
                            )
                        results.extend(executor.map(self._ocr_page, rendered))
            finally:
                document.close()

        elements = []
        bboxes = []
        docling_texts = []
        scores = []
        for result in sorted(results, key=lambda item: item["page"]):
            page_index = result["page"]
            for line_index, line in enumerate(result["lines"], start=1):
                element_id = f"tesseract_p{page_index:04d}_l{line_index:04d}"
                box = line["bbox"]
                score = line["confidence"]
                if score is not None:
                    scores.append(score)
                element = {
                    "element_id": element_id,
                    "element_type": "paragraph",
                    "type": "paragraph",
                    "text": line["text"],
                    "page": page_index,
                    "bbox": box,
                    "coord_origin": "TOPLEFT",
                    "ocr_confidence": score,
                }
                elements.append(element)
                bboxes.append(
                    {
                        "id": element_id,
                        "page_no": page_index,
                        "text": line["text"],
                        "bbox": box,
                        "coord_origin": "TOPLEFT",
                        "confidence": score,
                    }
                )
                docling_texts.append(
                    {
                        "self_ref": element_id,
                        "label": "paragraph",
                        "text": line["text"],
                        "prov": [
                            {
                                "page_no": page_index,
                                "bbox": {
                                    "l": box["left"], "t": box["top"],
                                    "r": box["right"], "b": box["bottom"],
                                    "coord_origin": "TOPLEFT",
                                },
                            }
                        ],
                    }
                )

        if not elements:
            raise RuntimeError("Tesseract did not recognize any text")
        return {
            "clean_text": "\n".join(item["text"] for item in elements),
            "normalized_elements": elements,
            "ocr_bboxes": bboxes,
            "image_bboxes": [],
            "doc_json": {
                "source": "tesseract_direct",
                "filename": filename or Path(file_path).name,
                "texts": docling_texts,
                "pages": page_count,
            },
            "page_count": page_count,
            "confidence": sum(scores) / len(scores) if scores else None,
        }
