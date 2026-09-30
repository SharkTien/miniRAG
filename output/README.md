# Hồ sơ bàn giao Mini RAG Service

**Ngày cập nhật:** 30/09/2026
**Commit source hiện tại:** `05185d9`

Thư mục này là bộ hồ sơ được đối chiếu lại với source code hiện tại. Báo cáo chính có đầy đủ milestone, acceptance criteria, evaluation criteria và bonus tại [milestones_bonus_ec.md](milestones_bonus_ec.md). Bản PDF tương ứng là [milestones_bonus_ec.pdf](milestones_bonus_ec.pdf).

## Trạng thái kiểm tra tại thời điểm cập nhật

| Hạng mục | Kết quả |
|---|---|
| `ruff check app tests` | Đạt |
| `python -m compileall -q app tests` | Đạt |
| `python -m pytest -q tests` | 22 passed |
| `python tools/quality_gate.py` | 98,8/100 |
| `npm run build` | Đạt |
| `docker compose config --quiet` | Đạt |
| Docker Compose local | API, worker, PostgreSQL, MinIO và frontend đang chạy |
| GitHub Actions | Workflow của commit `05185d9` đang chạy tại thời điểm lập báo cáo |

## Luồng hệ thống hiện tại

```text
PDF/TXT/DOCX/CSV/XLSX/PPTX/ảnh
        ↓
Upload API → MinIO + PostgreSQL trạng thái queued
        ↓
Worker nền → extract/layout/OCR NVIDIA → làm sạch
        ↓
chuẩn hóa ngữ nghĩa có timeout/fallback → chunk
        ↓
embedding NVIDIA → PostgreSQL + pgvector và metadata
        ↓
Question + conversation history → contextual query resolution → query planning → hybrid lexical + dense retrieval
        ↓
document/evidence filtering → reranking → grounded NVIDIA LLM
        ↓
answer + source citations
```

## Nội dung hồ sơ

- [milestones_bonus_ec.md](milestones_bonus_ec.md): milestone, acceptance criteria, evaluation và bonus.
- [`../docs/report.md`](../docs/report.md): hồ sơ nghiên cứu dữ liệu, benchmark và quyết định xử lý theo loại dữ liệu.
- [acceptance_matrix.md](acceptance_matrix.md): ma trận đối chiếu từng tiêu chí nghiệm thu.
- [requirements_traceability.md](requirements_traceability.md): truy vết yêu cầu trong `SUBJECT.md` tới source.
- [architecture.md](architecture.md): kiến trúc và data flow hiện tại.
- [api_examples.md](api_examples.md): health, upload, query, streaming, rename và cancel.
- [demo_script.md](demo_script.md): kịch bản demo.
- [test_report.md](test_report.md): bằng chứng kiểm tra mới nhất.
- [retrieval_verification.csv](retrieval_verification.csv): tập kiểm tra truy xuất cơ bản.
- [retrieval_verification.xlsx](retrieval_verification.xlsx): cùng dữ liệu ở dạng bảng tính.

## Chạy nhanh

```bash
cp .env.example .env
# điền các password/API key trong môi trường triển khai, không commit .env
docker compose up -d --build
curl -fsS http://localhost:41873/health
```

Frontend production chạy tại `http://localhost:4173`. Hệ thống không yêu cầu đăng nhập. Upload trả `queued`; worker xử lý nền và chuyển sang `processed`.

## Giới hạn được ghi nhận

- Chất lượng và thời gian trả lời phụ thuộc endpoint embedding/LLM NVIDIA, giới hạn tốc độ và kích thước tài liệu.
- Reranker hiện là deterministic evidence service; chưa dùng cross-encoder học từ dữ liệu phản hồi.
- Các chỉ số benchmark SynthDocQA trong `evaluation/` là kết quả của bộ 5 PDF và cấu hình benchmark riêng, không đại diện cho mọi tài liệu production.
- CI cần được xác nhận hoàn tất trên GitHub Actions sau mỗi thay đổi; local pass không thay thế runner.
