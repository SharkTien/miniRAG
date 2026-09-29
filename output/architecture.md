# Architecture Presentation

## Thành phần

```text
Client / CLI / Swagger
   │
   ├── POST /documents ──► FastAPI ──► MinIO (raw file)
   │                          │
   │                          └──────► PostgreSQL (metadata/state)
   │                                      │
   │                         worker ◄─────┘
   │                           │
   │             extract/OCR → clean → chunk → embedding
   │                                                   │
   │                                      PostgreSQL + pgvector
   │
   └── POST /query ──► question embedding → hybrid retrieval
                                      → evidence gate/rerank
                                      → grounded LLM
                                      → answer + citations
```

## Ingestion flow

1. API kiểm tra extension, size và checksum rồi lưu file vào MinIO.
2. PostgreSQL tạo document record ở trạng thái `queued`.
3. Worker claim record, chọn parser theo `DOCUMENT_PARSER_ENGINE`.
4. PDF text layer dùng trực tiếp; scan/mixed document dùng Tesseract, PP-OCR
   hoặc Docling fallback theo policy.
5. `NormalizeService` loại control character, chuẩn hóa whitespace, giữ page
   provenance và tạo semantic chunks.
6. Mỗi chunk được embed và lưu cùng `document_id`, `file_name`, `chunk_id`,
   model, page range, content và timestamp/metadata.

## Retrieval flow

Question được embed, tìm top-k bằng cosine similarity kết hợp lexical search,
sau đó `EvidenceService` kiểm tra lexical coverage/answerability. Chỉ evidence
đã được giới hạn token mới đi vào grounded prompt. Response luôn chứa nguồn gồm
filename, chunk id, page và snippet.

Các tham số vận hành được cấu hình qua environment: `DATABASE_URL`,
`EMBEDDING_MODEL`, `LLM_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K` và
`SIMILARITY_THRESHOLD`. Mã retrieval đọc các giá trị này từ
`app/config/settings.py`.

## Lý do chọn công nghệ

- FastAPI: API rõ schema, validation và dễ containerize.
- PostgreSQL + pgvector: lưu metadata và vector cùng một transaction boundary.
- MinIO: object storage local-compatible cho file gốc và visual evidence.
- Worker PostgreSQL queue: upload không phải chờ OCR/embedding hoàn tất.
- Docling/Tesseract/PP-OCR: hỗ trợ tài liệu text, scan và layout tiếng Việt.

## Giới hạn và hướng cải thiện

Chất lượng phụ thuộc embedding/LLM endpoint, OCR và dữ liệu benchmark. Reranker
hiện rule-based; có thể thay bằng cross-encoder. Cần bổ sung feedback loop,
human review cho high-impact answers và regression set lớn hơn trước production.
