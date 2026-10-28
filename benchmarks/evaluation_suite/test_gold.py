import copy,hashlib,json,tempfile,unittest,zipfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import gold,common

class GoldTests(unittest.TestCase):
    def fixture(self,root):
        text='2. Hai bên có thể giao kết bằng lời nói.'
        unit={'unit_id':'p','document_id':'doc','instrument_number':'45/2019/QH14',
            'source_url':'https://official.example/law','article_number':'14','clause_number':'2',
            'point_number':'','level':'CLAUSE','source_text':text.replace(' có','\n có'),
            'text':'context\n'+text,'kind':'PROVISION','valid_from':'2021-01-01','temporal_verified':True}
        cat={'evidence_id':'p','source_document_id':'doc','source_url':unit['source_url'],
            'locator':'Điều 14 khoản 2','evidence_text':text}
        rows=[{'question_id':'q'+str(i),'category':'cat','question':'Question '+str(i),
            'gold_answer':'Draft reference','applicable_date':'2026-10-23',
            'expected_status':s,'missing_facts':['Contract type'] if s=='NEED_MORE_FACTS' else [],
            'gold_evidence_ids':['p'],'gold_evidence_locators':[cat['locator']],
            'source_document_id':'doc','source_url':unit['source_url']}
            for i,s in enumerate(['ANSWERABLE','NEED_MORE_FACTS','INSUFFICIENT_EVIDENCE'])]
        manifest={'size':3,'distinct_evidence_ids':1,'counts_by_expected_status':{r['expected_status']:1 for r in rows},'data_cutoff':'2026-10-23'}
        path=Path(root)/'gold.zip'
        def write():
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('labor_gold_100.jsonl','\n'.join(json.dumps(r,ensure_ascii=False) for r in rows))
                z.writestr('evidence_catalog.jsonl',json.dumps(cat,ensure_ascii=False))
                z.writestr('manifest.json',json.dumps(manifest))
        write()
        return path,unit,cat,rows,write

    def store(self,unit):
        return NS(units=[unit],units_by_id={unit['unit_id']:unit},report=NS(corpus_snapshot_as_of='2026-09-15',build_id='build'))

    def test_zip_import_preserves_all_statuses_and_quotations_without_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,u,c,r,w=self.fixture(tmp)
            rows,report=gold.import_candidate(p,self.store(u),'fp')
            self.assertEqual(len(rows),3);self.assertEqual(report['retrieval_questions'],1)
            self.assertEqual(report['legal_approval'],'NOT_APPROVED')
            self.assertTrue(all(x['review_status']=='DRAFT' and x['query_after_corpus_snapshot'] for x in rows))
            self.assertEqual(rows[0]['reference_answer'],'Draft reference')
            self.assertEqual(len(list(Path(tmp).iterdir())),1)  # no ZIP extraction

    def test_changed_digit_in_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,u,c,r,w=self.fixture(tmp);u['source_text']='1. Different legal text'
            with self.assertRaisesRegex(ValueError,'quotation'):gold.import_candidate(p,self.store(u),'fp')

    def test_wrong_document_or_locator_is_rejected(self):
        for key,value in [('document_id','other'),('clause_number','9')]:
            with tempfile.TemporaryDirectory() as tmp:
                p,u,c,r,w=self.fixture(tmp);u[key]=value
                with self.assertRaises(ValueError):gold.import_candidate(p,self.store(u),'fp')

    def test_missing_old_id_rebinds_only_exact_text_and_law(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,u,c,r,w=self.fixture(tmp);u['unit_id']='new'
            rows,report=gold.import_candidate(p,self.store(u),'fp')
            self.assertEqual(rows[0]['required_groups'],[['new']]);self.assertEqual(report['migrated_evidence_ids'],['p'])
            u['source_text']='Changed provision';u['text']='Changed provision'
            with self.assertRaisesRegex(ValueError,'Unresolved'):gold.import_candidate(p,self.store(u),'fp')

    def test_duplicate_question_id_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,u,c,r,w=self.fixture(tmp);r[1]['question_id']=r[0]['question_id'];w()
            with self.assertRaisesRegex(ValueError,'Duplicate question'):gold.import_candidate(p,self.store(u),'fp')

    def test_annotation_notes_require_matching_source_hash_and_keep_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,u,c,r,w=self.fixture(tmp)
            note={'source_zip_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                'question_notes':{'q1':{'status_score_eligible':False,'qa_judge_eligible':False,'note':'Needs reference review'}}}
            file=Path(tmp)/'gold100_annotation_notes.json'
            file.write_text(json.dumps(note))
            with patch.object(gold,'__file__',str(Path(tmp)/'gold.py')):
                rows,report=gold.import_candidate(p,self.store(u),'fp')
                self.assertEqual(len(rows),3);self.assertFalse(rows[1]['status_score_eligible'])
                self.assertEqual(rows[1]['expected_status'],'NEED_MORE_FACTS')
                self.assertEqual(report['status_scoring_excluded_review_ids'],['q1'])
                note['source_zip_sha256']='different';file.write_text(json.dumps(note))
                rows,_=gold.import_candidate(p,self.store(u),'fp')
                self.assertTrue(all(r['status_score_eligible'] for r in rows))

    def test_wrong_manifest_count_refused_before_measurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,u,c,r,w=self.fixture(tmp);r.pop();w()
            with self.assertRaisesRegex(ValueError,'Manifest count'):gold.import_candidate(p,self.store(u),'fp')

    def test_smoke_is_deterministic_and_contains_all_statuses(self):
        rows=[{'id':str(i),'category':str(i%4),'expected_status':s} for i,s in enumerate(['ANSWERABLE']*4+['NEED_MORE_FACTS','INSUFFICIENT_EVIDENCE'])]
        chosen=gold.select_rows(rows,6)
        self.assertEqual(chosen,gold.select_rows(rows,6))
        self.assertEqual({r['expected_status'] for r in chosen},gold.STATUSES)
        self.assertEqual(gold.select_rows(rows,None),rows)
        with self.assertRaises(ValueError):gold.select_rows(rows,0)

    def test_disposition_is_not_completion_and_errors_stay_in_denominator(self):
        self.assertFalse(gold.status_comparison('ANSWERABLE','PARTIAL_ALLOWED'))
        self.assertTrue(gold.status_comparison('NEED_MORE_FACTS','NEED_MORE_FACTS'))
        records=[{'status':'OK','elapsed_ms':1,'expected_status':'ANSWERABLE','answer_status':'SUFFICIENT','draft_disposition_match':True},
            {'status':'ERROR','elapsed_ms':5,'expected_status':'ANSWERABLE'}]
        report=common.answer_summary(records)
        self.assertEqual(report['draft_disposition_match_rate'],.5)
        self.assertEqual(report['status_confusion']['ANSWERABLE']['TECHNICAL_ERROR'],1)
        self.assertIsNone(report['ai_correctness'])

    def test_gold_labels_are_only_judge_data_never_user_facts(self):
        # Production gets only question/date and genuine facts. Answers/missing
        # fact labels must never leak into QueryRequest as hints or overrides.
        import qa_worker
        source=Path(qa_worker.__file__).read_text(encoding='utf-8')
        query=source[source.index('response=pipe.ask('):source.index('record.update(answer=')]
        self.assertNotIn('reference_answer',query);self.assertNotIn('expected_status',query)
        self.assertNotIn('missing_facts',query)

if __name__=='__main__':unittest.main()
