from fastapi import Depends
from app.config.constants import SYSTEM_ACTOR
from app.config.database import DatabaseManager
from app.config.storage import StorageManager
from app.repositories.document_repo import DocumentRepository
from app.repositories.chunk_repo import ChunkRepository
from app.repositories.conversation_repo import ConversationRepository
from app.ingestion.document_service import DocumentService
from app.ingestion.extract_service import ExtractService
from app.retrieval.embedding_service import EmbeddingService
from app.retrieval.retrieval_service import RetrievalService
from app.retrieval.rag_service import RagService

def get_system_actor() -> str:
    """Return the fixed actor used by this single-tenant backend."""
    return SYSTEM_ACTOR

# Dependency Injection Providers
def get_database() -> DatabaseManager:
    """Return database."""
    return DatabaseManager()

def get_storage() -> StorageManager:
    """Return storage."""
    return StorageManager()

def get_document_repo(db: DatabaseManager = Depends(get_database)) -> DocumentRepository:
    """Return document repo."""
    return DocumentRepository(db)

def get_document_service(
    repo: DocumentRepository = Depends(get_document_repo),
    storage: StorageManager = Depends(get_storage)
) -> DocumentService:
    """Return document service."""
    return DocumentService(repo, storage)

def get_extract_service(
    repo: DocumentRepository = Depends(get_document_repo),
    storage: StorageManager = Depends(get_storage)
) -> ExtractService:
    """Return extract service."""
    return ExtractService(repo, storage)

def get_chunk_repo(db: DatabaseManager = Depends(get_database)) -> ChunkRepository:
    """Return chunk repo."""
    return ChunkRepository(db)

def get_embedding_service() -> EmbeddingService:
    """Return embedding service."""
    return EmbeddingService()

def get_retrieval_service(
    chunk_repo: ChunkRepository = Depends(get_chunk_repo),
    embedder: EmbeddingService = Depends(get_embedding_service)
) -> RetrievalService:
    """Return retrieval service."""
    return RetrievalService(chunk_repo, embedder)

def get_rag_service(
    retriever: RetrievalService = Depends(get_retrieval_service)
) -> RagService:
    """Return rag service."""
    return RagService(retriever)

def get_conversation_repo(db: DatabaseManager = Depends(get_database)) -> ConversationRepository:
    """Return conversation repo."""
    return ConversationRepository(db)
