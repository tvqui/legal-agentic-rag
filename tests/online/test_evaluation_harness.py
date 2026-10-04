from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH=Path(__file__).resolve().parents[2]/'scripts'/'evaluate_gold_set.py'
sys.path.insert(0,str(MODULE_PATH.parent))
SPEC=importlib.util.spec_from_file_location('evaluate_gold_set',MODULE_PATH)
MODULE=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)


class EvaluationHarnessTests(unittest.TestCase):
    def test_metric_normalization_and_markdown(self):
        metrics=MODULE.normalized_metrics({'citation_precision':.9,'citation_recall':.8,
          'wrong_version_rate':.1,'reference_audit_pass_rate':1.0,'abstention_accuracy':.75,
          'p95_latency_ms':12.5,'fabricated_citations':0})
        self.assertAlmostEqual(metrics['temporal_validity_accuracy'],.9)
        report={'status':'PROVISIONAL_DRAFT_GOLD','build_id':'b','gold_records':2,'metrics':metrics,
          'warning':'draft'}
        markdown=MODULE.render_markdown(report)
        self.assertIn('PROVISIONAL_DRAFT_GOLD',markdown)
        self.assertIn('temporal_validity_accuracy',markdown)


if __name__=='__main__': unittest.main()
