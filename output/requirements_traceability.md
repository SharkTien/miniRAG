# Đối chiếu mục 2 và mục 3

Tài liệu này đối chiếu trực tiếp các yêu cầu trong `SUBJECT.md` với phần đã
triển khai. Trạng thái `Đạt` nghĩa là đã có trong mã nguồn và có thể kiểm tra;
`Đã cấu hình` nghĩa là workflow đã khai báo nhưng cần một runner CI thực thi để
xác nhận kết quả.

## Mục 2 — Mục tiêu

| Yêu cầu | Bằng chứng | Trạng thái |
|---|---|---|
| Document → Extract/Clean → Chunking → Embedding → Vector DB → Retrieval → LLM → Answer + Source | [architecture.md](architecture.md), `app/ingestion`, `app/retrieval` | Đạt |
| Build | `Dockerfile`, `.github/workflows/ci.yml` | Đạt — Docker build đã chạy thành công cục bộ |
| Test | `tests/`, `.github/workflows/ci.yml` | Đạt ở lần kiểm tra ghi trong [test_report.md](test_report.md) |
| Containerize | `Dockerfile`, `docker-compose.yml` | Đạt |
| Run | `docker compose up -d --build` trong README | Đạt theo cấu hình Compose |
| CI khi có thay đổi | `.github/workflows/ci.yml` chạy khi push/pull request | Đã cấu hình; chuỗi tương đương runner đã đạt cục bộ |

CI có thêm job build frontend bằng Node.js 22 (`npm ci` và `npm run build`). Job
Docker khởi động cả API và frontend, sau đó kiểm tra `/health` và trang web.

## Mục 3 — Functional Requirements

### 3.1 Document Ingestion

Đạt: hệ thống nhận PDF, TXT và DOCX; kiểm tra phần mở rộng và kích thước; lưu
file gốc; worker thực hiện trích xuất/OCR, làm sạch, chunk, embedding và lưu
vector cùng metadata vào PostgreSQL/pgvector.

Metadata tối thiểu được lưu gồm `document_id`, `file_name`, `chunk_id`,
`content`, `embedding_model` và `created_at`. Metadata bổ sung gồm trang,
section, loại chunk, độ tin cậy OCR và bằng chứng hình ảnh.

### 3.2 Health Check API

```http
GET /health
```

Response khi tiến trình API hoạt động:

```json
{"status": "ok"}
```

Đây là kiểm tra tiến trình API. Trạng thái PostgreSQL và MinIO được kiểm tra
riêng bằng healthcheck của Docker Compose; endpoint này chưa phải readiness
check tổng hợp của mọi phụ thuộc.

### 3.3 Document Upload API

```http
POST /documents
```

API trả trạng thái `queued` ngay sau khi lưu file. Worker xử lý các bước
extract, chunk, embedding và lưu database ở chế độ nền. Vì vậy `total_chunks`
ban đầu bằng `0`; sau khi hoàn tất, lấy kết quả tại:

```http
GET /documents/{document_id}/extraction
```

Response sau xử lý có `document_id`, `file_name`, `status` và `total_chunks`.

### 3.4 Query API

```http
POST /query
```

API trả `answer` và danh sách `sources`. Mỗi source có tối thiểu `file_name` và
`chunk_id`, đồng thời có thể có trang, điểm tương đồng và đoạn trích.

Nếu không có bằng chứng phù hợp, hệ thống từ chối hoặc báo thiếu dữ liệu thay
vì sinh câu trả lời dựa trên nội dung không xác định được nguồn.

## Mục 4 — Data & Retrieval

Luồng thực tế là:

```text
Question → Embedding → hybrid vector/lexical search → Top-K chunks
         → evidence gate/rerank → grounded LLM → Answer + Source
```

PostgreSQL với pgvector lưu vector, nội dung chunk và metadata. Các cấu hình
`DATABASE_URL`, `EMBEDDING_MODEL`, `LLM_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP`,
`TOP_K` và `SIMILARITY_THRESHOLD` được đọc từ biến môi trường trong
`app/config/settings.py`; không dùng trực tiếp trong business logic.
`.env.example` và `docker-compose.yml` cung cấp các giá trị mẫu.
