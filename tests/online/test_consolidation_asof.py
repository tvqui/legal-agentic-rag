import unittest
from types import SimpleNamespace as NS
from vn_labor_online.models import Evidence
from vn_labor_online.temporal import source_available_from
from vn_labor_online.retrieval import temporal_filter,as_evidence
from vn_labor_online.audit import deterministic_audit

class ConsolidationAsOfTests(unittest.TestCase):
    def item(self,**updates):
        return Evidence(unit_id='e',document_id='doc',document_number='TEST',kind='PROVISION',
            article_number='6',text='Người lao động được trả đủ tiền lương.',source_text='Người lao động được trả đủ tiền lương.',
            retrieval_method='policy',valid_from='2021-01-01',temporal_verified=True,
            version_role='CONSOLIDATED',promulgated_date='2026-02-12',consolidation_as_of='2026-02-12',
            source_url='https://example.test/law',provenance={'file_id':'f'},provenance_span={'char_start':0,'char_end':40}).model_copy(update=updates)
    def store(self,e):
        return NS(units_by_id={'e':e.model_dump()},nodes_by_id={'doc':{},'e':{'properties':{'article_number':'6'}}},
            catalog_by_file_id={'f':{'catalog_status':'VERIFIED','source_url':e.source_url}})
    def test_inherited_effective_date_does_not_backdate_a_consolidation(self):
        e=self.item()
        kept,removed=temporal_filter([e],'2021-04-05',strict=False)
        self.assertFalse(kept);self.assertEqual(removed,['e'])
    def test_current_consolidation_is_not_globally_disabled(self):
        kept,_=temporal_filter([self.item()],'2026-03-01',strict=False)
        self.assertEqual(len(kept),1)
    def test_exact_audit_and_graph_candidates_enforce_the_same_date_constraint(self):
        e=self.item()
        audited=deterministic_audit(self.store(e),[e],'2021-04-05',True)[0]
        self.assertFalse(audited.verified)
        self.assertIn('SOURCE_NOT_AVAILABLE_AT_QUERY_DATE',audited.audit_issues)
    def test_period_overlapping_publication_is_not_silently_treated_as_uniform(self):
        e=self.item();kept,_=temporal_filter([e],'2026-02-01',strict=False,query_date_end='2026-02-28')
        self.assertIn('IMPRECISE_QUERY_DATE_OVERLAPS_VERSION_BOUNDARY',kept[0].audit_warnings)
    def test_invalid_publication_date_fails_closed(self):
        kept,removed=temporal_filter([self.item(consolidation_as_of='2026-19-01')],'2026-09-15',False)
        self.assertFalse(kept);self.assertEqual(removed,['e'])
    def test_source_dates_survive_conversion(self):
        e=self.item();converted=as_evidence(e.model_dump(),1,'bm25',1)
        self.assertEqual(converted.promulgated_date,e.promulgated_date)
        self.assertEqual(converted.consolidation_as_of,e.consolidation_as_of)
    def test_candidate_cannot_backdate_an_immutable_source(self):
        e=self.item();tampered=e.model_copy(update={'consolidation_as_of':'2020-01-01','promulgated_date':'2020-01-01'})
        audited=deterministic_audit(self.store(e),[tampered],'2021-04-05',True)[0]
        self.assertFalse(audited.verified)
        self.assertIn('SOURCE_NOT_AVAILABLE_AT_QUERY_DATE',audited.audit_issues)
    def test_missing_publication_date_is_never_invented_from_a_number(self):
        self.assertIsNone(source_available_from(self.item(promulgated_date=None,consolidation_as_of=None)))

if __name__=='__main__':unittest.main()
