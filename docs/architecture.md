# Mini RAG architecture

## Overview

The service accepts PDF, TXT, DOCX and common office/image files, stores the
original object in MinIO, and records document state in PostgreSQL. A worker
performs extraction and indexing so the upload request returns quickly.

```text
Client
  │
  ├── React/Vite + Nginx ──► backend API
  │
  ├── POST /documents ──► MinIO (raw file) + PostgreSQL (metadata/state)
  │                                  │
  │                                  ▼
  │                       background worker / ExtractService
  │                                  │
  │             Docling/DeepDoc/RAGFlow/Tesseract/PP-OCR extraction
  │                                  │
  │             normalize → semantic chunk → embedding
  │                                  │
  │                                  ▼
  │                       PostgreSQL + pgvector
  │
  └── POST /query ──► query planning → scoped exact/hybrid retrieval
                                  │
                                  ▼
                         evidence rerank and gating
                                  │
                                  ▼
                        grounded NVIDIA-compatible LLM
                                  │
                         answer + source citations
```

## Ingestion flow

1. `DocumentService` validates the extension and upload size, calculates a
   SHA-256 checksum, stores the file in MinIO, and creates a `queued` row.
2. `app.worker` claims queued documents and calls `ExtractService`.
3. Native PDFs use the text layer when it is reliable. Scan or mixed PDFs are
   routed to Tesseract, PP-OCR or Docling according to environment policy.
4. `NormalizeService` removes control characters and repeated page noise,
   preserves page/bounding-box provenance, and creates structure-aware chunks.
5. Each chunk receives an embedding and metadata including document id,
   filename, page range, chunk type and element ids. Docling picture crops and
   optional page snapshots are stored in MinIO as lazy visual evidence.
6. A failed embedding operation marks the document as `failed`; it is never
   reported as searchable without vectors.

## Retrieval and answer flow

`RagService` first creates a deterministic query plan. The plan identifies
exact, structured, comparison or broad-scope questions and creates at most one
normalized lexical variant. A request may also provide multiple document ids;
each document is searched independently so one large file cannot consume the
whole result set.

`RetrievalService` embeds each query and calls `ChunkRepository`. PostgreSQL
combines cosine similarity with full-text ranking, followed by a dependency-free
BM25 pass over the candidate pool. Exact phrase questions also have a literal
`ILIKE` retrieval path before semantic broadening. Results expose the dense and
BM25 scores and the actual retrieval method.

`EvidenceService` reranks the candidates, checks content coverage and records
which chunk supports each extracted question requirement. `RagService` limits
the prompt to the selected evidence, sends at most one image to the configured
vision endpoint, and returns citations containing filename, document id, chunk,
page, element ids, extraction method and retrieval scores where available.

The query endpoint is available at `POST /query`; `/api/query` is kept as a
compatibility alias. Document endpoints are available at both `/documents`
and `/api/documents`.

## Main components

| Component | Responsibility |
| --- | --- |
| React/Vite + Nginx | production UI và reverse proxy tới API |
| FastAPI routers | health, upload, query, conversation and document lifecycle APIs |
| PostgreSQL + pgvector | document metadata, chunks, embeddings and conversations |
| MinIO | original files, visual crops and page snapshots |
| ExtractService | parser routing, OCR, provenance and indexing orchestration |
| NormalizeService | cleaning, noise removal and semantic chunking |
| EmbeddingService | OpenAI-compatible NVIDIA embedding calls with retries |
| RetrievalService / ChunkRepository | filtered hybrid retrieval |
| EvidenceService | content-grounded reranking and answerability decision |
| RagService | bounded grounded prompt, optional image evidence and citations |

## Configuration

Runtime values are read from environment variables. Start from `.env.example`;
do not commit `.env`, API keys or GitHub credentials. The important tuning
values are `DOCUMENT_PARSER_ENGINE`, `SEMANTIC_NORMALIZER`,
`PERSIST_PAGE_VISUALS`, `EMBEDDING_MODEL`, `LLM_MODEL`, `CHUNK_SIZE`,
`CHUNK_OVERLAP`, `TOP_K` and `SIMILARITY_THRESHOLD`.

The default parser path is local Docling/DeepDoc. RAGFlow server mode is an
optional integration: install a compatible `ragflow-sdk` version separately
when `RAGFLOW_MODE=api` is enabled. It is intentionally excluded from the
core requirements because its dependency constraints conflict with the local
DeepDoc parser.

## Limits and next improvements

- Hosted embedding/LLM availability and rate limits affect latency and answer
  quality; the service returns a source-bearing fallback when no LLM key is
  configured.
- Page snapshots improve visual questions but increase object-storage use; set
  `PERSIST_PAGE_VISUALS=false` when storage is constrained.
- The current query planner and reranker are deterministic and rule based. A
  cross-encoder or learned reranker can improve recall after collecting
  production feedback.
- Version/effective-date resolution, typed facts for numeric tables and
  checkpoint-based exhaustive search are still future work.
- Human review, feedback capture and a larger regression set should be added
  before using answers for high-impact decisions.
