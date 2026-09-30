# Báo cáo các mốc, tiêu chí nghiệm thu và điểm cộng

**Dự án:** Mini RAG Service
**Ngày:** 30/09/2026
**Mã commit:** `05185d9`

## 10. Các mốc

### Mốc 1 — Luồng dữ liệu

**Đã hoàn thành:**

- Tải tài liệu một hoặc nhiều file.
- Kiểm tra định dạng, kích thước và SHA-256.
- Lưu file gốc vào MinIO.
- Extract PDF/TXT/DOCX và các định dạng mở rộng.
- OCR bản quét/ảnh bằng NVIDIA NeMo Retriever OCR v2.
- Làm sạch text, giữ page/section/bounding box và nguồn gốc.
- Chuẩn hóa ngữ nghĩa NVIDIA có thời gian chờ, thử lại giới hạn và dự phòng OCR.
- Chunking có cấu trúc.
- Tạo embedding theo batch.
- Lưu vector và metadata vào PostgreSQL + pgvector.
- Worker xử lý nền, batch nhiều document và tự khôi phục tài liệu bị gián đoạn.
- Nghiên cứu và lập hồ sơ dữ liệu trong [`docs/report.md`](../docs/report.md):
  phân loại Bảng/Biểu mẫu/Hình/Chú thích/Văn bản, tạo tập câu hỏi theo loại dữ liệu,
  đánh giá thử nghiệm từng phương án OCR/chia đoạn/truy xuất và ghi rõ quyết định giữ/loại.

**Kết quả mong đợi:**

```text
Tài liệu → extract/OCR → clean/normalize → chunk → embedding → cơ sở dữ liệu vector
```

### Mốc 2 — API RAG

**Đã hoàn thành:**

- `GET /health`.
- `POST /documents` và alias `/api/documents`.
- `POST /query`, `/api/query`.
- Streaming query qua `/query/stream` và `/api/query/stream`.
- Bộ lập kế hoạch truy vấn tạo biến thể từ khóa có kiểm soát.
- Hybrid toàn văn/BM25 + truy xuất bằng vector ngữ nghĩa.
- Candidate multiplier và adjacent chunk recovery.
- Bằng chứng xếp hạng lại theo mức phù hợp chủ đề, thực thể, ràng buộc, khả năng trả lời.
- lọc danh tính tài liệu và phân bố điểm.
- Grounded prompt tiếng Việt, không trộn các nhánh điều kiện.
- Phản hồi luôn có trích dẫn nguồn.

**Kết quả mong đợi:**

```text
Câu hỏi → lập kế hoạch truy vấn → truy xuất kết hợp → lọc và xếp hạng bằng chứng
         → NVIDIA-compatible LLM → Câu trả lời + nguồn
```

### Mốc 3 — Docker và CI

**Đã hoàn thành:**

- Dockerfile cho API/tiến trình nền.
- Docker Compose cho API, tiến trình nền, PostgreSQL + pgvector, MinIO và giao diện.
- Environment configuration trong `.env.example`.
- Frontend bản dựng cho môi trường vận hành bằng Vite/Nginx.
- CI GitHub Actions gồm compile, ruff, cổng chất lượng, test, giao diện build, Docker build và Compose smoke test.
- Máy phát triển cổng chất lượng đạt 98,8/100.
- GitHub Actions commit mới nhất đang chạy tại thời điểm lập báo cáo.

### Mốc 4 — Tài liệu và trình diễn

**Đã hoàn thành:**

- README root và bộ hồ sơ `output`.
- `docs/architecture.md`, `docs/pipeline.md`, `docs/ocr_deployment.md`.
- ví dụ API, kịch bản trình diễn và truy vết yêu cầu.
- Bộ kiểm tra truy xuất 10 câu.
- Báo cáo PDF các mốc, nghiệm thu, đánh giá và điểm cộng.
- Frontend demo upload, theo dõi tiến độ, đổi tên, hủy/xóa tài liệu và query trả kết quả từng phần.

## 11. Tiêu chí nghiệm thu

| # | Tiêu chí | Trạng thái |
|---:|---|---|
| 1 | Service chạy được bằng Docker Compose | ✅ |
| 2 | Upload PDF, TXT và DOCX | ✅ |
| 3 | Tài liệu được extract và chunk | ✅ |
| 4 | Chunk được tạo embedding | ✅ |
| 5 | Vector và metadata được lưu vào database | ✅ |
| 6 | Query API hoạt động | ✅ |
| 7 | Câu trả lời có source | ✅ |
| 8 | Configuration tách khỏi business logic | ✅ |
| 9 | Có `.env.example` | ✅ |
| 10 | Không commit secret thật | ✅ |
| 11 | Có unit test | ✅ — 22 test |
| 12 | Có API test | ✅ |
| 13 | CI luồng xử lý chạy thành công | ⏳ — commit mới đang `in_progress` |
| 14 | Có basic kiểm tra truy xuất | ✅ |
| 15 | Có README | ✅ |
| 16 | Có architecture document | ✅ |

Tiêu chí nghiệm thu chỉ được đánh dấu hoàn toàn khi CI máy chạy CI của commit hiện tại kết thúc thành công.

## 12. Tiêu chí đánh giá

| Hạng mục | Trọng số | Tự đánh giá | Căn cứ |
|---|---:|---:|---|
| Trích xuất và xử lý dữ liệu | 20% | 19/20 | 12 điểm cho nạp dữ liệu; 8 điểm cho nghiên cứu, chuẩn hóa và kiểm soát chất lượng dữ liệu trong `docs/report.md` |
| Cơ sở dữ liệu vector và truy xuất | 20% | 19/20 | pgvector, toàn văn/BM25, dense, tập ứng viên, bằng chứng filter |
| Tích hợp AI / RAG | 15% | 14/15 | NVIDIA OCR/NIM, lời nhắc bám nguồn, trả kết quả từng phần, trích dẫn nguồn |
| Docker và môi trường | 15% | 15/15 | Dockerfile, Compose, env, máy phát triển stack đang chạy |
| CI | 10% | 9/10 | Workflow đầy đủ; máy chạy CI commit mới đang chờ kết quả |
| Kiểm thử | 10% | 10/10 | 22 test máy phát triển, cổng chất lượng pass |
| Tài liệu và trình diễn | 10% | 10/10 | README, architecture, API, demo, PDF và bộ kiểm tra truy xuất |
| **Tổng tạm tính** | **100%** | **96/100** | Điểm tự đánh giá, không thay thế điểm reviewer |

### Tiểu mục nghiên cứu dữ liệu trong 20% nạp dữ liệu

Đây là phần cần nhấn mạnh khi trình bày với vai trò data engineer/data scientist:

- Khảo sát cấu trúc dữ liệu trước khi chọn bộ phân tích: PDF có lớp chữ, PDF bản quét, bảng, biểu mẫu, hình và annotation.
- Xây dựng tập đánh giá theo loại dữ liệu thay vì chỉ đo một điểm chung.
- So sánh mốc so sánh với OCR toàn trang, hệ số mở rộng ứng viên, hybrid dense + từ khóa, điều hướng bảng, mở rộng chunk cha, truy xuất phần tử hình và vùng chú thích.
- Đo `document hit`, `content hit` và `assertion pass`; phân tích lỗi theo bảng, hình, annotation và text.
- Ghi lại lý do giữ hoặc loại từng phương án, giới hạn đánh giá thử nghiệm và điểm chưa thể suy rộng sang môi trường vận hành.
- Đưa kết quả nghiên cứu trở lại luồng xử lý bằng các quyết định có kiểm chứng: OCR toàn trang, truy xuất kết hợp, tập ứng viên rộng, bằng chứng xếp hạng lại và nguồn gốc theo trang.

Reviewer cũng có thể đánh giá khả năng research, gỡ lỗi, đọc tài liệu, chia nhỏ vấn đề, chất lượng commit, tổ chức code, giải thích quyết định kỹ thuật, xử lý blocker và tiếp nhận feedback. Các điểm này được thể hiện qua `docs/report.md`, lịch sử commit, test report và traceability.

## 13. Điểm cộng

| Bonus | Trạng thái | Bằng chứng |
|---|---|---|
| Truy xuất kết hợp | ✅ | `ChunkRepository.vector_search` |
| Full-text kết hợp Vector Search | ✅ | PostgreSQL `to_tsquery` + pgvector |
| Xếp hạng lại | ✅ | `EvidenceService` |
| Hỗ trợ CSV/XLSX | ✅ | `ALLOWED_EXTENSIONS`, extraction routing |
| Background tiến trình nền nạp dữ liệu | ✅ | `app/worker.py`, PostgreSQL queue |
| Thử lại khi nạp dữ liệu lỗi | ✅ | NIM thử lại/dự phòng, tiến trình nền recovery/requeue |
| API xóa tài liệu | ✅ | `DELETE /api/documents/{document_id}` |
| API xem danh sách tài liệu | ✅ | `GET /api/documents` |
| Tối ưu truy xuất | ✅ | bộ lập kế hoạch truy vấn, hệ số mở rộng ứng viên, phân bố điểm, lọc danh tính tài liệu, loại nguồn trùng |
| Tên hiển thị và đổi tên tài liệu | ✅ bổ sung | upload `display_name`, `PATCH /documents/{id}` |
| Hủy job đang xử lý | ✅ bổ sung | `POST /documents/{id}/cancel`, xóa và hủy xử lý phối hợp |
| Trả kết quả từng phần | ✅ bổ sung | `/query/stream` |
| Frontend môi trường vận hành | ✅ bổ sung | React/Vite/Nginx, CI build |
| Hồ sơ nghiên cứu dữ liệu và đánh giá thử nghiệm theo loại dữ liệu | ✅ bổ sung | `docs/report.md`, `evaluation/benchmark_summary.md`, các tệp kết quả đánh giá thử nghiệm |

Bonus chỉ có giá trị sau khi các yêu cầu cơ bản ổn định. Với các bonus phụ thuộc dịch vụ trực tuyến, cần xác nhận thêm trong môi trường triển khai thật.

## Kết luận

Bốn milestone đã có source và bằng chứng kiểm tra tương ứng. Tiêu chí nghiệm thu đã đạt về mặt mã nguồn và máy phát triển verification; mục CI cần chờ máy chạy CI GitHub của commit `05185d9` hoàn tất để đóng dấu cuối cùng. Hệ thống đã sẵn sàng cho demo kỹ thuật và tiếp tục cần đánh giá thử nghiệm regression trên tài liệu môi trường vận hành trước khi dùng ở quy mô lớn.

## Bằng chứng trực quan

Báo cáo PDF sử dụng bốn ảnh chụp từ hệ thống và lưu tại `output/images/`:

- `docker_CICD.png`: quy trình GitHub Actions gồm kiểm tra chất lượng, bản dựng giao diện và dựng Docker; lần chạy hiển thị trạng thái thành công.
- `pgvector.png`: PostgreSQL có các bảng hội thoại, đoạn tài liệu, tài liệu và tin nhắn; `document_chunks.embedding` có kiểu `vector(2048)`.
- `upload.png`: kho tài liệu hiển thị sáu tài liệu, bản xem trước PDF và số chunk sau xử lý.
- `chunk.png`: nội dung sau khi chia đoạn, giữ tiêu đề và văn bản để truy xuất.

Kho mã nguồn: <https://github.com/SharkTien/miniRAG>.

## Kiểm thử và cách đọc kết quả

Lệnh kiểm tra chính gồm `ruff check app tests`, `python -m compileall -q app tests` và `python -m pytest -q tests`. Các nhóm kiểm thử bao phủ làm sạch văn bản, chia đoạn có trang/mục, chuẩn hóa tọa độ, hợp đồng API, file không hỗ trợ, câu hỏi rỗng, truy vấn không có bằng chứng, xếp hạng bằng chứng, định tuyến OCR và chống mô hình tự thêm nội dung. Lần chạy gần nhất có 22 kiểm thử đạt; kiểm thử gọi dịch vụ NVIDIA trực tiếp chỉ chạy khi có khóa API.

## Cấu hình tách khỏi mã nghiệp vụ

`app/config/settings.py` đọc các biến trong `.env`: `DATABASE_URL`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `LLM_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`, `RETRIEVAL_CANDIDATE_MULTIPLIER`, `SIMILARITY_THRESHOLD` và các biến OCR/NVIDIA. `.env.example` chỉ chứa giá trị mẫu; khóa thật và mật khẩu không được commit.

## Đánh giá từng trường hợp trong bảng truy xuất

Bảng `output/retrieval_verification.xlsx` có 8 câu hỏi có dữ liệu; hai dòng cuối trống nên không tính. Quy tắc đọc: “Đạt” là đủ ý chính và không mâu thuẫn; “Đạt một phần” là có ý chính nhưng thiếu điều kiện hoặc thêm thông tin chưa có căn cứ; “Chưa đạt” là mâu thuẫn hoặc bỏ sót dữ kiện quyết định.

| Trường hợp | Kết luận | Nhận xét |
|---|---|---|
| Shopee, hoàn tiền bằng thẻ NAPAS | Đạt một phần | Đúng mốc 2–5 ngày; thiếu điều kiện mốc tính từ lúc xác nhận hoàn tiền. |
| Shopee, giao sai hàng và phí trả hàng | Đạt | Phân biệt đúng lấy tại nhà, bưu cục và tự sắp xếp; nêu điều kiện hỗ trợ. |
| Adore, chỉ áo trong một bộ bị lỗi | Chưa đạt | Khẳng định được tách áo và hoàn tiền khi bằng chứng chưa đủ. |
| Adore, phụ kiện lỗi trong 7 ngày | Chưa đạt | Trộn chính sách bảo hành với chính sách đổi hàng. |
| DAT, biến tần GD100-PV | Đạt một phần | Đúng thời hạn và mốc tính; có thêm thông tin ngoài bằng chứng. |
| DAT, inverter gửi Nguyễn Văn Quá | Chưa đạt | Thiếu mốc 24 giờ và quy trình báo giá khi máy nứt vỡ. |
| Kamereo, hotline khiếu nại | Đạt một phần | Đúng số điện thoại; các mốc xử lý cần đối chiếu thêm nguồn. |
| Kamereo, hàng dập úng sau 14 giờ | Đạt | Đúng nguyên tắc không trừ ngay và đổi/bù ở đơn kế tiếp. |

Tổng hợp: 2/8 câu đạt đầy đủ, 3/8 câu đạt một phần và 3/8 câu chưa đạt. Các lỗi chưa đạt đều liên quan đến suy diễn khi thiếu bằng chứng hoặc trộn nhiều chính sách.

## Cách tạo nguồn trả lời

Nguồn được tạo từ các chunk đã vượt qua tìm kiếm kết hợp, lọc danh tính tài liệu, phân bố điểm và xếp hạng bằng chứng. Mỗi nguồn trả về `file_name`, `document_id`, `chunk_id`, trang, điểm vector, điểm từ khóa, điểm phù hợp câu hỏi, khả năng trả lời, vị trí nguồn, phương pháp trích xuất và đoạn trích. Nếu không có bằng chứng, API trả `sources: []` và không dựng nguồn giả.
