from app.retrieval.evidence_service import EvidenceService


def chunk(text, score=0.9, chunk_id="c1"):
    return {"chunk_id": chunk_id, "content": text, "similarity_score": score}


def test_related_registration_notice_is_not_sufficient_for_overtime_pay():
    service = EvidenceService()
    question = "Đăng ký và làm thêm giờ thì có được tính lương không?"
    result = service.assess(question, service.rerank(question, [chunk(
        "Hồ sơ đăng ký nội quy lao động được tiếp nhận và niêm yết tại nơi làm việc."
    )]))

    assert result.relevance == "RELEVANT"
    assert result.coverage != "SUFFICIENT"
    assert result.answerability is False
    assert result.missing_requirements


def test_overtime_rule_can_be_sufficient_from_content():
    service = EvidenceService()
    question = "Làm thêm giờ có được tính lương không?"
    chunks = service.rerank(question, [chunk(
        "Người lao động làm thêm giờ được trả tiền lương làm thêm giờ theo quy định tại điều này."
    )])
    result = service.assess(question, chunks)

    assert result.relevance == "RELEVANT"
    assert result.coverage == "SUFFICIENT"
    assert result.answerability is True


def test_filename_cannot_change_content_score():
    service = EvidenceService()
    question = "làm thêm giờ có được tính lương không"
    content = "Hồ sơ đăng ký nội quy lao động được tiếp nhận."
    first = service.rerank(question, [{"content": content, "similarity_score": 0.8, "file_name": "overtime-pay.pdf"}])
    second = service.rerank(question, [{"content": content, "similarity_score": 0.8, "file_name": "random.pdf"}])
    assert first[0]["content_relevance_score"] == second[0]["content_relevance_score"]
