import unittest
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from vn_labor_online.analysis import analyze,intake
from vn_labor_online.models import AnswerTask
from vn_labor_online.tasks import merge_tasks


class PeerReviewContracts(unittest.TestCase):
    def test_dismissal_date_is_not_contract_signature_date(self):
        q='Tôi ký hợp đồng ngày 01/01/2020, công ty sa thải tôi ngày 01/10/2026. Việc sa thải có đúng luật không?'
        a=analyze(intake(q,[]))
        self.assertEqual(a.query_date,'2026-10-01')

    def test_event_date_resolution_does_not_depend_on_sentence_order(self):
        q='Công ty sa thải tôi ngày 02/08/2026. Trước đó tôi ký hợp đồng ngày 15/02/2019. Việc sa thải có đúng luật không?'
        self.assertEqual(analyze(intake(q,[])).query_date,'2026-08-02')

    def test_criminal_article_reference_is_not_a_labour_scope_pass(self):
        q='Theo Điều 173 Bộ luật Hình sự, trộm cắp tài sản bị phạt mấy năm tù?'
        self.assertFalse(analyze(intake(q,[])).in_scope)

    def test_civil_article_reference_is_not_a_labour_scope_pass(self):
        q='Theo Điều 651 Bộ luật Dân sự, ai được hưởng thừa kế?'
        self.assertFalse(analyze(intake(q,[])).in_scope)

    def test_civil_contract_word_does_not_masquerade_as_employment_contract(self):
        q='Theo Điều 428 Bộ luật Dân sự, tôi được đơn phương chấm dứt hợp đồng vay tiền không?'
        self.assertFalse(analyze(intake(q,[])).in_scope)

    def test_researcher_addition_cannot_be_dropped_after_twelfth_task(self):
        tasks=[AnswerTask(task_id=f't{i}',request_quote='Câu hỏi lao động',description=f'Vấn đề {i}',retrieval_query=f'Vấn đề {i}') for i in range(12)]
        extra=AnswerTask(task_id='extra',request_quote='Câu hỏi lao động',description='Yêu cầu bổ sung',retrieval_query='Yêu cầu bổ sung')
        self.assertEqual({t.task_id for t in merge_tasks(tasks,[extra])},{t.task_id for t in tasks}|{'extra'})

if __name__=='__main__':unittest.main()
