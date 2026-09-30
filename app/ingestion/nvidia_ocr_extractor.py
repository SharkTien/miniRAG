"""OCR adapter for the NVIDIA NeMo Retriever OCR endpoint.

The hosted NVIDIA endpoint accepts base64 encoded PNG/JPEG data URLs and
returns paragraph detections with normalized bounding boxes and confidence
scores.  This adapter converts that response to the element contract used by
the ingestion and chunking pipeline.
"""

from __future__ import annotations

import base64
import concurrent.futures
import io
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image

from app.config.settings import (
    NGC_API_KEY,
    NVIDIA_OCR_BASE_URL,
    NVIDIA_OCR_BATCH_SIZE,
    NVIDIA_OCR_CONCURRENCY,
    NVIDIA_OCR_MODEL,
    NVIDIA_OCR_TIMEOUT_SECONDS,
    LOCAL_OCR_DPI,
)
from app.ingestion.normalize_service import NormalizeService


class NvidiaOcrExtractor:
    """Extract text and layout evidence through NVIDIA Nemotron OCR v2."""

    def __init__(
        self,
        base_url: str = NVIDIA_OCR_BASE_URL,
        api_key: str = NGC_API_KEY,
        timeout: int = NVIDIA_OCR_TIMEOUT_SECONDS,
        dpi: int = LOCAL_OCR_DPI,
        batch_size: int = NVIDIA_OCR_BATCH_SIZE,
        concurrency: int = NVIDIA_OCR_CONCURRENCY,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = (api_key or "").strip()
        self.timeout = max(10, timeout)
        self.dpi = max(96, min(dpi, 300))
        self.batch_size = max(1, batch_size)
        self.concurrency = max(1, concurrency)

    @staticmethod
    def _encode_image(image: Image.Image) -> str:
        """Return a compact JPEG data URL accepted by the OCR NIM."""
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=92, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"

    def _render(self, file_path: str) -> list[tuple[Image.Image, float, float]]:
        """Render a PDF or load one image while preserving page dimensions."""
        suffix = Path(file_path).suffix.lower()
        if suffix == ".pdf":
            import pypdfium2 as pdfium

            document = pdfium.PdfDocument(file_path)
            rendered: list[tuple[Image.Image, float, float]] = []
            scale = self.dpi / 72.0
            try:
                for page in document:
                    width, height = page.get_size()
                    image = page.render(scale=scale, rev_byteorder=True).to_pil().convert("RGB")
                    rendered.append((image, float(width), float(height)))
            finally:
                document.close()
            return rendered

        with Image.open(file_path) as source:
            image = source.convert("RGB")
        return [(image, float(image.width), float(image.height))]

    def _endpoint(self) -> str:
        """Resolve hosted and self-hosted URL formats to a POST endpoint."""
        if self.base_url.endswith("/v1/ocr") or "/v1/cv/" in self.base_url:
            return self.base_url
        return f"{self.base_url}/v1/ocr"

    def _request(self, images: list[Image.Image]) -> list[dict]:
        if not self.api_key:
            raise RuntimeError(
                "NVIDIA OCR requires NVIDIA_API_KEY or NGC_API_KEY; "
                "set the key in .env before uploading a scanned document"
            )
        payload = {
            "input": [
                {"type": "image_url", "url": self._encode_image(image)}
                for image in images
            ],
            "merge_levels": ["paragraph"] * len(images),
        }
        request = Request(
            self._endpoint(),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        for attempt in range(3):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    result = json.loads(response.read().decode("utf-8"))
                break
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:800]
                if exc.code in {429, 503, 504} and attempt < 2:
                    retry_after = exc.headers.get("Retry-After")
                    try:
                        delay = max(1.0, min(float(retry_after), 15.0))
                    except (TypeError, ValueError):
                        delay = float(2 ** attempt)
                    time.sleep(delay)
                    continue
                raise RuntimeError(f"NVIDIA OCR HTTP {exc.code}: {detail}") from exc
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt < 2:
                    time.sleep(float(2 ** attempt))
                    continue
                raise RuntimeError(f"NVIDIA OCR unavailable: {exc}") from exc
        else:
            raise RuntimeError("NVIDIA OCR request retries exhausted")
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, list) or len(data) != len(images):
            raise RuntimeError("NVIDIA OCR returned an invalid page result")
        return data

    @staticmethod
    def _detections(page_result: dict, page_width: float, page_height: float) -> list[dict]:
        """Convert normalized OCR detections to sorted page paragraphs."""
        lines: list[dict] = []
        for detection in page_result.get("text_detections") or []:
            prediction = detection.get("text_prediction") or {}
            text = NormalizeService.clean_text(str(prediction.get("text") or ""))
            points = (detection.get("bounding_box") or {}).get("points") or []
            if not text or len(points) < 2:
                continue
            xs = [float(point.get("x", 0.0)) for point in points]
            ys = [float(point.get("y", 0.0)) for point in points]
            confidence = prediction.get("confidence")
            try:
                confidence = max(0.0, min(1.0, float(confidence)))
            except (TypeError, ValueError):
                confidence = None
            lines.append(
                {
                    "text": text,
                    "bbox": {
                        "left": min(xs) * page_width,
                        "top": min(ys) * page_height,
                        "right": max(xs) * page_width,
                        "bottom": max(ys) * page_height,
                    },
                    "confidence": confidence,
                }
            )
        return sorted(lines, key=lambda item: (item["bbox"]["top"], item["bbox"]["left"]))

    def extract(self, file_path: str, filename: str | None = None) -> dict:
        """Run NVIDIA OCR and return the common ingestion extraction contract."""
        pages = self._render(file_path)
        batches = [
            pages[start : start + self.batch_size]
            for start in range(0, len(pages), self.batch_size)
        ]
        # Send bounded batches concurrently, then restore the original page
        # order before building provenance and chunks.
        batch_results: list[list[dict] | None] = [None] * len(batches)
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(self.concurrency, max(1, len(batches)))
        ) as executor:
            futures = {
                executor.submit(self._request, [item[0] for item in batch]): index
                for index, batch in enumerate(batches)
            }
            for future in concurrent.futures.as_completed(futures):
                batch_results[futures[future]] = future.result()
        api_results = [
            page_result
            for batch_result in batch_results
            if batch_result is not None
            for page_result in batch_result
        ]

        elements: list[dict] = []
        ocr_bboxes: list[dict] = []
        docling_texts: list[dict] = []
        scores: list[float] = []
        for page_index, (page_result, page_info) in enumerate(zip(api_results, pages), start=1):
            _, page_width, page_height = page_info
            for line_index, line in enumerate(
                self._detections(page_result, page_width, page_height), start=1
            ):
                element_id = f"nvidia_ocr_p{page_index:04d}_l{line_index:04d}"
                box = line["bbox"]
                score = line["confidence"]
                if score is not None:
                    scores.append(score)
                elements.append(
                    {
                        "element_id": element_id,
                        "element_type": "paragraph",
                        "type": "paragraph",
                        "text": line["text"],
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
                                    "l": box["left"],
                                    "t": box["top"],
                                    "r": box["right"],
                                    "b": box["bottom"],
                                    "coord_origin": "TOPLEFT",
                                },
                            }
                        ],
                    }
                )

        if not elements:
            raise RuntimeError("NVIDIA OCR did not recognize any text")
        return {
            "clean_text": "\n".join(item["text"] for item in elements),
            "normalized_elements": elements,
            "ocr_bboxes": ocr_bboxes,
            "image_bboxes": [],
            "doc_json": {
                "source": "nvidia_nemotron_ocr_v2",
                "model": NVIDIA_OCR_MODEL,
                "filename": filename or Path(file_path).name,
                "texts": docling_texts,
                "pages": len(pages),
            },
            "page_count": len(pages),
            "confidence": sum(scores) / len(scores) if scores else None,
        }
