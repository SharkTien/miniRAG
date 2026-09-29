"""Render one visual page snapshot per PDF page for annotation QA."""

import json
import os
from pathlib import Path

import pypdfium2 as pdfium


ROOT = Path(os.environ.get("VISUAL_DATASET", Path(__file__).resolve().parent.parent / "datasets" / "synthdocqa" / "grounding_pdfs_v2"))
OUT = Path(os.environ.get("PAGE_VISUAL_OUTPUT", Path(__file__).resolve().parent / "page_visual_cache"))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for pdf_path in sorted(ROOT.glob("doc_*.pdf")):
        pdf = pdfium.PdfDocument(str(pdf_path))
        pages = []
        for page_no in range(1, len(pdf) + 1):
            page = pdf[page_no - 1]
            image = page.render(scale=1.5).to_pil().convert("RGB")
            image_path = OUT / f"{pdf_path.name}_p{page_no}.jpg"
            image.save(image_path, format="JPEG", quality=88, optimize=True)
            pages.append({"page": page_no, "path": str(image_path)})
        pdf.close()
        (OUT / f"{pdf_path.name}.json").write_text(
            json.dumps({"file": pdf_path.name, "pages": pages}, ensure_ascii=False),
            encoding="utf-8",
        )
        print(pdf_path.name, len(pages), flush=True)


if __name__ == "__main__":
    main()
