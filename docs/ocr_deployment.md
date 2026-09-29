# Hướng xử lý và triển khai OCR tiếng Việt

## Kết luận kiến trúc

Không chọn một parser/model duy nhất cho mọi tài liệu. Pipeline dùng định tuyến theo đặc tính đầu vào, tương tự tư tưởng parser `auto/ocr/txt` của RAG-Anything và khuyến nghị chọn parser theo độ phức tạp tài liệu của RAGFlow.

```text
Upload
  ├─ PDF có text layer ──> Docling, OCR off ───────────────┐
  └─ PDF scan / ảnh ────> Tesseract vie+eng theo trang ───┤
                            └─ lỗi: PP-OCRv6 local         │
                                                          v
              confidence thấp ──> Qwen local ──> NVIDIA API fallback
              confidence cao ──────────────────> chunk + embedding
```

DeepDoc/RAGFlow không còn chạy mặc định cho mọi PDF. Nó là chế độ opt-in cho bảng và layout phức tạp (`DOCUMENT_PARSER_ENGINE=ragflow`). Cách này tránh OCR lại PDF đã có text và tránh dùng DeepDoc cho trường hợp tiếng Việt đơn giản mà Tesseract xử lý tốt hơn.

## Lựa chọn OCR

Benchmark smoke test trên cùng ảnh ba dòng tiếng Việt trong môi trường hiện tại:

| Engine | Thời gian | Kết quả |
|---|---:|---|
| Tesseract `vie+eng`, PSM 3 | 0,38–0,65 giây | Đúng toàn bộ ba dòng |
| PP-OCRv6 GPU local, `lang=vi` | 8,63 giây | Mất nhiều dấu/chữ dù confidence 97,6% |

Vì vậy Tesseract trực tiếp là mặc định. PP-OCRv6 vẫn hữu ích cho ảnh cần xoay, làm phẳng hoặc unwarping, nhưng không dùng confidence của PP-OCRv6 làm thước đo duy nhất.

Adapter Tesseract:

- render PDF ở 180 DPI;
- chạy tối đa 4 trang song song;
- đọc TSV để giữ bbox và confidence từng dòng;
- chỉ giữ tối đa một batch bitmap trong RAM;
- fallback tự động khi CLI lỗi hoặc không nhận được text.

## Local model hay NVIDIA API

Chính sách mặc định `SEMANTIC_NORMALIZER=auto`:

1. Ưu tiên Qwen 27B local đang chạy tại cổng `8027`.
2. Chỉ gọi model với tài liệu đã OCR và confidence Tesseract dưới `0.93`.
3. Nếu local lỗi/timeout, gọi NVIDIA NIM hosted khi có API key.
4. Nếu hosted API cũng lỗi, giữ nguyên text rule-based; ingestion không thất bại.

Ưu tiên local giúp dữ liệu không rời máy, không phụ thuộc rate limit và có chi phí biên thấp. Hosted API phù hợp làm failover, benchmark model mới hoặc xử lý burst khi GPU local bận. Cả hai dùng contract JSON patch và kiểm tra chống hallucination; bản sửa dấu tiếng Việt được phép, nhưng mở rộng nội dung bất thường bị từ chối.

## Cấu hình production hiện tại

```dotenv
DOCUMENT_PARSER_ENGINE=auto
DOCLING_DEVICE=cpu
DOCLING_DO_OCR=auto
DOCLING_OCR_LANG=vie,eng
DOCLING_TESSERACT_PSM=3
LOCAL_OCR_DPI=180
TESSERACT_PAGE_CONCURRENCY=4
LOCAL_OCR_BASE_URL=http://host.docker.internal:8012
QWEN_BASE_URL=http://host.docker.internal:8027/v1
SEMANTIC_NORMALIZER=auto
SEMANTIC_NORMALIZE_OCR_ONLY=true
SEMANTIC_OCR_CONFIDENCE_GATE=0.93
```

`DOCLING_DEVICE=cpu` là chủ ý: image hiện cài PyTorch CPU và Tesseract chạy CPU. GPU được dùng bởi các model server local riêng, không nên ghi `cuda` trong worker khi runtime thực tế không có CUDA Torch.

## Tiêu chí nghiệm thu

Chuẩn bị bộ 30–50 trang đại diện, gồm PDF native, scan rõ, scan lệch/mờ và bảng. Với mỗi trang lưu ground truth và đo:

- CER/WER tiếng Việt trước và sau Qwen;
- p50/p95 giây mỗi trang;
- tỷ lệ trang đi vào Qwen/NVIDIA fallback;
- tỷ lệ số/ngày tháng/tên riêng bị thay đổi sai;
- recall@k của truy vấn RAG sau ingestion.

Chỉ hạ confidence gate hoặc tăng DPI sau khi benchmark. Tăng DPI đồng loạt sẽ làm chậm và tăng RAM; gọi LLM cho mọi trang cũng làm latency tăng mạnh mà không giúp PDF có text hoặc OCR đã tốt.
