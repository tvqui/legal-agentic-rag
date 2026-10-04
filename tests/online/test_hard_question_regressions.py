from __future__ import annotations

import unittest

from vn_labor_online.analysis import analyze, intake, plan_evidence
from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.config import ApplicabilityConfig
from vn_labor_online.generation import adjudicate
from vn_labor_online.models import (
    Evidence,
    EvidenceState,
    SlotStatus,
    VerifiedEvidenceItem,
    VerifiedEvidencePack,
)


def _state(ids: list[str]) -> EvidenceState:
    return EvidenceState(
        slots={"governing_rule": {"status": SlotStatus.FOUND_VERIFIED, "evidence_ids": ids}},
        gaps=["official_source", "applicable_version"],
        coverage=0.75,
        mandatory_slots=["governing_rule"],
    )


def _verified(evidence_id: str, article: str, clause: str = "", point: str = "", text: str = "") -> VerifiedEvidenceItem:
    return VerifiedEvidenceItem(
        evidence_id=evidence_id,
        instrument_number="18/VBHN-VPQH",
        article=article,
        clause=clause,
        point=point,
        text=text,
        binding=True,
        official_source=True,
        authority_rank=100,
        official_url="https://congbao.chinhphu.vn/source",
    )


class HardQuestionRegressionTests(unittest.TestCase):
    def test_incidental_employment_words_do_not_hide_out_of_scope_criminal_questions(self):
        questions = [
            "Tôi là nhân viên công ty và lấy trộm laptop của công ty. Tôi phạm tội gì và mức án tù tối đa bao nhiêu năm?",
            "Một công nhân đánh đồng nghiệp gây thương tích 25%. Người đó có bị truy cứu hình sự không?",
            "Giám đốc công ty đưa tiền cho cán bộ nhà nước để được cấp dự án. Cấu thành tội gì?",
            "Nhân viên dùng mạng nội bộ phát tán nội dung chống Nhà nước. Mức án hình sự thế nào?",
            "Công ty tranh chấp quyền sử dụng đất với hộ dân. Bên nào được cấp giấy chứng nhận?",
        ]
        for question in questions:
            with self.subTest(question=question):
                self.assertFalse(analyze(intake(question, [])).in_scope)

    def test_incomplete_scenarios_are_gated_before_retrieval(self):
        questions = [
            "Công ty cho tôi nghỉ ngay hôm nay. Việc đó có đúng luật không?",
            "Tôi muốn tự nghỉ việc. Tôi có phải báo trước không?",
            "Công ty trả lương chậm nên tôi muốn nghỉ ngay. Tôi có được nghỉ không cần báo trước không?",
            "Tôi mới làm ở công ty chưa đủ một năm. Hỏi năm nay tôi được bao nhiêu ngày phép?",
            "Tôi nghỉ việc nhưng chỉ báo trước 35 ngày. Công ty yêu cầu tôi bồi thường bao nhiêu tiền?",
        ]
        for question in questions:
            with self.subTest(question=question):
                result = analyze(intake(question, []))
                self.assertTrue(result.in_scope)
                self.assertTrue(result.missing_facts)

    def test_definition_and_consequences_are_planned_as_two_rules(self):
        question = (
            "Hãy xác định điều luật định nghĩa khi nào đơn phương chấm dứt hợp đồng lao động trái pháp luật "
            "và điều luật quy định nghĩa vụ của người lao động sau đó."
        )
        result = analyze(intake(question, []))
        self.assertEqual(result.facts.get("query_intent"), "UNLAWFUL_DEFINITION_CONSEQUENCES")
        slots = plan_evidence(result).mandatory_slots
        self.assertIn("legal_classification", slots)
        self.assertIn("legal_consequences", slots)

    def test_clause_two_late_wage_exception_is_not_rejected_as_contract_mismatch(self):
        item = Evidence(
            unit_id="late-wage",
            retrieval_method="hybrid",
            component_scores={"policy": 1.0},
            document_id="doc",
            provision_identity_id="identity",
            provision_version_id="version",
            document_number="18/VBHN-VPQH",
            article_number="35",
            clause_number="2",
            point_number="b",
            text="Người lao động được đơn phương chấm dứt không cần báo trước khi không được trả lương đúng thời hạn.",
            source_text="Người lao động được đơn phương chấm dứt không cần báo trước khi không được trả lương đúng thời hạn.",
            kind="PROVISION",
            verified=True,
        )
        facts = {
            "actor": "EMPLOYEE",
            "contract_type": "INDEFINITE",
            "notice_days": 1,
            "termination_basis": "LATE_WAGE",
            "force_majeure_exception": False,
            "notice_exception": True,
        }
        accepted, decisions, _ = LegalApplicabilityAuditor(ApplicabilityConfig()).audit(
            [item], "Công ty trả lương chậm, người lao động nghỉ ngay", ["TERMINATION", "WAGE"], facts, "ASSESS_LEGALITY"
        )
        self.assertEqual([candidate.unit_id for candidate in accepted], ["late-wage"])
        self.assertEqual(decisions[0].audit_status, "PASS")
        self.assertIn("DETERMINISTIC_LATE_WAGE_CHAIN", decisions[0].reasons)

    def test_annual_leave_calculation_uses_base_then_seniority_without_double_counting(self):
        evidence = [
            _verified("base", "113", "1", "a", "12 ngày làm việc đối với công việc trong điều kiện bình thường."),
            _verified("seniority", "114", text="Cứ đủ 05 năm làm việc thì số ngày nghỉ hằng năm tăng thêm 01 ngày."),
        ]
        pack = VerifiedEvidencePack(
            query="Người lao động bình thường làm đủ 12 tháng và có 9 năm thâm niên thì có bao nhiêu ngày phép?",
            query_date="2025-01-01",
            facts={
                "query_intent": "ANNUAL_LEAVE_CALC",
                "worked_months": 12,
                "work_category": "NORMAL",
                "service_years": 9,
            },
            requested_outcome="EXPLAIN",
            coverage_state=_state(["base", "seniority"]),
            evidence=evidence,
        )
        draft = adjudicate(pack, True, [])
        self.assertIn("Tổng tối thiểu là 13 ngày", draft.answer_summary)
        self.assertNotIn("24 ngày", draft.answer_summary)

    def test_mutual_agreement_is_not_treated_as_unilateral_notice_breach(self):
        agreement = _verified(
            "agreement",
            "34",
            "3",
            text="Hai bên thỏa thuận chấm dứt hợp đồng lao động.",
        )
        pack = VerifiedEvidencePack(
            query="Công ty đồng ý bằng văn bản cho nghỉ sớm; có tự động coi là đơn phương trái pháp luật không?",
            query_date="2025-01-01",
            facts={"query_intent": "MUTUAL_TERMINATION", "mutual_termination_agreement": True},
            requested_outcome="ASSESS_LEGALITY",
            coverage_state=_state(["agreement"]),
            evidence=[agreement],
        )
        draft = adjudicate(pack, True, [])
        self.assertTrue(draft.answer_summary.startswith("Không."))
        self.assertIn("Khoản 3 Điều 34", draft.answer_summary)
        self.assertNotIn("phải bồi thường", draft.answer_summary)


if __name__ == "__main__":
    unittest.main()
