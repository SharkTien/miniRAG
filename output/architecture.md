# Kiến trúc hệ thống hiện tại

## 1. Sơ đồ tổng thể

```text
Frontend / CLI
     │
     ├── POST /api/documents ──► FastAPI
     │                              ├── MinIO: file gốc, crop, page snapshot
     │                              └── PostgreSQL: document state + metadata
     │                                      │
     │                              background worker
     │                                      │
     │                    extract/layout → OCR → clean → semantic normalize
     │                                      ↓
     │                              chunk → embedding → pgvector
     │
     └── POST /api/query ──► query planner
                                ↓
                      BM25/full-text + dense vector retrieval
                                ↓
                 document identity + evidence reranking/gating
                                ↓
                  grounded NVIDIA-compatible LLM
                                ↓
                          answer + source citations
```

## 2. Luồng ingestion

1. Upload API kiểm tra phần mở rộng, kích thước và SHA-256; lưu file vào MinIO.
2. PostgreSQL tạo document ở trạng thái `queued`.
3. Worker claim nhiều document bằng cơ chế khóa hàng và `SKIP LOCKED`.
4. PDF có lớp chữ được đọc bằng Docling. PDF scan/ảnh được định tuyến tới NVIDIA NeMo Retriever OCR v2; kết quả giữ page, bounding box và confidence.
5. `NormalizeService` loại ký tự điều khiển, chuẩn hóa khoảng trắng, giữ ranh giới trang/section và tạo chunk.
6. Semantic normalization NVIDIA chạy theo cửa sổ trang. Request có timeout 30 giây, tối đa một retry và deadline toàn bước 45 giây; nếu thất bại, hệ thống giữ OCR gốc để job không bị treo.
7. Embedding được tạo theo batch và lưu vào PostgreSQL/pgvector cùng metadata.
8. Document chuyển `processed`; lỗi embedding hoặc extract chuyển `failed`. Xóa tài liệu đang chạy sẽ đặt `cancelled` trước khi xóa.

## 3. Luồng retrieval và trả lời

1. Với hội thoại, API lấy các lượt trước và bộ phân giải tham chiếu viết lại câu hỏi ngắn thành truy vấn độc lập; câu hỏi gốc vẫn được giữ để sinh câu trả lời.
2. Query planner giữ truy vấn độc lập, tạo biến thể lexical và nhận diện câu hỏi có cấu trúc.
3. Chunk repository kết hợp PostgreSQL full-text/BM25 với dense vector search; candidate pool được mở rộng trước rerank.
4. EvidenceService tính topical relevance, entity match, constraint match, answerability và query compatibility.
5. RagService lọc theo document identity, score distribution, câu hỏi/điều kiện trả lời và loại chunk nhiễu.
6. Context được giới hạn kích thước, giữ metadata phạm vi của từng nhánh chính sách và gửi tới NVIDIA-compatible LLM.
7. Response bắt buộc có `answer` và `sources`; streaming gửi token trước, metadata nguồn sau.

## 4. Metadata tối thiểu

Mỗi chunk lưu `document_id`, `chunk_id`, `file_name`, `content`, `embedding_model`, `created_at` và bổ sung `chunk_index`, `page_start`, `page_end`, `section`, `chunk_type`, `extraction_method`, `ocr_confidence`, `source_locator`, visual evidence nếu có.

## 5. Thành phần và lý do chọn

| Thành phần | Vai trò |
|---|---|
| FastAPI | API, schema validation và streaming |
| PostgreSQL + pgvector | Metadata, hội thoại, chunk và vector trong cùng hệ quản trị |
| MinIO | Lưu file gốc và bằng chứng hình ảnh |
| Docling | Đọc PDF có lớp chữ và bố cục Office |
| NVIDIA NeMo Retriever OCR v2 | OCR cho scan/ảnh, trả vùng chữ và confidence |
| NVIDIA NIM | Embedding, chuẩn hóa ngữ nghĩa và sinh câu trả lời theo cấu hình môi trường |
| Worker PostgreSQL queue | Tách ingestion nặng khỏi request upload |
| React + Vite + Nginx | Frontend production |

## 6. Cấu hình

Các giá trị `DATABASE_URL`, `EMBEDDING_MODEL`, `LLM_MODEL`, `NIM_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`, `SIMILARITY_THRESHOLD`, `NIM_REQUEST_TIMEOUT_SECONDS` và các tham số OCR/NIM được đọc từ environment hoặc `.env`.

## 7. Giới hạn và hướng tiếp theo

- Hybrid retrieval và reranker hiện deterministic; cross-encoder có thể cải thiện các câu hỏi mơ hồ.
- Visual crop/page snapshot được lưu làm evidence lazy; chưa phải index figure/annotation độc lập cho mọi tài liệu.
- Cần thêm test regression cho document identity và score distribution trên bộ tài liệu production.
- CI runner phụ thuộc secret/API key và khả năng pull image; local pass không thay thế xác nhận từ GitHub.

## 8. Vòng lặp nghiên cứu dữ liệu

`docs/report.md` là hồ sơ nghiên cứu đi kèm kiến trúc, dùng để kiểm chứng các
quyết định ở lớp ingestion và retrieval. Quy trình gồm: phân loại tài liệu và
loại dữ liệu, đo chất lượng sau extract/OCR, chạy benchmark theo Table/Form/
Figure/Annotation/Text, phân tích lỗi rồi đưa cấu hình có kết quả tốt hơn trở
vào production. Benchmark cao nhất đạt document hit 90,65%, content hit 41,33%
và assertion pass 23,72% trên 5 PDF SynthDocQA; các điểm này không được hiểu là
điểm bảo đảm cho mọi tài liệu upload. Hai hướng còn cần mở rộng cho production
là chỉ mục hình độc lập và OCR vùng annotation.
