import uuid
from pathlib import Path
from fastapi import UploadFile, HTTPException
from app.config.settings import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES
from app.config.storage import StorageManager
from app.repositories.document_repo import DocumentRepository

class DocumentService:
    """Provide the documentservice application component."""
    def __init__(self, repo: DocumentRepository, storage: StorageManager):
        self.repo = repo
        self.storage = storage

    def list_documents(self, page: int, size: int, filter_type: str, actor: str):
        """List documents."""
        offset = (page - 1) * size
        docs, count = self.repo.get_documents_by_filter(filter_type, actor, size, offset)
        
        result = []
        for d in docs:
            meta = d[8] if len(d) > 8 and isinstance(d[8], dict) else {}
            conf = meta.get("confidence_score")
            ocr_pct = meta.get("ocr_percent")
            if ocr_pct is None and conf is not None:
                try:
                    ocr_pct = round(float(conf) * 100, 1)
                except (ValueError, TypeError):
                    ocr_pct = None
            page_count = meta.get("page_count", 1)
            progress = d[9] if len(d) > 9 and d[9] is not None else 0
            progress_stage = d[10] if len(d) > 10 and d[10] is not None else ''
            # Neu da xu ly xong thi progress = 100
            if d[5] == 'processed':
                progress = 100
            result.append({
                "id": str(d[0]), "filename": d[1], "content_type": d[2],
                "size_bytes": d[3], "uploaded_by": d[4], "status": d[5],
                "created_at": d[6].isoformat() if d[6] else None,
                "error_message": d[7],
                "ocr_percent": ocr_pct,
                "confidence_score": conf,
                "page_count": page_count,
                "progress": progress,
                "progress_stage": progress_stage,
            })
            
        return {
            "documents": result,
            "total": count,
            "page": page,
            "size": size,
            "total_pages": (count + size - 1) // size
        }

    def process_upload(self, file: UploadFile, actor: str) -> uuid.UUID:
        """Process upload."""
        name = file.filename
        if not name:
            raise HTTPException(400, "Tên file không hợp lệ")
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Định dạng chưa được hỗ trợ: {ext or '(không có phần mở rộng)'}")
        if file.size is not None and file.size > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"Kích thước file vượt quá {MAX_UPLOAD_BYTES // 1024 // 1024} MB")
            
        doc_id = uuid.uuid4()
        object_key = f"{doc_id}{ext}"
        
        # Calculate SHA-256
        import hashlib
        file.file.seek(0)
        file_hash = hashlib.sha256()
        while chunk := file.file.read(8192):
            file_hash.update(chunk)
            if file.file.tell() > MAX_UPLOAD_BYTES:
                raise HTTPException(413, f"Kích thước file vượt quá {MAX_UPLOAD_BYTES // 1024 // 1024} MB")
        sha256_hex = file_hash.hexdigest()
        file.file.seek(0)
        
        # Upload to MinIO
        try:
            self.storage.upload_fileobj(file.file, object_key, file.content_type)
        except Exception as e:
            raise HTTPException(500, f"Lỗi lưu trữ: {str(e)}")
            
        # Save to DB; remove the object if metadata persistence fails.
        size = file.size or file.file.tell()
        try:
            self.repo.create_document(doc_id, name, object_key, content_type=file.content_type, size=size, actor=actor, sha256=sha256_hex)
        except Exception:
            try:
                self.storage.delete_object(object_key)
            finally:
                raise
        
        return doc_id

    def delete_doc(self, doc_id: uuid.UUID, actor: str):
        """Delete doc."""
        row = self.repo.get_document(doc_id, actor)
        if not row:
            raise HTTPException(404, "Tài liệu không tồn tại hoặc không có quyền")
            
        object_key = row[2] # based on SELECT *
        deleted = self.repo.delete_document(doc_id, actor)
        if not deleted:
            raise HTTPException(404, "Tài liệu không tồn tại hoặc không có quyền")
        
        try:
            self.storage.delete_object(object_key)
        except Exception:
            pass # Ignore storage error if DB is cleaned

    def delete_all_docs(self, filter_type: str, actor: str) -> int:
        """Delete all docs."""
        docs = self.repo.delete_all_documents(filter_type, actor)
        count = 0
        for doc_id, object_key in docs:
            count += 1
            try:
                self.storage.delete_object(object_key)
            except Exception:
                pass
        return count
