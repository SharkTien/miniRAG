# Mini RAG Service — Submission Output

Đây là bộ hồ sơ trình bày và bằng chứng đối chiếu với `SUBJECT.md`. Source code
gốc vẫn nằm ở thư mục cha; các liên kết dưới đây dùng đường dẫn tương đối để
reviewer có thể kiểm tra trực tiếp.

## Kết luận ngắn

Project đáp ứng luồng chính:

```text
PDF/TXT/DOCX → extract/OCR → normalize/chunk → embedding → pgvector
                                                        ↓
Question → hybrid retrieval → evidence gate → grounded LLM → answer + sources
```

Kết quả kiểm tra tại thời điểm đóng gói:

```text
22 tests passed
ruff E9: All checks passed
compileall: passed
docker compose config --quiet: passed
frontend npm run build: passed
```

## Hồ sơ trong thư mục này

- [acceptance_matrix.md](acceptance_matrix.md): đối chiếu từng acceptance criterion và bằng chứng.
- [requirements_traceability.md](requirements_traceability.md): đối chiếu chi tiết mục 2 và mục 3 của `SUBJECT.md`.
- [architecture.md](architecture.md): kiến trúc, data flow và các quyết định kỹ thuật.
- [api_examples.md](api_examples.md): demo health, upload, query và các ca lỗi.
- [demo_script.md](demo_script.md): kịch bản demo 20–30 phút.
- [test_report.md](test_report.md): lệnh kiểm tra và kết quả reproducible.
- [retrieval_verification.csv](retrieval_verification.csv): 10 câu hỏi kiểm tra source retrieval.

## Các file deliverable chính ở root

- [README.md](../README.md)
- [Dockerfile](../Dockerfile)
- [docker-compose.yml](../docker-compose.yml)
- [.env.example](../.env.example)
- [CI workflow](../.github/workflows/ci.yml)
- [Frontend](../frontend/)
- [Architecture source](../docs/architecture.md)
- [Benchmark summary](../evaluation/benchmark_summary.md)

## Cách reviewer chạy nhanh

```bash
cp .env.example .env
# thay toàn bộ placeholder password/secret trong .env
docker compose up -d --build
curl -fsS http://localhost:41873/health
PYTHONPATH=. pytest -q tests
npm --prefix frontend ci
npm --prefix frontend run build
```

API không yêu cầu đăng nhập. Upload tạo trạng thái `queued`; worker xử lý
ingestion và query chỉ nên chạy sau khi document chuyển sang `processed`.
Frontend production được phục vụ qua Nginx tại cổng `FRONTEND_PORT` (mặc định
`4173`) và chuyển tiếp API tới backend.

Demo hoàn chỉnh với file và câu hỏi tự chọn:

```bash
chmod +x scripts/demo_terminal.sh
scripts/demo_terminal.sh "/absolute/path/to/file.pdf" "Question in the target language"
```
