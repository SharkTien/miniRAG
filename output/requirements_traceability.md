# Truy vết yêu cầu tới source

## Mục 2 — Mục tiêu

| Yêu cầu | Source/bằng chứng | Kết luận |
|---|---|---|
| Document → extract → chunk → embedding → vector DB | `app/ingestion`, `app/repositories/chunk_repo.py` | Đạt |
| Question → retrieval → LLM → answer + source | `app/retrieval/rag_service.py`, `app/api/routers/query.py` | Đạt |
| Build, test, containerize, run | `Dockerfile`, `docker-compose.yml`, CI | Đạt local |

## Năng lực nghiên cứu dữ liệu

Ngoài luồng kỹ thuật, repository có hồ sơ nghiên cứu tại [`docs/report.md`](../docs/report.md). Hồ sơ này mô tả cách khảo sát dữ liệu, phân loại theo loại câu hỏi, thiết kế benchmark, so sánh phương án OCR/chunk/retrieval, phân tích lỗi và chuyển kết quả thành quyết định cấu hình. Đây là bằng chứng cho tiểu mục 8 điểm nằm trong trọng số Data ingestion & processing, không phải một hạng mục cộng thêm làm thay đổi tổng 100%.

## Mục 3 — Functional Requirements

### 3.1 Document ingestion

`DocumentService.process_upload` kiểm tra extension, kích thước, SHA-256, lưu MinIO và tạo document record. Worker gọi `ExtractService`, làm sạch, chunk, embedding và lưu vector/metadata. Upload không chờ toàn bộ pipeline mà trả `queued`.

### 3.2 Health check

`GET /health` trả `{"status":"ok"}`. PostgreSQL và MinIO có health/dependency checks riêng trong Compose.

### 3.3 Document upload API

`POST /documents` và `POST /api/documents` nhận một hoặc nhiều file. Có thể truyền `display_name`/`display_names`. Response trả document id, tên hiển thị, tên gốc, trạng thái và số chunk ban đầu.

### 3.4 Query API

`POST /query` và `/api/query` trả `answer` cùng `sources`. `POST /query/stream` và `/api/query/stream` trả token streaming rồi metadata nguồn. Không có evidence thì không được sinh câu trả lời không nguồn.

## Mục 4 — Data & Retrieval

PostgreSQL + pgvector; lexical full-text search dùng PostgreSQL `to_tsquery`/BM25 pass; dense search dùng pgvector; candidate pool được rerank bằng EvidenceService. Cấu hình tách trong `app/config/settings.py` và `.env.example`.

## Mục 5 — Containerization

Có API, worker, frontend, PostgreSQL + pgvector và MinIO trong Compose. Có `Dockerfile`, frontend Dockerfile, `docker-compose.yml`, `.env.example`; secret thật không nằm trong source commit.

## Mục 6 — CI

`.github/workflows/ci.yml` chạy trên push/pull request: compile, ruff, quality gate, test, frontend build, Docker build và Compose smoke test. Commit mới nhất đang được GitHub Actions xác nhận tại thời điểm báo cáo.

## Mục 7 — Testing

Có unit test cleaning/chunking/config/evidence, API test health/upload/query/error, và bảng retrieval verification 10 câu.
