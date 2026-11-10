import unittest
from types import SimpleNamespace as NS
from vn_labor_online.config import GraphConfig
from vn_labor_online.graph import GraphExplorer


class DynamicGraphRequirementTests(unittest.TestCase):
    def graph(self):
        units={'target':{'unit_id':'target','text':'Điều kiện xác nhận hồ sơ theo quy định.','kind':'PROVISION'}}
        edges=[{'id':'reference','source':'seed','target':'target','type':'REFERENCES'}]
        return GraphExplorer(NS(edges=edges,units_by_id=units,nodes_by_id={}),GraphConfig())

    def test_new_planned_slot_can_follow_a_legal_reference(self):
        graph=self.graph()
        result=graph.expand_round(['seed'],['new_document_requirement'],'hồ sơ',{'seed'},{},4,4,
            requirement_slots={'new_document_requirement':[]})
        self.assertEqual([e.unit_id for e in result[0]],['target'])
        self.assertFalse(result[0][0].verified)
        self.assertEqual(result[0][0].graph_relations,['REFERENCES'])

    def test_unknown_unplanned_gap_does_not_enable_generic_traversal(self):
        result=self.graph().expand_round(['seed'],['unknown_provider_failure'],'hồ sơ',{'seed'},{},4,4)
        self.assertFalse(result[0])

    def test_no_gap_and_node_budget_still_limit_graph_work(self):
        graph=self.graph()
        self.assertFalse(graph.expand_round(['seed'],[],'hồ sơ',{'seed'},{},4,4,requirement_slots={'new':[]})[0])
        self.assertFalse(graph.expand_round(['seed'],['new'],'hồ sơ',{'seed'},{},0,4,requirement_slots={'new':[]})[0])


if __name__=='__main__':unittest.main()
