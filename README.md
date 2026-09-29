# NTC Document RAG — Mini RAG Service

## Tổng quan

Mini RAG Service xử lý PDF, TXT, DOCX và ảnh/Office phổ biến theo luồng:

```text
upload → extract/OCR → clean + chunk → embedding → pgvector
                                              ↓
question → hybrid retrieval + evidence gate → grounded answer + sources
```

PDF scan và tài liệu có bảng/hình được giữ provenance theo trang. Crop hình và
snapshot trang được lưu lazy trong MinIO để câu hỏi về figure/annotation có thể
được gửi tới vision model khi cần.

Chi tiết kiến trúc: [`docs/architecture.md`](docs/architecture.md).

## Cấu trúc backend

```text
app/
├── api/          # FastAPI routers và dependency injection
├── config/       # constants, prompts, settings, database, object storage
├── ingestion/    # upload, extract/OCR, normalize, chunking
├── retrieval/    # embedding, vector/hybrid search, evidence, RAG
├── repositories/ # PostgreSQL/pgvector data access
├── schemas/      # request/response models
├── main.py       # API entrypoint
└── worker.py     # background ingestion worker
tests/            # unit và API tests
evaluation/       # retrieval verification và benchmark
docs/             # architecture documentation
```

Backend có thể kiểm thử bằng terminal, cURL hoặc Swagger tại `/docs`; frontend
production được chạy riêng trong service Nginx.

## Công nghệ sử dụng

- FastAPI và Python 3.12 cho API/worker.
- PostgreSQL + pgvector cho metadata, chunk và embedding.
- MinIO cho file gốc và bằng chứng trực quan.
- React/Vite và Nginx cho giao diện production.
- GitHub Actions cho lint, test, build và smoke test.

## Chạy bằng Docker

```bash
cp .env.example .env
# Điền POSTGRES_PASSWORD, MINIO_ROOT_PASSWORD và NGC_API_KEY (nếu dùng model hosted)
docker compose up -d --build
```

- API: http://localhost:41873
- Frontend: http://localhost:4173
- Swagger: http://localhost:41873/docs
- MinIO Console: http://localhost:41901
- Health: http://localhost:41873/health

Frontend production được phục vụ qua Nginx và chuyển tiếp các request API tới
backend. API cũng có thể kiểm thử độc lập bằng cURL, Swagger hoặc test
terminal. MinIO Console chạy tại `41901`; có thể đổi bằng
`APP_PORT` và `MINIO_CONSOLE_PORT` trong `.env`. Tài liệu upload tối đa 200
MB/file, được lưu tại bucket `ntc-documents` dưới prefix `raw/<document-id>/`;
PostgreSQL chỉ lưu metadata, checksum SHA-256 và trạng thái ingestion.

Worker `ntc_document_rag_worker` xử lý tài liệu từ hàng đợi PostgreSQL. Nếu worker bị restart, tài liệu ở trạng thái `queued` vẫn được xử lý tiếp. Backend không có hệ thống tài khoản; tin nhắn được lưu theo từng `conversation_id` trong PostgreSQL.

Thư mục `documents/NTC_doc` là nguồn tài liệu ban đầu; MVP này chưa tự động nạp hàng loạt để tránh upload ngoài ý muốn. Bước tiếp theo có thể thêm job bulk-ingestion có dry-run, dedup theo SHA-256 và trạng thái xử lý chunk/embedding.

## OCR tiếng Việt và định tuyến model

Pipeline mặc định dùng `DOCUMENT_PARSER_ENGINE=auto`:

1. PDF có lớp text: Docling đọc text trực tiếp, không OCR và không gọi LLM.
2. PDF scan/JPG/PNG: render ở 180 DPI, chạy Tesseract `vie+eng` song song theo trang.
3. Nếu Tesseract lỗi: fallback sang PP-OCRv6 GPU local tại `http://host.docker.internal:8012`.
4. Nếu confidence Tesseract dưới `0.93`: sửa lỗi OCR bằng Qwen local tại cổng `8027`.
5. Nếu Qwen local lỗi và có `NGC_API_KEY`: fallback NVIDIA NIM hosted API; nếu cả hai lỗi thì giữ nguyên kết quả rule-based.

Kết quả lưu cả `raw_ocr_text` và `ocr_text` sau hậu xử lý. Metadata có parser, confidence, thời gian extraction và provider normalization để theo dõi chất lượng/latency.

Các chế độ vận hành:

- `DOCUMENT_PARSER_ENGINE=auto`: khuyến nghị cho luồng tiếng Việt hỗn hợp.
- `DOCUMENT_PARSER_ENGINE=tesseract`: ép OCR Tesseract trực tiếp.
- `DOCUMENT_PARSER_ENGINE=ppocr`: ép PP-OCRv6 local, phù hợp khi cần orientation/unwarping.
- `DOCUMENT_PARSER_ENGINE=ragflow`: DeepDoc cho tài liệu có layout/bảng phức tạp.
- `DOCUMENT_PARSER_ENGINE=docling`: pipeline Docling đầy đủ.
- `SEMANTIC_NORMALIZER=auto|local|nvidia|none`: chọn chiến lược sửa OCR/semantic.

Các biến tuning chính:

```dotenv
DOCLING_OCR_LANG=vie,eng
DOCLING_TESSERACT_PSM=3
LOCAL_OCR_DPI=180
TESSERACT_PAGE_CONCURRENCY=4
SEMANTIC_NORMALIZER=auto
SEMANTIC_NORMALIZE_OCR_ONLY=true
SEMANTIC_OCR_CONFIDENCE_GATE=0.93
```

Kiểm tra sau khi chạy:

```bash
docker compose ps --all
docker compose logs --tail=200 ntc_document_rag_worker
curl -fsS http://localhost:41873/health
```

## API chính

`GET /health` trả về `{"status":"ok"}`.

Upload một hoặc nhiều file (cả hai prefix đều được hỗ trợ):

```bash
curl -F 'files=@policy.pdf' http://localhost:41873/documents
```

Demo terminal end-to-end với file và câu hỏi tự chọn:

```bash
chmod +x scripts/demo_terminal.sh
scripts/demo_terminal.sh "/absolute/path/to/file.pdf" "Question in the target language"
```

The script uploads the file, waits for the worker to reach `processed`, creates
a conversation, sends the question, and prints the persisted conversation.

Truy vấn và nhận câu trả lời cùng nguồn:

```bash
curl -X POST http://localhost:41873/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Chính sách bảo hành là gì?","top_k":5}'
```

Response luôn có `answer` và `sources` (`file_name`, `chunk_id`, `page`,
`snippet`). Ingestion chạy qua worker; chỉ truy vấn tài liệu khi trạng thái là
`processed`.

## Kiểm tra và benchmark

```bash
# Unit/API tests (sau khi cài requirements-dev.txt)
pip install -r requirements.txt -r requirements-dev.txt
PYTHONPATH=. pytest -q tests

# Quality gate: naming, lint, public docstrings, tests, repository score
python tools/quality_gate.py

# Kiểm tra cú pháp và cấu hình compose
python -m compileall -q app tests
docker compose config --quiet
```

Benchmark SynthDocQA chỉ dùng 5 PDF cục bộ và các câu hỏi thuộc 5 file đó.
Báo cáo cải thiện và giới hạn được lưu tại
[`evaluation/benchmark_summary.md`](evaluation/benchmark_summary.md).

Quality gate dùng các chuẩn kiểm tra có thể tái lập: Ruff E/F/N, docstring cho
public class/function trong `app`, pytest và kiểm tra deliverable. Mức đạt là
`tối thiểu 90/100`; lần kiểm tra hiện tại đạt `100/100`.

## Giới hạn đã biết

- Chất lượng/latency phụ thuộc embedding và LLM endpoint được cấu hình.
- Snapshot trang làm tăng dung lượng MinIO; tắt bằng `PERSIST_PAGE_VISUALS=false`
  khi cần tiết kiệm storage.
- Reranker hiện là rule-based; nên bổ sung cross-encoder và feedback loop trước
  khi dùng cho quyết định có ảnh hưởng cao.

Chi tiết quyết định kỹ thuật và kế hoạch benchmark nằm tại
[`docs/ocr_deployment.md`](docs/ocr_deployment.md).
