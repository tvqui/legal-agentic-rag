import unittest
from vn_labor_online.analysis import analyze,intake
from vn_labor_online.topics import detect_topics


class AccidentContextRoutingTests(unittest.TestCase):
    def test_accident_during_work_routes_to_safety_without_assuming_coverage(self):
        analysis=analyze(intake('Người lao động bị tai nạn trong giờ làm việc. Công ty phải trả gì và bảo hiểm xử lý thế nào?',[]))
        self.assertIn('occupational_accident',analysis.routing_topics)
        self.assertIn('SAFETY',analysis.legal_issues)
        self.assertNotIn('normal_hours',analysis.routing_topics)
        self.assertNotIn('WORKING_TIME',analysis.legal_issues)
        self.assertNotIn('accident_qualified',analysis.facts)

    def test_independent_hours_issue_is_retained_beside_accident(self):
        analysis=analyze(intake('Tôi bị tai nạn lao động. Công ty còn cho làm 12 giờ/ngày, có đúng không?',[]))
        self.assertIn('occupational_accident',analysis.routing_topics)
        self.assertIn('normal_hours',analysis.routing_topics)
        self.assertIn('WORKING_TIME',analysis.legal_issues)

    def test_general_hours_question_is_not_removed(self):
        self.assertIn('normal_hours',{t.key for t in detect_topics('Trong giờ làm việc có được nghỉ giữa giờ không?')})

    def test_unrelated_private_accident_is_not_promoted_to_work_accident(self):
        self.assertNotIn('occupational_accident',{t.key for t in detect_topics('Tôi bị tai nạn trong kỳ nghỉ riêng, cần hỏi trách nhiệm dân sự.')})


if __name__=='__main__': unittest.main()
