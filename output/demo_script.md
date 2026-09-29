# Demo Script (20–30 phút)

## 1. Context và mục tiêu — 2 phút

Nêu bài toán: ingest tài liệu, hỏi đáp có grounding và citation; nhấn mạnh
answer không đủ nếu không truy được source.

## 2. Architecture — 4 phút

Mở [architecture.md](architecture.md), chỉ vào hai flow: ingestion qua worker và
query qua retrieval/evidence/LLM.

## 3. Start stack — 3 phút

```bash
cp .env.example .env
# điền các placeholder secret/password
docker compose up -d --build
docker compose ps
curl -fsS http://localhost:41873/health
```

## 4. Upload file tùy chọn và kiểm tra ingestion — 4 phút

Lệnh dưới đây nhận một file được hỗ trợ, chờ worker xử lý xong, tạo một
conversation, gửi câu hỏi và đọc lại messages từ PostgreSQL:

```bash
chmod +x scripts/demo_terminal.sh
scripts/demo_terminal.sh \
  "/absolute/path/to/your-document.pdf" \
  "Your question in the language you want to test"
```

Supported extensions are configured in `app/config/constants.py`. The upload
request creates a `queued` document; the worker changes it to `processing` and
then `processed`. Raw files are stored in MinIO, while extracted chunks and
embeddings are stored in PostgreSQL/pgvector.

To inspect the worker independently:

```bash
docker compose logs -f ntc_document_rag_worker
```

## 5. Query grounded — 4 phút

Gửi câu hỏi có đáp án trong file. Chỉ vào `answer`, `file_name`, `chunk_id`,
`page`, `snippet`; sau đó thử câu hỏi ngoài tài liệu để minh họa evidence gate.

## 6. Test và CI — 3 phút

```bash
PYTHONPATH=. pytest -q tests
ruff check app tests --select E9
python -m compileall -q app tests
docker compose config --quiet
```

Mở `.github/workflows/ci.yml` để chỉ ra thứ tự lint → unit/API test → Docker
build và điều kiện Docker job phụ thuộc quality job.

## 7. Retrieval verification — 3 phút

Mở [retrieval_verification.csv](retrieval_verification.csv), giải thích 10
câu hỏi thuộc 5 document và quy tắc pass là filename source phải khớp expected.
Đối chiếu thêm benchmark chi tiết trong `evaluation/benchmark_summary.md`.

## 8. Hạn chế và Q&A — 2–7 phút

Nêu dependency vào model endpoint, OCR/layout là phần khó, reranker hiện
rule-based; hướng tiếp theo là cross-encoder, feedback loop và human review.
