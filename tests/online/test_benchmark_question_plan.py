import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('benchmark_plan_tests',ROOT/'scripts/benchmark_online_reliability.py')
benchmark=importlib.util.module_from_spec(spec); spec.loader.exec_module(benchmark)


class BenchmarkQuestionPlanTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)

    def write(self,value):
        path=self.root/'plan.json'; path.write_text(json.dumps(value),encoding='utf-8'); return path

    def test_custom_plan_preserves_original_question_and_context(self):
        row={'id':'one','question':'Question?','conversation_turns':[{'role':'user','turn_id':'one','content':'Previous'}]}
        self.assertEqual(benchmark.plan(self.write([row])),[row])

    def test_custom_conversations_are_isolated_unless_a_group_id_is_explicit(self):
        first={'id':'one','question':'Question?'}
        second={'id':'two','question':'Follow-up?','conversation_turns':[{'role':'user','turn_id':'one','content':'Previous'}]}
        with patch.object(benchmark.secrets,'token_hex',side_effect=['aaaa','bbbb']):
            self.assertEqual(benchmark.conversation_id_for(first),'bench_aaaa')
            self.assertEqual(benchmark.conversation_id_for(second),'bench_bbbb')
        self.assertEqual(benchmark.conversation_id_for({'batch':'USER_5'}),'reliability_user5')
        self.assertEqual(benchmark.conversation_id_for({'conversation_id':'case-1'}),'case-1')

    def test_empty_duplicate_or_missing_questions_are_rejected(self):
        for value in ([],{},[{}],[{'id':'a','question':' '}],
                      [{'id':'a','question':'Q?'},{'id':'a','question':'Q?'}]):
            with self.subTest(value=value),self.assertRaises(ValueError): benchmark.plan(self.write(value))

    def test_custom_conversation_id_is_validated(self):
        with self.assertRaisesRegex(ValueError,'conversation_id'):
            benchmark.plan(self.write([{'id':'a','question':'Q?','conversation_id':'not safe / invalid'}]))

    def test_export_counts_the_actual_custom_plan(self):
        (self.root/'questions.json').write_text(json.dumps([{'id':str(i),'question':'Q'} for i in range(100)]))
        row={'id':'0','question':'Q','elapsed_seconds':1.25,'http_status':200,
             'response':{'status':'PARTIAL_ALLOWED','answer':'Answer','citations':[]}}
        (self.root/'responses.jsonl').write_text(json.dumps(row)+'\n')
        summary=benchmark.export(self.root)
        self.assertEqual(summary['planned'],100)
        self.assertEqual(summary['remaining'],99)
        self.assertEqual(summary['attempted'],1)
        self.assertTrue((self.root/'responses.csv').is_file())

    def test_resuming_different_question_text_is_rejected_before_connection(self):
        plan=self.write([{'id':'a','question':'Changed?'}])
        (self.root/'questions.json').write_text(json.dumps([{'id':'a','question':'Original?'}]))
        (self.root/'responses.jsonl').write_text('{}\n')
        with patch.object(benchmark,'Connection') as connection,self.assertRaisesRegex(ValueError,'plan changed'):
            benchmark.run(self.root,set(),20,True,plan)
        connection.assert_not_called()


if __name__=='__main__': unittest.main()
