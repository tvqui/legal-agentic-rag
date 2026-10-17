"""Audit routing, dated requirements and tasks without loading models/indexes."""
from pathlib import Path
import argparse,json,collections
from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.taxonomy import profile_covers_issues,TAXONOMY_VERSION
from vn_labor_online.topics import TOPICS,VERSION

def audit(rows):
    results=[]
    for row in rows:
        analysis=analyze(intake(row['question'],[]),row.get('query_date'),row.get('facts'))
        plan=plan_evidence(analysis)
        results.append({'id':row.get('id',row.get('query_id')),'question':row['question'],
          'routing_topics':analysis.routing_topics,'legal_subissues':analysis.legal_subissues,
          'profile_covers_issues':profile_covers_issues(analysis),
          'dated_requirement_slots':list(plan.slot_requirements),
          'tasks':[task.model_dump(mode='json') for task in analysis.answer_tasks]})
    return {'status':'MECHANICAL_COVERAGE_ONLY_NOT_LEGAL_ACCURACY','taxonomy_version':TAXONOMY_VERSION,
      'topic_registry_version':VERSION,'registered_topics':len(TOPICS),'total':len(results),
      'has_routing_topics':sum(bool(row['routing_topics']) for row in results),
      'has_legal_subissue':sum(bool(row['legal_subissues']) for row in results),
      'profile_covers_issues':sum(row['profile_covers_issues'] for row in results),
      'has_dated_requirements':sum(bool(row['dated_requirement_slots']) for row in results),
      'multi_task_queries':sum(len(row['tasks'])>1 for row in results),'rows':results,
      'warning':'A routing label is not a legal profile, source approval, citation recall or an answered question.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--questions',type=Path,required=True)
    parser.add_argument('--out',type=Path,default=Path('artifacts/reports/online_coverage.json'))
    args=parser.parse_args()
    text=args.questions.read_text(encoding='utf-8-sig')
    rows=json.loads(text) if text.lstrip().startswith('[') else [json.loads(line) for line in text.splitlines() if line.strip()]
    report=audit(rows)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key!='rows'},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
