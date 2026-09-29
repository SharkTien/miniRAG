import json
from pathlib import Path
import pypdfium2 as pdfium
from docling.document_converter import DocumentConverter, InputFormat, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions

ROOT = Path(__import__('os').environ.get('VISUAL_DATASET', '/tmp/table_trial'))
OUT = Path(__import__('os').environ.get('VISUAL_OUTPUT', '/tmp/visual_cache'))

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    options = PdfPipelineOptions(do_ocr=False, do_table_structure=False)
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    for pdf_path in sorted(ROOT.glob('doc_*.pdf')):
        result = converter.convert(str(pdf_path))
        doc = result.document.export_to_dict()
        pdf = pdfium.PdfDocument(str(pdf_path))
        items = []
        for idx, picture in enumerate(doc.get('pictures', [])):
            for prov in picture.get('prov', []):
                bbox = prov.get('bbox') or {}
                page_no = int(prov.get('page_no') or 1)
                if not {'l','b','r','t'} <= set(bbox) or page_no > len(pdf):
                    continue
                page = pdf[page_no - 1]
                width, height = page.get_size()
                scale = 2.0
                image = page.render(scale=scale).to_pil().convert('RGB')
                left = max(0, int(float(bbox['l']) * scale))
                right = min(image.width, int(float(bbox['r']) * scale))
                top = max(0, int((height - float(bbox['t'])) * scale))
                bottom = min(image.height, int((height - float(bbox['b'])) * scale))
                if right <= left or bottom <= top:
                    continue
                path = OUT / f'{pdf_path.name}_p{page_no}_{idx}.png'
                image.crop((left, top, right, bottom)).save(path, format='PNG', optimize=True)
                items.append({'page': page_no, 'path': str(path), 'bbox': {'left': bbox['l'], 'bottom': bbox['b'], 'right': bbox['r'], 'top': bbox['t']}})
        pdf.close()
        (OUT / f'{pdf_path.name}.json').write_text(json.dumps({'file': pdf_path.name, 'items': items}, ensure_ascii=False), encoding='utf-8')
        print(pdf_path.name, len(items), flush=True)

if __name__ == '__main__':
    main()
