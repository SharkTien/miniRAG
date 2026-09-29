"""Build OCR block crops for callouts, highlights and colored tables.

Docling's ``pictures`` collection does not cover these baked-in visual
annotations. Tesseract TSV gives us word coordinates; grouping words by block
creates retrievable regions while preserving a crop for the vision model.
"""

import csv
import io
import json
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image


PAGE_ROOT = Path(os.environ.get("PAGE_VISUAL_OUTPUT", Path(__file__).resolve().parent / "page_visual_cache"))
OUT = Path(os.environ.get("ANNOTATION_OUTPUT", Path(__file__).resolve().parent / "annotation_region_cache"))


def tsv_words(image_path: Path) -> list[dict]:
    if not shutil.which("tesseract"):
        return []
    result = subprocess.run(
        ["tesseract", str(image_path), "stdout", "--oem", "3", "--psm", "11", "tsv"],
        check=False, capture_output=True, text=True,
    )
    rows = []
    for row in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
        text = (row.get("text") or "").strip()
        try:
            conf = float(row.get("conf", "-1"))
            left, top = int(row["left"]), int(row["top"])
            width, height = int(row["width"]), int(row["height"])
            block, par = int(row["block_num"]), int(row["par_num"])
        except (TypeError, ValueError, KeyError):
            continue
        if text and conf >= 0:
            rows.append({
                "text": text, "conf": conf, "left": left, "top": top,
                "right": left + width, "bottom": top + height,
                "group": (block, par),
            })
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifests = sorted(PAGE_ROOT.glob("doc_*.pdf.json"))
    total = 0
    for manifest_path in manifests:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        items = []
        for page_item in data.get("pages", []):
            page = int(page_item.get("page") or 0)
            page_path = Path(page_item.get("path", ""))
            if not page_path.exists():
                page_path = PAGE_ROOT / page_path.name
            if not page_path.exists():
                continue
            words = tsv_words(page_path)
            with Image.open(page_path) as source:
                image = source.convert("RGB")
                # Fixed layout tiles retain colors/highlights and avoid an
                # index full of tiny OCR fragments. Eight tiles per page is a
                # practical compromise for callouts and colored tables.
                cols, rows = 2, 4
                tile_width, tile_height = image.width / cols, image.height / rows
                groups: dict[tuple[int, int], list[dict]] = {}
                for word in words:
                    cx = (word["left"] + word["right"]) / 2
                    cy = (word["top"] + word["bottom"]) / 2
                    key = (min(cols - 1, int(cx / tile_width)), min(rows - 1, int(cy / tile_height)))
                    groups.setdefault(key, []).append(word)
                for region_idx, ((col, row), region_words) in enumerate(sorted(groups.items())):
                    text = " ".join(w["text"] for w in region_words)
                    if len(text) < 3:
                        continue
                    left = int(col * tile_width)
                    top = int(row * tile_height)
                    right = min(image.width, int((col + 1) * tile_width))
                    bottom = min(image.height, int((row + 1) * tile_height))
                    if right <= left or bottom <= top:
                        continue
                    crop_path = OUT / f"{manifest_path.stem}_p{page}_{region_idx}.jpg"
                    image.crop((left, top, right, bottom)).save(crop_path, format="JPEG", quality=88, optimize=True)
                    items.append({
                        "page": page,
                        "path": str(crop_path),
                        "bbox_px": {"left": left, "top": top, "right": right, "bottom": bottom},
                        "ocr_text": text,
                        "ocr_confidence": round(sum(w["conf"] for w in region_words) / len(region_words), 2),
                    })
        out_path = OUT / manifest_path.name
        out_path.write_text(json.dumps({"file": data.get("file"), "items": items}, ensure_ascii=False), encoding="utf-8")
        total += len(items)
        print(manifest_path.name, len(items), flush=True)
    print(f"regions={total}")


if __name__ == "__main__":
    main()
