import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.dependencies import get_conversation_repo, get_rag_service
from app.repositories.conversation_repo import ConversationRepository
from app.retrieval.rag_service import RagService
from app.config.settings import TOP_K

logger = logging.getLogger("conversations_router")

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

class CreateConversationRequest(BaseModel):
    """Provide the createconversationrequest application component."""
    title: Optional[str] = Field(default=None, description="Optional conversation title")
    id: Optional[str] = Field(default=None, description="Optional client-generated UUID")

class UpdateConversationRequest(BaseModel):
    """Provide the updateconversationrequest application component."""
    title: str = Field(..., description="New conversation title")

class SendMessageRequest(BaseModel):
    """Provide the sendmessagerequest application component."""
    question: str = Field(..., description="Question to answer")
    top_k: Optional[int] = Field(default=TOP_K, ge=1, le=20, description="Maximum number of retrieved chunks")
    document_id: Optional[str] = Field(default=None, description="Optional document scope")
    document_ids: Optional[List[str]] = Field(default=None, description="Optional multi-document scope")

@router.get("", summary="List conversations")
def list_conversations(
    repo: ConversationRepository = Depends(get_conversation_repo),
):
    """List conversations."""
    try:
        return repo.list_conversations()
    except Exception as e:
        logger.error("Failed to list conversations: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail={"code": "conversation_list_failed"})

@router.post("", summary="Create a conversation")
def create_conversation(
    payload: CreateConversationRequest,
    repo: ConversationRepository = Depends(get_conversation_repo),
):
    """Create conversation."""
    try:
        conv = repo.create_conversation(title=payload.title, conv_id=payload.id)
        return conv
    except Exception as e:
        logger.error("Failed to create conversation: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail={"code": "conversation_create_failed"})

@router.get("/{conversation_id}", summary="Get a conversation and its messages")
def get_conversation_details(
    conversation_id: str,
    repo: ConversationRepository = Depends(get_conversation_repo),
):
    """Return conversation details."""
    conv = repo.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail={"code": "conversation_not_found"})
    messages = repo.get_messages(conversation_id)
    conv["messages"] = messages
    return conv

@router.patch("/{conversation_id}", summary="Rename a conversation")
def update_conversation(
    conversation_id: str,
    payload: UpdateConversationRequest,
    repo: ConversationRepository = Depends(get_conversation_repo),
):
    """Update conversation."""
    success = repo.update_title(conversation_id, payload.title)
    if not success:
        raise HTTPException(status_code=404, detail={"code": "conversation_update_failed"})
    return {"status": "updated"}

@router.delete("/{conversation_id}", summary="Delete a conversation")
def delete_conversation(
    conversation_id: str,
    repo: ConversationRepository = Depends(get_conversation_repo),
):
    """Delete conversation."""
    success = repo.delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail={"code": "conversation_delete_failed"})
    return {"status": "deleted"}

@router.post("/{conversation_id}/messages", summary="Answer and persist a conversation message")
def send_message_in_conversation(
    conversation_id: str,
    payload: SendMessageRequest,
    repo: ConversationRepository = Depends(get_conversation_repo),
    rag_service: RagService = Depends(get_rag_service),
):
    """Send message in conversation."""
    query_text = payload.question.strip()
    if not query_text:
        raise HTTPException(status_code=400, detail={"code": "question_required"})

    conv = repo.get_conversation(conversation_id)
    if not conv:
        try:
            conv = repo.create_conversation(
                title=query_text[:50],
                conv_id=conversation_id
            )
        except Exception:
            raise HTTPException(status_code=404, detail={"code": "conversation_not_found"})

    # 1. Persist the user message.
    user_msg = repo.add_message(
        conv_id=conversation_id,
        role="user",
        content=query_text
    )

    # Generate a title from the first question when no title was supplied.
    if not conv.get("title"):
        clean_title = query_text[:50].strip()
        repo.update_title(conversation_id, clean_title)

    # 2. Run hybrid retrieval and LLM synthesis.
    try:
        query_kwargs = {
            "question": query_text,
            "top_k": payload.top_k or TOP_K,
            "document_id": payload.document_id,
        }
        if payload.document_ids:
            query_kwargs["document_ids"] = payload.document_ids
        rag_res = rag_service.answer_question(**query_kwargs)
        answer_text = rag_res.get("answer", "")
        sources = rag_res.get("sources", [])
        retrieved_chunks = rag_res.get("retrieved_chunks", [])
    except Exception as exc:
        logger.error("RAG processing failed: %s", exc, exc_info=True)
        answer_text = "rag_processing_failed"
        sources = []
        retrieved_chunks = []

    # 3. Persist the assistant message.
    assistant_msg = repo.add_message(
        conv_id=conversation_id,
        role="assistant",
        content=answer_text,
        sources=sources,
        retrieved_chunks=retrieved_chunks
    )

    return {
        "user_message": user_msg,
        "assistant_message": assistant_msg,
        "answer": answer_text,
        "sources": sources,
        "retrieved_chunks": retrieved_chunks
    }
