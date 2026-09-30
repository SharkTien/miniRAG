# MINI RAG — PIPELINE XỬ LÝ TÀI LIỆU CHI TIẾT

Tài liệu này mô tả toàn bộ luồng xử lý tài liệu từ khâu Ingestion đến khi hoàn tất Clean Text, Chuẩn hóa ngữ nghĩa và Chunking cho hệ thống RAG.

---

## 1. Sơ Đồ Kiến Trúc Luồng Dữ Liệu (Flow Diagram)

```text
[ File Đầu Vào: PDF / Scan / Ảnh / Office ]
                     │
                     ▼
┌────────────────────────────────────────────────────────┐
│ GIAI ĐOẠN 1: BÓC TÁCH & PHÂN TÍCH BỐ CỤC (LAYOUT)      │
│                                                        │
│  • PDF có lớp chữ: Docling đọc trực tiếp                 │
│  • PDF scan/ảnh: NVIDIA NeMo Retriever OCR v2           │
│  • Nhận diện: Paragraphs, Section Headers, Tables      │
│  • Trích xuất tọa độ Bounding Boxes (OCR & Images)     │
└────────────────────────────┬───────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────┐
│ GIAI ĐOẠN 2: LÀM SẠCH & LỌC DỮ LIỆU (RULE-BASED)       │
│                                                        │
│  • Loại bỏ ký tự rác, watermarks, header/footer lặp lại │
│  • Chuẩn hóa khoảng trắng, ngắt dòng tiếng Việt        │
│  • Phân vùng dữ liệu theo từng trang (Page-Level)      │
└────────────────────────────┬───────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────┐
│ GIAI ĐOẠN 3: NVIDIA NIM PARALLEL NORMALIZATION         │
│                                                        │
│  • Chia nhỏ thành các Page Windows (Trang 1, 2, ..., N)│
│  • Gửi đồng thời (NIM_CONCURRENCY = 4) lên Cloud NIM   │
│  • Model: meta/llama-3.2-11b-vision-instruct           │
│  • Gán Semantic Type (heading, list_item, table, text) │
│  • Sửa lỗi chính tả OCR & phục hồi cấu trúc câu        │
│  • Cơ chế Fallback: Nếu timeout, tự động giữ Rule-based│
└────────────────────────────┬───────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────┐
│ GIAI ĐOẠN 4: CHUNKING & XUẤT DỮ LIỆU                   │
│                                                        │
│  • LlamaIndex Sentence / Semantic Splitter             │
│  • Cắt nhỏ văn bản theo ngữ cảnh (~500 - 1500 ký tự)   │
│  • Gán Metadata: document_id, filename, page, bbox     │
│  • Sẵn sàng Embedding & nạp vào PostgreSQL (pgvector)  │
│  • Tự động xuất báo cáo kiểm thử (JSON & Markdown)     │
└────────────────────────────────────────────────────────┘
```

---

## 2. Chi Tiết Các Giai Đoạn Trong Pipeline

### Giai Đoạn 1: Bóc Tách & Phân Tích Bố Cục
- **Xử lý tài liệu theo lô**: worker dùng `FOR UPDATE SKIP LOCKED` để nhận một
  nhóm tài liệu đang chờ, sau đó xử lý song song với giới hạn
  `INGESTION_WORKER_CONCURRENCY`. Cách này tránh một tài liệu dài chặn toàn bộ
  các tài liệu phía sau.
- **PDF có lớp chữ**: Docling đọc trực tiếp để không phát sinh lượt gọi OCR.
- **PDF scan và ảnh**: NVIDIA NeMo Retriever OCR v2 nhận ảnh JPEG theo trang,
  trả văn bản, độ tin cậy và tọa độ vùng chữ.
- **Bảng và bố cục phức tạp**: RAGFlow DeepDoc vẫn là chế độ tùy chọn.
- Tọa độ chữ (`ocr_bboxes`) và hình (`image_bboxes`) được lưu để truy vết
  nguồn và hiển thị bằng chứng.

### Giai Đoạn 2: Làm Sạch Quy Tắc (Rule-based Clean & Page Partitioning)
- Xóa bỏ các ký tự vô nghĩa sinh ra trong quá trình OCR.
- Lọc bỏ số trang, tiêu đề đầu trang (`page_header`) và chân trang (`page_footer`) bị lặp lại.
- Gom các phần tử văn bản theo từng trang (`page_no`) độc lập.
- Thiết lập ranh giới ngữ cảnh (Context Boundary) để tránh tràn token cho mô hình ngôn ngữ ở bước tiếp theo.

### Giai Đoạn 3: Chuẩn Hóa Ngữ Nghĩa Song Song Qua NVIDIA NIM (Semantic Normalization)
- **Nền tảng**: NVIDIA NIM Cloud API (`https://integrate.api.nvidia.com/v1`).
- **Model**: `meta/llama-3.2-11b-vision-instruct` qua NVIDIA NIM; đây là cấu hình
  mặc định chi phí thấp hơn cho giai đoạn thử nghiệm.
- **Xử lý song song (Parallel Processing)**:
  - Thay vì gửi tuần tự từng trang gây chậm trễ, hệ thống sử dụng `ThreadPoolExecutor` gửi đồng thời 4 trang cùng lúc (`NIM_CONCURRENCY=4`).
  - Tốc độ xử lý tài liệu 10–20 trang được rút ngắn từ vài phút xuống còn vài chục giây.
- **Nhiệm vụ của mô hình AI**:
  - Định danh chính xác vai trò ngữ nghĩa của từng đoạn: `section_header`, `paragraph`, `list_item`, `table_row`.
  - Phục hồi các từ ngữ tiếng Việt bị mất dấu hoặc sai sót do OCR scan mờ.
- **Cơ chế chịu lỗi (Fault Tolerance & Resilience)**:
  - Bắt lỗi HTTP 429 (Rate Limit) với Exponential Backoff & Jitter.
  - Nếu chuẩn hóa timeout, pipeline giữ dữ liệu OCR gốc. Nếu OCR NVIDIA lỗi,
    tài liệu được đánh dấu lỗi để không chuyển ngầm sang mô hình khác.

### Giai Đoạn 4: Phân Đoạn Văn Bản (Chunking) & Lưu Trữ
- **Công cụ**: Sử dụng **LlamaIndex** Sentence Splitter.
- **Nguyên tắc Chunking**:
  - Không cắt ngang câu hoặc ngắt gãy cấu trúc bảng biểu.
  - Giữ lại tiêu đề phân mục (`section_header`) ở đầu mỗi chunk để duy trì ngữ cảnh khi vector search.
  - Kích thước chunk tối ưu: ~500 đến 1500 ký tự (phù hợp với các embedding model tiếng Việt và đa ngôn ngữ).
- **Đầu ra**:
  - Nạp vào Database PostgreSQL (hỗ trợ pgvector cho bước Semantic Search sau này).
  - Lưu file gốc và các artifact vào MinIO Object Storage.
  - Khi chạy ở chế độ kiểm thử, tự động xuất kết quả ra:
    - `evaluation/artifacts/debug_output.md`: Báo cáo đọc trực quan.
    - `evaluation/artifacts/debug_output.json`: Cấu trúc dữ liệu thô và tọa độ BBox.

---

## 3. Bảng Tham Số Cấu Hình Chính (.env)

| Tham Số | Giá Trị Mặc Định | Ý Nghĩa |
| :--- | :--- | :--- |
| `DOCUMENT_PARSER_ENGINE` | `auto` | Định tuyến Docling native text hoặc NVIDIA OCR |
| `RAGFLOW_MODE` | `deepdoc` | Chế độ chạy RAGFlow (`deepdoc` in-process hoặc `api`) |
| `NGC_API_KEY` | *(Key của bạn)* | API Key truy cập NVIDIA NIM Cloud |
| `NIM_MODEL` | `meta/llama-3.2-11b-vision-instruct` | Model LLM chuẩn hóa văn bản |
| `NIM_CONCURRENCY` | `4` | Số trang gửi song song lên NIM |
| `NIM_TIMEOUT_SECONDS` | `150` | Thời gian chờ tối đa cho mỗi trang |
| `NVIDIA_OCR_BASE_URL` | `https://ai.api.nvidia.com/v1/cv/nvidia/nemotron-ocr-v2` | Endpoint OCR NVIDIA |
| `NVIDIA_OCR_MODEL` | `nvidia/nemotron-ocr-v2` | Mô hình OCR tài liệu |
| `NVIDIA_OCR_BATCH_SIZE` | `2` | Số trang gửi trong một yêu cầu OCR |
| `NVIDIA_OCR_CONCURRENCY` | `4` | Số yêu cầu OCR chạy song song |
| `INGESTION_WORKER_CONCURRENCY` | `2` | Số tài liệu worker xử lý đồng thời |
| `HF_KEY` / `HF_TOKEN` | *(Key của bạn)* | Token Hugging Face tải layout models nhanh hơn |
