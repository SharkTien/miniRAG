# Báo cáo Benchmark Hệ thống RAG — SynthDocQA (5 File Cục bộ)

- **Thời gian thực hiện**: `2026-09-21 23:59:34`
- **Phạm vi đánh giá**: Chỉ tính trên **5 tệp PDF có sẵn** (loại bỏ mọi query ngoài phạm vi)
- **Tổng số câu hỏi đánh giá**: `877` câu hỏi
- **Tham số Retrieval Top-K**: `5`
- **Tổng thời gian chạy**: `146.4` giây

## 1. Kết quả Tổng quan

| Chỉ số Đánh giá | Giá trị (%) | Mô tả |
| :--- | :--- | :--- |
| **Document Hit Rate** | **83.35%** | Top-K chunks chứa đúng tài liệu mục tiêu |
| **Content / Keyword Hit Rate** | **35.58%** | Top-K chunks chứa đúng thông tin/từ khóa đáp án |
| **Assertion Pass Rate** | **0.0%** | Câu trả lời AI đáp ứng đầy đủ tiêu chí bắt buộc |

## 2. Phân tích theo Loại Phần tử (Element Type Breakdown)

| Loại Phần tử | Số câu hỏi | Content Hit Rate (%) | Assertion Pass Rate (%) |
| :--- | :--- | :--- | :--- |
| `table` | 299 | 24.1% | 0.0% |
| `form` | 107 | 45.8% | 0.0% |
| `figure` | 159 | 7.5% | 0.0% |
| `annotation` | 285 | 55.8% | 0.0% |
| `text_block` | 27 | 74.1% | 0.0% |

## 3. Phân tích theo Từng Tài liệu

| Tên Tệp PDF | Số câu hỏi | Retrieval Hit (%) | Assertion Pass (%) |
| :--- | :--- | :--- | :--- |
| `doc_0000_s39946201.pdf` | 139 | 40.3% | 0.0% |
| `doc_0000_s71722309.pdf` | 151 | 41.1% | 0.0% |
| `doc_0000_s1045958549.pdf` | 235 | 30.6% | 0.0% |
| `doc_0000_s1131058660.pdf` | 131 | 45.0% | 0.0% |
| `doc_0000_s341236940.pdf` | 221 | 28.5% | 0.0% |