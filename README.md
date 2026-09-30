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
- pgAdmin tùy chọn tại `http://localhost:41874` để xem PostgreSQL/pgvector.
- MinIO cho file gốc và bằng chứng trực quan.
- React/Vite và Nginx cho giao diện production.
- GitHub Actions cho lint, test, build và smoke test.

### Mô hình mặc định

| Thành phần | Mô hình hoặc công cụ | Vai trò |
|---|---|---|
| Embedding | `nvidia/nemotron-3-embed-1b` (2048 chiều) | Biến câu hỏi và từng đoạn văn thành véc-tơ để tìm kiếm ngữ nghĩa. |
| Mô hình trả lời và chuẩn hóa | `meta/llama-3.2-11b-vision-instruct` qua NVIDIA NIM | Tạo câu trả lời tiếng Việt và chuẩn hóa đoạn OCR có độ tin cậy thấp từ các bằng chứng đã chọn. |
| OCR tài liệu | `nvidia/nemotron-ocr-v2` qua NVIDIA NeMo Retriever OCR | Đọc PDF scan, JPG và PNG, đồng thời trả tọa độ vùng chữ và độ tin cậy. |
| Phân tích bố cục | Docling; RAGFlow DeepDoc là chế độ tùy chọn | Giữ trang, mục, bảng, hình và vị trí của đoạn trích. |

Các mô hình trên chỉ là giá trị mặc định. Có thể thay đổi bằng các biến
`EMBEDDING_MODEL`, `LLM_MODEL` (hoặc `NIM_MODEL`), `NVIDIA_OCR_MODEL` và các
biến định tuyến OCR trong `.env`, không cần sửa mã nghiệp vụ.

Khi dùng endpoint NVIDIA hosted, tài khoản nhà phát triển được dùng các
endpoint miễn phí cho mục đích thử nghiệm. NVIDIA áp dụng giới hạn theo từng
mô hình và tải hệ thống, không có một số token miễn phí cố định dùng chung cho
tất cả mô hình. Dùng self-hosted NIM trên hạ tầng NVIDIA nếu cần kiểm soát chi
phí và lưu lượng ổn định hơn.

### Phương pháp được dùng trong RAG

Pipeline đầy đủ của hệ thống là:

```text
tài liệu
  → trích xuất văn bản/bố cục (Docling hoặc NVIDIA NeMo Retriever OCR v2)
  → làm sạch và chuẩn hóa có kiểm tra nguồn
  → chia đoạn theo cấu trúc và ngữ nghĩa
  → embedding nvidia/nemotron-3-embed-1b
  → PostgreSQL + pgvector
  → truy hồi kết hợp véc-tơ và từ khóa
  → lọc theo phân bố điểm + xếp hạng bằng chứng
  → LLM tạo câu trả lời có nguồn
```

Các bước truy hồi và kiểm soát bằng chứng:

1. **Lập kế hoạch câu hỏi:** chuẩn hóa cách viết tiếng Việt, tạo biến thể tìm
   kiếm và nhận diện câu hỏi cần khớp chính xác, câu hỏi so sánh hoặc câu hỏi
   tổng hợp.
2. **Truy hồi kết hợp:** tìm kiếm gần đúng bằng cosine similarity trên
   `pgvector`, tìm kiếm toàn văn PostgreSQL và chấm lại ứng viên bằng BM25.
   Hai tín hiệu được hợp nhất bằng thứ hạng tương hỗ (RRF), sau đó tính điểm
   kết hợp với trọng số 0,65 cho ngữ nghĩa và 0,35 cho BM25.
3. **Khớp chính xác:** câu hỏi có cụm từ hoặc giá trị cụ thể được tìm bằng
   cụm từ nguyên văn trước khi mở rộng sang tìm kiếm ngữ nghĩa.
4. **Lọc theo phân bố điểm:** lấy nhiều ứng viên hơn số kết quả cuối cùng,
   loại các đoạn có điểm thấp so với trung vị và độ phân tán của nhóm kết quả,
   rồi loại nội dung trùng lặp.
5. **Đánh giá bằng chứng:** xếp hạng lại theo độ phủ từ khóa, độ khớp cụm từ
   và điểm ngữ nghĩa; kiểm tra mức liên quan, độ bao phủ, tính nhất quán và
   khả năng trả lời. Khi thiếu bằng chứng, hệ thống từ chối hoặc nêu phần còn
   thiếu thay vì đoán.
6. **Sinh câu trả lời có căn cứ:** LLM chỉ nhận các đoạn đã qua cổng bằng
   chứng. Phản hồi luôn kèm tên tệp, mã đoạn, trang và thông tin định vị để
   người dùng kiểm tra lại nguồn.

Không phải mọi tài liệu đều gọi LLM. PDF có lớp chữ được đọc trực tiếp; LLM
chỉ tham gia khi cần sửa OCR/chuẩn hóa hoặc sinh câu trả lời cuối cùng.

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

## OCR và định tuyến mô hình NVIDIA

Pipeline mặc định dùng `DOCUMENT_PARSER_ENGINE=auto`:

1. PDF có lớp chữ: Docling đọc trực tiếp, không OCR và không gọi mô hình OCR.
2. PDF scan/JPG/PNG: render theo trang và gửi tới
   `nvidia/nemotron-ocr-v2` tại NVIDIA NeMo Retriever OCR.
3. Kết quả OCR lưu văn bản, tọa độ vùng chữ và độ tin cậy để tạo provenance.
4. Chỉ khi cần sửa OCR hoặc chuẩn hóa cấu trúc, hệ thống mới gọi
   `meta/llama-3.2-11b-vision-instruct` qua NVIDIA NIM.
5. Nếu NVIDIA OCR không khả dụng, tài liệu được đánh dấu lỗi để tránh âm thầm
   chuyển sang Tesseract hoặc PP-OCR cục bộ làm thay đổi kết quả benchmark.

Kết quả lưu cả `raw_ocr_text` và `ocr_text` sau hậu xử lý. Metadata có parser, confidence, thời gian extraction và provider normalization để theo dõi chất lượng/latency.

Các chế độ vận hành:

- `DOCUMENT_PARSER_ENGINE=auto`: khuyến nghị cho luồng tiếng Việt hỗn hợp.
- `DOCUMENT_PARSER_ENGINE=nvidia_ocr`: ép NVIDIA NeMo Retriever OCR v2.
- `DOCUMENT_PARSER_ENGINE=ragflow`: DeepDoc cho tài liệu có layout/bảng phức tạp.
- `DOCUMENT_PARSER_ENGINE=docling`: pipeline Docling đầy đủ.
- `SEMANTIC_NORMALIZER=nvidia`: dùng NVIDIA NIM cho chuẩn hóa; đây là mặc định.

Các biến tuning chính:

```dotenv
LOCAL_OCR_DPI=180
SEMANTIC_NORMALIZER=nvidia
SEMANTIC_NORMALIZE_OCR_ONLY=true
SEMANTIC_OCR_CONFIDENCE_GATE=0.93
NVIDIA_OCR_BASE_URL=https://ai.api.nvidia.com/v1/cv/nvidia/nemotron-ocr-v2
NVIDIA_OCR_MODEL=nvidia/nemotron-ocr-v2
NVIDIA_OCR_BATCH_SIZE=2
NVIDIA_OCR_CONCURRENCY=4
INGESTION_WORKER_CONCURRENCY=2
```

Worker nhận tối đa `INGESTION_WORKER_CONCURRENCY` tài liệu trong một lượt và
xử lý đồng thời. Mỗi tài liệu tiếp tục được chia trang thành các lô OCR, vì
vậy nhiều tài liệu và nhiều trang không còn bị xếp hàng tuần tự trong một
worker.

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
