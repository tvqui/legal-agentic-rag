"""Checks on the distributed versioned annotations, not legal expert approval."""
import unittest
from pathlib import Path
from gold import read_candidate


class DistributedGoldTests(unittest.TestCase):
    def data(self,size):
        root=Path(__file__).resolve().parents[2]
        path=root/'gold_dataset'/f'PhapDienAI_Gold_{size}_Labor_v0_2.zip'
        if not path.exists():self.skipTest('Versioned Gold not present in this source checkout')
        return read_candidate(path)

    def test_default_questions_have_bounded_date_and_distinguish_missing_facts(self):
        rows,catalog,manifest=self.data(100)
        self.assertEqual(len(rows),100)
        self.assertEqual(manifest['counts_by_expected_status'],{'ANSWERABLE':88,'NEED_MORE_FACTS':12})
        self.assertTrue(all(r['applicable_date']=='2026-09-15' for r in rows))
        self.assertTrue(all(r['missing_facts'] for r in rows if r['expected_status']=='NEED_MORE_FACTS'))
        self.assertTrue(all(r['verification_status'].startswith('DRAFT') for r in rows))
        self.assertEqual(len(catalog),93)
        self.assertTrue(all(e.get('source_text_sha256') and 'ancestor_context' in e for e in catalog))

    def test_extended_set_keeps_same_default_questions_and_does_not_replace_them(self):
        rows,_,_=self.data(100);extended,_,_=self.data(120)
        by_id={r['question_id']:r for r in extended}
        self.assertEqual(len(by_id),120)
        self.assertTrue(all(r==by_id[r['question_id']] for r in rows))
        self.assertEqual(sum(r['expected_status']=='ANSWERABLE' for r in extended),108)

    def test_insufficient_reference_repairs_remain_in_the_distributed_dataset(self):
        rows,_,_=self.data(100);rows={r['question_id']:r for r in rows}
        self.assertEqual(rows['TD012']['gold_evidence_locators'],['Điều 14 khoản 1','Điều 14 khoản 2'])
        self.assertIn('Điều 25 khoản 1',rows['TD002']['gold_evidence_locators'])
        self.assertIn('Điều 107 khoản 4',rows['TG009']['gold_evidence_locators'])
        self.assertIn('Điều 36 khoản 2 điểm b',rows['CD007']['gold_evidence_locators'])
        self.assertIn('tổng thu nhập',rows['TD003']['question'].lower())


if __name__=='__main__':unittest.main()
