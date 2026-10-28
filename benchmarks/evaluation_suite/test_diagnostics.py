import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from diagnose_labor import diagnose


class DiagnosticTests(unittest.TestCase):
    def archive(self, root):
        path = root / 'evaluation.zip'
        gold = [
            {'id': 'multi', 'required_groups': [['a', 'a2'], ['b']]},
            {'id': 'lost', 'required_groups': [['z']]},
        ]
        rows = [
            {'id': 'multi', 'variant': 'full', 'status': 'OK',
             'answer_status': 'INSUFFICIENT_EVIDENCE', 'trace_id': 't', 'citations': []},
            {'id': 'lost', 'variant': 'full', 'status': 'ERROR', 'answer_status': 'ERROR'},
            {'id': 'out', 'variant': 'full', 'status': 'OK', 'answer_status': 'ABSTAIN', 'trace_id': 'o'},
            {'id': 'multi', 'variant': 'without_graph', 'status': 'ERROR', 'answer_status': 'ERROR'},
        ]
        trace = {
            'retrieval_candidates': [{'unit_id': 'a2'}, {'unit_id': 'b'}],
            'events': [
                {'event': 'applicability_audit', 'decisions': [
                    {'evidence_id': 'a2', 'audit_status': 'PASS', 'reasons': ['MATCH', 'CONDITION']},
                    {'evidence_id': 'b', 'audit_status': 'UNRESOLVED', 'reasons': ['CONDITION']}]},
                {'event': 'selection', 'evidence_ids': ['a2']},
                {'event': 'semantic_answer_audit', 'error_code': 'GROUNDING_QUOTE_MISMATCH'},
            ],
        }
        with ZipFile(path, 'w') as z:
            z.writestr('labor_retrieval_gold.jsonl', '\n'.join(map(json.dumps, gold)))
            z.writestr('ablation/responses.jsonl', '\n'.join(map(json.dumps, rows)))
            z.writestr('ablation/traces/full/t.json', json.dumps(trace))
            z.writestr('ablation/traces/full/o.json', '{}')
            z.writestr('ablation/full_config.json', json.dumps({
                'adjudication': {'provider': 'ollama', 'review_provider': 'gemini', 'api_key': 'PRIVATE'},
                'researcher': {'model': 'test', 'secret': 'PRIVATE'}}))
        return path

    def test_partial_group_match_is_not_full_coverage_or_correctness(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = diagnose(self.archive(Path(tmp)))
        self.assertEqual(report['stage_matches']['seed_candidates_in_trace'], {'any': 1, 'all': 1})
        self.assertEqual(report['stage_matches']['auditor_any_pass'], {'any': 1, 'all': 0})
        self.assertEqual(report['stage_matches']['selected'], {'any': 1, 'all': 0})
        self.assertEqual(report['stage_matches']['public_citations'], {'any': 0, 'all': 0})
        self.assertEqual(report['selected_any_gold_but_blocked'], ['multi'])

    def test_missing_trace_and_failed_other_variant_do_not_corrupt_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = diagnose(self.archive(Path(tmp)))
        self.assertEqual(report['gold_questions'], 2)
        self.assertEqual(report['eligible_with_trace'], 1)
        self.assertEqual(report['eligible_missing_trace_ids'], ['lost'])
        self.assertEqual(report['technical_errors_all_questions'], 1)
        self.assertEqual(report['statuses_all_questions'], {
            'INSUFFICIENT_EVIDENCE': 1, 'ERROR': 1, 'ABSTAIN': 1})
        self.assertEqual(report['decision_reason_occurrences']['CONDITION'], 2)

    def test_config_is_allowlisted_and_report_does_not_extract_or_modify_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self.archive(root)
            original = archive.read_bytes()
            report = diagnose(archive)
            self.assertEqual(archive.read_bytes(), original)
            self.assertEqual(list(root.iterdir()), [archive])
        self.assertEqual(report['configuration']['adjudication']['review_provider'], 'gemini')
        self.assertNotIn('PRIVATE', json.dumps(report))
        self.assertEqual(report['review_error_occurrences'], {'GROUNDING_QUOTE_MISMATCH': 1})
