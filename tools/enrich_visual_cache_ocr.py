"""Add region-level OCR text to the visual crop manifests.

The visual cache is intentionally kept separate from page text chunks.  Each
crop becomes a retrievable element later, so OCR must be computed on the crop
itself instead of being inherited from full-page OCR.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
try:
    import pytesseract
except ImportError:  # The container can use the tesseract CLI directly.
    pytesseract = None


ROOT = Path(os.environ.get("VISUAL_OUTPUT", Path(__file__).resolve().parent / "visual_cache"))


def ocr_region(path: Path) -> str:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return ""
    # Upscaling helps small axis labels and callouts. Keep the original too so
    # anti-aliased text is not lost by thresholding.
    image = cv2.resize(image, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    variants = [image]
    denoised = cv2.fastNlMeansDenoising(image, None, 7, 7, 21)
    variants.append(cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 11,
    ))
    texts = []
    for variant in variants:
        if shutil.which("tesseract"):
            # Avoid requiring the Python wrapper in the extraction container.
            temp_path = path.with_suffix(".ocr-input.png")
            cv2.imwrite(str(temp_path), variant)
            try:
                result = subprocess.run(
                    ["tesseract", str(temp_path), "stdout", "--oem", "3", "--psm", "6"],
                    check=False, capture_output=True, text=True,
                )
                text = result.stdout
            finally:
                temp_path.unlink(missing_ok=True)
        elif pytesseract is not None:
            text = pytesseract.image_to_string(variant, config="--oem 3 --psm 6")
        else:
            text = ""
        text = " ".join(text.split())
        if text and text not in texts:
            texts.append(text)
    return "\n".join(texts[:2])


def main() -> None:
    manifests = sorted(ROOT.glob("doc_*.pdf.json"))
    if not manifests:
        raise SystemExit(f"No visual manifests found in {ROOT}")
    total = 0
    for manifest_path in manifests:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in data.get("items", []):
            image_path = Path(item.get("path", ""))
            if not image_path.is_absolute():
                image_path = ROOT / image_path
            item["path"] = str(image_path)
            if not item.get("ocr_text"):
                item["ocr_text"] = ocr_region(image_path) if image_path.exists() else ""
            total += 1
        manifest_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print(manifest_path.name, len(data.get("items", [])), flush=True)
    print(f"enriched={total}")


if __name__ == "__main__":
    main()
