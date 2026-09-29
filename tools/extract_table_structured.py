"""Extract Docling table structure to JSON for the five SynthDocQA PDFs."""
import json
from pathlib import Path
from docling.document_converter import DocumentConverter, InputFormat, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions

DATASET = Path(__import__("os").environ.get("TABLE_DATASET", "datasets/synthdocqa/grounding_pdfs_v2"))
OUT = Path(__import__("os").environ.get("TABLE_OUTPUT", "evaluation/artifacts/table_structured_cache"))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    options = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    for pdf in sorted(DATASET.glob("doc_*.pdf")):
        result = converter.convert(str(pdf.resolve()))
        tables = []
        for index, table in enumerate(result.document.tables):
            try:
                frame = table.export_to_dataframe(doc=result.document)
                rows = [[None if str(v) == "nan" else str(v) for v in row] for row in frame.values.tolist()]
                columns = [str(c) for c in frame.columns.tolist()]
            except Exception:
                rows, columns = [], []
            pages = sorted({p.page_no for p in getattr(table, "prov", []) if getattr(p, "page_no", None)})
            tables.append({"table_id": f"{pdf.name}:t{index}", "pages": pages, "columns": columns, "rows": rows})
        (OUT / f"{pdf.name}.json").write_text(json.dumps({"file": pdf.name, "tables": tables}, ensure_ascii=False), encoding="utf-8")
        print(pdf.name, len(tables), flush=True)


if __name__ == "__main__":
    main()
