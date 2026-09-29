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

## Cấu hình tạo kết quả benchmark cao nhất

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
Sau:   34/159 content hits, 19/159 assertion pass (11,95%)

### Annotation

Đã thử ba hướng xử lý:

1. Gắn visual crop vào page chunk: không đủ để truy xuất đúng vùng chú thích.
2. OCR tile cố định: đạt 92/285 content hits, thấp hơn cách lấy native/page context.
3. Document-scoped retrieval kết hợp native crop và page snapshot: đạt
   117/285 content hits và 45/279 assertion pass (15,79%), tăng 11 câu pass
   so với tuyến annotation trước đó.

Các trường hợp vẫn khó:

Callout box
Highlight màu
Colored table
Bố cục cần đếm dòng/cột

Page snapshot đã được chuẩn bị làm bằng chứng cho bước sinh câu trả lời, nhưng
một số lần chạy generation bị timeout. Vì vậy chưa dùng kết quả page snapshot
để tuyên bố một điểm tổng hợp mới.

## Hướng thay thế tiếp theo

Giữ cấu hình hybrid + OCR + table cho production.

Giữ visual-element OCR cho figure.

Với annotation, hướng tiếp theo là phát triển detector dựa trên:
Màu nền và vùng highlight.
Đường viền/callout.
Geometry của vùng bảng.
Quan hệ giữa text và vùng đánh dấu.

Dùng page snapshot làm fallback generation sau khi retrieval chọn đúng trang,
đồng thời giới hạn kích thước ảnh và thời gian gọi mô hình để tránh timeout.

Re-ingest tài liệu để lưu đầy đủ crop, bbox và metadata mới.

## Đối chiếu với backend production hiện tại

Các số liệu trên được tạo từ bộ benchmark 5 PDF, trong đó benchmark có thể nạp
thêm các cache chuyên biệt `table_structured`, `visual_element` và
`annotation_region`. Đây không phải là toàn bộ luồng upload production.

Backend production hiện đã nạp các phần nền tảng của cấu hình tốt nhất:

- OCR toàn trang.
- Phân tích cấu trúc bảng và tạo phần tử bảng theo hàng khi Docling trả về dữ liệu ô.
- Hybrid retrieval bằng vector và từ khóa.
- Candidate multiplier bằng 8 trước khi rerank.
- Lưu crop hình, ảnh toàn trang và metadata vị trí.

Backend production vẫn chưa tương đương hoàn toàn với benchmark ở hai điểm:

- Visual crop chưa được lập chỉ mục như một retrieval item độc lập cho mọi tài liệu.
- OCR vùng annotation chưa được tạo thành nhánh truy xuất độc lập.

Vì vậy các chỉ số `90.65%`, `41.33%` và `23.72%` là kết quả của cấu hình
benchmark có dữ liệu bổ sung; không nên ghi là điểm đã được xác nhận trực tiếp
trên mọi tài liệu upload production. Cần re-ingest một bộ tài liệu production
và benchmark lại sau khi triển khai hai nhánh visual/annotation độc lập. Hiện
chưa có điểm production mới thay thế cho kết quả SynthDocQA này.
