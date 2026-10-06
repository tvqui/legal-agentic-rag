"""Reproducible ONLINE Gold evaluation with strict approval/build gating."""
from __future__ import annotations

import argparse,json
from pathlib import Path

from vn_labor_offline.gold import validate_gold_record
from vn_labor_online.config import load_config
from vn_labor_online.pipeline import OnlinePipeline

from evaluate_online_ablation import evaluate_variant,load_jsonl


def normalized_metrics(raw:dict)->dict:
    wrong=raw.get('wrong_version_rate')
    return {
      'precision_at_k':raw.get('citation_precision'),
      'recall_at_k':raw.get('citation_recall'),
      'temporal_validity_accuracy':None if wrong is None else 1-wrong,
      'citation_accuracy':raw.get('citation_precision'),
      'groundedness_score':raw.get('reference_audit_pass_rate'),
      'abstention_accuracy':raw.get('abstention_accuracy'),
      'latency_p95_ms':raw.get('p95_latency_ms'),
      'fabricated_citations':raw.get('fabricated_citations'),
    }


def render_markdown(report:dict)->str:
    lines=['# ONLINE Gold Evaluation','',f"- Status: **{report['status']}**",
      f"- Build ID: `{report.get('build_id') or 'UNKNOWN'}`",f"- Gold records: {report['gold_records']}",'',
      '| Metric | Value |','|---|---:|']
    for key,value in report['metrics'].items():
        shown='N/A' if value is None else f'{value:.4f}' if isinstance(value,float) else str(value)
        lines.append(f'| `{key}` | {shown} |')
    if report.get('warning'): lines+=['',f"> {report['warning']}"]
    return '\n'.join(lines)+'\n'


def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,default=Path('config/online.yaml'))
    parser.add_argument('--gold',type=Path,required=True)
    parser.add_argument('--out',type=Path,default=Path('artifacts/online_evaluation/gold_evaluation.json'))
    parser.add_argument('--markdown-out',type=Path,default=Path('artifacts/online_evaluation/gold_evaluation.md'))
    args=parser.parse_args()
    gold=load_jsonl(args.gold); pipeline=OnlinePipeline(load_config(args.config))
    raw=evaluate_variant(pipeline,gold)
    build_id=pipeline.store.report.gold_build_id
    supplied=sorted({str(row.get('build_id')) for row in gold if row.get('build_id')})
    reviewed=bool(gold) and all(row.get('review_status')=='APPROVED' and not validate_gold_record(row) for row in gold)
    compatible=bool(build_id) and supplied==[build_id]
    official=reviewed and compatible
    report={'status':'OFFICIAL' if official else 'PROVISIONAL_DRAFT_GOLD','build_id':build_id,
      'supplied_build_ids':supplied,'gold_build_compatible':compatible,'gold_records':len(gold),
      'warning':None if official else 'Không được công bố các chỉ số là kết quả chính thức trước khi Gold được người có chuyên môn duyệt và khớp build.',
      'metrics':normalized_metrics(raw),'details':raw}
    args.out.parent.mkdir(parents=True,exist_ok=True); args.markdown_out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    args.markdown_out.write_text(render_markdown(report),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))


if __name__=='__main__': main()
