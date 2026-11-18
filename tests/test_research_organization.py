from pathlib import Path
import importlib.util
import json
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'organize_research_data.py'
spec = importlib.util.spec_from_file_location('research_organization', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ResearchOrganizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.artifact = self.root / 'artifact'
        self.artifact.mkdir()
        self.nodes = [{'id': 'p', 'label': 'Article', 'properties': {'text': 'source'}},
                      {'id': 'i', 'label': 'LegalIssue'}, {'id': 'c', 'label': 'Case'},
                      {'id': 'd', 'label': 'DiagnosticItem'}, {'id': 'x', 'label': 'FutureType'}]
        self.edges = [{'id': 'e', 'source': 'p', 'target': 'i', 'type': 'HAS_ISSUE'},
                      {'id': 'f', 'source': 'c', 'target': 'c', 'type': 'SAME_RECORD'}]
        module.write_rows(self.artifact / '05_graph/nodes.jsonl', self.nodes)
        module.write_rows(self.artifact / '05_graph/edges.jsonl', self.edges)
        module.write_rows(self.artifact / '06_indexes/retrieval_units.jsonl', [{'unit_id': 'p', 'source_text': 'source'}])

    def peer(self):
        peer = self.root / 'peer'
        base = peer / 'Hierargraph'
        module.write_rows(base / 'rule_graph/nodes.jsonl', [
            {'id': 'peer:p', 'type': 'Provision', 'properties': {
                'source_record_id': 'p', 'source_properties': {'text': 'source'}}}])
        module.write_rows(base / 'ontology_graph/nodes.jsonl', [
            {'id': 'concept', 'type': 'LegalConcept', 'properties': {
                'label_vi': 'Synthetic concept', 'definition_vi': 'source',
                'verification': {'semantic': 'VERIFIED'}, 'independent_approval': {'reviewer': 'AI'}}}])
        module.write_rows(base / 'ontology_graph/edges.jsonl', [
            {'source_id': 'concept', 'target_id': 'peer:p', 'type': 'REGULATED_BY'}])
        module.write_rows(base / 'ontology_graph/evidence.jsonl', [
            {'graph_record_id': 'concept', 'provenance': [{'provision_node_id': 'peer:p',
             'provision_char_start': 0, 'provision_char_end': 6, 'quote': 'source',
             'quote_sha256': module.sha(b'source')}]}])
        return peer

    def test_partition_is_lossless_and_unknown_types_retained(self):
        groups, cross = module.partition(self.nodes, self.edges)
        self.assertEqual(sorted(self.nodes, key=lambda n: n['id']),
                         sorted([n for g in groups.values() for n in g['nodes']], key=lambda n: n['id']))
        self.assertEqual(len(cross) + sum(len(g['edges']) for g in groups.values()), len(self.edges))
        self.assertEqual({n['id'] for n in groups['derived']['nodes']}, {'d', 'x'})

    def test_invalid_graph_rejected(self):
        with self.assertRaises(ValueError):
            module.partition(self.nodes + [self.nodes[0]], self.edges)
        with self.assertRaises(ValueError):
            module.partition(self.nodes, self.edges + [dict(self.edges[0])])
        with self.assertRaises(ValueError):
            module.partition(self.nodes, [{'source': 'p', 'target': 'missing'}])

    def test_matching_definition_does_not_gain_legal_approval(self):
        report = module.build(self.artifact, self.root / 'out', self.peer())
        self.assertEqual(report['peer']['accepted'], 1)
        hint = module.rows((self.root / 'out/04_peer_ontology/definition_hints.jsonl').read_bytes())[0]
        self.assertFalse(hint['enabled_online'])
        self.assertFalse(hint['temporal_verified'])
        self.assertFalse(hint['applicability_verified'])
        self.assertFalse(report['peer']['legal_approval'])
        self.assertEqual(hint['source_claims']['verification']['semantic'], 'VERIFIED')

    def test_mismatch_rejects_peer_concept(self):
        peer = self.peer()
        for quote, hash_value, start in [('changed', module.sha(b'changed'), 0),
                                          ('source', 'bad', 0), ('source', module.sha(b'source'), -1)]:
            with self.subTest(quote=quote, hash_value=hash_value, start=start):
                module.write_rows(peer / 'Hierargraph/ontology_graph/evidence.jsonl', [
                    {'graph_record_id': 'concept', 'provenance': [{'provision_node_id': 'peer:p',
                     'provision_char_start': start, 'provision_char_end': 6, 'quote': quote,
                     'quote_sha256': hash_value}]}])
                result = module.stage_peer(peer, [{'unit_id': 'p', 'source_text': 'source'}], self.root / 'stage')
                self.assertEqual(result['accepted'], 0)
        self.peer()
        result = module.stage_peer(peer, [{'unit_id': 'p', 'source_text': 'different'}], self.root / 'stage')
        self.assertEqual(result['accepted'], 0)

    def test_output_refuses_existing_and_input_overlap(self):
        with self.assertRaises(FileExistsError):
            module.build(self.artifact, self.artifact)
        with self.assertRaises(ValueError):
            module.build(self.artifact, self.artifact / 'nested')

    def test_failure_leaves_no_partial_export(self):
        module.write_rows(self.artifact / '05_graph/edges.jsonl', [{'source': 'p', 'target': 'missing'}])
        with self.assertRaises(ValueError):
            module.build(self.artifact, self.root / 'out')
        self.assertFalse((self.root / 'out').exists())
        self.assertFalse(list(self.root.glob('.research-*')))

    def test_zip_and_directory_equivalent(self):
        archive = self.root / 'artifact.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            for p in self.artifact.rglob('*'):
                if p.is_file():
                    z.write(p, 'artifacts/' + p.relative_to(self.artifact).as_posix())
        before = module.file_hash(archive)
        a = module.build(archive, self.root / 'zip_out')
        b = module.build(self.artifact, self.root / 'dir_out')
        self.assertEqual(a['input_sha256'], b['input_sha256'])
        self.assertEqual(a['groups'], b['groups'])
        self.assertEqual(module.file_hash(archive), before)
        entries = module.rows((self.root / 'zip_out/00_catalog/output_hashes.jsonl').read_bytes())
        for item in entries:
            self.assertEqual(module.file_hash(self.root / 'zip_out' / item['path']), item['sha256'])

    def test_unsafe_zip_names_rejected_without_extraction(self):
        for i, bad in enumerate(['../escape', '/absolute', 'C:/drive', 'a\\b']):
            archive = self.root / f'bad{i}.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('06_indexes/retrieval_units.jsonl', '')
                info = zipfile.ZipInfo('safe')
                info.filename = bad
                z.writestr(info, 'bad')
            with self.assertRaises(ValueError):
                module.build(archive, self.root / f'out{i}')


if __name__ == '__main__':
    unittest.main()
