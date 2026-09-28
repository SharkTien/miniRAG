from io import BytesIO

from fastapi import UploadFile
from fastapi.exceptions import HTTPException

from app.main import app, health
from app.api.routers.documents import upload_docs
from app.api.routers.query import query_documents
from app.schemas.query import QueryRequest


class FakeDocumentService:
    def process_upload(self, file, user):
        return "00000000-0000-0000-0000-000000000001"

    class Repo:
        @staticmethod
        def update_document_status(*args, **kwargs):
            return None

    repo = Repo()


class FakeRagService:
    def answer_question(self, question, top_k, document_id=None):
        return {
            "answer": "Theo tài liệu, câu trả lời là có.",
            "sources": [{"file_name": "policy.pdf", "chunk_id": "c1", "page": 1}],
            "total_chunks_retrieved": 1,
            "execution_time_seconds": 0.01,
        }


def test_required_routes_and_health_contract():
    paths = {route.path for route in app.routes}
    assert {"/health", "/documents", "/api/documents", "/query"}.issubset(paths)
    assert health() == {"status": "ok"}


def test_query_handler_returns_answer_and_sources():
    response = query_documents(
        QueryRequest(question="Chính sách là gì?"),
        rag_service=FakeRagService(),
    )
    assert response.answer.startswith("Theo tài liệu")
    assert response.sources[0].file_name == "policy.pdf"


def test_query_handler_rejects_empty_question():
    try:
        query_documents(QueryRequest(question="   "), rag_service=FakeRagService())
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("empty question should be rejected")


def test_upload_handler_returns_queued_document():
    upload = UploadFile(
        filename="notes.txt",
        file=BytesIO(b"hello"),
        headers={"content-type": "text/plain"},
    )
    response = upload_docs([upload], user="admin", doc_service=FakeDocumentService())
    assert response["documents"][0]["status"] == "queued"
