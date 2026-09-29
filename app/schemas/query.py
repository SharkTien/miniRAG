from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from app.config.settings import TOP_K


class QueryRequest(BaseModel):
    """Provide the queryrequest application component."""
    question: str = Field(..., description="Question to answer from indexed documents")
    top_k: Optional[int] = Field(TOP_K, description="Maximum number of retrieved chunks")
    document_id: Optional[str] = Field(None, description="Optional document scope")
    document_ids: Optional[List[str]] = Field(
        default=None,
        description="Optional multi-document scope; each document is searched independently",
    )


class SourceCitation(BaseModel):
    """Provide the sourcecitation application component."""
    document_id: Optional[str] = None
    file_name: str
    chunk_id: str
    page: Optional[Any] = None
    similarity_score: Optional[float] = None
    dense_score: Optional[float] = None
    bm25_score: Optional[float] = None
    retrieval_method: Optional[str] = None
    source_locator: Optional[Any] = None
    element_ids: List[str] = Field(default_factory=list)
    section: Optional[str] = None
    extraction_method: Optional[Any] = None
    ocr_confidence: Optional[float] = None
    page_start: Optional[Any] = None
    page_end: Optional[Any] = None
    snippet: Optional[str] = None


class QueryResponse(BaseModel):
    """Provide the queryresponse application component."""
    answer: str
    sources: List[SourceCitation]
    total_chunks_retrieved: Optional[int] = 0
    execution_time_seconds: Optional[float] = 0.0
    query_plan: Optional[Dict[str, Any]] = None
    retrieval_queries: List[str] = Field(default_factory=list)
    scope_document_ids: List[str] = Field(default_factory=list)
    retrieval_scope: Optional[Dict[str, Any]] = None
    evidence: Optional[Dict[str, Any]] = None
    decision: Optional[str] = None
