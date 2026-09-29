# Acceptance Matrix

| Yêu cầu trong `SUBJECT.md` | Bằng chứng | Trạng thái |
|---|---|---|
| Docker Compose khởi chạy service | `docker-compose.yml`, API/frontend Dockerfile; Compose config và smoke test API | API PASS; frontend Compose runner đang xác nhận |
| Upload PDF, TXT, DOCX | `app/config/settings.py` (`ALLOWED_EXTENSIONS`), `app/api/routers/documents.py` | PASS |
| Extract và clean dữ liệu | `app/ingestion/extract_service.py`, `app/ingestion/normalize_service.py` | PASS |
| Chunk dữ liệu | `NormalizeService.chunk_elements`; unit test trong `tests/test_core_components.py` | PASS |
| Tạo embedding | `app/retrieval/embedding_service.py`; cấu hình `EMBEDDING_MODEL`, `EMBEDDING_DIM` | PASS |
| Lưu vector + metadata | `app/repositories/chunk_repo.py`, PostgreSQL/pgvector trong Compose | PASS |
| `GET /health` | `app/main.py`; test `test_required_routes_and_health_contract` | PASS |
| `POST /documents` | Router `/documents` và alias `/api/documents`; upload trả trạng thái queued | PASS |
| `POST /query` | `app/api/routers/query.py`, `QueryResponse` bắt buộc `answer` + `sources` | PASS |
| Retrieval top-k | `app/retrieval/retrieval_service.py`, `TOP_K` trong environment | PASS |
| Grounded answer + source | `app/retrieval/rag_service.py`, `EvidenceService`, source citation schema | PASS |
| Prompt policy tách khỏi business logic | `app/config/prompts.py`; prompt version `rag-grounded-v1` | PASS |
| Không hard-code config business | `app/config/constants.py`, `app/config/settings.py`, `.env.example` | PASS |
| Dockerfile, Compose, env template | Ba file deliverable ở root | PASS |
| CI lint → test → Docker build | `.github/workflows/ci.yml`; local CI-equivalent đã chạy | PASS local; runner GitHub đang chạy commit mới |
| Frontend production build | `frontend/Dockerfile`, `frontend/package.json`, CI job `frontend` | Đã bổ sung; `npm run build` đạt |
| Unit test | `tests/test_core_components.py`, test report: 22 passed | PASS |
| API test | `tests/test_api.py`: health, upload hợp lệ/không hỗ trợ, query hợp lệ/rỗng/không có dữ liệu | PASS |
| Retrieval verification 5–10 câu | [retrieval_verification.csv](retrieval_verification.csv): 10/10 pass | PASS |
| README | `README.md` root và [submission README](README.md) | PASS |
| Architecture document | `docs/architecture.md` và [bản trình bày](architecture.md) | PASS |
| Không commit secret thật | `.env.example` chỉ chứa placeholder; `.env` không nằm trong deliverable | PASS |
| Naming/docstring/software quality >90 | `pyproject.toml`, `tools/quality_gate.py`; kết quả 100/100 | PASS |

## Bonus đã có

- Hybrid dense + lexical retrieval.
- Evidence reranking/gating.
- Background worker cho ingestion.
- OCR routing và provenance theo page/figure.
- MinIO lưu raw file và visual evidence.
- Benchmark SynthDocQA trong `evaluation/benchmark_summary.md`.
