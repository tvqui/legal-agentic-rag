import tempfile
import unittest
from pathlib import Path

from vn_labor_offline.neo4j_loader import validate_export
from vn_labor_offline.indexes import build_retrieval_units
from vn_labor_offline.provenance import enrich_provenance
from vn_labor_offline.provision_versions import materialize_provision_versions
from vn_labor_offline.util import read_jsonl, write_jsonl


class ProvenanceMappingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.out = Path(self.temp.name)
        (self.out / "03_structure").mkdir()
        self.registry = [{"document_id": "doc", "file_id": "file"}]

    def tearDown(self):
        self.temp.cleanup()

    def map_one(self, document_text, segment_text, pages=None, start=0, end=None):
        write_jsonl(self.out / "03_structure" / "segments.jsonl", [
            {"segment_id": "seg", "text": segment_text}
        ])
        provision = {"provision_id": "p", "document_id": "doc", "segment_id": "seg",
                     "char_start": start, "char_end": len(segment_text) if end is None else end}
        extracted = [{"document_id": "doc", "text": document_text,
                      "page_provenance": pages or []}]
        return enrich_provenance([provision], extracted, self.registry, self.out)[0]

    def test_preamble_shifts_document_span(self):
        segment = "Điều 1. Phạm vi áp dụng"
        text = "Lời mở đầu\n" + segment
        result = self.map_one(text, segment)
        self.assertEqual(result["document_char_start"], len("Lời mở đầu\n"))
        self.assertEqual(text[result["document_char_start"]:result["document_char_end"]], segment)
        self.assertEqual(result["provenance_status"], "RESOLVED")

    def test_repeated_segment_is_unresolved(self):
        segment = "Điều 1. Phạm vi áp dụng"
        result = self.map_one(segment + "\n" + segment, segment)
        self.assertIsNone(result["document_char_start"])
        self.assertEqual(result["provenance_status"], "UNRESOLVED")

    def test_page_span_uses_resolved_document_coordinates(self):
        segment = "Điều 1. Phạm vi áp dụng"
        prefix = "Lời mở đầu\n"
        text = prefix + segment
        result = self.map_one(text, segment, [{"page": 1, "text_start": 0,
                                               "text_end": len(text)}])
        self.assertEqual(result["page_start"], 1)
        self.assertEqual(result["page_status"], "RESOLVED")

    def test_collapsed_blank_line_keeps_later_span_exact(self):
        prefix = "Điều 1. " + "Nội dung căn cứ pháp lý. " * 8
        clause = "Khoản 1. Quy định áp dụng"
        segment = prefix + "\n" + clause
        document = "Lời mở đầu\n" + prefix + "\n\n" + clause
        result = self.map_one(document, segment, start=segment.index(clause))
        self.assertEqual(document[result["document_char_start"]:result["document_char_end"]], clause)
        self.assertEqual(result["provenance_status"], "RESOLVED")

    def test_changed_legal_text_remains_unresolved(self):
        prefix = "Điều 1. " + "Nội dung căn cứ pháp lý. " * 8
        segment = prefix + "\nKhoản 1. Phải thực hiện"
        document = prefix + "\nKhoản 1. Không phải thực hiện"
        result = self.map_one(document, segment, start=segment.index("Khoản 1"))
        self.assertIsNone(result["document_char_start"])
        self.assertEqual(result["provenance_status"], "UNRESOLVED")

    def test_new_graph_identity_label_can_be_loaded(self):
        nodes = [{"id": "identity", "label": "ProvisionIdentity"},
                 {"id": "version", "label": "Article"}]
        edges = [{"id": "edge", "source": "identity", "target": "version",
                  "type": "HAS_PROVISION_VERSION"}]
        validate_export(nodes, edges)

    def test_final_provision_rows_survive_audit_reload(self):
        segment = "Điều 1. Phạm vi áp dụng"
        provision = self.map_one("Lời mở đầu\n" + segment, segment)
        materialize_provision_versions(self.registry, [provision], self.out)
        saved = list(read_jsonl(self.out / "03_structure" / "provisions.jsonl"))[0]
        self.assertEqual(saved["document_char_start"], len("Lời mở đầu\n"))
        self.assertTrue(saved["provision_identity_id"])
        self.assertEqual(saved["page_status"], "NOT_APPLICABLE")

    def test_retrieval_unit_keeps_document_and_page_coordinates(self):
        provision = {"provision_id": "p", "document_id": "doc", "parent_id": "doc",
                     "level": "ARTICLE", "number": "1", "segment_type": "MAIN_BODY",
                     "text": "Điều 1. Phạm vi áp dụng", "chapter": "II", "section": "1",
                     "segment_id": "seg", "char_start": 0, "char_end": 23,
                     "document_char_start": 100, "document_char_end": 123,
                     "page_start": 3, "page_end": 3, "page_status": "RESOLVED",
                     "provenance_status": "RESOLVED"}
        registry = [{"document_id": "doc", "title": "Luật mẫu", "instrument_number": "01/2026",
                     "provenance": {"file_id": "file"}}]
        unit = build_retrieval_units([provision], [], registry)[0]
        self.assertIn("Mục 1", unit["breadcrumb"])
        self.assertEqual(unit["provenance_span"]["document_char_start"], 100)
        self.assertEqual(unit["provenance_span"]["page_start"], 3)


if __name__ == "__main__":
    unittest.main()
