import importlib.util,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import yaml

READY=importlib.util.find_spec('openpyxl') is not None
if READY:
    from openpyxl import load_workbook
source=Path(__file__).with_name('source_links_workbook.py')
if not source.exists():source=Path(__file__).resolve().parents[2]/'scripts/source_links_workbook.py'
spec=importlib.util.spec_from_file_location('link_book',source)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

@unittest.skipUnless(READY,'Install optional review dependencies to test Excel import/export')
class SourceLinkWorkbookTests(unittest.TestCase):
    def fixture(self,root):
        (root/'data').mkdir();(root/'config').mkdir();(root/'review/attachments').mkdir(parents=True)
        (root/'data/law.pdf').write_bytes(b'%PDF-law-fixture')
        (root/'review/attachments/bound.pdf').write_bytes(b'%PDF-attachment-fixture')
        sha=module.sha(root/'data/law.pdf')
        catalog={'sources':{'law.pdf':{'sha256':sha,'source_url':'https://vbpl.vn/old','title':'LAW TITLE',
            'document_number':'DEMO/2026','metadata_verified':True,'temporal_verified':True,
            'official_source':True,'reviewer':'previous-reviewer','reviewed_at':'2026-01-02','collected_at':'2026-01-01','review_evidence':'old URL'}}}
        attachment={'attachments':{'law.pdf':{'path':'review/attachments/bound.pdf',
            'sha256':module.sha(root/'review/attachments/bound.pdf'),'source_url':'https://vbpl.vn/old',
            'download_urls':['https://vbpl.vn/part1.pdf','https://vbpl.vn/part2.pdf']}}}
        for name,value in [('source_catalog.yaml',catalog),('source_attachments.yaml',attachment),
                           ('metadata_overrides.yaml',{'overrides':{}}),('source_provider_registry.yaml',{'providers':[{'id':'congbao','allowed_domains':['congbao.chinhphu.vn']}]})]:
            (root/'config'/name).write_text(yaml.safe_dump(value,allow_unicode=True),encoding='utf-8')
        artifact=root/'artifact.zip'
        with zipfile.ZipFile(artifact,'w') as z:
            z.writestr('artifacts/00_manifest/files.jsonl',json.dumps({'file_id':'f','relative_path':'law.pdf','sha256':sha,'source_group':'LEGAL_DOCUMENT'}))
            z.writestr('artifacts/02_registry/documents.jsonl',json.dumps({'file_id':'f','document_id':'d','title':'LAW TITLE','document_number':'DEMO/2026','source_url':'https://vbpl.vn/artifact-old'}))
            z.writestr('artifacts/03_structure/provisions.jsonl','')
        workbook=root/'links.xlsx';module.export_book(root,artifact,workbook)
        return artifact,workbook
    def edit(self,workbook,source_url='https://congbao.chinhphu.vn/new',confirmed=True,download=False):
        wb=load_workbook(workbook)
        if source_url is not None:
            ws=wb['DIEN_LINK_MOI'];ws['F5']=source_url;ws['G5']='DA_DOI_CHIEU' if confirmed else 'CHUA_DOI_CHIEU'
        if download:
            ws=wb['LINK_TAI_FILE'];ws['E5']='https://congbao.chinhphu.vn/one.pdf\nhttps://congbao.chinhphu.vn/two.pdf';ws['F5']='DA_DOI_CHIEU'
        wb.save(workbook);wb.close()

    def test_blank_roundtrip_and_existing_artifact_link_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);artifact,book=self.fixture(root);before=(root/'config/source_catalog.yaml').read_bytes()
            report=module.import_book(root,artifact,book,root/'out',apply=True)
            self.assertFalse(report['changes']);self.assertEqual((root/'config/source_catalog.yaml').read_bytes(),before)
            wb=load_workbook(book);self.assertEqual(wb['THONG_TIN_DATA']['M5'].value,'https://vbpl.vn/artifact-old');wb.close()
    def test_preview_is_read_only_and_apply_updates_both_source_configs_without_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);artifact,book=self.fixture(root);self.edit(book)
            original=(root/'config/source_catalog.yaml').read_bytes();binary=(root/'review/attachments/bound.pdf').read_bytes();artifact_bytes=artifact.read_bytes()
            report=module.import_book(root,artifact,book,root/'preview')
            self.assertFalse(report['applied']);self.assertEqual((root/'config/source_catalog.yaml').read_bytes(),original)
            report=module.import_book(root,artifact,book,root/'apply',apply=True)
            c=module.config(root,'source_catalog.yaml')['sources']['law.pdf'];a=module.config(root,'source_attachments.yaml')['attachments']['law.pdf']
            self.assertEqual(c['source_url'],'https://congbao.chinhphu.vn/new');self.assertEqual(a['source_url'],c['source_url'])
            self.assertEqual(c['source_provider'],'congbao');self.assertFalse(c['official_source']);self.assertNotIn('reviewer',c)
            self.assertTrue(c['temporal_verified']);self.assertEqual(artifact.read_bytes(),artifact_bytes)
            self.assertEqual((root/'review/attachments/bound.pdf').read_bytes(),binary)
            self.assertEqual(report['human_legal_approvals_created'],0)
    def test_unconfirmed_link_is_reported_but_not_applied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);artifact,book=self.fixture(root);self.edit(book,confirmed=False)
            report=module.import_book(root,artifact,book,root/'out')
            self.assertFalse(report['changes']);self.assertTrue(report['warnings'])
    def test_download_multiline_updates_urls_without_replacing_pdf_or_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);artifact,book=self.fixture(root);self.edit(book,source_url=None,download=True)
            old=module.config(root,'source_attachments.yaml')['attachments']['law.pdf']
            module.import_book(root,artifact,book,root/'out',apply=True)
            new=module.config(root,'source_attachments.yaml')['attachments']['law.pdf']
            self.assertEqual(new['sha256'],old['sha256']);self.assertEqual(new['path'],old['path'])
            self.assertNotEqual(new['download_urls'],old['download_urls'])
    def test_wrong_artifact_or_changed_source_cannot_be_applied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);artifact,book=self.fixture(root);self.edit(book)
            (root/'data/law.pdf').write_bytes(b'changed')
            with self.assertRaises(ValueError):module.import_book(root,artifact,book,root/'out',apply=True)
            self.assertFalse((root/'out').exists())
            artifact.write_bytes(b'not the original artifact')
            with self.assertRaises(ValueError):module.import_book(root,artifact,book,root/'other',apply=True)
    def test_readonly_id_fields_changed_or_formula_in_new_url_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);artifact,book=self.fixture(root)
            wb=load_workbook(book);wb['DIEN_LINK_MOI']['B5']='OTHER';wb.save(book);wb.close()
            with self.assertRaises(ValueError):module.import_book(root,artifact,book,root/'out')
            wb=load_workbook(book);wb['DIEN_LINK_MOI']['B5']='DEMO/2026';wb['DIEN_LINK_MOI']['F5']='=HYPERLINK("x")';wb.save(book);wb.close()
            with self.assertRaises(ValueError):module.import_book(root,artifact,book,root/'other')
    def test_concurrent_config_edit_is_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);artifact,book=self.fixture(root);self.edit(book)
            current=module.config(root,'source_catalog.yaml');current['sources']['law.pdf']['source_url']='https://vbpl.vn/changed-elsewhere'
            (root/'config/source_catalog.yaml').write_text(yaml.safe_dump(current),encoding='utf-8')
            with self.assertRaises(ValueError):module.import_book(root,artifact,book,root/'out',apply=True)
    def test_failed_multi_file_apply_restores_original_configs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);artifact,book=self.fixture(root);self.edit(book)
            originals={p:p.read_bytes() for p in (root/'config').glob('*.yaml')}
            replace=module.os.replace;calls=0
            def fail_second(*args):
                nonlocal calls
                calls+=1
                if calls==2:raise OSError('fixture failure')
                return replace(*args)
            with patch.object(module.os,'replace',side_effect=fail_second):
                with self.assertRaises(OSError):module.import_book(root,artifact,book,root/'out',apply=True)
            for path,data in originals.items():self.assertEqual(path.read_bytes(),data)
    def test_unsafe_urls_are_not_valid_citations(self):
        for value in ['file:///C:/secret','javascript:alert(1)','https://token@vbpl.vn/x','http://localhost/x','http://127.0.0.1/x','https://vbpl.vn/space here']:
            with self.assertRaises(ValueError):module.url(value)

if __name__=='__main__':unittest.main()
