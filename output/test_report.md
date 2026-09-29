# Verification Report

Ngày ghi nhận: `2026-09-28`.

## Kết quả

| Kiểm tra | Lệnh | Kết quả |
|---|---|---|
| Python syntax/bytecode | `python -m compileall -q app tests` | PASS |
| Unit + API + OCR/evidence tests | `PYTHONPATH=. pytest -q tests` | PASS — 22 passed |
| Ruff critical syntax checks | `ruff check app tests --select E9` | PASS — All checks passed |
| Compose schema/interpolation | `docker compose config --quiet` | PASS |
| Compose smoke run | `docker compose up -d` + `GET /health` + teardown | PASS — local CI-equivalent run |
| Retrieval verification | `retrieval_verification.csv` | PASS — 10/10 |
| Repository quality gate | `python tools/quality_gate.py` | PASS — 100/100 |

## Phạm vi test đã chạy

- Cleaning whitespace/control characters.
- Semantic chunking và page/section metadata.
- Chuẩn hóa bounding-box metadata.
- Health route contract.
- Query trả `answer` và `sources`.
- Query rỗng bị reject HTTP 400.
- Upload trả document ở trạng thái `queued`.
- Upload file có phần mở rộng không hỗ trợ bị từ chối HTTP 400.
- Query không có bằng chứng trả về `sources=[]` và không sinh nguồn giả.
- Config loading kiểm tra database, embedding, LLM, chunk và top-k.
- OCR routing/evidence service regression tests.
- Naming theo PEP 8 và public docstring coverage 100% trong `app`.

## Ghi chú môi trường

Lần chạy ban đầu thiếu `pytest`, `ruff` và một số runtime dependency trong
Python host. Đã cài đúng `requirements-dev.txt` cùng các dependency runtime
cần cho test; không sửa source code để làm test pass. CI thực hiện cả việc tạo
CI được cấu hình để tạo Docker image, chạy smoke test bằng Docker Compose, gọi
`/health` rồi dọn các container và volume tạm. Đã chạy đầy đủ chuỗi tương đương
trên máy hiện tại: image build thành công, PostgreSQL healthy, API trả
`{"status":"ok"}`, và container/volume đã được dọn sau test. GitHub Actions
chưa được kích hoạt từ phiên làm việc này vì chưa push commit lên remote.
