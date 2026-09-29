1. Đừng nhét tất cả vào prompt → thiết kế Prompt Boundary rõ: instruction ≠ user data ≠ RAG data ≠ tool output.
2. Context không phải càng nhiều càng tốt → đặt Token Budget, chỉ đưa những gì cần thiết.
3. Đừng tin context dài → Context Rot khiến thông tin dù vẫn nằm trong context nhưng model có thể sử dụng kém hơn. → retrieve/rerank/compress.
4. Đừng coi conversation là memory → Memory phải có cơ chế chọn lọc, cập nhật và kiểm soát; không lưu mọi thứ agent nói.
5. Tool calling phải có contract → tool có schema, input/output rõ ràng, permission rõ ràng; agent không được tùy tiện gọi tool nguy hiểm.
6. Tool result là untrusted input → validate/sanitize/schema-check trước khi đưa lại cho LLM. Đặc biệt chống prompt injection từ web/RAG/MCP.



RAG architect: 
User
 ↓
Boundary
 ↓
Router / Agent
 ├── Memory ──→ filter
 ├── RAG ─────→ retrieve → rerank → limit
 └── Tool ────→ permission
                    ↓
                Tool Result
                    ↓
             validate/sanitize
                    ↓
                   Agent
                    ↓
                 Answer

7. Confidence UI

Không chỉ cho user xem câu trả lời, mà cho họ biết agent tự tin đến mức nào / căn cứ vào đâu.

Ví dụ RAG ngân hàng:

Phí duy trì tài khoản: 10.000đ/tháng

Confidence: High
Sources: Điều 5, biểu phí 2025

Quan trọng: confidence không nên chỉ là một con số LLM tự bịa ra.

Có thể dựa trên:

retrieval score
số lượng nguồn đồng thuận
evidence coverage
model confidence
rule/policy checks

→ User biết khi nào nên tin và khi nào cần kiểm tra.


8. Human Review

Không phải việc gì cũng để AI tự quyết.

Thiết kế:

AI
 ↓
Draft
 ↓
Human Review
 ↓
Approve / Edit / Reject
 ↓
Production

Ví dụ:

AI tạo câu hỏi → người duyệt
AI trích xuất thông tin hợp đồng → người kiểm tra
AI tạo email → user sửa trước khi gửi
AI chuẩn bị SQL → engineer review trước execution

Đặc biệt với high-impact actions, human review có thể là safety gate.


9. Feedback loop: 

User:
"Thông tin này sai."

       ↓

Feedback:
wrong_answer

       ↓

Log:
query
retrieved_chunks
tool_calls
model
prompt version
answer

       ↓

Analysis

       ↓

Fix:
retrieval / prompt / tool / model / data

10. . Failure Mode Library

Đây là thứ mình nghĩ AI Engineer nên có càng sớm càng tốt.

Thay vì mỗi lần agent lỗi lại debug từ đầu, xây một thư viện:

Failure Mode

FM-001
Wrong retrieval

FM-002
Hallucination

FM-003
Prompt injection

FM-004
Tool timeout

FM-005
Invalid tool arguments

FM-006
Tool returns malicious content

FM-007
Context overflow

FM-008
Memory contamination

Mỗi failure nên có:

Symptom
Cause
Example
Detection
Mitigation
Test case

Sau đó biến failure thành regression test:

Bug xảy ra
   ↓
ghi vào Failure Library
   ↓
tạo test case
   ↓
fix
   ↓
CI evaluation

Một bug xảy ra một lần, không nên để nó xảy ra lần thứ hai mà không bị phát hiện.

11. 6. ROI cho AI Engineer

Cuối cùng là câu hỏi:

AI này thực sự tạo ra giá trị gì?

Không phải cứ:

RAG + Agent + MCP + Vector DB + VLM

là có ROI.

Phải đo:

Before AI
↓
thời gian xử lý = 30 phút
chi phí = 50k
accuracy = 85%

After AI
↓
thời gian = 5 phút
chi phí = 8k
accuracy = 92%

Có thể tính các metric như:

thời gian tiết kiệm
cost/request
throughput
automation rate
human review rate
error rate
task success rate
revenue/cost impact

Ví dụ:

1000 tasks/month

Manual:
30 min/task

AI:
5 min/task + 10% cần review

→ giảm đáng kể thời gian vận hành

12. Một project cần có Prototype, SPEC, Demo, User Flow và Success Criteria.
Mình nhận ra demo tốt không phải là làm cho AI trông “magic”.
Demo tốt là cho người xem thấy:
bài toán là gì,
user đang đau ở đâu,
workflow mới giải quyết nó như thế nào,
và kết quả có đủ rõ để tin được hay không.
Phần SPEC cũng rất quan trọng.
Nếu không viết rõ input, output, tool, data, scope và success criteria, team rất dễ bị cuốn vào việc build nhiều thứ nhưng không có một luồng chính đủ mạnh.

13. Bản chất Pipeline RAG nên là Pipeline : Raw Knowledge → Chunking → Embedding → Vector Store → Retrieval → Grounded Answer

Nếu chunking sai, retrieval sẽ yếu.
Nếu metadata thiếu, hệ thống khó lọc đúng context.
Nếu evaluation không rõ, mình không biết RAG đang tốt lên hay tệ đi.
Và nếu retrieval sai, LLM vẫn có thể trả lời rất tự tin — nhưng tự tin trên context sai.

gồm data strategy, embedding, vector search, retrieval evaluation và reliability.



