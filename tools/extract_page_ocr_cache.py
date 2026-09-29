"""Create page OCR chunks from the rendered page snapshots."""
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(os.environ.get("PAGE_VISUAL_OUTPUT", Path(__file__).resolve().parent / "page_visual_cache"))
OUT = Path(os.environ.get("OCR_OUTPUT", Path(__file__).resolve().parent / "ocr_cache"))

def main():
    if not shutil.which("tesseract"):
        raise SystemExit("tesseract CLI is required")
    OUT.mkdir(parents=True, exist_ok=True)
    for manifest in sorted(ROOT.glob("doc_*.pdf.json")):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        chunks = []
        for item in data.get("pages", []):
            path = Path(item.get("path", ""))
            if not path.exists(): path = ROOT / path.name
            if not path.exists(): continue
            result = subprocess.run(["tesseract", str(path), "stdout", "--oem", "3", "--psm", "6"], capture_output=True, text=True, check=False)
            text = " ".join(result.stdout.split())
            if text:
                page = int(item.get("page") or 0)
                chunks.append({"chunk_id": f"{manifest.stem}_ocr_p{page}", "file_name": data.get("file", manifest.name.replace('.json','')), "page": page, "content": text, "retrieval_source": "tesseract_ocr"})
        (OUT / f"{manifest.name[:-5]}_tesseract.json").write_text(json.dumps({"chunks": chunks}, ensure_ascii=False), encoding="utf-8")
        print(manifest.name, len(chunks), flush=True)

if __name__ == "__main__": main()
