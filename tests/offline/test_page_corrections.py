import hashlib,tempfile,unittest
from pathlib import Path
import pymupdf,yaml
from vn_labor_offline.page_reviews import correction_text,reviewed_pages
from vn_labor_offline.extract import extract_pdf_pages
from vn_labor_offline.page_quality import finalize_page_quality


class PageCorrectionTests(unittest.TestCase):
    def fixture(self,root):
        target=root/'review/corrections/page.txt';target.parent.mkdir(parents=True)
        target.write_text('Điều 87. Nội dung đầy đủ, 01 bộ hồ sơ.',encoding='utf-8')
        rule={'action':'TEXT_OVERRIDE','path':'review/corrections/page.txt',
            'text_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'review_kind':'AI_VISUAL_TRANSCRIPTION','reason':'Đối chiếu ảnh nguồn.'}
        return target,rule

    def test_correction_requires_exact_file_sha_and_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target,rule=self.fixture(root);cfg={'project_root':root}
            self.assertIn('01 bộ',correction_text(rule,cfg))
            with self.assertRaises(ValueError):correction_text({**rule,'text_sha256':'wrong'},cfg)
            with self.assertRaises(ValueError):correction_text({**rule,'path':'../outside.txt'},cfg)
            target.write_text('Changed',encoding='utf-8')
            with self.assertRaises(ValueError):correction_text(rule,cfg)

    def test_pdf_body_override_preserves_review_warning_and_source_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,rule=self.fixture(root)
            pdf=root/'source.pdf'
            with pymupdf.open() as doc:
                doc.new_page().insert_text((72,72),'Incomplete native text');doc.save(pdf)
            row={'relative_path':'sample.pdf','sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'file_id':'f'}
            (root/'config').mkdir()
            (root/'config/page_reviews.yaml').write_text(yaml.safe_dump({'documents':{
                'sample.pdf':{'sha256':row['sha256'],'pages':{1:rule}}}}),encoding='utf-8')
            cfg={'project_root':root,'extraction':{'use_docling':'never'}}
            pages,provenance=extract_pdf_pages(pdf,row,cfg,root/'artifacts')
            self.assertIn('Điều 87',pages[0]);self.assertEqual(provenance[0]['sha256'],row['sha256'])
            self.assertEqual(provenance[0]['method'],'source_bound_transcription')
            finalize_page_quality(provenance[0],pages[0],pages[0])
            self.assertEqual(provenance[0]['page_quality_status'],'REVIEW_REQUIRED')
            with self.assertRaises(ValueError):reviewed_pages({**row,'sha256':'different'},cfg)

    def test_git_crlf_checkout_does_not_break_canonical_text_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target,rule=self.fixture(root)
            canonical='Dòng một.\nDòng hai.\n'
            rule['text_sha256']=hashlib.sha256(canonical.encode('utf-8')).hexdigest()
            target.write_bytes(canonical.replace('\n','\r\n').encode('utf-8'))
            self.assertEqual(correction_text(rule,{'project_root':root}),canonical)
