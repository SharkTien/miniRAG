# Ma trận acceptance criteria

**Đối chiếu source:** commit `05185d9`
**Ngày:** 30/09/2026

| Tiêu chí | Bằng chứng trong repository | Trạng thái |
|---|---|---|
| Service chạy bằng Docker Compose | `docker-compose.yml`; Compose config hợp lệ; stack local đang chạy | ✅ Đạt |
| Upload PDF, TXT, DOCX | `ALLOWED_EXTENSIONS`; `POST /api/documents` | ✅ Đạt |
| Extract và chunk | `app/ingestion/extract_service.py`, `normalize_service.py` | ✅ Đạt |
| Chunk tạo embedding | `EmbeddingService`; ingestion worker | ✅ Đạt |
| Lưu vector và metadata | PostgreSQL + pgvector; `ChunkRepository.save_chunks_batch` | ✅ Đạt |
| Query API hoạt động | `POST /query`, `/api/query` | ✅ Đạt |
| Answer có source | `QueryResponse.sources`; `RagService` tạo citation | ✅ Đạt |
| Configuration tách khỏi business logic | `app/config/settings.py`, environment variables | ✅ Đạt |
| Có `.env.example` | `.env.example` | ✅ Đạt |
| Không commit secret thật | `.env` không nằm trong source commit; template dùng placeholder | ✅ Đạt |
| Có unit test | `tests/test_core_components.py`, `tests/test_evidence_service.py` | ✅ 22 test đạt |
| Có API test | `tests/test_api.py` | ✅ Đạt |
| CI pipeline | `.github/workflows/ci.yml`: lint, test, frontend build, Docker smoke | ⏳ Chờ runner |
| Basic retrieval verification | `retrieval_verification.csv`, 10 câu hỏi | ✅ Có tập kiểm tra |
| README | `README.md` root và hồ sơ trong `output` | ✅ Đạt |
| Architecture document | `docs/architecture.md`, `output/architecture.md` | ✅ Đạt |

## Bằng chứng nghiên cứu dữ liệu

Phần nghiên cứu dữ liệu được đánh giá trong tiểu mục của Data ingestion & processing, không tính thêm ngoài tổng 100%: `docs/report.md` ghi rõ khảo sát 5 PDF/877 câu hỏi, phân loại Table/Form/Figure/Annotation/Text, các phương án đã thử, chỉ số trước/sau, failure analysis và quyết định đưa vào production.

## Ghi chú về CI

Local quality gate hiện đạt **98,8/100**. GitHub Actions của commit `05185d9` đang ở trạng thái `in_progress` tại thời điểm lập hồ sơ; chỉ đánh dấu “CI pass” sau khi runner hoàn tất thành công.
