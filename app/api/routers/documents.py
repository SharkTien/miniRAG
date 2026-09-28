import uuid
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from starlette.background import BackgroundTask
from app.api.dependencies import get_current_user, get_document_service, get_extract_service, get_document_repo, get_storage
from app.services.document_service import DocumentService
from app.services.extract_service import ExtractService
from app.repositories.document_repo import DocumentRepository
from app.core.storage import StorageManager

router = APIRouter(tags=["documents"])

@router.get("")
def get_docs(
    page: int = 1, size: int = 10, filter: str = 'all',
    user: str = Depends(get_current_user),
    doc_service: DocumentService = Depends(get_document_service)
):
    return doc_service.list_documents(page, size, filter, user)

@router.post("")
def upload_docs(
    files: list[UploadFile] = File(...), 
    user: str = Depends(get_current_user),
    doc_service: DocumentService = Depends(get_document_service)
):
    docs = []
    for file in files:
        doc_id = doc_service.process_upload(file, user)
        doc_service.repo.update_document_status(doc_id, "queued")
        docs.append({"id": str(doc_id), "filename": file.filename, "status": "queued"})
    return {"message": "Tải lên thành công", "documents": docs, "uploaded": docs}

@router.delete("/{document_id}")
def delete_document_api(
    document_id: uuid.UUID, 
    user: str = Depends(get_current_user),
    doc_service: DocumentService = Depends(get_document_service)
):
    doc_service.delete_doc(document_id, user)
    return {"message": "Đã xóa tài liệu", "id": str(document_id)}

@router.post("/{document_id}/cancel")
def cancel_document_api(
    document_id: uuid.UUID,
    user: str = Depends(get_current_user),
    repo: DocumentRepository = Depends(get_document_repo),
):
    row = repo.get_document(document_id, user)
    if not row:
        raise HTTPException(404, "Tài liệu không tồn tại hoặc không có quyền")
    status = repo.get_document_status_and_data(document_id, user)[0]
    if status not in ("queued", "processing"):
        raise HTTPException(409, "Tài liệu không còn đang xử lý")
    repo.update_document_status(document_id, "cancelled", error_message="Đã hủy theo yêu cầu người dùng")
    return {"message": "Đã hủy tiến trình xử lý", "id": str(document_id), "status": "cancelled"}

@router.delete("/bulk/all")
def delete_all_documents_api(
    filter: str = 'all',
    user: str = Depends(get_current_user),
    doc_service: DocumentService = Depends(get_document_service)
):
    count = doc_service.delete_all_docs(filter, user)
    return {"message": f"Đã xóa toàn bộ {count} tài liệu"}

@router.get("/{document_id}/extraction")
def get_extraction(
    document_id: uuid.UUID, 
    user: str = Depends(get_current_user),
    repo: DocumentRepository = Depends(get_document_repo)
):
    row = repo.get_document_status_and_data(document_id, user)
    if not row:
        raise HTTPException(404, "Tài liệu không tồn tại")
    return {
        "status": row[0],
        "filename": row[1],
        "extracted_data": row[2]
    }

@router.get("/{document_id}/images")
def get_document_images(
    document_id: uuid.UUID,
    user: str = Depends(get_current_user),
    repo: DocumentRepository = Depends(get_document_repo),
):
    row = repo.get_document_status_and_data(document_id, user)
    if not row:
        raise HTTPException(404, "Tài liệu không tồn tại")
    extracted_data = row[2] or {}
    meta = extracted_data.get("metadata", {})
    conf = meta.get("confidence_score")
    ocr_pct = meta.get("ocr_percent")
    if ocr_pct is None and conf is not None:
        try:
            ocr_pct = round(float(conf) * 100, 1)
        except (ValueError, TypeError):
            ocr_pct = None
    return {
        "document_id": str(document_id),
        "filename": row[1],
        "metadata": meta,
        "ocr_percent": ocr_pct or 98.0,
        "confidence_score": conf or 0.98,
        "page_count": meta.get("page_count", 1),
        "images": extracted_data.get("images", []),
        "ocr_bboxes": extracted_data.get("ocr_bboxes", []),
        "normalized_elements": extracted_data.get("normalized_elements", []),
    }

@router.get("/{document_id}/content")
def get_document_content(
    document_id: uuid.UUID, 
    user: str = Depends(get_current_user),
    repo: DocumentRepository = Depends(get_document_repo),
    storage: StorageManager = Depends(get_storage)
):
    row = repo.get_document(document_id, user)
    if not row:
        raise HTTPException(404, "Tài liệu không tồn tại")
        
    try:
        # row indexes: 0=id, 1=original_filename, 2=object_key, 3=content_type
        obj = storage.get_object(row[2])
        safe_filename = str(row[1]).replace('"', '').replace('\r', '').replace('\n', '')
        encoded_filename = quote(safe_filename, safe='')
        return StreamingResponse(
            obj['Body'].iter_chunks(),
            media_type=row[3] or "application/octet-stream",
            headers={
                # filename* preserves Vietnamese/UTF-8 names without latin-1 errors.
                "Content-Disposition": f"inline; filename=document; filename*=UTF-8''{encoded_filename}",
                "X-Content-Type-Options": "nosniff",
            }
        )
    except Exception as e:
        raise HTTPException(500, f"Lỗi đọc file: {str(e)}")

@router.get("/{document_id}/preview")
def preview_document(
    document_id: uuid.UUID,
    user: str = Depends(get_current_user),
    repo: DocumentRepository = Depends(get_document_repo),
    storage: StorageManager = Depends(get_storage),
):
    """Convert Office documents to a temporary PDF for browser preview."""
    row = repo.get_document(document_id, user)
    if not row:
        raise HTTPException(404, "Tài liệu không tồn tại")
    suffix = Path(row[1]).suffix.lower()
    if suffix not in {".pptx", ".docx", ".xlsx"}:
        return get_document_content(document_id, user, repo, storage)

    workdir = tempfile.mkdtemp(prefix="ntc-preview-")
    source = os.path.join(workdir, f"source{suffix}")
    try:
        storage.download_file(row[2], source)
        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", workdir, source],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        converted = os.path.join(workdir, "source.pdf")
        if result.returncode != 0 or not os.path.exists(converted):
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "LibreOffice conversion failed")
        return FileResponse(
            converted,
            media_type="application/pdf",
            filename=f"{Path(row[1]).stem}.pdf",
            background=BackgroundTask(shutil.rmtree, workdir, ignore_errors=True),
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(504, "Chuyển đổi tài liệu quá thời gian cho phép")
    except Exception as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(500, f"Không thể tạo bản xem trước: {exc}")

@router.get("/{document_id}/file")
def get_document_file_alias(
    document_id: uuid.UUID,
    user: str = Depends(get_current_user),
    repo: DocumentRepository = Depends(get_document_repo),
    storage: StorageManager = Depends(get_storage),
):
    """Alias for previewing/downloading document file."""
    return preview_document(document_id, user, repo, storage)

@router.post("/{document_id}/extract")
def manual_extract_document(
    document_id: uuid.UUID, 
    user: str = Depends(get_current_user),
    repo: DocumentRepository = Depends(get_document_repo)
):
    row = repo.get_document_status_and_data(document_id, user)
    if not row:
        raise HTTPException(404, "Tài liệu không tồn tại")
        
    repo.update_document_status(document_id, "queued")
    return {"message": "Đã đưa vào hàng đợi trích xuất", "status": "queued"}
