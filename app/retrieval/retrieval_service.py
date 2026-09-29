"""
Retrieval Service
=================
Retrieve the most relevant document chunks with pgvector vector search.
"""

import uuid
import logging
from typing import List, Dict, Any, Optional

from app.config.settings import TOP_K, SIMILARITY_THRESHOLD
from app.retrieval.embedding_service import EmbeddingService
from app.repositories.chunk_repo import ChunkRepository

logger = logging.getLogger("retrieval_service")


class RetrievalService:
    """Provide the retrievalservice application component."""
    def __init__(self, chunk_repo: ChunkRepository, embedder: Optional[EmbeddingService] = None):
        self.chunk_repo = chunk_repo
        self.embedder = embedder or EmbeddingService()

    def retrieve(
        self,
        query: str,
        top_k: int = TOP_K,
        document_id: Optional[str] = None,
        min_score: float = SIMILARITY_THRESHOLD,
    ) -> List[Dict[str, Any]]:
        """
        1. Embed the question.
        2. Query cosine similarity in the document_chunks table.
        3. Return the most relevant top-k chunks with metadata.
        """
        if not query or not query.strip():
            return []

        doc_uuid = uuid.UUID(document_id) if document_id else None
        
        # 1. Tạo vector cho câu hỏi (input_type='query')
        query_vector = self.embedder.embed_query(query.strip())

        # 2. Vector / Hybrid search trong PostgreSQL
        matched_chunks = self.chunk_repo.vector_search(
            query_embedding=query_vector,
            top_k=top_k,
            document_id=doc_uuid,
            min_similarity=min_score,
            query_text=query.strip(),
        )

        logger.info("Truy vấn: '%s' -> Tìm thấy %d chunks phù hợp", query[:50], len(matched_chunks))
        return matched_chunks

    def retrieve_exact(
        self,
        query: str,
        top_k: int = TOP_K,
        document_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve literal phrase matches without semantic broadening."""
        if not query or not query.strip():
            return []
        doc_uuid = uuid.UUID(document_id) if document_id else None
        return self.chunk_repo.exact_search(query.strip(), top_k=top_k, document_id=doc_uuid)
