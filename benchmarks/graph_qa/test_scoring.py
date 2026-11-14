"""Synthetic tests: no API, model, artifact, or legal judgment implied."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest

try:
    from . import scoring as s
except ImportError:
    import scoring as s


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.corpus={u:dict(unit_id=u,document_number="Doc",instrument_number="Law",article_number=a,
            clause_number="1",point_number=None,source_url="https://example.gov/doc?id=1",
            valid_from="2021-01-01",valid_to="2027-01-01") for u,a in [("a","1"),("b","2")]}
        self.gold=dict(id="q1",group="exception",question="Question",query_date="2026-11-14",required_groups=[["a"],["b"]])
        self.manifest=dict(selected_ids=["q1"],repetitions=1,arms=["graph_off","graph_on"],k=10)

    def citation(self,uid="a"):
        u=self.corpus[uid]
        return dict(evidence_id=uid,document_number=u["document_number"],instrument_number=u["instrument_number"],
            article=u["article_number"],clause="1",point=None,official_url=u["source_url"])

    def record(self,arm="graph_off",repeat=1,chosen=None):
        return dict(id="q1",arm=arm,repeat=repeat,status="OK",elapsed_ms=10,
            response=dict(answer="Answer",status="ANSWERED",citations=[self.citation()],parts=[],
                trace=dict(retrieval_candidates=[dict(unit_id="a")],verified_evidence_count=2,
                    events=[dict(event="selection",evidence_ids=chosen or ["a","b"])],retrieval_rounds=int(arm=="graph_on"))))

    def test_seed_selected_cited_are_separate(self):
        m=s.score_record(self.record(),self.gold,self.corpus)
        self.assertEqual(m["seed_recall_at_k"],.5)
        self.assertEqual(m["selected_group_recall"],1)
        self.assertEqual(m["citation_group_recall"],.5)
        self.assertEqual(m["citation_metadata_accuracy"],1)
        self.assertIsNone(m["human_correctness"])

    def test_metadata_checks_unknown_id_locator_and_url_query(self):
        c=self.citation();c["article"]="99";c["official_url"]="https://example.gov/doc?id=2"
        result=s.citation_check(c,self.corpus,"2026-11-14")
        self.assertEqual(result["errors"],["ARTICLE_MISMATCH","URL_MISMATCH_OR_MISSING"])
        c["evidence_id"]="missing"
        self.assertEqual(s.citation_check(c,self.corpus,"2026-11-14")["errors"],["UNKNOWN_EVIDENCE_ID"])

    def test_url_normalization_retains_query(self):
        self.assertEqual(s.normalized_url("HTTPS://EXAMPLE.GOV/doc/?id=1"),"https://example.gov/doc?id=1")
        self.assertIsNone(s.normalized_url("javascript:bad"))

    def test_temporal_metadata_half_open_and_unknown(self):
        self.assertFalse(s.citation_check(self.citation(),self.corpus,"2027-01-01")["temporal_consistent"])
        self.assertTrue(s.citation_check(self.citation(),self.corpus,"2021-01-01")["temporal_consistent"])
        self.corpus["a"]["valid_from"]=None
        self.assertIsNone(s.citation_check(self.citation(),self.corpus,"2026-11-14")["temporal_consistent"])

    def test_no_citations_is_not_metadata_perfect(self):
        r=self.record();r["response"]["citations"]=[]
        m=s.score_record(r,self.gold,self.corpus)
        self.assertIsNone(m["citation_metadata_accuracy"])
        self.assertEqual(m["citation_group_recall"],0)

    def test_missing_selection_instrumentation_stays_na(self):
        r=self.record();r["response"]["trace"]["events"]=[]
        self.assertIsNone(s.score_record(r,self.gold,self.corpus)["selected_group_recall"])
        r["response"]["trace"].pop("verified_evidence_count")
        self.assertIsNone(s.score_record(r,self.gold,self.corpus)["selected_group_recall"])
        r["response"]["trace"]["verified_evidence_count"]=0
        self.assertEqual(s.score_record(r,self.gold,self.corpus)["selected_group_recall"],0)

    def test_judge_denominator_and_invalid_values(self):
        left=self.record();right=self.record("graph_on")
        left["judge"]=dict(status="AI_JUDGED",correctness=.8,completeness=float("nan"))
        result=s.build_report([self.gold],[left,right],self.corpus,self.manifest)
        off,on=result["tables"][:2]
        self.assertEqual(off["ai_correctness"],.8)
        self.assertIsNone(off["ai_completeness"])
        self.assertIsNone(on["ai_correctness"])
        self.assertEqual(on["ai_correctness_n_queries"],0)

    def test_human_review_requires_identity_and_stamp(self):
        r=self.record();r["human_review"]=dict(status="REVIEWED",correctness=1)
        self.assertIsNone(s.score_record(r,self.gold,self.corpus)["human_correctness"])
        r["human_review"].update(reviewer="Reviewer",reviewed_at="2026-11-14")
        self.assertEqual(s.score_record(r,self.gold,self.corpus)["human_correctness"],1)

    def test_failure_schedule_and_all_completed_latency(self):
        left=self.record();right=self.record("graph_on");right.update(status="TIMEOUT",elapsed_ms=1000)
        result=s.build_report([self.gold],[left,right],self.corpus,self.manifest)
        self.assertEqual(result["execution_status"],"COMPLETE_WITH_ERRORS")
        self.assertEqual(result["tables"][1]["error_rate_over_completed"],1)
        self.assertEqual(result["tables"][1]["mean_ms_all_completed"],1000)
        self.assertIsNone(result["tables"][1]["selected_group_recall"])
        self.assertEqual(result["successful_pairs"],0)

    def test_incomplete_duplicate_unexpected_empty_schedules(self):
        result=s.build_report([self.gold],[self.record()],self.corpus,self.manifest)
        self.assertEqual(result["execution_status"],"INCOMPLETE")
        self.assertEqual(len(result["missing_schedule"]),1)
        for rows,manifest in [([self.record(),self.record()],self.manifest),
            ([self.record(repeat=2)],self.manifest),([],{**self.manifest,"selected_ids":[]})]:
            with self.assertRaises(ValueError):s.build_report([self.gold],rows,self.corpus,manifest)

    def test_paired_bootstrap_unit_is_query_and_matches_repeats(self):
        manifest={**self.manifest,"repetitions":3}
        rows=[]
        for rep in (1,2,3):
            rows.extend([self.record(repeat=rep,chosen=["a"]),self.record("graph_on",rep)])
        rows[3]["status"]="ERROR"
        result=s.build_report([self.gold],rows,self.corpus,manifest)
        metric=next(r for r in result["paired"] if r["group"]=="all" and r["metric"]=="selected_group_recall")
        self.assertEqual(metric["n_queries"],1)
        self.assertEqual(metric["mean_delta"],.5)
        self.assertIsNone(metric["ci95_low"])
        self.assertEqual(result["successful_pairs"],2)

    def test_gold_groups_must_be_disjoint_known_and_nonempty(self):
        for groups in [[],[["a"],["a"]],[["missing"]],[[]]]:
            with self.assertRaises(ValueError):s.score_record(self.record(),{**self.gold,"required_groups":groups},self.corpus)

    def test_report_resume_preserves_reviews_and_adds_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            def write(name,rows):
                (p/name).write_text("".join(json.dumps(r)+"\n" for r in rows),encoding="utf8")
            write("gold.jsonl",[self.gold]);write("corpus.jsonl",list(self.corpus.values()))
            (p/"run_manifest.json").write_text(json.dumps(self.manifest),encoding="utf8")
            write("responses.jsonl",[self.record()]);s.report(p)
            with (p/"human_review.csv").open(encoding="utf-8-sig",newline="") as f:reviews=list(csv.DictReader(f))
            reviews[0].update(correctness=".9",reviewer="Teacher",reviewed_at="2026-11-14",review_status="REVIEWED",notes="Keep me")
            s.write_csv(p/"human_review.csv",reviews)
            write("responses.jsonl",[self.record(),self.record("graph_on")]);result=s.report(p)
            self.assertEqual(result["tables"][0]["human_correctness"],.9)
            self.assertIsNone(result["tables"][1]["human_correctness"])
            with (p/"human_review.csv").open(encoding="utf-8-sig",newline="") as f:reviews=list(csv.DictReader(f))
            self.assertEqual(len(reviews),2)
            self.assertEqual(reviews[0]["notes"],"Keep me")
            self.assertEqual(reviews[1]["review_status"],"")
            for name in ("comparison.json","comparison.csv","paired.csv","per_attempt_metrics.csv","comparison.md","responses.md"):
                self.assertTrue((p/name).exists(),name)


if __name__=="__main__":unittest.main()
