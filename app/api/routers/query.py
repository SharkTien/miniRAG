"""
Query Router
============
Implement the POST /query endpoint specified by SUBJECT.md:
- accept a question;
- run retrieval-augmented generation;
- return an answer with mandatory source citations.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.query import QueryRequest, QueryResponse
from app.retrieval.rag_service import RagService
from app.api.dependencies import get_rag_service
from app.config.settings import TOP_K

router = APIRouter(tags=["query"])
logger = logging.getLogger("query_router")


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Answer a question using indexed documents (RAG)",
)
def query_documents(
    payload: QueryRequest,
    rag_service: RagService = Depends(get_rag_service),
) -> QueryResponse:
    """
    Accept a question, retrieve grounded evidence, and return cited output.

    The endpoint embeds the question, performs top-k PostgreSQL/pgvector
    retrieval, calls the configured LLM, and returns answer sources.
    """
    if not payload.question or not payload.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "question_required", "message_key": "errors.question_required"},
        )

    try:
        query_kwargs = {
            "question": payload.question,
            "top_k": payload.top_k or TOP_K,
            "document_id": payload.document_id,
        }
        if payload.document_ids:
            query_kwargs["document_ids"] = payload.document_ids
        result = rag_service.answer_question(**query_kwargs)
        return QueryResponse(**result)
    except Exception as exc:
        logger.error("Failed to process POST /query: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "query_failed", "message_key": "errors.query_failed"},
        )
