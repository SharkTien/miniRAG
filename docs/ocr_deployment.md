# Hướng xử lý và triển khai OCR qua NVIDIA

## Kết luận kiến trúc

Không chọn một parser/model duy nhất cho mọi tài liệu. Pipeline dùng định tuyến theo đặc tính đầu vào, tương tự tư tưởng parser `auto/ocr/txt` của RAG-Anything và khuyến nghị chọn parser theo độ phức tạp tài liệu của RAGFlow.

```text
Upload
  ├─ PDF có lớp chữ ──────> Docling đọc trực tiếp ─────────┐
  └─ PDF scan / ảnh ──────> NVIDIA NeMo Retriever OCR v2 ──┤
                             văn bản + bbox + confidence   v
              confidence thấp ──> NVIDIA NIM chuẩn hóa ────┤
              confidence cao ──────────────────────────────> chunk + embedding
```

DeepDoc/RAGFlow không chạy mặc định. Đây là chế độ tùy chọn cho bảng và bố cục
phức tạp (`DOCUMENT_PARSER_ENGINE=ragflow`).

## Lựa chọn OCR

Benchmark smoke test trên cùng ảnh ba dòng tiếng Việt trong môi trường hiện tại:

| Engine | Mục đích | Ghi chú |
|---|---:|---|
| NVIDIA `nvidia/nemotron-ocr-v2` | OCR scan, bảng và bố cục | Trả văn bản, bbox và confidence qua `/v1/ocr` |
| Docling native text | PDF đã có lớp chữ | Không gọi OCR, giảm chi phí và độ trễ |

NVIDIA OCR v2 là mặc định cho mọi đầu vào cần OCR. Khi endpoint không sẵn sàng,
ingestion dừng và đánh dấu tài liệu lỗi thay vì tự động chuyển sang một mô hình
OCR cục bộ khác, nhờ đó kết quả benchmark luôn cùng một nhà cung cấp.

Adapter NVIDIA OCR:

- render PDF ở 180 DPI;
- gửi tối đa hai trang mỗi yêu cầu để tránh vượt giới hạn kích thước;
- mã hóa ảnh thành data URL JPEG theo hợp đồng `/v1/ocr`;
- giữ bbox chuẩn hóa, confidence và thứ tự đọc của từng đoạn;
- lưu `extraction_method=nvidia_nemotron_ocr_v2` trong metadata.

## Local model hay NVIDIA API

Chính sách mặc định `SEMANTIC_NORMALIZER=nvidia`:

1. Chỉ gọi mô hình chuẩn hóa khi tài liệu đã OCR và confidence dưới `0.93`.
2. Dùng `meta/llama-3.2-11b-vision-instruct` qua NVIDIA NIM.
3. Kết quả được kiểm tra theo cấu trúc và đối chiếu với văn bản OCR nguồn.
4. Nếu chuẩn hóa lỗi, giữ văn bản OCR gốc; nếu OCR lỗi, ingestion đánh dấu lỗi.

API NVIDIA phù hợp cho giai đoạn thử nghiệm nhờ endpoint miễn phí theo giới
hạn tài khoản. NVIDIA hiện không công bố một hạn mức token cố định cho mọi mô
hình; giới hạn tốc độ thay đổi theo mô hình và tải hệ thống.

## Cấu hình production hiện tại

```dotenv
DOCUMENT_PARSER_ENGINE=auto
DOCLING_DEVICE=cpu
DOCLING_DO_OCR=auto
DOCLING_OCR_LANG=vie,eng
LOCAL_OCR_DPI=180
NVIDIA_OCR_BASE_URL=https://ai.api.nvidia.com/v1/cv/nvidia/nemotron-ocr-v2
NVIDIA_OCR_MODEL=nvidia/nemotron-ocr-v2
NVIDIA_OCR_BATCH_SIZE=2
NVIDIA_OCR_CONCURRENCY=4
SEMANTIC_NORMALIZER=nvidia
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
