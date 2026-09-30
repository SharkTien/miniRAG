"""
Query Router
============
Implement the POST /query endpoint specified by SUBJECT.md:
- accept a question;
- run retrieval-augmented generation;
- return an answer with mandatory source citations.
"""

import logging
import json
import queue
import threading
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.schemas.query import QueryRequest, QueryResponse
from app.retrieval.rag_service import RagService
from app.api.dependencies import get_rag_service
from app.api.dependencies import get_conversation_repo
from app.repositories.conversation_repo import ConversationRepository
from app.config.settings import TOP_K

router = APIRouter(tags=["query"])
logger = logging.getLogger("query_router")

@router.post("/query/stream", summary="Stream a grounded answer")
def stream_query(payload: QueryRequest, conversation_id: str | None = None, rag_service: RagService = Depends(get_rag_service), repo: ConversationRepository = Depends(get_conversation_repo)):
    """Stream grounded answer tokens and retrieval metadata to the client."""
    if not payload.question or not payload.question.strip():
        raise HTTPException(status_code=400, detail={"code": "question_required"})
    events: queue.Queue = queue.Queue()
    done = object()
    def run():
        try:
            if conversation_id:
                repo.add_message(conversation_id, "user", payload.question.strip())
            result = rag_service.answer_question(
                question=payload.question, top_k=payload.top_k or TOP_K,
                document_id=payload.document_id, document_ids=payload.document_ids,
                on_token=lambda token: events.put({"type": "token", "text": token}),
            )
            if conversation_id:
                repo.add_message(conversation_id, "assistant", result.get("answer", ""), result.get("sources", []), result.get("retrieved_chunks", []))
            events.put({"type": "metadata", "sources": result.get("sources", []), "retrieved_chunks": result.get("retrieved_chunks", [])})
            events.put(done)
        except Exception as exc:
            logger.error("Streaming query failed: %s", exc, exc_info=True)
            events.put({"type": "error", "message": "Không thể xử lý truy vấn lúc này."})
            events.put(done)
    threading.Thread(target=run, daemon=True).start()
    def body():
        while True:
            event = events.get()
            if event is done:
                yield "data: [DONE]\n\n"
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    return StreamingResponse(body(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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
