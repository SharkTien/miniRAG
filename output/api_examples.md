# API Demo Examples

## 1. Health check

```bash
curl -fsS http://localhost:41873/health
```

```json
{"status":"ok"}
```

## 2. Upload document

```bash
curl -X POST http://localhost:41873/documents -F 'files=@policy.pdf'
```

```json
{
  "message": "Tải lên thành công",
  "documents": [
    {
      "document_id": "<uuid>",
      "file_name": "policy.pdf",
      "status": "queued",
      "total_chunks": 0
    }
  ]
}
```

Upload hỗ trợ tối thiểu PDF, TXT và DOCX. Worker tiếp tục xử lý `queued` thành
`processed`; dùng `GET /documents/{document_id}/extraction` để xem
`total_chunks` sau khi ingestion hoàn tất.

## 3. Query có source

```bash
curl -X POST http://localhost:41873/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Chính sách bảo hành là gì?","top_k":5}'
```

```json
{
  "answer": "...",
  "sources": [
    {
      "file_name": "policy.pdf",
      "chunk_id": "chunk_10",
      "page": 2,
      "similarity_score": 0.84,
      "snippet": "..."
    }
  ],
  "total_chunks_retrieved": 1,
  "execution_time_seconds": 0.42
}
```

## 4. Conversation và lưu tin nhắn

```bash
curl -X POST http://localhost:41873/api/conversations \
  -H 'Content-Type: application/json' \
  -d '{"title":"Tra cứu chính sách"}'
```

Gửi câu hỏi vào `POST /api/conversations/{conversation_id}/messages`. Backend
lưu cả tin nhắn `user` và `assistant` vào bảng `messages`; dùng
`GET /api/conversations` để liệt kê nhiều hộp thoại và `GET
/api/conversations/{conversation_id}` để đọc lịch sử.

## 5. Validation/error cases

```bash
curl -X POST http://localhost:41873/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"   "}'
```

Expected: HTTP `400`, message `question` không được để trống.

File extension không hỗ trợ bị từ chối ở document service. Query không có
evidence phù hợp sẽ báo không đủ dữ liệu hoặc không tìm thấy thông tin thay vì
sinh câu trả lời không xác định được nguồn.
