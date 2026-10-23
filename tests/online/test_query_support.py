import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock
from vn_labor_online.query_support import restore_source_quote,task_bm25_channels
from vn_labor_online.answer_review import Review,validate_review
from vn_labor_online.errors import StructuredOutputError
from tests.online.test_semantic_answer_review import sample


class SourceRestorationTests(unittest.TestCase):
    def test_pdf_layout_returns_original_contiguous_source(self):
        source='Tiêu đề: Người lao động\n  được nghỉ\t12 ngày làm việc. Kết thúc.'
        quote='Người lao động được nghỉ 12 ngày làm việc.'
        result=restore_source_quote(quote,[source])
        self.assertEqual(result,'Người lao động\n  được nghỉ\t12 ngày làm việc.')
        self.assertIn(result,source)

    def test_number_negation_punctuation_and_case_cannot_be_rewritten(self):
        source='Không được giữ bản chính văn bằng; mức 12 ngày.'
        for quote in ['Được giữ bản chính văn bằng','Không được giữ bản chính văn bằng,',
                      'Không được giữ bản chính văn bằng; mức 21 ngày.',
                      'không được giữ bản chính văn bằng;']:
            with self.subTest(quote=quote): self.assertIsNone(restore_source_quote(quote,[source]))

    def test_cannot_bridge_distinct_evidence_texts(self):
        self.assertIsNone(restore_source_quote('Điều kiện bình thường được nghỉ 12 ngày',
            ['Điều kiện bình thường','được nghỉ 12 ngày']))

    def test_empty_and_unicode_whitespace(self):
        self.assertIsNone(restore_source_quote('   ',['Nội dung']))
        self.assertEqual(restore_source_quote('được nghỉ 12 ngày',['được\u00a0nghỉ\n12 ngày']),
            'được\u00a0nghỉ\n12 ngày')

    def test_review_still_requires_semantic_and_id_accounting(self):
        p,d,v=sample()
        source=p.evidence[0].text.replace('được nghỉ','được\n  nghỉ')
        p.evidence[0]=p.evidence[0].model_copy(update={'text':source,'full_text':source})
        review=Review.model_validate(v)
        self.assertEqual(validate_review(review,d,p,p.answer_tasks),{'claim'})
        self.assertEqual(review.claims[0].grounding[0].quote,source)
        v['claims'][0]['grounding'][0]['evidence_id']='other'
        with self.assertRaises(StructuredOutputError):validate_review(Review.model_validate(v),d,p,p.answer_tasks)


class TaskSearchTests(unittest.TestCase):
    def tasks(self,*queries):
        return [NS(task_id=str(i),retrieval_query=q) for i,q in enumerate(queries)]

    def test_each_independent_issue_is_searched_not_just_full_question(self):
        retriever=NS(bm25=Mock(side_effect=lambda q:[NS(unit_id=q,verified=False)]))
        tasks=self.tasks('giữ bản chính văn bằng','nghỉ hằng năm')
        channels,report=task_bm25_channels(retriever,tasks,['câu hỏi gồm hai yêu cầu'])
        self.assertEqual(retriever.bm25.call_count,2)
        self.assertEqual(len(channels),2)
        self.assertEqual([r['task_id'] for r in report['searched_tasks']],['0','1'])
        self.assertTrue(all(not channel[0].verified for channel in channels))

    def test_duplicate_queries_and_single_task_add_no_work(self):
        retriever=NS(bm25=Mock(return_value=[]))
        channels,report=task_bm25_channels(retriever,self.tasks('nghỉ phép'),[])
        self.assertEqual(channels,[]);retriever.bm25.assert_not_called()
        channels,report=task_bm25_channels(retriever,self.tasks('  Nghỉ  phép','NGHỈ PHÉP'),['nghỉ phép'])
        self.assertEqual(report['duplicate_task_ids'],['0','1'])
        retriever.bm25.assert_not_called()

    def test_budget_reports_deferred_tasks_without_mutating_plan(self):
        retriever=NS(bm25=Mock(return_value=[]));tasks=self.tasks('A','B','C')
        channels,report=task_bm25_channels(retriever,tasks,[],max_queries=2)
        self.assertEqual(len(channels),2)
        self.assertEqual(report['deferred_task_ids'],['2'])
        self.assertEqual(len(tasks),3)

    def test_zero_budget_does_not_silently_consider_tasks_searched(self):
        retriever=NS(bm25=Mock(return_value=[]))
        channels,report=task_bm25_channels(retriever,self.tasks('A','B'),[],max_queries=0)
        self.assertEqual(report['deferred_task_ids'],['0','1'])
        retriever.bm25.assert_not_called()

if __name__=='__main__': unittest.main()
