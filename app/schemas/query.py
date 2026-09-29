from typing import List, Optional, Any
from pydantic import BaseModel, Field
from app.config.settings import TOP_K


class QueryRequest(BaseModel):
    """Provide the queryrequest application component."""
    question: str = Field(..., description="Question to answer from indexed documents")
    top_k: Optional[int] = Field(TOP_K, description="Maximum number of retrieved chunks")
    document_id: Optional[str] = Field(None, description="Optional document scope")


class SourceCitation(BaseModel):
    """Provide the sourcecitation application component."""
    file_name: str
    chunk_id: str
    page: Optional[Any] = None
    similarity_score: Optional[float] = None
    snippet: Optional[str] = None


class QueryResponse(BaseModel):
    """Provide the queryresponse application component."""
    answer: str
    sources: List[SourceCitation]
    total_chunks_retrieved: Optional[int] = 0
    execution_time_seconds: Optional[float] = 0.0
