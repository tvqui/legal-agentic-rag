import unittest,tempfile
from pathlib import Path
import yaml
from vn_labor_offline.source_links import check_source_links

class SourceLinkConsistencyTests(unittest.TestCase):
    def data(self):
        catalog={'law.pdf':{'source_url':'https://official.example/new','sha256':'sha'}}
        registry=[{'document_id':'d','file_id':'f','relative_path':'law.pdf','sha256':'sha','source_url':'https://official.example/new'}]
        units=[{'unit_id':'u','document_id':'d','source_url':'https://official.example/new'}]
        nodes=[{'id':'d','properties':{'source_url':'https://official.example/new'}}]
        resolved=[{'file_id':'f','source_url':'https://official.example/new'}]
        return catalog,registry,units,nodes,resolved
    def test_fresh_urls_are_checked_through_each_artifact_layer(self):
        report=check_source_links(*self.data())
        self.assertTrue(report['passed']);self.assertEqual(report['matched_configured_documents'],1)
        self.assertEqual(report['records_checked'],{'registry':1,'retrieval_units':1,'graph_documents':1,'source_catalog':1})
    def test_old_checkpoint_urls_are_not_accepted_after_config_update(self):
        catalog,registry,units,nodes,resolved=self.data();registry[0]['source_url']='https://official.example/old'
        report=check_source_links(catalog,registry,units,nodes,resolved)
        self.assertFalse(report['passed']);self.assertEqual(report['issues'][0]['stage'],'registry')
    def test_stale_retrieval_graph_and_resolved_catalog_cannot_hide_behind_fresh_registry(self):
        catalog,registry,units,nodes,resolved=self.data()
        units[0]['source_url']='old';nodes[0]['properties']['source_url']='old';resolved[0]['source_url']='old'
        report=check_source_links(catalog,registry,units,nodes,resolved)
        self.assertFalse(report['passed']);self.assertEqual({i['stage'] for i in report['issues']},{'retrieval_units','graph_documents','source_catalog'})
    def test_missing_source_is_reported_pending_without_inventing_a_url(self):
        catalog,registry,units,nodes,resolved=self.data()
        registry.append({'document_id':'case','relative_path':'case.pdf'})
        report=check_source_links(catalog,registry,units,nodes,resolved)
        self.assertTrue(report['passed']);self.assertFalse(report['all_documents_have_configured_links'])
        self.assertEqual(report['missing_source_count'],1);self.assertEqual(report['human_legal_approvals_created'],0)
    def test_same_url_with_wrong_pdf_sha_is_not_a_valid_match(self):
        catalog,registry,units,nodes,resolved=self.data();registry[0]['sha256']='changed'
        report=check_source_links(catalog,registry,units,nodes,resolved)
        self.assertFalse(report['passed']);self.assertEqual(report['issues'][0]['reason'],'CONFIG_SOURCE_SHA_MISMATCH')
    def test_source_provenance_fields_are_accepted_only_in_source_catalog(self):
        from vn_labor_offline.metadata import checked_metadata
        value={'source_url':'https://official.example/new','source_provider':'provider','official_source':False,
            'reviewer':None,'effective_from':'2026-01-01'}
        self.assertEqual(checked_metadata(value,source_catalog=True),{
            'source_url':'https://official.example/new','effective_from':'2026-01-01'})
        with self.assertRaises(ValueError):checked_metadata(value)
        with self.assertRaises(ValueError):checked_metadata({**value,'hidden_override':True},source_catalog=True)
    def test_excel_style_catalog_builds_registry_without_approving_source(self):
        from vn_labor_offline.metadata import build_registry
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'config').mkdir()
            (root/'config/source_catalog.yaml').write_text(yaml.safe_dump({'sources':{'law.pdf':{
                'sha256':'sha','document_number':'45/2019/QH14','source_url':'https://official.example/new',
                'source_provider':'provider','official_source':False,'effective_from':'2021-01-01'}}}),encoding='utf-8')
            extracted=[{'file_id':'f','relative_path':'law.pdf','filename':'law.pdf','sha256':'sha',
                'source_group':'LEGAL_DOCUMENT','document_type_hint':'LAW','binding_default':True,'text':'Điều 1. Nội dung nguồn.'}]
            registry=build_registry(extracted,{'project_root':root},root/'out')
            self.assertEqual(registry[0]['source_url'],'https://official.example/new')
            self.assertNotIn('official_source',registry[0])
    def test_modern_vbpl_slug_keeps_selected_url_and_extracts_id(self):
        from vn_labor_offline.source_resolver.normalizer import extract_item_id,vbpl_routes
        url='https://vbpl.vn/van-ban/chi-tiet/example-law--123456'
        self.assertEqual(extract_item_id(url),'123456');self.assertEqual(vbpl_routes(url)[0],url)
        self.assertIsNone(extract_item_id('https://other.example/van-ban/chi-tiet/example-law--123456'))
        self.assertIsNone(extract_item_id('https://vbpl.vn/van-ban/chi-tiet/example-law-without-id'))
    def test_modern_vbpl_url_is_allowed_for_identity_without_trusting_other_hosts(self):
        from vn_labor_offline.source_resolver.provider_registry import ProviderRegistry
        from vn_labor_offline.source_resolver.verification.authority import verify_authority
        registry=ProviderRegistry.load(Path(__file__).resolve().parents[2]/'config/source_provider_registry.yaml')
        url='https://vbpl.vn/van-ban/chi-tiet/example-law--123456'
        self.assertTrue(verify_authority(registry,url,url,'IDENTITY','LEGAL_DOCUMENT')[0])
        self.assertFalse(verify_authority(registry,url,'https://other.example/van-ban/chi-tiet/example-law--123456','IDENTITY','LEGAL_DOCUMENT')[0])
