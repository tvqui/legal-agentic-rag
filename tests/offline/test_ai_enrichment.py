from pathlib import Path
import tempfile,unittest
from vn_labor_offline.ai_enrichment import cached_structured,report_ai_progress
from vn_labor_offline.checklists import ai_checklist,checklist_identity,finalize_checklists,select_hybrid_ai_ids

class Provider:
    model='fixture-model'
    def __init__(self,payload): self.payload=payload; self.calls=0
    def structured(self,*args): self.calls+=1; return self.payload

class OfflineAIEnrichmentTests(unittest.TestCase):
    def test_cache_is_deterministic_and_resumable(self):
        provider=Provider({'items':[]})
        with tempfile.TemporaryDirectory() as directory:
            cache=Path(directory)
            first=cached_structured(provider,'system',{'source':'law'},{'type':'object'},cache,'p1')
            second=cached_structured(provider,'system',{'source':'law'},{'type':'object'},cache,'p1')
        self.assertEqual(first,second); self.assertEqual(provider.calls,1)

    def test_ai_checklist_requires_a_resolvable_source_quote(self):
        source='Người lao động phải báo trước ít nhất 45 ngày.'
        provision={'provision_id':'p1','document_id':'d1','level':'CLAUSE','text':source,'segment_id':'s1',
          'char_start':0,'char_end':len(source),'document_char_start':0,'document_char_end':len(source),
          'source_unit_type':'TEXT','page_status':'NOT_APPLICABLE'}
        provider=Provider({'items':[{'type':'REQUIRED','question':'Có báo trước đủ 45 ngày không?',
          'source_text':'phải báo trước ít nhất 45 ngày','fact_slots':['notice_days']},
          {'type':'REQUIRED','question':'Bịa đặt?','source_text':'đoạn không tồn tại','fact_slots':[]}]})
        with tempfile.TemporaryDirectory() as directory:
            rows=ai_checklist(provision,provider,Path(directory),source,source,[])
        self.assertEqual(len(rows),1); self.assertEqual(rows[0]['provenance_status'],'VERIFIED')
        self.assertEqual(rows[0]['source_text'],'phải báo trước ít nhất 45 ngày')

    def test_hybrid_selection_is_bounded_and_requires_rule_signals(self):
        prepared=[
          ({'provision_id':'p3','level':'ARTICLE','text':'x'*500},[{'type':'REQUIRED'}],()),
          ({'provision_id':'p1','level':'POINT','text':'x'*100},[{'type':'REQUIRED'},{'type':'DEADLINE'}],()),
          ({'provision_id':'p2','level':'CLAUSE','text':'x'*300},[],()),
        ]
        self.assertEqual(select_hybrid_ai_ids(prepared,1),{'p1'})
        self.assertEqual(select_hybrid_ai_ids(prepared,10),{'p1','p3'})

    def test_semantic_checklist_ids_do_not_collide_between_rule_types(self):
        quote='Nguoi lao dong phai bao truoc it nhat 45 ngay.'
        required=checklist_identity('prov_1','REQUIRED',quote)
        deadline=checklist_identity('prov_1','DEADLINE',quote)
        self.assertNotEqual(required,deadline)
        self.assertEqual(required,checklist_identity('prov_1','REQUIRED','  '+quote+'  '))

    def test_hybrid_rows_are_canonical_and_prefer_structured_ai(self):
        quote='Nguoi lao dong phai bao truoc it nhat 45 ngay.'
        base={'provision_id':'prov_1','source_text':quote,'provenance_status':'VERIFIED'}
        rows=finalize_checklists([
          {**base,'checklist_id':'old-heuristic','type':'REQUIRED','generator':'heuristic','question':'heuristic'},
          {**base,'checklist_id':'old-ai','type':'REQUIRED','generator':'structured-ai:qwen','question':'ai'},
          {**base,'checklist_id':'old-collision','type':'DEADLINE','generator':'structured-ai:qwen','question':'deadline'},
        ])
        self.assertEqual(len(rows),2)
        self.assertEqual(len({row['checklist_id'] for row in rows}),2)
        required=next(row for row in rows if row['type']=='REQUIRED')
        self.assertEqual(required['question'],'ai')
        self.assertEqual(required['checklist_id'],checklist_identity('prov_1','REQUIRED',quote))

    def test_progress_is_atomic_and_machine_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            payload=report_ai_progress(output,'checklists',7,20,ai_attempted=3)
            stored=__import__('json').loads(
                (output/'reports/offline_ai_progress.json').read_text(encoding='utf-8'))
        self.assertEqual(payload,stored)
        self.assertEqual(stored['stage'],'checklists')
        self.assertEqual(stored['completed'],7)

if __name__=='__main__': unittest.main()
