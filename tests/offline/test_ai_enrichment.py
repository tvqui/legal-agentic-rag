from pathlib import Path
import tempfile,unittest
from vn_labor_offline.ai_enrichment import cached_structured
from vn_labor_offline.checklists import ai_checklist

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

if __name__=='__main__': unittest.main()
