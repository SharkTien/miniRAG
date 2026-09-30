# Hồ sơ nghiên cứu và xử lý dữ liệu cho hệ thống RAG

## 1. Mục đích và vai trò của nghiên cứu dữ liệu

Tài liệu này ghi lại quá trình khảo sát, chuẩn hóa, thử nghiệm và lựa chọn
phương án xử lý dữ liệu cho Mini RAG Service. Đây là một phần của sản phẩm,
không phải phụ lục mô tả cách chạy. Với vai trò kỹ sư dữ liệu và nhà khoa học dữ liệu,
cần chứng minh được dữ liệu đầu vào đã được phân loại, các lỗi đã được đo lường,
phương án đã được so sánh và quyết định triển khai có căn cứ.

Nghiên cứu tập trung vào bốn câu hỏi:

1. Tài liệu có lớp chữ sẵn hay là bản quét cần nhận dạng ký tự?
2. Nội dung quan trọng nằm ở văn bản thường, bảng, hình, chú thích hay biểu mẫu?
3. Cách trích xuất và chia nhỏ nào giúp hệ thống tìm đúng đoạn có thể trả lời?
4. Kết quả đánh giá thử nghiệm nào đủ ổn định để đưa vào luồng tải lên môi trường vận hành?

Nguyên tắc đánh giá là tách rõ ba lớp: chất lượng dữ liệu sau trích xuất,
khả năng tìm đúng tài liệu và khả năng tìm đúng bằng chứng để trả lời. Một
chunk có chủ đề giống câu hỏi nhưng không chứa dữ kiện trả lời được xem là
liên quan theo chủ đề, chưa được xem là bằng chứng đạt yêu cầu.

## 2. Phạm vi và hồ sơ dữ liệu

### 2.1 Bộ dữ liệu đánh giá

Đánh giá thử nghiệm được chạy trên 5 tệp PDF SynthDocQA, tổng cộng 877 câu hỏi. Các câu
hỏi được chia theo loại dữ liệu mà câu trả lời phụ thuộc vào:

| Loại dữ liệu | Số câu | Tỷ lệ | Rủi ro chính |
|---|---:|---:|---|
| Bảng | 299 | 34,1% | Mất quan hệ hàng, cột và tiêu đề khi tách chữ |
| Biểu mẫu | 107 | 12,2% | Ô trống, nhãn và giá trị bị tách rời |
| Hình | 159 | 18,1% | Dữ kiện nằm trong sơ đồ hoặc hình minh họa |
| Chú thích/đánh dấu | 285 | 32,5% | Callout, tô màu và vùng đánh dấu không có lớp chữ độc lập |
| Văn bản thường | 27 | 3,1% | Ít rủi ro hơn nhưng vẫn chịu ảnh hưởng của chia đoạn |
| Tổng | 877 | 100% | |

### 2.2 Kiểm kê dữ liệu trước khi lập chỉ mục

Mỗi tài liệu cần được ghi nhận tối thiểu: số trang, có lớp chữ hay không, tỷ
lệ trang cần OCR, số bảng, số hình, số vùng chú thích, ngôn ngữ, số chunk,
tạo vector model, thời điểm tạo và nguồn tệp. Với bảng và vùng trực quan, hệ
thống cần lưu thêm page_number, bbox, parent_chunk_id, element_type và liên
kết về tài liệu gốc.

Kiểm kê này giúp phân biệt ba lỗi thường bị gộp nhầm:

- Lỗi trích xuất: dữ kiện đã có trong PDF nhưng không đi vào văn bản hoặc
  cấu trúc trung gian.
- Lỗi lập chỉ mục: dữ kiện đã trích xuất nhưng chunk hoặc tạo vector không
  được lưu đúng.
- Lỗi truy xuất: chunk đúng tồn tại nhưng không lọt vào tập ứng viên hoặc
  bị xếp dưới các chunk chỉ giống chủ đề.

## 3. Chuẩn hóa và xử lý dữ liệu

### 3.1 Tuyến xử lý đã nghiên cứu

    Tệp gốc
      ↓
    Phân loại lớp chữ, trang quét, bảng, hình, chú thích
      ↓
    Trích xuất Docling; OCR toàn trang bằng NVIDIA khi cần
      ↓
    Làm sạch ký tự điều khiển, khoảng trắng và phần đầu/cuối rác
      ↓
    Tạo chunk văn bản, bảng, phần tử trực quan và liên kết chunk cha
      ↓
    Tạo vector NVIDIA + chỉ mục từ khóa
      ↓
    Truy xuất kết hợp, lọc tài liệu, xếp hạng bằng chứng
      ↓
    Đánh giá khả năng trả lời và lưu nguồn

### 3.2 Các phép kiểm tra chất lượng

Nghiên cứu dữ liệu sử dụng các phép kiểm tra sau trước khi kết luận về mô hình:

- kiểm tra mất chữ, ký tự lỗi và dòng bị ghép sai;
- kiểm tra bảng có còn tiêu đề, thứ tự cột và quan hệ hàng hay không;
- kiểm tra vùng hình/chú thích có bbox và số trang để truy ngược hay không;
- kiểm tra chunk không trộn hai tài liệu hoặc hai nhánh nghiệp vụ;
- kiểm tra mỗi câu hỏi có thể truy về tài liệu, trang và chunk cụ thể;
- kiểm tra các cụm rác như đầu trang, chân trang, ký tự mạng xã hội và đoạn
  điều hướng không chiếm vị trí cao trong truy xuất.

Chunk được đánh giá theo khả năng chứa dữ kiện trả lời, không chỉ theo số
từ khóa trùng. Ví dụ, với câu hỏi về thời gian hoàn tiền bằng thẻ NAPAS,
chunk có “thẻ nội địa NAPAS — 2–5 ngày làm việc” là bằng chứng chính; chunk
chỉ nói chung về thời hạn yêu cầu trả hàng là ngữ cảnh phụ.

## 4. Thiết kế đánh giá thử nghiệm và chỉ số

Mỗi phương án được chạy trên cùng bộ 877 câu hỏi và so sánh ba chỉ số:

- Tìm đúng tài liệu: tài liệu đúng xuất hiện trong kết quả.
- Tìm đúng nội dung: kết quả có đoạn chứa thông tin cần trả lời.
- Mệnh đề đúng: câu trả lời cuối cùng đúng các mệnh đề được kiểm tra.

Tìm đúng tài liệu đo khả năng định vị nguồn; tìm đúng nội dung đo chất lượng dữ liệu và
truy xuất; mệnh đề đúng đo chất lượng đầu ra sau khi mô hình tổng hợp. Không
được dùng tìm đúng tài liệu cao để che giấu việc tìm đúng nội dung thấp.

## 5. Ma trận thử nghiệm và quyết định

| Phương án | Kết quả chính | Quyết định |
|---|---|---|
| Tuyến ban đầu | tài liệu 85,52%; nội dung 33,52%; assertion 18,59% | Mốc so sánh |
| Thêm OCR toàn trang | nội dung 34,44%; mệnh đề 19,73% | Giữ làm lớp bổ sung |
| OCR nhưng không tăng tập ứng viên | Document giảm còn 83,81%; nội dung 33,52% | Loại |
| OCR + hệ số mở rộng ứng viên 8 | tài liệu 88,26%; nội dung 37,66% | Giữ |
| Truy xuất kết hợp vector và từ khóa | tài liệu 90,65%; nội dung 41,33%; mệnh đề 23,72% | Mốc so sánh mới |
| Tạo cấu trúc bảng toàn cục cho mọi truy vấn | Nội dung giảm còn 36,85% | Loại |
| Điều hướng truy vấn bảng | 119/299 câu bảng tìm đúng | Giữ theo điều kiện |
| Mở rộng từ chunk bảng về chunk cha | 105/299 câu bảng đạt, tăng từ 92/299 | Giữ |
| Gắn ảnh cắt vào chunk trang | Hình: 16 lần tìm đúng, 13 đạt; chú thích: 34 đạt | Không dùng mặc định |
| Chỉ mục phần tử hình + OCR vùng | Hình: 34/159 lần tìm đúng, 19/159 đạt | Giữ cho hình |
| OCR lát cắt kích thước cố định cho chú thích | 92/285 lần tìm đúng, thấp hơn tuyến văn bản gốc/ngữ cảnh trang 109/285 | Loại |
| Ảnh chụp trang cho chú thích | Đã chuẩn bị nhưng một số lượt sinh bị quá thời gian | Chưa dùng để công bố điểm mới |

### 5.1 Cấu hình đánh giá thử nghiệm cao nhất

    OCR toàn trang
    + mở rộng tập ứng viên 8 lần
    + truy xuất kết hợp vector và từ khóa
    + chunk bảng có cấu trúc, điều hướng bảng và mở rộng chunk cha
    + chỉ mục phần tử hình độc lập
    + OCR theo vùng hình

Kết quả tốt nhất trên bộ 5 PDF:

| Chỉ số | Kết quả |
|---|---:|
| Tìm đúng tài liệu | 90,65% |
| Tìm đúng nội dung | 41,33% |
| Mệnh đề đúng | 23,72% |

Đây là kết quả của đánh giá thử nghiệm có các cache chuyên biệt cho bảng, hình và vùng
chú thích. Các số liệu này chưa phải cam kết chất lượng cho mọi tài liệu được
tải lên vào môi trường vận hành.

## 6. Phân tích lỗi theo loại dữ liệu

### 6.1 Bảng

Lỗi chính là tách từng dòng mà mất tiêu đề cột, hoặc đưa toàn bộ bảng vào một
chunk quá lớn. Cách có kết quả tốt hơn là giữ bảng có cấu trúc, thêm chunk cha
để cung cấp tiêu đề và chỉ dùng nhánh bảng khi câu hỏi có dấu hiệu hỏi về
phương án, mức tiền, thời hạn hoặc quan hệ cột.

### 6.2 Hình

Hình chỉ có giá trị truy xuất khi được lập chỉ mục như một phần tử riêng, có
liên kết trang và mô tả vùng. Cách chỉ gắn ảnh cắt vào chunk trang làm giảm
khả năng chọn đúng bằng chứng.

### 6.3 Chú thích và vùng đánh dấu

Chú thích thường là lớp trình bày chồng lên văn bản: callout, tô màu, đường
viền hoặc ghi chú bên cạnh bảng. OCR lát cắt cố định không ổn định vì vùng
thông tin thay đổi theo bố cục. Tuyến theo phạm vi tài liệu kết hợp ảnh cắt từ văn bản gốc và
ngữ cảnh trang đạt 117/285 tìm đúng nội dung và 45/279 mệnh đề đúng (15,79%),
tăng 11 câu đạt so với tuyến trước đó, nhưng vẫn cần detector dựa trên hình học
và quan hệ giữa vùng đánh dấu với văn bản.

### 6.4 Văn bản thường và biểu mẫu

Văn bản thường dễ xử lý hơn nhưng vẫn bị ảnh hưởng bởi header/footer và chunk
quá ngắn. Biểu mẫu cần giữ quan hệ nhãn–giá trị, không nên biến mỗi ô thành
chunk độc lập nếu câu hỏi yêu cầu đọc cả một dòng hoặc nhóm trường.

## 7. Từ kết quả nghiên cứu đến cấu hình môi trường vận hành

| Phát hiện từ dữ liệu | Thay đổi trong hệ thống |
|---|---|
| Tài liệu quét mất lớp chữ | OCR toàn trang bằng dịch vụ NVIDIA, có thời gian chờ và dự phòng |
| OCR có thể tạo chữ rác | Làm sạch ký tự điều khiển, chuẩn hóa khoảng trắng, loại vùng lặp |
| Chunk nhỏ làm mất ngữ cảnh bảng | Lưu chunk bảng, chunk cha và metadata hàng/cột |
| Từ khóa chung như “trả hàng” gây lẫn tài liệu | Kết hợp điểm vector và từ khóa, lập kế hoạch truy vấn, lọc danh tính tài liệu |
| Chunk giống chủ đề nhưng không trả lời được | Evidence service chấm mức phù hợp nội dung và ràng buộc câu hỏi |
| Hình chứa dữ kiện riêng | Lưu crop, ảnh trang, bbox và loại phần tử để có thể mở rộng thành chỉ mục hình |
| Mô hình ngữ nghĩa có thể chậm hoặc lỗi | Giới hạn thời gian, thử lại có kiểm soát và quay về OCR/chunk gốc |

Backend hiện đã có OCR toàn trang, phân tích bảng, truy xuất kết hợp, mở rộng
tập ứng viên, lọc theo danh tính tài liệu và lưu metadata vị trí. Hai phần
đánh giá thử nghiệm chưa được bật cho mọi tài liệu môi trường vận hành là chỉ mục phần tử hình
độc lập và nhánh OCR vùng chú thích. Vì vậy cần nạp lại tài liệu và chạy lại đánh giá thử nghiệm
sau khi hai nhánh này được triển khai.

## 8. Khả năng tái lập và kiểm soát thay đổi

Mỗi lần đánh giá thử nghiệm cần lưu:

- mã commit và phiên bản cấu hình;
- danh sách tệp, mã băm tệp và loại dữ liệu;
- mô hình OCR, tạo vector và mô hình sinh;
- kích thước chunk, độ chồng lấn, số ứng viên và ngưỡng lọc;
- kết quả theo từng câu hỏi, tài liệu, trang và loại dữ liệu;
- lý do giữ hoặc loại một phương án.

Tập kiểm tra cơ bản của dự án được lưu tại
output/retrieval_verification.csv và bản bảng tính tương ứng. Các kết quả
SynthDocQA chi tiết nằm trong thư mục evaluation/; không trộn chúng với điểm
kiểm tra API hoặc điểm kiểm thử đơn vị.

## 9. Việc cần làm tiếp theo

1. Tạo bộ mẫu môi trường vận hành cân bằng giữa văn bản, bảng, biểu mẫu, hình và chú
   thích; không chỉ dùng 5 PDF tổng hợp.
2. Re-ingest sau khi bật chỉ mục hình và OCR vùng chú thích, rồi so sánh cùng
   ba chỉ số trên.
3. Gắn nhãn câu hỏi theo thực thể, ý định và ràng buộc trả lời để đo lỗi
   mức phù hợp tài liệu và khả năng trả lời riêng biệt.
4. Bổ sung kiểm tra tự động cho bảng có tiêu đề, quan hệ nhãn–giá trị và nguồn
   trang trước khi cho phép tài liệu chuyển sang trạng thái processed.
5. Theo dõi độ trễ, tỷ lệ dự phòng OCR, tỷ lệ không tìm thấy bằng chứng và
   phân bố điểm hybrid theo từng loại dữ liệu.

## 10. Kết luận

Nghiên cứu dữ liệu cho thấy điểm yếu ban đầu không chỉ nằm ở mô hình sinh mà
chủ yếu nằm ở việc dữ kiện trong bảng, hình và chú thích chưa được biểu diễn
đúng trước khi tạo vector. Truy xuất kết hợp và cấu trúc hóa dữ liệu đã nâng
tìm đúng nội dung từ 33,52% lên 41,33% và mệnh đề đúng từ 18,59% lên 23,72% trên
bộ đánh giá thử nghiệm 5 PDF. Đây là cơ sở để chấm riêng năng lực nghiên cứu, xử lý và
kiểm soát chất lượng dữ liệu trong tiêu chí Trích xuất và xử lý dữ liệu; đồng
thời cần giữ rõ giới hạn rằng đánh giá thử nghiệm chuyên biệt chưa thay thế đánh giá
môi trường vận hành trên tài liệu thực tế.

## 11. Dẫn chứng trực quan

Các ảnh chụp dùng trong báo cáo bàn giao được lưu tại `output/images/`:

- `docker_CICD.png`: lần chạy quy trình tự động gồm kiểm tra chất lượng, bản dựng giao diện và dựng Docker.
- `pgvector.png`: cấu trúc bảng `document_chunks`, cột vector 2048 chiều và khóa liên kết về tài liệu.
- `upload.png`: tài liệu đã tải lên, bản xem trước và số lượng chunk trên giao diện.
- `chunk.png`: các đoạn sau khi chia, có tiêu đề và nội dung để truy xuất.

Mỗi ảnh được chú thích trong `output/milestones_bonus_ec.pdf` và được đối chiếu
với mã nguồn hoặc câu lệnh tạo ra kết quả tương ứng.
