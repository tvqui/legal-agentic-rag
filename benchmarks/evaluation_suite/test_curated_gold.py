"""Corpus-binding and scoring-integrity regressions; no inference/API calls."""
import copy
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace as NS

import gold
import test_gold
from qa_worker import judging_evidence


class CuratedGoldTests(unittest.TestCase):
    def fixture(self,tmp):
        return test_gold.GoldTests().fixture(tmp)

    def rewrite_manifest(self,path,binding):
        with zipfile.ZipFile(path) as archive:
            contents={name:archive.read(name) for name in archive.namelist()}
        manifest=json.loads(contents['manifest.json']);manifest['corpus_binding']=binding
        contents['manifest.json']=json.dumps(manifest).encode()
        with zipfile.ZipFile(path,'w') as archive:
            for name,value in contents.items():archive.writestr(name,value)

    def test_changed_offline_build_cannot_silently_reuse_curated_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,u,c,r,w=self.fixture(tmp)
            self.rewrite_manifest(p,{'build_id':'different'})
            with self.assertRaisesRegex(ValueError,'corpus binding mismatch'):
                gold.import_candidate(p,test_gold.GoldTests().store(u),'fp')

    def test_changed_retrieval_fingerprint_even_with_same_build_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,u,c,r,w=self.fixture(tmp);store=test_gold.GoldTests().store(u)
            store.report.retrieval_unit_fingerprint='units-original'
            self.rewrite_manifest(p,{'build_id':'build','retrieval_unit_fingerprint':'changed'})
            with self.assertRaisesRegex(ValueError,'retrieval_unit_fingerprint'):
                gold.import_candidate(p,store,'fp')

    def test_edited_parent_context_cannot_reverse_evidence_polarity(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,u,c,r,w=self.fixture(tmp)
            c['ancestor_context']='Prohibited acts';u['ancestor_context']='Permitted acts';w()
            with self.assertRaisesRegex(ValueError,'ancestor context'):
                gold.import_candidate(p,test_gold.GoldTests().store(u),'fp')

    def test_text_hash_catches_edit_even_when_other_fields_still_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,u,c,r,w=self.fixture(tmp);c['source_text_sha256']='0'*64;w()
            with self.assertRaisesRegex(ValueError,'source text hash'):
                gold.import_candidate(p,test_gold.GoldTests().store(u),'fp')

    def test_duplicate_wording_with_different_ids_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,u,c,r,w=self.fixture(tmp);r[1]['question']=r[0]['question'];w()
            with self.assertRaisesRegex(ValueError,'Duplicate question text'):
                gold.import_candidate(p,test_gold.GoldTests().store(u),'fp')

    def test_judge_keeps_parent_and_all_alternatives_without_mutating_sources(self):
        units={'a':{'source_text':'Phạt tiền, cắt lương.','ancestor_context':'Các hành vi bị nghiêm cấm.'},
               'b':{'text':'Alternative source'}}
        before=copy.deepcopy(units)
        result=judging_evidence(NS(units_by_id=units),[['a','b'],['a']])
        self.assertEqual([x['id'] for x in result],['a','b'])
        self.assertEqual(result[0]['ancestor_context'],'Các hành vi bị nghiêm cấm.')
        self.assertEqual(result[0]['text'],'Phạt tiền, cắt lương.')
        self.assertEqual(units,before)


if __name__=='__main__':unittest.main()
