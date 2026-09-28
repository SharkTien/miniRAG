# Benchmark summary — 5 PDF SynthDocQA

Phạm vi gồm đúng 5 PDF cục bộ và 877 câu hỏi liên quan các file này. Các chỉ
số `content hit` là proxy literal answer-span; `assertion pass` yêu cầu câu trả
lời đạt toàn bộ assertion của câu hỏi.

| Pipeline | Document hit | Content hit | Assertion pass |
| --- | ---: | ---: | ---: |
| Baseline trước tuning | 85.52% | 33.52% | 18.59% (163/877) |
| Hybrid dense + lexical + grounded generation | **90.65%** | **41.33%** | **23.72% (208/877)** |

Các tuyến chuyên biệt đã được kiểm tra:

- **Table**: table routing + parent context đạt 105/299 assertion pass
  (35.12%), tăng 13 câu so với hybrid table route.
- **Figure**: visual-element OCR + crop đạt 34/159 content hits và 19/159
  assertion pass (11.95%), tăng 8 câu pass so với hybrid figure route.
- **Annotation**: document-scoped retrieval + native crop/page snapshot đạt
  117/285 content hits và 45/279 assertion pass (15.79%), tăng 11 câu pass
  so với tuyến annotation trước đó.

## Diễn giải

Hybrid retrieval cải thiện rõ document/content recall. Hình và annotation vẫn
là phần yếu nhất vì nhiều đáp án nằm trong pixel/layout thay vì text layer;
pipeline production hiện đã lưu picture crop và snapshot từng trang để vision
model có bằng chứng trực quan khi chunk tương ứng được retrieve.

Các số liệu trên không thể so trực tiếp với RAGBench/TRACe vì SynthDocQA không
có relevant-span/utilized-span annotation đầy đủ. Báo cáo benchmark chi tiết
và các artifact thử nghiệm nằm trong thư mục `test/` khi chạy benchmark cục bộ.
