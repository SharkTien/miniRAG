import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.config.database import DatabaseManager
from app.config.storage import StorageManager
from app.repositories.document_repo import DocumentRepository
from app.ingestion.extract_service import ExtractService
from app.config.settings import INGESTION_WORKER_CONCURRENCY


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
    print(f"Worker batch concurrency={INGESTION_WORKER_CONCURRENCY}", flush=True)
    while True:
        try:
            doc_ids = repo.get_next_queued_documents(INGESTION_WORKER_CONCURRENCY)
        except Exception as exc:
            # Keep the worker alive during transient database/network failures.
            print(f"Worker database error: {exc}", flush=True)
            time.sleep(5)
            continue
        if not doc_ids:
            time.sleep(2)
            continue
        print(f"Worker claimed batch size={len(doc_ids)} ids={doc_ids}", flush=True)

        def process_document(doc_id):
            # Keep service state isolated per document while sharing only the
            # database manager and storage configuration.
            service = ExtractService(repo, StorageManager())
            print(f"Worker started document {doc_id}", flush=True)
            try:
                service.extract_document_background(doc_id)
            except Exception as exc:
                # The extraction service normally persists failures itself;
                # this catches failures before it can update the document.
                print(f"Worker failed document {doc_id}: {exc}", flush=True)
                repo.update_document_status(doc_id, "failed", error_message=str(exc))
            finally:
                print(f"Worker finished document {doc_id}", flush=True)

        with ThreadPoolExecutor(max_workers=len(doc_ids)) as executor:
            futures = [executor.submit(process_document, doc_id) for doc_id in doc_ids]
            for future in as_completed(futures):
                future.result()


if __name__ == "__main__":
    main()
