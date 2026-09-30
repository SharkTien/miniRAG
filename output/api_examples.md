# Ví dụ API hiện tại

## Health check

```bash
curl -fsS http://localhost:41873/health
# {"status":"ok"}
```

## Upload một hoặc nhiều file

```bash
curl -X POST http://localhost:41873/api/documents \\
  -F 'files=@policy.pdf' \\
  -F 'display_name=Chính sách bảo hành'
```

Response ban đầu:

```json
{
  "message": "Tải lên thành công",
  "documents": [{
    "document_id": "<uuid>",
    "file_name": "Chính sách bảo hành",
    "original_filename": "policy.pdf",
    "status": "queued",
    "total_chunks": 0
  }]
}
```

Định dạng hiện hỗ trợ: PDF, TXT, DOCX, CSV, Markdown, PPTX, XLSX, PNG, JPG và JPEG. Worker xử lý nền; xem tiến độ bằng `GET /api/documents` hoặc kết quả extraction.

## Đổi tên và hủy tài liệu

```bash
curl -X PATCH http://localhost:41873/api/documents/<document_id> \\
  -H 'Content-Type: application/json' \\
  -d '{"display_name":"Tên hiển thị mới"}'

curl -X POST http://localhost:41873/api/documents/<document_id>/cancel
curl -X DELETE http://localhost:41873/api/documents/<document_id>
```

Xóa tài liệu đang `queued`/`processing` sẽ hủy trạng thái trước khi xóa record và object.

## Query trả nguồn

```bash
curl -X POST http://localhost:41873/api/query \\
  -H 'Content-Type: application/json' \\
  -d '{"question":"Chính sách bảo hành sản phẩm là gì?","top_k":5}'
```

Response có `answer`, `sources`, `retrieved_chunks`, điểm tương thích và metadata trang/chunk.

## Query streaming

```bash
curl -N -X POST 'http://localhost:41873/api/query/stream' \\
  -H 'Content-Type: application/json' \\
  -d '{"question":"Thời gian hoàn tiền là bao lâu?"}'
```

Sự kiện `token` được gửi trong quá trình sinh; sự kiện `metadata` chứa `sources` và `retrieved_chunks`; cuối cùng là `data: [DONE]`.

## Ca lỗi

- Câu hỏi rỗng: HTTP 400.
- Định dạng không hỗ trợ hoặc file vượt kích thước: HTTP 400/413.
- Không có bằng chứng: trả lời từ chối hoặc nêu phần thiếu, không sinh nguồn giả.
