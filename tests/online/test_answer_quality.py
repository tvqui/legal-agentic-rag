from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from vn_labor_online.answer_quality import (
    clean_display, clean_source_excerpt, draft_issues, guarded_language_edit, language_issues,
)
from vn_labor_online.audit import citations, reference_audit
from vn_labor_online.compression import compress_evidence
from vn_labor_online.config import AdjudicationConfig, OnlineConfig, RetrievalConfig
from vn_labor_online.generation import LegalAdjudicator
from vn_labor_online.models import (
    AdjudicationDraft, Claim, Evidence, EvidenceState, QueryRequest, Stop,
    VerifiedEvidenceItem, VerifiedEvidencePack,
)
from vn_labor_online.pipeline import OnlinePipeline
from tests.online.test_online_core import fixture


def pack(text='Người lao động được nghỉ 12 ngày làm việc.'):
    state = EvidenceState(slots={'governing_rule': {'status': 'FOUND_VERIFIED', 'evidence_ids': ['prov_1']}},
                          gaps=[], coverage=1, mandatory_slots=['governing_rule'])
    return VerifiedEvidencePack(query='Quy định về nghỉ phép như thế nào?', coverage_state=state,
        evidence=[VerifiedEvidenceItem(evidence_id='prov_1', text=text, article='113', clause='1',
                  instrument_number='45/2019/QH14', official_url='https://vbpl.vn/source')])


def draft(text='Người lao động được nghỉ 12 ngày làm việc.'):
    return AdjudicationDraft(answer_summary=f'- {text} [prov_1]',
        claims=[Claim(claim_id='claim_1', text=text, evidence_ids=['prov_1'])], applicable_law_versions=[])


class AnswerQualityTests(unittest.TestCase):
    def test_layout_cleanup_preserves_dates_money_minus_and_point(self):
        raw='----\nĐiều 1: 12 ngày; 1.000.000 đồng; 30/09/2026.\n- Điểm l: x - y = -1.\n___'
        cleaned=clean_display(raw)
        self.assertNotIn('----',cleaned)
        for token in ('Điều 1', '12', '1.000.000', '30/09/2026', 'Điểm l', 'x - y = -1'):
            self.assertIn(token,cleaned)

    def test_quotes_are_immutable_even_if_admin_or_spacing(self):
        raw='Nguồn ghi “Kính gửi:  Công ty\n-----”.\n>   Kính gửi:  A\n"- - -"'
        self.assertEqual(clean_display(raw),raw)

    def test_admin_removed_only_from_display_when_not_requested(self):
        raw='Kính gửi: Công ty\n----\nNgười lao động được nghỉ 12 ngày.\nNơi nhận: Bộ phận hành chính'
        cleaned=clean_source_excerpt(raw,'Nghỉ phép bao nhiêu ngày?')
        self.assertEqual(cleaned,'Người lao động được nghỉ 12 ngày.')
        self.assertIn('Kính gửi:',clean_source_excerpt(raw,'Mục kính gửi trong đơn có gì?'))

    def test_compression_does_not_mutate_source_or_span(self):
        raw='Kính gửi: Công ty\n----\nNgười lao động được nghỉ 12 ngày.'
        item=Evidence(unit_id='prov_1',retrieval_method='EXACT',text=raw,source_text=raw,
                      provenance_span={'char_start':0,'char_end':len(raw)})
        before=item.model_dump()
        self.assertEqual(compress_evidence(item,'nghỉ phép'),'Người lao động được nghỉ 12 ngày.')
        self.assertEqual(item.model_dump(),before)

    def test_ocr_detection_does_not_replace_legal_one_or_point_l(self):
        self.assertIn('SUSPECT_OCR_WORD',language_issues('Người 1ao động được hưởng 1ương.'))
        self.assertIn('SUSPECT_LEGAL_LOCATOR',language_issues('Điều l quy định quyền nghỉ.'))
        self.assertEqual(language_issues('Điều 1 khoản 1 điểm l: nghỉ 12 ngày.'),[])

    def test_corrupted_encoding_and_decorative_claim_are_detected(self):
        self.assertIn('CORRUPTED_CHARACTERS',language_issues('Người lao động �'))
        self.assertIn('CORRUPTED_CHARACTERS',language_issues('Quyá»n nghỉ'))
        self.assertIn('EMPTY_OR_DECORATIVE_TEXT',language_issues('-----'))

    def test_guard_accepts_only_small_edit_with_same_legal_content(self):
        original=draft('Người lao động được nghỉ 12 ngày làm việc , hưởng lương.')
        edited=draft('Người lao động được nghỉ 12 ngày làm việc, hưởng lương.')
        self.assertTrue(guarded_language_edit(original,edited))
        for bad in ('Người lao động được nghỉ 14 ngày làm việc, hưởng lương.',
                    'Người lao động không được nghỉ 12 ngày làm việc, hưởng lương.',
                    'Người sử dụng lao động được nghỉ 12 ngày làm việc, hưởng lương.'):
            self.assertFalse(guarded_language_edit(original,draft(bad)))

    def test_guard_rejects_working_day_to_calendar_day_and_changed_scope(self):
        original=draft('Người lao động làm công việc bình thường được nghỉ 12 ngày làm việc theo quy định của hợp đồng lao động đã ký.')
        for replacement in ('12 ngày', '12 ngày làm việc'):
            edited=original.claims[0].text.replace('12 ngày làm việc',replacement)
            if replacement=='12 ngày làm việc': edited=edited.replace('bình thường','đặc thù')
            self.assertFalse(guarded_language_edit(original,draft(edited)))

    def test_guard_rejects_new_id_url_quote_assumption_or_point(self):
        original=draft('Điểm l Điều 1: không được nghỉ 12 ngày. “nguyên văn” https://vbpl.vn/source')
        for changed in (original.claims[0].text.replace('Điểm l','Điểm a'),
                        original.claims[0].text.replace('nguyên văn','sửa nguyên văn'),
                        original.claims[0].text.replace('/source','/other')):
            self.assertFalse(guarded_language_edit(original,draft(changed)))
        self.assertFalse(guarded_language_edit(original,original.model_copy(update={'assumptions':['mới']})))
        changed=original.model_copy(update={'claims':[original.claims[0].model_copy(update={'evidence_ids':['prov_2']})]})
        self.assertFalse(guarded_language_edit(original,changed))

    def test_clean_deterministic_answer_needs_no_provider(self):
        p=pack('Kính gửi: Công ty\n-----\nNgười lao động được nghỉ 12 ngày làm việc.')
        before=p.model_dump()
        result,warnings=LegalAdjudicator(AdjudicationConfig()).generate(p,False)
        self.assertNotIn('Kính gửi',result.answer_summary)
        self.assertNotIn('applicability',result.answer_summary)
        self.assertIn('[prov_1]',result.answer_summary)
        self.assertNotIn('ANSWER_QUALITY_BLOCKED',warnings)
        self.assertEqual(p.model_dump(),before)

    def test_corrupt_source_is_not_guessed_even_with_provider(self):
        p=pack('Người 1ao động được nghỉ 12 ngày.')
        engine=LegalAdjudicator(AdjudicationConfig())
        engine.provider=Mock()
        with patch.object(engine,'_generate',return_value=(draft(),[])):
            _,warnings=engine.generate(p,False)
        engine.provider.structured.assert_not_called()
        self.assertIn('ANSWER_QUALITY_BLOCKED',warnings)

    def test_one_language_repair_and_free_summary_never_exposed(self):
        text='Người lao động được nghỉ 12 ngày làm việc , hưởng lương.'
        noisy=draft(text)
        noisy=noisy.model_copy(update={'answer_summary':noisy.answer_summary+'\n-----'})
        # A repeated word defect remains after layout cleanup, triggering one repair.
        noisy=draft('Người lao động được nghỉ 12 ngày làm việc và nhận tiền tiền tiền lương theo hợp đồng đã ký với công ty.')
        fixed=draft('Người lao động được nghỉ 12 ngày làm việc và nhận tiền tiền lương theo hợp đồng đã ký với công ty.')
        fixed=fixed.model_copy(update={'answer_summary':'Điều 999 cho nghỉ 100 ngày.'})
        engine=LegalAdjudicator(AdjudicationConfig()); engine.provider=Mock()
        engine.provider.structured.return_value=fixed.model_dump()
        with patch.object(engine,'_generate',return_value=(noisy,[])):
            result,warnings=engine.generate(pack(),False)
        self.assertEqual(engine.provider.structured.call_count,1)
        self.assertIn('ANSWER_LANGUAGE_REPAIRED',warnings)
        self.assertNotIn('999',result.answer_summary)
        self.assertFalse(draft_issues(result,pack().query))

    def test_unsafe_repair_and_timeout_fall_back_without_loop(self):
        noisy=draft('Người lao động được được được nghỉ 12 ngày làm việc.')
        for response in (draft('Người lao động được nghỉ 99 ngày làm việc.').model_dump(),RuntimeError('timeout')):
            engine=LegalAdjudicator(AdjudicationConfig()); engine.provider=Mock()
            if isinstance(response,Exception): engine.provider.structured.side_effect=response
            else: engine.provider.structured.return_value=response
            with patch.object(engine,'_generate',return_value=(noisy,[])):
                result,warnings=engine.generate(pack(),False)
            self.assertEqual(engine.provider.structured.call_count,1)
            self.assertNotIn('99',result.answer_summary)
            self.assertIn('ANSWER_LANGUAGE_SAFE_FALLBACK',warnings)

    def test_final_reference_audit_rejects_corrupt_claim(self):
        item=Evidence(unit_id='prov_1',retrieval_method='EXACT',verified=True,
                      text='Người 1ao động được nghỉ 12 ngày.')
        d=draft(item.text)
        ok,issues=reference_audit(d.answer_summary,[item],citations([item]),d.claims)
        self.assertFalse(ok)
        self.assertTrue(any('SUSPECT_OCR_WORD' in issue for issue in issues))

    def test_pipeline_blocks_bad_source_with_no_citations_and_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); build=fixture(root)
            cfg=OnlineConfig(artifact_source=str(root),expected_build_id=build,trace_dir=str(root/'traces'),
                retrieval=RetrievalConfig(dense_enabled=False),cache_dir=str(root/'cache'))
            pipeline=OnlinePipeline(cfg)
            bad=draft('Người 1ao động được nghỉ 12 ngày.')
            with patch.object(pipeline.adjudicator,'generate',return_value=(bad,['ANSWER_QUALITY_BLOCKED'])):
                result=pipeline.ask(QueryRequest(question='Điều 1 của Nghị định 145/2020/ND-CP quy định gì?'))
            self.assertEqual(result.status,Stop.INSUFFICIENT_EVIDENCE)
            self.assertEqual(result.citations,[])
            self.assertEqual(result.claims,[])
            self.assertIn('source_text_quality',result.limitations)
            self.assertIn('đối chiếu bản gốc',result.answer)
            self.assertEqual(result.trace.reference_audit,'PASS')
            self.assertTrue(list((root/'traces').glob('*.json')))


if __name__ == '__main__':
    unittest.main()
