import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_offline_completion import audit_completion
from scripts.package_offline_human_review import quarantine_cases


class OfflineCompletionAuditTests(unittest.TestCase):
    def test_quarantine_groups_raw_rows_under_root_issues(self):
        rows = [
            {"document_id": "d1", "provision_id": "p1", "parent_id": None},
            {"document_id": "d1", "provision_id": "p2", "parent_id": "p1"},
            {"document_id": "d2", "provision_id": "p3", "parent_id": None},
        ]
        issues = [
            {"type": "SHORT_PROVISION_QUARANTINED", "document_id": "d1", "provision_id": "p1"},
            {"type": "AMBIGUOUS_CANONICAL_PATH_QUARANTINED", "document_id": "d2",
             "duplicate_ids": ["p3"], "quarantined_rows": 1},
        ]
        cases, members = quarantine_cases(issues, rows, {})
        self.assertEqual(len(cases), 2)
        self.assertEqual(len(members), 3)
        self.assertEqual(sum(case["member_count"] for case in cases), 3)
        self.assertTrue(all(case["review_status"] == "DRAFT" for case in cases))

    def test_missing_automation_prerequisites_is_failed_not_human_waiting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            reports.mkdir()
            (reports / "final_outputs_validation.json").write_text(json.dumps({
                "stages": {name: True for name in ("registry", "structure", "graph", "indexes")},
                "checks": [],
            }), encoding="utf-8")
            (reports / "neo4j_validation.json").write_text(
                json.dumps({"passed": True, "build_id": "build-1"}), encoding="utf-8")
            seed = root / "seed.csv"
            seed.write_text(
                "record_id,source_group,legal_decision\n"
                "r1,LEGAL_DOCUMENT,\n", encoding="utf-8")
            (root / "legal_change_review_queue.jsonl").write_text(
                '{"review_status":"DRAFT"}\n', encoding="utf-8")
            (root / "quarantine_review_queue.jsonl").write_text("", encoding="utf-8")
            result = audit_completion(root, seed)
            self.assertEqual(result["status"], "FAILED_CODE")
            self.assertFalse(result["offline_ready_for_online"])
            self.assertIn("Review all grouped legal-change cases.", result["remaining_actions"])

    def test_technical_failure_is_not_waiting_for_human(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            reports.mkdir()
            (reports / "final_outputs_validation.json").write_text(
                json.dumps({"stages": {"registry": False}, "checks": []}), encoding="utf-8")
            seed = root / "seed.csv"
            seed.write_text("record_id,source_group\nr1,LEGAL_DOCUMENT\n", encoding="utf-8")
            result = audit_completion(root, seed)
            self.assertEqual(result["status"], "FAILED_CODE")
