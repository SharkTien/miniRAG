# Kịch bản demo

## 1. Khởi động

```bash
cp .env.example .env
# điền secret/password trong môi trường local
docker compose up -d --build
docker compose ps
curl -fsS http://localhost:41873/health
```

Mở frontend tại `http://localhost:4173`.

## 2. Upload và theo dõi ingestion

1. Upload một PDF/TXT/DOCX.
2. Đặt tên hiển thị nếu cần.
3. Quan sát `queued → processing → processed`.
4. Mở chi tiết extraction để xem text, page, chunk và confidence OCR.
5. Xóa thử một tài liệu đang xử lý để minh họa trạng thái `cancelled`.

## 3. Query có nguồn

Đặt câu hỏi có dữ kiện rõ trong tài liệu. Chỉ vào câu trả lời, tên file, chunk, trang và snippet. Sau đó hỏi một câu không có trong tài liệu để minh họa evidence gate.

## 4. Demo retrieval khó

- Câu hỏi về bảng hoàn tiền NAPAS: kiểm tra hàng đúng phương thức và thời gian.
- Câu hỏi về nhiều nhánh trả hàng: kiểm tra phí của từng nhánh không bị trộn.
- Câu hỏi có thương hiệu Adore/Kamereo: kiểm tra nguồn chỉ còn tài liệu đúng thương hiệu.

## 5. Kiểm tra chất lượng

```bash
ruff check app tests
python -m compileall -q app tests
python -m pytest -q tests
python tools/quality_gate.py
npm --prefix frontend run build
docker compose config --quiet
```

## 6. CI và bàn giao

Mở `.github/workflows/ci.yml`: push/pull request chạy lint, compile, test, frontend build, Docker build và Compose smoke test. Ghi nhận trạng thái runner từ GitHub Actions, không suy đoán từ local.
