# Báo cáo milestone, acceptance criteria và bonus

**Dự án:** Mini RAG Service
**Ngày:** 30/09/2026
**Source commit:** `05185d9`

## 10. Milestones

### Milestone 1 — Data Pipeline

**Đã hoàn thành:**

- Document upload một hoặc nhiều file.
- Kiểm tra định dạng, kích thước và SHA-256.
- Lưu file gốc vào MinIO.
- Extract PDF/TXT/DOCX và các định dạng mở rộng.
- OCR scan/ảnh bằng NVIDIA NeMo Retriever OCR v2.
- Làm sạch text, giữ page/section/bounding box và provenance.
- Semantic normalization NVIDIA có timeout, retry giới hạn và fallback OCR.
- Chunking có cấu trúc.
- Tạo embedding theo batch.
- Lưu vector và metadata vào PostgreSQL + pgvector.
- Worker xử lý nền, batch nhiều document và tự khôi phục document bị gián đoạn.
- Nghiên cứu và lập hồ sơ dữ liệu trong [`docs/report.md`](../docs/report.md):
  phân loại Table/Form/Figure/Annotation/Text, tạo tập câu hỏi theo loại dữ liệu,
  benchmark từng phương án OCR/chunk/retrieval và ghi rõ quyết định giữ/loại.

**Expected result:**

```text
Document → extract/OCR → clean/normalize → chunk → embedding → Vector Database
```

### Milestone 2 — RAG API

**Đã hoàn thành:**

- `GET /health`.
- `POST /documents` và alias `/api/documents`.
- `POST /query`, `/api/query`.
- Streaming query qua `/query/stream` và `/api/query/stream`.
- Query planner tạo biến thể lexical có kiểm soát.
- Hybrid full-text/BM25 + dense vector retrieval.
- Candidate multiplier và adjacent chunk recovery.
- Evidence reranking theo topical relevance, entity, constraint, answerability.
- Document identity filter và score-distribution filter.
- Grounded prompt tiếng Việt, không trộn các nhánh điều kiện.
- Response luôn có source citation.

**Expected result:**

```text
Question → query planning → hybrid retrieval → evidence gate/rerank
         → NVIDIA-compatible LLM → Answer + Source
```

### Milestone 3 — Docker & CI

**Đã hoàn thành:**

- Dockerfile cho API/worker.
- Docker Compose cho API, worker, PostgreSQL + pgvector, MinIO và frontend.
- Environment configuration trong `.env.example`.
- Frontend production build bằng Vite/Nginx.
- CI GitHub Actions gồm compile, ruff, quality gate, test, frontend build, Docker build và Compose smoke test.
- Local quality gate đạt 98,8/100.
- GitHub Actions commit mới nhất đang chạy tại thời điểm lập báo cáo.

### Milestone 4 — Documentation & Demo

**Đã hoàn thành:**

- README root và bộ hồ sơ `output`.
- `docs/architecture.md`, `docs/pipeline.md`, `docs/ocr_deployment.md`.
- API examples, demo script và requirements traceability.
- Basic retrieval verification 10 câu.
- Báo cáo PDF milestone/acceptance/evaluation/bonus.
- Frontend demo upload, theo dõi tiến độ, đổi tên, hủy/xóa tài liệu và query streaming.

## 11. Acceptance Criteria

| # | Tiêu chí | Trạng thái |
|---:|---|---|
| 1 | Service chạy được bằng Docker Compose | ✅ |
| 2 | Upload PDF, TXT và DOCX | ✅ |
| 3 | Document được extract và chunk | ✅ |
| 4 | Chunk được tạo embedding | ✅ |
| 5 | Vector và metadata được lưu vào database | ✅ |
| 6 | Query API hoạt động | ✅ |
| 7 | Câu trả lời có source | ✅ |
| 8 | Configuration tách khỏi business logic | ✅ |
| 9 | Có `.env.example` | ✅ |
| 10 | Không commit secret thật | ✅ |
| 11 | Có unit test | ✅ — 22 test |
| 12 | Có API test | ✅ |
| 13 | CI pipeline chạy thành công | ⏳ — commit mới đang `in_progress` |
| 14 | Có basic retrieval verification | ✅ |
| 15 | Có README | ✅ |
| 16 | Có architecture document | ✅ |

Acceptance criteria chỉ được đánh dấu hoàn toàn khi CI runner của commit hiện tại kết thúc thành công.

## 12. Evaluation Criteria

| Hạng mục | Trọng số | Tự đánh giá | Căn cứ |
|---|---:|---:|---|
| Data ingestion & processing | 20% | 19/20 | 12 điểm cho ingestion; 8 điểm cho nghiên cứu, chuẩn hóa và kiểm soát chất lượng dữ liệu trong `docs/report.md` |
| Vector Database & Retrieval | 20% | 19/20 | pgvector, full-text/BM25, dense, candidate pool, evidence filter |
| AI / RAG Integration | 15% | 14/15 | NVIDIA OCR/NIM, grounded prompt, streaming, source citation |
| Docker & Environment | 15% | 15/15 | Dockerfile, Compose, env, local stack đang chạy |
| CI | 10% | 9/10 | Workflow đầy đủ; runner commit mới đang chờ kết quả |
| Testing | 10% | 10/10 | 22 test local, quality gate pass |
| Documentation & Demo | 10% | 10/10 | README, architecture, API, demo, PDF và retrieval set |
| **Tổng tạm tính** | **100%** | **96/100** | Điểm tự đánh giá, không thay thế điểm reviewer |

### Tiểu mục data research trong 20% ingestion

Đây là phần cần nhấn mạnh khi trình bày với vai trò data engineer/data scientist:

- Khảo sát cấu trúc dữ liệu trước khi chọn parser: PDF có text layer, PDF scan, bảng, biểu mẫu, hình và annotation.
- Xây dựng tập đánh giá theo loại dữ liệu thay vì chỉ đo một điểm chung.
- So sánh baseline với OCR toàn trang, candidate multiplier, hybrid dense + lexical, table routing, parent expansion, visual-element retrieval và annotation region.
- Đo `document hit`, `content hit` và `assertion pass`; phân tích failure theo bảng, hình, annotation và text.
- Ghi lại lý do giữ hoặc loại từng phương án, giới hạn benchmark và điểm chưa thể suy rộng sang production.
- Đưa kết quả nghiên cứu trở lại pipeline bằng các quyết định có kiểm chứng: OCR toàn trang, hybrid retrieval, candidate pool rộng, evidence reranking và provenance theo trang.

Reviewer cũng có thể đánh giá khả năng research, debug, đọc documentation, chia nhỏ vấn đề, chất lượng commit, tổ chức code, giải thích quyết định kỹ thuật, xử lý blocker và tiếp nhận feedback. Các điểm này được thể hiện qua `docs/report.md`, lịch sử commit, test report và traceability.

## 13. Bonus

| Bonus | Trạng thái | Bằng chứng |
|---|---|---|
| Hybrid Search | ✅ | `ChunkRepository.vector_search` |
| Full-text kết hợp Vector Search | ✅ | PostgreSQL `to_tsquery` + pgvector |
| Reranking | ✅ | `EvidenceService` |
| Hỗ trợ CSV/XLSX | ✅ | `ALLOWED_EXTENSIONS`, extraction routing |
| Background worker ingestion | ✅ | `app/worker.py`, PostgreSQL queue |
| Retry khi ingestion lỗi | ✅ | NIM retry/fallback, worker recovery/requeue |
| API xóa tài liệu | ✅ | `DELETE /api/documents/{document_id}` |
| API xem danh sách tài liệu | ✅ | `GET /api/documents` |
| Tối ưu retrieval | ✅ | query planner, candidate multiplier, score distribution, identity filter, source dedup |
| Tên hiển thị và đổi tên tài liệu | ✅ bổ sung | upload `display_name`, `PATCH /documents/{id}` |
| Hủy job đang xử lý | ✅ bổ sung | `POST /documents/{id}/cancel`, delete cooperative cancellation |
| Query streaming | ✅ bổ sung | `/query/stream` |
| Frontend production | ✅ bổ sung | React/Vite/Nginx, CI build |
| Data research dossier và benchmark theo loại dữ liệu | ✅ bổ sung | `docs/report.md`, `evaluation/benchmark_summary.md`, các artifact benchmark |

Bonus chỉ có giá trị sau khi các yêu cầu cơ bản ổn định. Với các bonus phụ thuộc dịch vụ hosted, cần xác nhận thêm trong môi trường triển khai thật.

## Kết luận

Bốn milestone đã có source và bằng chứng kiểm tra tương ứng. Acceptance criteria đã đạt về mặt mã nguồn và local verification; mục CI cần chờ runner GitHub của commit `05185d9` hoàn tất để đóng dấu cuối cùng. Hệ thống đã sẵn sàng cho demo kỹ thuật và tiếp tục cần benchmark regression trên tài liệu production trước khi dùng ở quy mô lớn.
