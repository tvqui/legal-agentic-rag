"""Replay observed content failures against a pinned OFFLINE release.

This checks rule completeness and citation locations, not expert legal approval.
It never loads neural models or rewrites OFFLINE artifacts. Warm local timings
exclude server startup/network and cannot be compared with remote benchmarks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

from vn_labor_online.config import (
    AdjudicationConfig, ApplicabilityConfig, ResearcherConfig, load_config,
)
from vn_labor_online.models import QueryRequest
from vn_labor_online.pipeline import OnlinePipeline

CASE_IDS={
    'OLD-1.1','OLD-1.2','OLD-1.3','OLD-1.4','OLD-3.1',
    'NEW-2.4','NEW-3.1','NEW-4.1','NEW-5.1','NEW-5.4',
    'NEW-6.3','NEW-6.4','NEW-9.1','NEW-9.3','NEW-9.5',
    'OLD-3.3','OLD-3.4','OLD-3.5','NEW-1.2','NEW-1.5','NEW-2.2',
    'NEW-4.2','NEW-4.3','NEW-4.4','NEW-4.5','NEW-5.2','NEW-5.3',
}


def content_checks(case_id,response):
    answer=response.answer.lower()
    cited={(str(c.article or ''),str(c.clause or ''),str(c.point or '')) for c in response.citations}
    checks={
        'expected_status':response.status.value==('NEED_MORE_FACTS' if case_id in {'NEW-5.4','NEW-5.2'} else 'PARTIAL_ALLOWED'),
        'no_provider_fallback':not any('PROVIDER_ERROR' in w or 'PROVIDER_FALLBACK' in w for w in response.warnings),
    }
    if case_id not in {'NEW-5.4','NEW-5.2'}:
        checks['citations_present']=bool(cited)
        checks['reference_audit_pass']=response.trace.reference_audit=='PASS'
        checks['review_not_fabricated']=response.evidence_status=='PARTIAL'
    if case_id=='OLD-1.1': checks['late_wage_reference']={('35','2','b'),('97','4','')}<=cited
    if case_id=='OLD-1.2': checks['misinformation_reference']={('35','2','g'),('16','1','')}<=cited
    if case_id=='OLD-1.3': checks['travel_rule']=('113','6','') in cited and '3 ngày' in answer
    if case_id=='OLD-1.4': checks['definition_and_liability']={('39','',''),('40','1',''),('40','2',''),('40','3','')}<=cited
    if case_id=='OLD-3.1': checks['employee_chain']={('35','1','a'),('39','',''),('40','1',''),('40','2',''),('40','3','')}<=cited
    if case_id=='NEW-2.4': checks['deposit_prohibition']=('17','2','') in cited
    if case_id=='NEW-3.1': checks['only_two_contract_types']={('20','1','a'),('20','1','b')}<=cited
    if case_id=='NEW-4.1':
        checks['four_probation_branches']={c.proposition.value for c in response.claims if c.proposition}=={180,60,30,6}
        checks['probation_units']=all(f'{n} ngày làm việc' not in answer for n in (180,60,30))
    if case_id=='NEW-5.1':
        checks['fee_and_pay']='không được thu học phí' in answer and ('61','5','') in cited
        checks['no_inverted_sanction']='không được đào tạo' not in answer and 'không được ký hợp đồng đào tạo' not in answer
        checks['merged_boundary_disclosed']='SOURCE_CLAUSE_BOUNDARY_NEEDS_REVIEW' in response.warnings
    if case_id=='NEW-5.4':
        checks['relationship_question']=any('chương trình của trường' in q for q in response.questions)
        checks['no_wage_date_question']=not any('Thời điểm phát sinh' in q for q in response.questions)
    if case_id in {'NEW-6.3','NEW-6.4'}:
        checks['training_chain']={('62','1',''),('62','2','d'),('62','3','')}<=cited
        checks['no_invented_exit_rule']='nếu có lý do chính đáng' not in answer and 'nghỉ việc trước thời hạn sau đào tạo' not in answer
        checks['no_wrong_vbhn_type']='nghị định số 18/vbhn' not in answer
        if case_id=='NEW-6.3': checks['stipulated_liability']=('40','3','') in cited and not response.questions
        else: checks['no_automatic_liability']='không thể khẳng định cứ nghỉ trước thời hạn' in answer
    if case_id=='NEW-9.1':
        checks['overtime_limits']=all(t in answer for t in ('50%','12 giờ','40 giờ','200 giờ','300 giờ'))
        checks['extended_conditions']={('107','3',p) for p in ('a','b','c','d','đ')}<=cited
    if case_id=='NEW-9.3':
        checks['night_overtime_chain']={('98','1',''),('98','2',''),('98','3',''),('57','1',''),('57','1','b'),('57','2','')}<=cited
        checks['no_unnecessary_holiday_list']=not any(article=='112' for article,_,_ in cited)
    if case_id=='NEW-9.5': checks['mandatory_overtime_pay']={('98','1',''),('98','1','a'),('98','1','b'),('98','1','c')}<=cited and not response.questions
    if case_id=='OLD-3.3':
        checks['harassment_exception']=('35','2','d') in cited and not response.questions
        checks['no_false_liability']=not any(a in {'36','40'} for a,_,_ in cited)
    if case_id=='OLD-3.4':
        checks['misinformation_complete']={('35','2','g'),('16','1','')}<=cited and not response.questions
    if case_id=='OLD-3.5':
        checks['agreement_mechanism']=('34','3','') in cited and not response.questions
    if case_id in {'NEW-1.2','NEW-1.5'}:
        checks['relationship_rule']=('13','1','') in cited
        checks['no_employer_exit']=not any(a=='36' for a,_,_ in cited)
    if case_id=='NEW-2.2':
        checks['original_documents']=('17','1','') in cited and 'bị cấm' in answer
        checks['no_termination_dump']=not any(a in {'35','36'} for a,_,_ in cited)
    if case_id=='NEW-4.2':
        checks['probation_pay_application']=('26','','') in cited and '80%' in answer and 'thấp hơn' in answer
    if case_id=='NEW-4.3':
        checks['sanction_and_remedy']={('26','',''),('10','2',''),('10','2','c'),('10','3','a'),('6','1','')}<=cited
        checks['organization_multiplier']='hai lần' in answer
    if case_id=='NEW-4.4':
        checks['conditional_duration']=all(t in answer for t in ('180','60','30','06','chưa thể kết luận')) and bool(response.questions)
    if case_id=='NEW-4.5':
        checks['probation_once']=('25','','') in cited and 'một lần' in answer and 'thực chất' in answer
        checks['no_false_rule']='không có quy định cấm' not in answer
    if case_id=='NEW-5.2':
        checks['intern_relationship_clarification']=any('chương trình của trường' in q for q in response.questions)
    if case_id=='NEW-5.3':
        checks['four_mechanisms']={('13','1',''),('24','1',''),('26','',''),('61','1',''),('61','2',''),('61','5','')}<=cited
        checks['not_assigned_probation_contract']='contract_type' not in response.facts
    return checks


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',required=True,type=Path)
    parser.add_argument('--verify-fast-path',action='store_true',help='Keep full config; fail if these known cases call a neural/generic retrieval component.')
    parser.add_argument('--config',type=Path,default=Path('config/online.yaml'))
    parser.add_argument('--output',type=Path,default=Path('artifacts/online_benchmarks/review_content_20261008_local'))
    args=parser.parse_args()
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    raw=args.baseline.read_bytes()
    baseline=[json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    selected=[row for row in baseline if row['id'] in CASE_IDS]
    if len(selected)!=len(CASE_IDS) or {row['id'] for row in selected}!=CASE_IDS:
        parser.error('Baseline must contain every selected ID exactly once; no questions are fabricated.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    cfg=load_config(args.config)
    repo=Path(__file__).resolve().parents[1]
    source=Path(cfg.artifact_source)
    cache=Path(cfg.cache_dir)
    overrides={
        'artifact_source':str(source if source.is_absolute() else repo/source),
        'cache_dir':str(cache if cache.is_absolute() else repo/cache),
        'trace_dir':str(args.output.parent/(args.output.name+'_traces')),
    }
    if args.verify_fast_path:
        overrides.update({
            'researcher':ResearcherConfig(mode='ollama'),
            'applicability':ApplicabilityConfig(mode='hybrid'),
            'adjudication':AdjudicationConfig(mode='ollama'),
            'retrieval':cfg.retrieval.model_copy(update={'bm25_enabled':True,'dense_enabled':True,'issue_anchor_enabled':True}),
            'reranker':cfg.reranker.model_copy(update={'enabled':True}),
        })
    else:
        overrides.update({
            'researcher':ResearcherConfig(),'applicability':ApplicabilityConfig(),'adjudication':AdjudicationConfig(),
            'retrieval':cfg.retrieval.model_copy(update={'bm25_enabled':False,'dense_enabled':False,'issue_anchor_enabled':False}),
            'reranker':cfg.reranker.model_copy(update={'enabled':False}),
            'graph':cfg.graph.model_copy(update={'enabled':False}),
        })
    cfg=cfg.model_copy(update=overrides)
    pipeline=OnlinePipeline(cfg)
    forbidden_calls=[]
    if args.verify_fast_path:
        def forbid(name):
            def tripwire(*unused_args,**unused_kwargs):
                forbidden_calls.append(name)
                raise RuntimeError('UNEXPECTED_EXPENSIVE_PATH:'+name)
            return tripwire
        for name in ('researcher','applicability','adjudicator'):
            component=getattr(pipeline,name)
            if component.provider is not None: component.provider.structured=forbid(name)
        for name in ('bm25','dense','neural_rerank','issue_anchor','case_law','community_cases'):
            setattr(pipeline.retriever,name,forbid(name))
    rows=[]
    try:
        for source in selected:
            calls_before=len(forbidden_calls)
            start=time.perf_counter()
            response=pipeline.ask(QueryRequest(question=source['question']))
            elapsed=time.perf_counter()-start
            checks=content_checks(source['id'],response)
            if args.verify_fast_path: checks['no_expensive_path_called']=len(forbidden_calls)==calls_before
            result={'id':source['id'],'question':source['question'],'elapsed_seconds':round(elapsed,6),
                'baseline_elapsed_seconds':source['elapsed_seconds'],'baseline_status':source['response']['status'],
                'checks':checks,'passed':all(checks.values()),'response':response.model_dump(mode='json')}
            rows.append(result)
            print(source['id'],response.status.value,f'{elapsed:.4f}s','PASS' if result['passed'] else 'FAIL',flush=True)
    finally:
        pipeline.close()
    args.output.with_suffix('.jsonl').write_text('\n'.join(json.dumps(row,ensure_ascii=False) for row in rows)+'\n',encoding='utf-8')
    elapsed=[r['elapsed_seconds'] for r in rows]
    report={'schema_version':1,'mode':'FULL_CONFIG_FAST_PATH_CONTRACT' if args.verify_fast_path else 'LOCAL_RULE_PROFILE_REPLAY_NO_NEURAL_INFERENCE',
        'forbidden_calls':forbidden_calls,'build_id':pipeline.store.report.build_id,
        'provider_modes':{name:getattr(cfg,name).mode for name in ('researcher','applicability','adjudication')},
        'baseline_sha256':hashlib.sha256(raw).hexdigest(),'baseline_questions_unchanged':True,
        'cases':len(rows),'passed':sum(r['passed'] for r in rows),
        'timings_scope':'Warm local ask() including trace persistence; excludes startup/network/GPU/LLM.',
        'mean_seconds':statistics.mean(elapsed),'median_seconds':statistics.median(elapsed),'max_seconds':max(elapsed),
        'human_gold_approval':False,'remote_285_rebenchmark_required':True,
        'case_results':[{k:r[k] for k in ('id','elapsed_seconds','passed','checks')} for r in rows]}
    args.output.with_suffix('.summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"Content replay: {report['passed']}/{report['cases']}; not a legal Gold evaluation.")
    return 0 if report['passed']==report['cases'] else 1


if __name__=='__main__': raise SystemExit(main())
