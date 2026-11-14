import importlib.util
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

_spec = importlib.util.spec_from_file_location("graph_qa_dataset", Path(__file__).with_name("dataset.py"))
dataset = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(dataset)

class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.loc = dict(instrument_number="test", version_role="ORIGINAL", article_number="1", clause_number="", point_number="")
        self.unit = dict(self.loc, kind="PROVISION", unit_id="u", source_text="Rule", source_url="https://example.gov/rule", valid_from="2021-01-01", valid_to=None, provenance_status="RESOLVED")
    def test_strict_resolution(self):
        self.assertEqual(dataset.resolve([self.unit], self.loc, "2026-09-15")["unit_id"], "u")
        for units in ([], [self.unit, self.unit]):
            with self.assertRaises(ValueError): dataset.resolve(units, self.loc, "2026-09-15")
    def test_wrong_date_and_missing_metadata(self):
        with self.assertRaises(ValueError): dataset.resolve([self.unit], self.loc, "2020-12-31")
        with self.assertRaises(ValueError): dataset.resolve([dict(self.unit, valid_to="2026-09-15")], self.loc, "2026-09-15")
        for update in ({"source_url":""}, {"source_text":""}, {"provenance_status":"QUARANTINED"}):
            with self.assertRaises(ValueError): dataset.resolve([dict(self.unit, **update)], self.loc, "2026-09-15")
    def test_original_not_merged_into_consolidated(self):
        different = dict(self.unit, version_role="CONSOLIDATED", unit_id="v", source_text="Different rule")
        self.assertEqual(dataset.resolve([self.unit, different], self.loc, "2026-09-15")["unit_id"], "u")
    def test_graph_missing_does_not_reject(self):
        spec = dict(id="q", query_date="2026-09-15", group="cross_document", locators=[self.loc])
        bound = dataset.bind(spec, [self.unit], [])
        self.assertEqual(bound["required_groups"], [["u"]])
        self.assertFalse(bound["graph_support"]["graph_required"])
        self.assertEqual(bound["review_status"], "DRAFT")
        self.assertIsNone(bound["reviewer"])
    def test_context_only_requires_verbatim_child_context(self):
        child_loc = dict(self.loc, clause_number="1")
        child = dict(self.unit, **child_loc, unit_id="child", source_text="Detail", ancestor_context="Rule")
        spec = dict(id="q", query_date="2026-09-15", group="independent_controls", locators=[child_loc], context_locators=[self.loc])
        bound = dataset.bind(spec,[self.unit,child],[])
        self.assertEqual(bound["required_groups"],[["child"]])
        self.assertEqual(bound["context_support"][0]["unit_id"],"u")
        with self.assertRaises(ValueError):
            dataset.bind(spec,[self.unit,dict(child,ancestor_context="Wrong context")],[])
    def test_archive_ambiguity(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory)/"a.zip"
            with zipfile.ZipFile(archive,"w") as z:
                z.writestr("a/06_indexes/retrieval_units.jsonl", "{}")
                z.writestr("b/06_indexes/retrieval_units.jsonl", "{}")
            with self.assertRaises(ValueError): dataset.read_artifact(archive)
    def test_question_design(self):
        rows = [json.loads(x) for x in Path(__file__).with_name("questions.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 24)
        self.assertEqual(len({r["question"] for r in rows}),24)
        for row in rows:
            self.assertTrue(row["reference_answer"])
            self.assertEqual(len(row["expected_tasks"]),len(row["task_requirements"]))
            for task in row["task_requirements"]:
                self.assertTrue(task["required_group_indices"])
                self.assertTrue(all(0 <= i < len(row["locators"]) for i in task["required_group_indices"]))
    @unittest.skipUnless(os.getenv("GRAPH_QA_TEST_ARTIFACT"), "Set GRAPH_QA_TEST_ARTIFACT for real read-only coverage check")
    def test_real_artifact_coverage_and_freeze(self):
        with tempfile.TemporaryDirectory() as d:
            first = dataset.build(os.environ["GRAPH_QA_TEST_ARTIFACT"],d)
            self.assertEqual(first,dataset.build(os.environ["GRAPH_QA_TEST_ARTIFACT"],d))
            gold=[json.loads(x) for x in (Path(d)/"gold.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(gold),24)
            self.assertTrue(all(r["support"] for r in gold))
            inference=[json.loads(x) for x in (Path(d)/"inference.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(all(set(r)=={"id","question","query_date"} for r in inference))
            p=Path(d)/"gold.jsonl";p.write_text("tampered",encoding="utf-8")
            with self.assertRaises(ValueError):dataset.build(os.environ["GRAPH_QA_TEST_ARTIFACT"],d)

if __name__ == "__main__": unittest.main()
