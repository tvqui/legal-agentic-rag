import unittest
from types import SimpleNamespace

from vn_labor_online.article_content import heading_only,resolve_article_requirements
from vn_labor_online.models import EvidencePlan,LegalLocator,VerifiedEvidenceItem,Claim
from vn_labor_online.retrieval import Retriever,as_evidence
from vn_labor_online.config import OnlineConfig
from vn_labor_online.evidence import select_for_plan,state_for
from vn_labor_online.answer_review import hard_issues


def unit(uid,clause='',point='',text='',document='45/2019/QH14',version='current',start='2021-01-01',end=None):
    return dict(unit_id=uid,kind='PROVISION',document_number=document,document_id=version,
        article_number='77',clause_number=clause,point_number=point,
        text=text,source_text=text,ancestor_context='',valid_from=start,valid_to=end,
        provision_version_id=uid,authority_rank=100,official_source=True,source_catalog_status='VERIFIED',
        temporal_verified=True,provision_temporal_verified=True)


class ArticleContentTests(unittest.TestCase):
    def root(self): return unit('root',text='Điều 77. Nghĩa vụ của các bên trong quan hệ lao động')
    def plan(self,locator=None):
        return EvidencePlan(mandatory_slots=['governing_rule','operative_rule'],
            slot_requirements={'operative_rule':[[locator or LegalLocator(documents=['45/2019/QH14'],article='77')]]})

    def test_header_is_distinct_from_short_operative_definition(self):
        self.assertTrue(heading_only(self.root()))
        self.assertFalse(heading_only(unit('definition',text='Điều 77. Nghĩa vụ Các bên phải thực hiện đúng hợp đồng.')))
        self.assertFalse(heading_only(unit('seniority',text='Điều 77. Cứ đủ 05 năm làm việc được tăng 01 ngày nghỉ.')))
        self.assertFalse(heading_only(unit('clause','1',text='Điều 77. Nghĩa vụ của các bên')))
        self.assertFalse(heading_only(dict(self.root(),kind='CASE')))

    def test_header_does_not_satisfy_substantive_coverage(self):
        header=as_evidence(self.root(),1,'policy',1).model_copy(update={'verified':True})
        state=state_for([header],self.plan(),'2026-01-01')
        self.assertIn('governing_rule',state.gaps)
        self.assertIn('operative_rule',state.gaps)

    def test_materialize_each_source_branch_without_mutating_original(self):
        root=self.root()
        children=[unit('one','1',text='1. Các bên phải cung cấp thông tin.'),
            unit('two','2',text='2. Các nghĩa vụ bao gồm:'),
            unit('a','2','a','a) Phải thông báo bằng văn bản.'),
            unit('b','2','b','b) Phải trao đổi trước khi thực hiện.')]
        original=self.plan(); index={('45/2019/QH14','77'):[root,*children]}
        resolved,notes=resolve_article_requirements(original,index,'2026-01-01')
        self.assertEqual(len(original.slot_requirements['operative_rule']),1)
        self.assertEqual(len(resolved.slot_requirements['operative_rule']),4)
        self.assertTrue(all(g[0].exact_level for g in resolved.slot_requirements['operative_rule']))
        self.assertEqual(notes[0]['branch_groups'],4)
        items=[as_evidence(u,1,'policy',i).model_copy(update={'verified':True}) for i,u in enumerate([root,*children],1)]
        selected,state=select_for_plan(items,resolved,'2026-01-01',False,8)
        self.assertEqual({e.unit_id for e in selected},{u['unit_id'] for u in children})
        self.assertNotIn('operative_rule',state.gaps)
        _,clipped=select_for_plan(items,resolved,'2026-01-01',False,2)
        self.assertIn('operative_rule',clipped.gaps)

    def test_no_same_version_children_does_not_invent_content(self):
        index={('45/2019/QH14','77'):[self.root(),unit('foreign','1',text='1. Phải thông báo.',version='other')]}
        resolved,notes=resolve_article_requirements(self.plan(),index,'2026-01-01')
        self.assertEqual(notes,[])
        self.assertIsNone(resolved.slot_requirements['operative_rule'][0][0].clause)

    def test_inactive_editions_do_not_add_historical_branches(self):
        old=unit('old','9',text='9. Quy định trước đây.',version='old',start='2013-01-01',end='2021-01-01')
        child=unit('new','1',text='1. Các bên phải thông báo.')
        index={('45/2019/QH14','77'):[self.root(),old,child]}
        resolved,_=resolve_article_requirements(self.plan(),index,'2026-01-01')
        self.assertEqual([g[0].clause for g in resolved.slot_requirements['operative_rule']],['1'])

    def test_explicit_level_or_text_scope_is_not_broadened(self):
        index={('45/2019/QH14','77'):[self.root(),unit('one','1',text='1. Phải cung cấp thông tin.')]}
        for locator in (LegalLocator(documents=['45/2019/QH14'],article='77',exact_level=True),
                        LegalLocator(documents=['45/2019/QH14'],article='77',clause='1'),
                        LegalLocator(documents=['45/2019/QH14'],article='77',text_contains=['thông tin'])):
            with self.subTest(locator=locator):
                original=self.plan(locator)
                resolved,notes=resolve_article_requirements(original,index,'2026-01-01')
                self.assertEqual(resolved,original)
                self.assertEqual(notes,[])

    def test_retriever_seeds_every_required_child(self):
        units=[self.root(),unit('one','1',text='1. Các bên phải cung cấp thông tin.'),unit('two','2',text='2. Các bên không được cưỡng ép.')]
        store=SimpleNamespace(units=units)
        retriever=Retriever(store,OnlineConfig(artifact_source='fixture'))
        resolved,_=retriever.resolve_article_plan(self.plan(),'2026-01-01')
        self.assertEqual({e.unit_id for e in retriever.profile_anchors(resolved)},{'one','two'})

    def test_long_title_cannot_support_an_invented_legal_permission(self):
        item=VerifiedEvidenceItem(evidence_id='root',instrument_number='45/2019/QH14',article='77',
            text=self.root()['text'],full_text=self.root()['text'])
        claim=Claim(claim_id='invented',text='Doanh nghiệp được chấm dứt hợp đồng với mọi lao động.',evidence_ids=['root'])
        self.assertIn('HEADING_ONLY_SUPPORT',hard_issues(claim,[item]))

    def test_clause_enumeration_keeps_introduction_and_every_point(self):
        units=[self.root(),unit('intro','2',text='2. Người sử dụng lao động phải báo trước như sau:'),
            unit('a','2','a','a) Phải thông báo bằng văn bản.'),
            unit('b','2','b','b) Phải trao đổi với người lao động.'),
            unit('other','3','a','a) Một trường hợp khác.')]
        plan=self.plan(LegalLocator(documents=['45/2019/QH14'],article='77',clause='2'))
        resolved,notes=resolve_article_requirements(plan,{('45/2019/QH14','77'):units},'2026-01-01')
        groups=resolved.slot_requirements['operative_rule']
        self.assertEqual({(g[0].clause,g[0].point) for g in groups},{('2',None),('2','a'),('2','b')})
        self.assertEqual(notes[0]['clause'],'2')
        items=[as_evidence(u,1,'policy',1).model_copy(update={'verified':True}) for u in units if u['unit_id']=='intro']
        self.assertIn('operative_rule',state_for(items,resolved,'2026-01-01').gaps)

    def test_operative_article_intro_is_not_lost_when_resolving_children(self):
        intro=unit('intro',text='Điều 77. Các bên phải thực hiện các nghĩa vụ sau:')
        children=[unit('a','1',text='1. Phải trao đổi trước.'),unit('b','2',text='2. Phải thông báo sau.')]
        resolved,_=resolve_article_requirements(self.plan(),{('45/2019/QH14','77'):[intro,*children]},'2026-01-01')
        self.assertEqual({g[0].clause for g in resolved.slot_requirements['operative_rule']},{None,'1','2'})

    def test_intro_without_same_version_children_or_explicit_exact_scope_stays_unchanged(self):
        intro=unit('intro','2',text='2. Quy định được áp dụng trong các trường hợp sau:')
        foreign=unit('foreign','2','a','a) Nghĩa vụ.',version='other')
        for locator in (LegalLocator(documents=['45/2019/QH14'],article='77',clause='2'),
            LegalLocator(documents=['45/2019/QH14'],article='77',clause='2',exact_level=True)):
            plan=self.plan(locator)
            resolved,notes=resolve_article_requirements(plan,{('45/2019/QH14','77'):[intro,foreign]},'2026-01-01')
            self.assertEqual(resolved,plan)
            self.assertFalse(notes)

    def test_resolved_scope_is_bound_to_actual_units_from_the_container_version(self):
        units=[self.root(),unit('current','1',text='1. Phải thông báo.'),
            unit('foreign','1',text='1. Văn bản khác.',version='other')]
        retriever=Retriever(SimpleNamespace(units=units),OnlineConfig(artifact_source='fixture'))
        resolved,_=retriever.resolve_article_plan(self.plan(),'2026-01-01')
        self.assertEqual(resolved.slot_requirements['operative_rule'][0][0].unit_ids,['current'])
        self.assertEqual([e.unit_id for e in retriever.profile_anchors(resolved)],['current'])

    def test_vietnamese_point_order_places_d_stroke_between_d_and_e(self):
        units=[self.root(),*[unit(point,'1',point,'Nội dung điểm '+point) for point in ('e','đ','d')]]
        resolved,_=resolve_article_requirements(self.plan(),{('45/2019/QH14','77'):units},'2026-01-01')
        self.assertEqual([g[0].point for g in resolved.slot_requirements['operative_rule']],['d','đ','e'])


if __name__=='__main__': unittest.main()
