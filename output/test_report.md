# Verification Report

Ngày ghi nhận: `2026-09-28`.

## Kết quả

| Kiểm tra | Lệnh | Kết quả |
|---|---|---|
| Python syntax/bytecode | `python -m compileall -q app tests` | PASS |
| Unit + API + OCR/evidence tests | `PYTHONPATH=. pytest -q tests` | PASS — 22 passed |
| Ruff critical syntax checks | `ruff check app tests --select E9` | PASS — All checks passed |
| Compose schema/interpolation | `docker compose config --quiet` | PASS |
| Frontend build | `npm ci` + `npm run build` trong `frontend/` | PASS |
| Frontend Docker image | `docker build -t mini-rag-frontend:ci frontend` | PASS |
| Compose smoke run | API `/health` + frontend `/` + teardown | API PASS; full local run blocked by stale Docker network collision |
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
CI được cấu hình để tạo API và frontend image, chạy smoke test bằng Docker
Compose, gọi `/health` và trang frontend rồi dọn container/volume. Chuỗi tương
đương cho API đã được kiểm tra cục bộ. Frontend build và frontend Docker image
đã đạt; lần Compose đầy đủ tại máy hiện tại bị chặn bởi network Docker cũ
`mini_rag_default` chiếm dải địa chỉ. GitHub Actions đã được kích hoạt cho các
commit trên nhánh `main`.
