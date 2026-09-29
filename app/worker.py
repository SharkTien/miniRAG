import time
import signal

from app.config.database import DatabaseManager
from app.config.storage import StorageManager
from app.repositories.document_repo import DocumentRepository
from app.ingestion.extract_service import ExtractService
from app.config.settings import EXTRACTION_TIMEOUT_SECONDS


class ExtractionTimeoutError(Exception):
    """Provide the extractiontimeouterror application component."""
    pass


def _timeout_handler(signum, frame):
    raise ExtractionTimeoutError(f"Extraction timeout sau {EXTRACTION_TIMEOUT_SECONDS} giây")


def main() -> None:
    """Run the background ingestion worker loop."""
    database = DatabaseManager()
    # Run idempotent schema migrations here as well: the worker and API start
    # independently under Compose, so neither may assume the other starts first.
    database.init_db()
    repo = DocumentRepository(database)
    recovered = repo.requeue_processing_documents()
    if recovered:
        print(f"Requeued {recovered} interrupted document(s)", flush=True)
    service = ExtractService(repo, StorageManager())
    while True:
        try:
            doc_id = repo.get_next_queued_document()
        except Exception as exc:
            # Keep the worker alive during transient database/network failures.
            print(f"Worker database error: {exc}", flush=True)
            time.sleep(5)
            continue
        if doc_id is None:
            time.sleep(2)
            continue
        print(f"Worker started document {doc_id}", flush=True)
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(EXTRACTION_TIMEOUT_SECONDS)
        try:
            service.extract_document_background(doc_id)
        except ExtractionTimeoutError as exc:
            print(f"Worker timeout document {doc_id}: {exc}", flush=True)
            repo.update_document_status(doc_id, "failed", error_message=str(exc))
        finally:
            signal.alarm(0)
        print(f"Worker finished document {doc_id}", flush=True)


if __name__ == "__main__":
    main()
