# Tóm tắt benchmark và tuning RAG

## Phạm vi

5 file PDF SynthDocQA.

877 câu hỏi:
Table: 299
Form: 107
Figure: 159
Annotation: 285
Text: 27

## Các phương án đã thử

 Phương án                                                                             Kết quả chính    Quyết định
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━
 Baseline                             Document hit 85.52%, content hit 33.52%, assertion pass 18.59%    Mốc ban đầu
───────────────────────────────────  ────────────────────────────────────────────────────────────────  ──────────────────────
 Thêm OCR toàn trang                                                     Content 34.44%, pass 19.73%    Giữ OCR
───────────────────────────────────  ────────────────────────────────────────────────────────────────  ──────────────────────
 OCR không giảm trọng số                                    Document giảm còn 83.81%, content 33.52%    Loại
───────────────────────────────────  ────────────────────────────────────────────────────────────────  ──────────────────────
 OCR + candidate multiplier 8                                        Document 88.26%, content 37.66%    Giữ
───────────────────────────────────  ────────────────────────────────────────────────────────────────  ──────────────────────
 Hybrid dense + lexical retrieval                       Document 90.65%, content 41.33%, pass 23.72%    Giữ làm baseline mới
───────────────────────────────────  ────────────────────────────────────────────────────────────────  ──────────────────────
 Structured table toàn cục                                                   Content giảm còn 36.85%    Loại
───────────────────────────────────  ────────────────────────────────────────────────────────────────  ──────────────────────
 Table query routing                                                          Table đạt 119/299 hits    Giữ
───────────────────────────────────  ────────────────────────────────────────────────────────────────  ──────────────────────
 Table parent expansion                                           Table pass 105/299, tăng từ 92/299    Giữ
───────────────────────────────────  ────────────────────────────────────────────────────────────────  ──────────────────────
 Visual crop gắn vào page chunk                          Figure 16 hits, 13 pass; annotation 34 pass    Không dùng mặc định
───────────────────────────────────  ────────────────────────────────────────────────────────────────  ──────────────────────
 Visual-element index + region OCR                                   Figure 34/159 hits, 19/159 pass    Giữ cho figure
───────────────────────────────────  ────────────────────────────────────────────────────────────────  ──────────────────────
 OCR tile cố định cho annotation                                       92/285 hits, thấp hơn 109/285    Loại
───────────────────────────────────  ────────────────────────────────────────────────────────────────  ──────────────────────
 Page snapshot cho annotation                             Đã triển khai, nhưng generation bị timeout    Chưa chốt điểm

## Cấu hình đang chọn

Hybrid dense + lexical retrieval
+ OCR toàn trang
+ candidate multiplier 8
+ table structured chunks
+ table query routing
+ table parent expansion
+ visual-element index riêng cho figure
+ region OCR cho figure

Kết quả tốt nhất toàn bộ benchmark:

Document hit: 90.65%
Content hit: 41.33%
Assertion pass: 23.72%

## Kết luận theo loại dữ liệu

### Figure

Visual crop có hiệu quả khi được biến thành retrieval item độc lập:

Trước: 20 retrieval hits, 11 assertion pass
Sau:   34 retrieval hits, 19 assertion pass

### Annotation

Visual crop hiện tại chưa đại diện đúng cho:

Callout box
Highlight màu
Colored table
Bố cục cần đếm dòng/cột

OCR tile làm giảm điểm, nên chưa bật cho annotation.

## Hướng thay thế tiếp theo

Giữ cấu hình hybrid + OCR + table cho production.

Giữ visual-element OCR cho figure.

Với annotation, phát triển detector dựa trên:
Màu nền và vùng highlight.
Đường viền/callout.
Geometry của vùng bảng.
Quan hệ giữa text và vùng đánh dấu.

Dùng page snapshot làm fallback generation sau khi retrieval chọn đúng trang.

Re-ingest tài liệu để lưu đầy đủ crop, bbox và metadata mới.