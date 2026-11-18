"""Runtime layout integration tests: real BM25/FAISS; synthetic legal records."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from vn_labor_offline.artifact_layout import package_outputs, resolve_member, resolve_path, runtime_name, validate_layout
from vn_labor_online.artifact_store import ArtifactStore
from vn_labor_online.config import OnlineConfig
from vn_labor_online.errors import OfflineArtifactMismatch
from vn_labor_online.retrieval import Retriever

spec = importlib.util.spec_from_file_location('layout_fixture', Path(__file__).parents[1] / 'online/test_online_core.py')
fixture_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture_module)


class ArtifactLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = self.root / 'original'
        self.build_id = fixture_module.fixture(self.original)
        self.source = self.original / 'artifacts'
        (self.source / 'reports/extra.log').write_text('diagnostics')
        (self.source / '01_extracted').mkdir()
        (self.source / '01_extracted/documents.jsonl').write_text('{}\n')
        self.cfg = OnlineConfig(artifact_source=str(self.original), expected_build_id=self.build_id,
                               cache_dir=str(self.root / 'cache'))
        self.release = self.root / 'release'

    def export(self):
        return package_outputs(self.original, self.release)

    def test_runtime_roundtrip_loads_real_bm25_and_faiss(self):
        old = ArtifactStore(self.cfg)
        self.export()
        new = ArtifactStore(self.cfg.model_copy(update={'artifact_source':str(self.release / 'vn_labor_online.zip')}))
        self.assertEqual(old.units, new.units)
        self.assertEqual(old.nodes, new.nodes)
        self.assertEqual(old.edges, new.edges)
        self.assertEqual(old.report.build_id, new.report.build_id)
        self.assertEqual(old.report.retrieval_unit_fingerprint, new.report.retrieval_unit_fingerprint)
        self.assertEqual(old.report.provisional_reasons, new.report.provisional_reasons)
        a, b = Retriever(old, self.cfg), Retriever(new, self.cfg)
        self.assertEqual([(e.unit_id,e.score) for e in a.bm25('tiền lương',2)],
                         [(e.unit_id,e.score) for e in b.bm25('tiền lương',2)])
        a._model = fixture_module.FakeModel(); b._model = fixture_module.FakeModel()
        self.assertEqual([(e.unit_id,e.score) for e in a.dense('tiền lương',2)],
                         [(e.unit_id,e.score) for e in b.dense('tiền lương',2)])
        self.assertEqual(new.load_faiss().ntotal, 2)
        self.assertEqual(len(new.load_bm25().corpus), 2)

    def test_flat_runtime_zip_and_kaggle_directory_detection(self):
        self.export()
        flat = self.root / 'flat.zip'
        with zipfile.ZipFile(self.release / 'vn_labor_online.zip') as original, zipfile.ZipFile(flat,'w') as target:
            for n in original.namelist(): target.writestr(n.removeprefix('artifacts/'),original.read(n))
        store = ArtifactStore(self.cfg.model_copy(update={'artifact_source':str(flat)}))
        self.assertEqual(len(store.units),2)
        from kaggle.online_remote import _artifact_directory_roots
        with zipfile.ZipFile(self.release / 'vn_labor_online.zip') as original:
            original.extractall(self.root / 'kaggle_input')
        self.assertEqual(_artifact_directory_roots(self.root / 'kaggle_input'), [self.root / 'kaggle_input'])

    def test_final_kaggle_export_publishes_both_packages(self):
        from kaggle import remote
        report = self.source / 'reports/final_outputs_validation.json'
        data = json.loads(report.read_text()); data['ready_for_offline_v1'] = True
        report.write_text(json.dumps(data))
        (self.source / 'reports/kaggle_run.json').write_text('{"pipeline_exit_code":0}')
        with patch.object(remote,'ROOT',self.original), patch.object(remote,'OUT',self.source):
            remote.export()
        self.assertTrue((self.root / 'vn_labor_results.zip').is_file())
        self.assertTrue((self.root / 'vn_labor_online.zip').is_file())
        self.assertTrue((self.root / 'vn_labor_offline_review.zip').is_file())
        release=json.loads((self.root / 'release.json').read_text())
        self.assertEqual(release['build_id'],self.build_id)
        store=ArtifactStore(self.cfg.model_copy(update={'artifact_source':str(self.root / 'vn_labor_online.zip')}))
        self.assertEqual(store.report.build_id,self.build_id)

    def test_runtime_excludes_logs_and_intermediates(self):
        self.export()
        with zipfile.ZipFile(self.release / 'vn_labor_online.zip') as z:
            names = set(z.namelist())
            self.assertIn('artifacts/graph/nodes.jsonl', names)
            self.assertIn('artifacts/checks/neo4j_validation.json', names)
            self.assertFalse(any('/reports/' in n or '/01_extracted/' in n for n in names))
            for old in ['05_graph/nodes.jsonl','05_graph/edges.jsonl','06_indexes/retrieval_units.jsonl']:
                self.assertEqual(z.read('artifacts/' + runtime_name(old)), (self.source / old).read_bytes())
        with zipfile.ZipFile(self.release / 'vn_labor_offline_review.zip') as z:
            self.assertIn('offline_review/reports/extra.log', z.namelist())
            self.assertIn('offline_review/01_extracted/documents.jsonl', z.namelist())
            self.assertNotIn('offline_review/05_graph/nodes.jsonl', z.namelist())

    def test_corruption_rejected_before_json_parse(self):
        self.export()
        source = self.root / 'extracted'
        with zipfile.ZipFile(self.release / 'vn_labor_online.zip') as z: z.extractall(source)
        (source / 'artifacts/graph/nodes.jsonl').write_text('corrupt')
        with self.assertRaisesRegex(OfflineArtifactMismatch,'SHA256'):
            ArtifactStore(self.cfg.model_copy(update={'artifact_source':str(source)}))

    def test_mixed_and_missing_manifest_rejected(self):
        self.export()
        source = self.root / 'extracted'
        with zipfile.ZipFile(self.release / 'vn_labor_online.zip') as z: z.extractall(source)
        root = source / 'artifacts'
        (root / '05_graph').mkdir()
        with self.assertRaisesRegex(ValueError,'Mixed'): validate_layout(root)
        (root / 'runtime_manifest.json').unlink()
        with self.assertRaisesRegex(ValueError,'manifest missing'): validate_layout(root)

    def test_missing_checks_do_not_generate_fake_pass(self):
        (self.source / 'reports/neo4j_validation.json').unlink()
        with self.assertRaises((FileNotFoundError, OfflineArtifactMismatch)):
            self.export()
        self.assertFalse(self.release.exists())

    def test_refuses_overwrite_and_source_overlap(self):
        self.export()
        with self.assertRaises(FileExistsError): self.export()
        with self.assertRaises(ValueError): package_outputs(self.source, self.source / 'release')

    def test_member_aliases_reject_ambiguous_graph(self):
        self.assertEqual(resolve_member(['artifacts/graph/nodes.jsonl'],'05_graph/nodes.jsonl'), 'artifacts/graph/nodes.jsonl')
        with self.assertRaises(ValueError):
            resolve_member(['artifacts/graph/nodes.jsonl','artifacts/05_graph/nodes.jsonl'],'05_graph/nodes.jsonl')
        for bad in ['../escape','/absolute','C:/drive','a\\b']:
            with self.assertRaises(ValueError): runtime_name(bad)

    def test_manifest_cannot_read_outside_root(self):
        self.export()
        source = self.root / 'extracted'
        with zipfile.ZipFile(self.release / 'vn_labor_online.zip') as z: z.extractall(source)
        root = source / 'artifacts'
        m = json.loads((root / 'runtime_manifest.json').read_text())
        m['files']['../outside'] = 'bad'
        (root / 'runtime_manifest.json').write_text(json.dumps(m))
        with self.assertRaises(ValueError): validate_layout(root)


if __name__ == '__main__': unittest.main()
