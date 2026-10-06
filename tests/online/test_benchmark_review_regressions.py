from __future__ import annotations

import unittest

from vn_labor_online.analysis import analyze, intake
from vn_labor_online.audit import citations, reference_audit
from vn_labor_online.config import AdjudicationConfig
from vn_labor_online.generation import LegalAdjudicator, adjudicate
from vn_labor_online.models import (
    Evidence,
    EvidenceState,
    SlotStatus,
    VerifiedEvidenceItem,
    VerifiedEvidencePack,
)


def state(ids):
    return EvidenceState(
        slots={"governing_rule": {"status": SlotStatus.FOUND_VERIFIED, "evidence_ids": ids}},
        gaps=["official_source", "applicable_version"],
        coverage=0.75,
        mandatory_slots=["governing_rule"],
    )


def verified(evidence_id, article, clause="", point="", text=""):
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


class BenchmarkReviewRegressionTests(unittest.TestCase):
    def test_negated_notice_threshold_means_zero_days(self):
        question = (
            "C ký HĐLĐ không xác định thời hạn, bị quấy rối tình dục tại nơi làm việc, "
            "nghỉ ngay trong ngày và không báo trước 45 ngày."
        )
        result = analyze(intake(question, []))
        self.assertEqual(result.facts.get("notice_days"), 0)
        candidate = next(item for item in result.fact_candidates if item.field == "notice_days")
        self.assertTrue(
            "nghỉ ngay" in candidate.source_quote.lower()
            or "không báo trước 45 ngày" in candidate.source_quote.lower()
        )

    def test_positive_notice_period_remains_unchanged(self):
        result = analyze(intake("Tôi chỉ báo trước 20 ngày rồi nghỉ việc.", []))
        self.assertEqual(result.facts.get("notice_days"), 20)

    def test_service_years_does_not_invent_twelve_worked_months(self):
        result = analyze(intake("Tôi làm cho công ty được 6 năm. Năm nay tôi được bao nhiêu ngày phép?", []))
        self.assertNotIn("worked_months", result.facts)
        self.assertIn(
            "Trong năm đang xét, người lao động đã làm việc thực tế bao nhiêu tháng?",
            result.missing_facts,
        )

    def test_money_question_requests_training_costs(self):
        result = analyze(
            intake(
                "Tôi nghỉ việc nhưng chỉ báo trước 35 ngày. Công ty yêu cầu tôi bồi thường bao nhiêu tiền?",
                [],
            )
        )
        self.assertTrue(any("chi phí đào tạo" in question for question in result.missing_facts))

    def test_minor_full_year_with_seniority_is_fifteen_days(self):
        evidence = [
            verified("minor", "113", "1", "b", "14 ngày làm việc đối với người lao động chưa thành niên."),
            verified("seniority", "114", text="Cứ đủ 05 năm làm việc thì số ngày nghỉ hằng năm tăng thêm 01 ngày."),
        ]
        pack = VerifiedEvidencePack(
            query="A 17 tuổi, làm đủ 12 tháng và đây là năm thứ 6.",
            query_date="2025-01-01",
            facts={
                "query_intent": "ANNUAL_LEAVE_CALC",
                "worked_months": 12,
                "work_category": "NORMAL",
                "minor": True,
                "service_years": 6,
            },
            requested_outcome="EXPLAIN",
            coverage_state=state(["minor", "seniority"]),
            evidence=evidence,
        )
        draft = adjudicate(pack, True, [])
        self.assertIn("Tổng tối thiểu là 15 ngày", draft.answer_summary)
        self.assertNotIn("Mức nền phù hợp là 12 ngày", draft.answer_summary)

    def test_overlapping_leave_groups_choose_sixteen_then_add_seniority(self):
        evidence = [
            verified("special", "113", "1", "c", "16 ngày làm việc đối với công việc đặc biệt nặng nhọc."),
            verified("seniority", "114", text="Cứ đủ 05 năm làm việc thì số ngày nghỉ hằng năm tăng thêm 01 ngày."),
        ]
        pack = VerifiedEvidencePack(
            query="Người khuyết tật làm việc đặc biệt nặng nhọc đủ 12 tháng, thâm niên 11 năm.",
            query_date="2025-01-01",
            facts={
                "query_intent": "ANNUAL_LEAVE_CALC",
                "worked_months": 12,
                "work_category": "SPECIAL_HEAVY",
                "disabled": True,
                "service_years": 11,
            },
            requested_outcome="EXPLAIN",
            coverage_state=state(["special", "seniority"]),
            evidence=evidence,
        )
        draft = adjudicate(pack, True, [])
        self.assertIn("không cộng chồng", draft.answer_summary)
        self.assertIn("Tổng tối thiểu là 18 ngày", draft.answer_summary)

    def test_mutual_agreement_bypasses_llm_and_passes_reference_audit(self):
        agreement = verified(
            "agreement",
            "34",
            "3",
            text="Hai bên thỏa thuận chấm dứt hợp đồng lao động.",
        )
        pack = VerifiedEvidencePack(
            query="Hai bên thỏa thuận chấm dứt.",
            query_date="2025-01-01",
            facts={"query_intent": "MUTUAL_TERMINATION", "mutual_termination_agreement": True},
            requested_outcome="ASSESS_LEGALITY",
            coverage_state=state(["agreement"]),
            evidence=[agreement],
        )
        adjudicator = LegalAdjudicator(AdjudicationConfig(mode="deterministic"))

        class FailingProvider:
            def structured(self, *args, **kwargs):
                raise AssertionError("provider must not run for a deterministic rule chain")

        adjudicator.provider = FailingProvider()
        draft, warnings = adjudicator.generate(pack, True, [])
        self.assertFalse(warnings)
        raw = Evidence(
            unit_id="agreement",
            retrieval_method="policy",
            document_id="doc",
            provision_identity_id="identity",
            provision_version_id="version",
            document_number="18/VBHN-VPQH",
            article_number="34",
            clause_number="3",
            text=agreement.text,
            source_text=agreement.text,
            kind="PROVISION",
            verified=True,
            source_url=agreement.official_url,
        )
        ok, problems = reference_audit(
            draft.answer_summary,
            [raw],
            citations([raw]),
            draft.claims,
        )
        self.assertTrue(ok, problems)


if __name__ == "__main__":
    unittest.main()
