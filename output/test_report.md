# Báo cáo kiểm tra hiện tại

**Ngày:** 30/09/2026
**Commit:** `05185d9`

| Kiểm tra | Lệnh | Kết quả |
|---|---|---|
| Ruff | `ruff check app tests` | PASS |
| Compile | `python -m compileall -q app tests` | PASS |
| Unit/API | `python -m pytest -q tests` | PASS — 22 passed |
| Quality gate | `python tools/quality_gate.py` | PASS — 98,8/100 |
| Frontend | `npm run build` | PASS |
| Compose syntax | `docker compose config --quiet` | PASS |
| Runtime stack | `docker compose ps --all` | API, worker, PostgreSQL, MinIO, frontend đang Up; PostgreSQL healthy |
| Retrieval verification | `retrieval_verification.csv` | Tập kiểm tra 10 câu được bàn giao; kết quả cần chạy lại khi re-ingest dữ liệu |
| GitHub Actions | CI commit `05185d9` | `in_progress` tại thời điểm lập báo cáo |

## Phạm vi test

- Làm sạch control character, whitespace và ranh giới đoạn.
- Chunking theo cấu trúc/page metadata.
- API health, upload hợp lệ, extension không hỗ trợ, câu hỏi rỗng.
- Query không có evidence và bắt buộc source.
- Evidence reranking, answerability, document filtering.
- Upload có tên hiển thị và tương thích service test giả lập.
- OCR/NIM fallback không để semantic normalization treo vô hạn.

## Giới hạn xác nhận

Test local không thay thế GitHub Actions. LLM, embedding và OCR hosted cần credential thật; test NIM trực tiếp không được xem là unit test offline. Benchmark 5 PDF là báo cáo riêng trong `evaluation/`, không dùng để khẳng định mọi tài liệu production.

Hồ sơ nghiên cứu dữ liệu và các phép so sánh OCR, chunking, bảng, hình và
annotation được ghi tại [`docs/report.md`](../docs/report.md); đây là bằng chứng
cho phần Data ingestion & processing trong evaluation.
