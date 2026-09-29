from psycopg.types.json import Jsonb
from app.config.database import DatabaseManager

class DocumentRepository:
    """Provide the documentrepository application component."""
    def __init__(self, db: DatabaseManager):
        self.db = db

    def get_documents_by_filter(self, filter_type: str, actor: str, limit: int, offset: int):
        """Return documents by filter."""
        with self.db.connect() as conn:
            if filter_type in ('mine', 'all'):
                where_clause = "WHERE uploaded_by = %s"
                params = (actor, limit, offset)
            elif filter_type == 'shared':
                # There is no document-sharing ACL yet; never expose other users' metadata.
                where_clause = "WHERE 1 = 0"
                params = (limit, offset)
            else: # all
                where_clause = ""
                params = (limit, offset)

            docs = conn.execute(
                f"SELECT id, original_filename, content_type, size_bytes, uploaded_by, status, created_at, error_message, (extracted_data->'metadata') as meta, progress, progress_stage FROM documents {where_clause} ORDER BY created_at DESC LIMIT %s OFFSET %s",
                params
            ).fetchall()
            
            count = conn.execute(
                f"SELECT COUNT(*) FROM documents {where_clause}", 
                params[:-2]
            ).fetchone()[0]
            
        return docs, count

    def create_document(self, doc_id, filename, object_key, content_type, size, actor, sha256):
        """Create document."""
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO documents (id, original_filename, object_key, content_type, size_bytes, uploaded_by, sha256) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (doc_id, filename, object_key, content_type, size, actor, sha256)
            )

    def get_next_queued_document(self):
        """Return next queued document."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT id FROM documents WHERE status = 'queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            conn.execute("UPDATE documents SET status = 'processing', progress = 0, progress_stage = 'Bat dau xu ly' WHERE id = %s", (row[0],))
            return row[0]

    def get_document(self, doc_id, actor=None):
        """Return document."""
        with self.db.connect() as conn:
            if actor and actor != 'system':
                return conn.execute("SELECT * FROM documents WHERE id = %s AND uploaded_by = %s", (doc_id, actor)).fetchone()
            return conn.execute("SELECT * FROM documents WHERE id = %s", (doc_id,)).fetchone()

    def is_document_active(self, doc_id):
        """Return whether document active."""
        with self.db.connect() as conn:
            row = conn.execute("SELECT status FROM documents WHERE id = %s", (doc_id,)).fetchone()
            return bool(row and row[0] in ("queued", "processing"))

    def get_document_status_and_data(self, doc_id, actor=None):
        """Return document status and data."""
        with self.db.connect() as conn:
            if actor and actor != 'system':
                return conn.execute("SELECT status, original_filename, extracted_data FROM documents WHERE id = %s AND uploaded_by = %s", (doc_id, actor)).fetchone()
            return conn.execute("SELECT status, original_filename, extracted_data FROM documents WHERE id = %s", (doc_id,)).fetchone()

    def delete_document(self, doc_id, actor=None):
        """Delete document."""
        with self.db.connect() as conn:
            if actor and actor != 'system':
                result = conn.execute(
                    "DELETE FROM documents WHERE id = %s AND uploaded_by = %s",
                    (doc_id, actor),
                )
            else:
                result = conn.execute(
                    "DELETE FROM documents WHERE id = %s",
                    (doc_id,),
                )
            conn.commit()
            return result.rowcount > 0

    def delete_all_documents(self, filter_type: str, actor: str):
        """Delete all documents."""
        with self.db.connect() as conn:
            if filter_type in ('mine', 'all'):
                where_clause = "WHERE uploaded_by = %s"
                params = (actor,)
            elif filter_type == 'shared':
                where_clause = "WHERE 1 = 0"
                params = ()
            else:
                where_clause = ""
                params = ()
                
            docs = conn.execute(f"SELECT id, object_key FROM documents {where_clause}", params).fetchall()
            if docs:
                conn.execute(f"DELETE FROM documents {where_clause}", params)
            return docs

    def update_document_status(self, doc_id, status, error_message=None, extracted_data=None):
        """Update document status."""
        with self.db.connect() as conn:
            if extracted_data is not None:
                conn.execute("UPDATE documents SET status = %s, extracted_data = %s, progress = 100, progress_stage = 'Hoan thanh' WHERE id = %s", (status, Jsonb(extracted_data), doc_id))
            elif error_message is not None:
                conn.execute("UPDATE documents SET status = %s, error_message = %s WHERE id = %s", (status, error_message, doc_id))
            else:
                conn.execute("UPDATE documents SET status = %s WHERE id = %s", (status, doc_id))

    def update_progress(self, doc_id, progress: int, stage: str = ''):
        """Ghi nhan tien do xu ly thuc te (0-100) va ten giai doan hien tai."""
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE documents SET progress = %s, progress_stage = %s WHERE id = %s",
                (progress, stage, doc_id)
            )
