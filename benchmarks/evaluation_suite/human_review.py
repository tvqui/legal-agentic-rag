"""Optional human answer scoring bound to the exact saved responses."""
from pathlib import Path
import argparse,csv,hashlib,json
from common import jsonl,save,mean

FIELDS=['id','variant','repeat','answer_sha256','question','answer','reference_answer','reviewer','reviewed_at',
        'correct','complete','supported','temporal_correct','notes']

def answer_hash(row):return hashlib.sha256(str(row.get('answer') or '').encode('utf-8')).hexdigest()

def export_template(output,records):
    records=[r for r in records if r.get('status')=='OK']
    if not records:return
    path=Path(output)/'human_review_template.csv'
    if path.exists():
        with path.open(encoding='utf-8-sig',newline='') as f:old=list(csv.DictReader(f))
        if any(r.get('reviewer') or any(r.get(k) for k in ('correct','complete','supported','temporal_correct')) for r in old):
            path=path.with_name('human_review_template_new.csv')
            if path.exists():return
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader()
        for row in records:
            w.writerow({k:v for k,v in {**row,'answer_sha256':answer_hash(row)}.items() if k in FIELDS})

def score(run,review_csv):
    run=Path(run);responses=run/'ablation/responses.jsonl'
    records=jsonl(responses);by_key={(r['id'],r['variant'],str(r['repeat'])):r for r in records}
    with Path(review_csv).open(encoding='utf-8-sig',newline='') as f:reviews=list(csv.DictReader(f))
    seen=set();judged=[]
    for row in reviews:
        key=(row['id'],row['variant'],str(row['repeat']))
        if key in seen:raise ValueError('Duplicate human review row')
        seen.add(key);source=by_key.get(key)
        if not source or row.get('answer_sha256')!=answer_hash(source):raise ValueError('Human review does not match saved answer')
        scores={k:row.get(k,'').strip() for k in ('correct','complete','supported','temporal_correct')}
        if not any(scores.values()):continue
        if not row.get('reviewer') or not row.get('reviewed_at'):raise ValueError('Reviewer and review date required')
        if any(scores[k] not in {'0','1'} for k in ('correct','complete','supported')):raise ValueError('Human binary labels 0/1 required')
        if scores['temporal_correct'] not in {'','0','1'}:raise ValueError('temporal_correct must be blank, 0 or 1')
        judged.append({**row,**{k:int(v) if v else None for k,v in scores.items()}})
    result={'scope':'human_answer_review_NOT_gold_or_source_approval','reviewed':len(judged),'variants':{}}
    for name in sorted({r['variant'] for r in records}):
        rs=[r for r in judged if r['variant']==name]
        result['variants'][name]={'n_reviewed':len(rs),
            'human_correct_rate':mean([r['correct'] for r in rs]),'human_complete_rate':mean([r['complete'] for r in rs]),
            'human_supported_rate':mean([r['supported'] for r in rs]),
            'human_correct_and_supported_rate':mean([r['correct'] and r['supported'] for r in rs]),
            'human_temporal_accuracy':mean([r['temporal_correct'] for r in rs if r['temporal_correct'] is not None]),
            'n_temporal_reviewed':sum(r['temporal_correct'] is not None for r in rs)}
    save(run/'human_review_summary.json',result)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--reviews',required=True)
    a=p.parse_args();print(json.dumps(score(a.run,a.reviews),ensure_ascii=False,indent=2))
