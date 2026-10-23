"""Mandatory source recall must survive multi-query fusion; auditing remains mandatory."""
import unittest
from vn_labor_online.models import Evidence,EvidencePlan,LegalLocator
from vn_labor_online.retrieval import retain_required_anchors,temporal_filter,authority_filter


def item(uid,article,doc='45/2019/QH14',**extra):
    return Evidence(unit_id=uid,document_number=doc,article_number=str(article),
        kind='PROVISION',
        retrieval_method=extra.pop('retrieval_method','policy'),
        text='Source text retained without editing.',score=.1,valid_from='2021-01-01',
        temporal_verified=True,authority_rank=100,source_url='https://example.test/source',**extra)


def plan(*articles):
    return EvidencePlan(mandatory_slots=['required'],slot_requirements={'required':[
        [LegalLocator(documents=['45/2019/QH14'],article=str(a))] for a in articles]})


class RequiredAnchorRetentionTests(unittest.TestCase):
    def test_a_low_rank_required_source_displaces_only_optional_candidates(self):
        required=item('required',13)
        candidates=[item('optional-'+str(i),100+i) for i in range(3)]
        result,report=retain_required_anchors(candidates,[required],plan(13),3)
        self.assertEqual(len(result),3)
        self.assertEqual(result[0].unit_id,'required')
        self.assertEqual(report['restored_ids'],['required'])
        self.assertFalse(result[0].verified)
        self.assertEqual(result[0].text,required.text)
        self.assertEqual([x.unit_id for x in candidates],['optional-0','optional-1','optional-2'])

    def test_one_alternative_per_group_leaves_room_for_other_required_rules(self):
        result,report=retain_required_anchors([], [item('a',13),item('b',13),item('c',2)],plan(13,2),2)
        self.assertEqual([x.unit_id for x in result],['a','c'])
        self.assertFalse(report['unrepresented_group_indexes'])

    def test_when_required_groups_exceed_budget_the_gap_is_explicit(self):
        result,report=retain_required_anchors([], [item('a',13),item('b',2)],plan(13,2),1)
        self.assertEqual(len(result),1)
        self.assertEqual(report['unrepresented_group_indexes'],[1])

    def test_existing_semantic_score_and_metadata_are_preserved_without_duplicates(self):
        fused=item('same',13,component_scores={'dense':.8},retrieval_method='hybrid')
        result,report=retain_required_anchors([fused],[item('same',13)],plan(13),5)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0].score,fused.score)
        self.assertEqual(result[0].component_scores,{'dense':.8,'policy':1.0})
        self.assertFalse(report['restored_ids'])

    def test_optional_slot_does_not_displace_mandatory_or_semantic_candidates(self):
        p=plan(13)
        p.slot_requirements['optional']=[[LegalLocator(documents=['45/2019/QH14'],article='2')]]
        result,report=retain_required_anchors([item('semantic',90)],[item('optional',2),item('required',13)],p,2)
        self.assertEqual([x.unit_id for x in result],['required','semantic'])
        self.assertEqual(report['required_groups'],1)

    def test_expired_and_unreviewed_strict_sources_are_not_rescued(self):
        expired=item('old',13,valid_to='2022-01-01')
        anchors,_=temporal_filter([expired],'2026-09-15',strict=False)
        result,report=retain_required_anchors([],anchors,plan(13),3)
        self.assertFalse(result)
        self.assertEqual(report['unrepresented_group_indexes'],[0])
        anchors,_=authority_filter([item('unreviewed',13)],strict=True)
        result,_=retain_required_anchors([],anchors,plan(13),3)
        self.assertFalse(result)


if __name__=='__main__': unittest.main()
