"""Adapter for the already-running Vietnamese PP-OCRv6 HTTP service.

The service accepts base64 images, so PDFs are rendered page-by-page locally.
Results are converted to the same element/bbox contract used by the rest of
the ingestion pipeline.  The adapter deliberately has no Paddle dependency.
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image

from app.config.settings import (
    LOCAL_OCR_BASE_URL,
    LOCAL_OCR_BATCH_SIZE,
    LOCAL_OCR_DPI,
    LOCAL_OCR_TIMEOUT_SECONDS,
)
from app.ingestion.normalize_service import NormalizeService


class PpOcrExtractor:
    """Provide the ppocrextractor application component."""
    def __init__(
        self,
        base_url: str = LOCAL_OCR_BASE_URL,
        timeout: int = LOCAL_OCR_TIMEOUT_SECONDS,
        dpi: int = LOCAL_OCR_DPI,
        batch_size: int = LOCAL_OCR_BATCH_SIZE,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.dpi = max(96, min(dpi, 300))
        self.batch_size = max(1, batch_size)

    def ready(self) -> bool:
        """Return whether the provider is ready."""
        request = Request(f"{self.base_url}/v1/health/ready", method="GET")
        try:
            with urlopen(request, timeout=min(self.timeout, 5)) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return response.status == 200 and bool(payload.get("ready"))
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            return False

    @staticmethod
    def _encode_image(image: Image.Image) -> str:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=92, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    def _render(self, file_path: str) -> list[tuple[Image.Image, float, float]]:
        suffix = Path(file_path).suffix.lower()
        if suffix == ".pdf":
            import pypdfium2 as pdfium

            document = pdfium.PdfDocument(file_path)
            rendered = []
            scale = self.dpi / 72.0
            try:
                for page in document:
                    width, height = page.get_size()
                    bitmap = page.render(scale=scale, rev_byteorder=True)
                    rendered.append((bitmap.to_pil().convert("RGB"), float(width), float(height)))
            finally:
                document.close()
            return rendered

        with Image.open(file_path) as source:
            image = source.convert("RGB")
        # Image coordinates have no PDF point space, so retain pixel dimensions.
        return [(image, float(image.width), float(image.height))]

    def _request(self, images: list[Image.Image]) -> list[dict]:
        payload = {"images": [self._encode_image(image) for image in images]}
        request = Request(
            f"{self.base_url}/v1/ocr",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"PP-OCRv6 HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"PP-OCRv6 unavailable: {exc}") from exc
        if not isinstance(result, list) or len(result) != len(images):
            raise RuntimeError("PP-OCRv6 returned an invalid page result")
        return result

    def extract(self, file_path: str, filename: str | None = None) -> dict:
        """Run the extract operation."""
        if not self.ready():
            raise RuntimeError(f"PP-OCRv6 is not ready at {self.base_url}")

        pages = self._render(file_path)
        api_results: list[dict] = []
        for start in range(0, len(pages), self.batch_size):
            batch = pages[start : start + self.batch_size]
            api_results.extend(self._request([item[0] for item in batch]))

        elements: list[dict] = []
        ocr_bboxes: list[dict] = []
        docling_texts: list[dict] = []
        scores: list[float] = []

        for page_index, (page_result, page_info) in enumerate(zip(api_results, pages), start=1):
            _, page_width, page_height = page_info
            lines = page_result.get("lines") or []
            # The official pipeline normally returns reading order already; this
            # stable sort protects against detector ordering changes.
            lines = sorted(
                lines,
                key=lambda line: (
                    (line.get("bbox") or [0, 0, 0, 0])[1],
                    (line.get("bbox") or [0, 0, 0, 0])[0],
                ),
            )
            for line_index, line in enumerate(lines, start=1):
                text = NormalizeService.clean_text(str(line.get("text", "")))
                bbox = line.get("bbox")
                if not text or not isinstance(bbox, list) or len(bbox) != 4:
                    continue
                left, top, right, bottom = (
                    float(bbox[0]) * page_width,
                    float(bbox[1]) * page_height,
                    float(bbox[2]) * page_width,
                    float(bbox[3]) * page_height,
                )
                element_id = f"ppocr_p{page_index:04d}_l{line_index:04d}"
                box = {"left": left, "top": top, "right": right, "bottom": bottom}
                score = line.get("score")
                if isinstance(score, (int, float)):
                    scores.append(float(score))
                elements.append(
                    {
                        "element_id": element_id,
                        "element_type": "paragraph",
                        "type": "paragraph",
                        "text": text,
                        "page": page_index,
                        "bbox": box,
                        "coord_origin": "TOPLEFT",
                        "ocr_confidence": score,
                    }
                )
                ocr_bboxes.append(
                    {
                        "id": element_id,
                        "page_no": page_index,
                        "text": text,
                        "bbox": box,
                        "coord_origin": "TOPLEFT",
                        "confidence": score,
                    }
                )
                docling_texts.append(
                    {
                        "self_ref": element_id,
                        "label": "paragraph",
                        "text": text,
                        "prov": [
                            {
                                "page_no": page_index,
                                "bbox": {
                                    "l": left,
                                    "t": top,
                                    "r": right,
                                    "b": bottom,
                                    "coord_origin": "TOPLEFT",
                                },
                            }
                        ],
                    }
                )

        clean_text = "\n".join(item["text"] for item in elements)
        confidence = sum(scores) / len(scores) if scores else None
        return {
            "clean_text": clean_text,
            "normalized_elements": elements,
            "ocr_bboxes": ocr_bboxes,
            "image_bboxes": [],
            "doc_json": {
                "source": "local_ppocrv6",
                "filename": filename or Path(file_path).name,
                "texts": docling_texts,
                "pages": len(pages),
            },
            "page_count": len(pages),
            "confidence": confidence,
        }
