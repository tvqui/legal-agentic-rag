"""Live writer quality smoke using ONLY a fixed public synthetic task, no source upload.

It saves a proposal and checks JSON/Python syntax; NEVER executes model code.
Codex must read the saved source and run independent reviewed tests afterwards.
"""
import argparse,ast,hashlib,json,time
from pathlib import Path
import team
import writer

TASK = ("Return ONLY a JSON object with keys summary (string), code (string), limitations (list of strings). "
    "The code must define one pure Python function stable_unique_ids(ids): require a list of nonempty strings; "
    "raise ValueError otherwise, including for None, bool, int or an empty string inside the list. "
    "Return a NEW list of unique IDs in first occurrence order, with case and whitespace unchanged, "
    "and never mutate input. No imports, file/network/process access, dynamic execution or top-level effects. "
    "This is a public synthetic coding smoke task, not private project source. Tests are NOT RUN.")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',choices=sorted(writer.NEW_MODELS),default=writer.GROQ_MODEL)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--timeout',type=int,default=60)
    a=p.parse_args()
    if a.output.exists():raise FileExistsError('Choose new output')
    writer.load_tool_env(Path(__file__).resolve().parent/'.env')
    record={};a.output.mkdir(parents=True)
    route=writer.route_for(a.model,'json',fallback=False)
    def persist():team.save(a.output/'record.json',record)
    team.save(a.output/'manifest.json',{'scope':'PUBLIC_SYNTHETIC_SPEC_ONLY_NO_SOURCE_UPLOAD',
        'task':TASK,'task_sha256':hashlib.sha256(TASK.encode()).hexdigest(),'route':route,
        'route_sha256':writer.route_hash(route)})
    start=time.perf_counter()
    try:
        response=writer.generate(route,TASK,'You are a coding proposal writer. Return JSON only. Never claim tests ran.',
            record,persist,team.call_with_retry,team.reject_secrets,team.http_code,
            retries=1,timeout=a.timeout)
        text=response.text;proposal=json.loads(text)
        if not isinstance(proposal.get('code'),str) or not isinstance(proposal.get('summary'),str) or not isinstance(proposal.get('limitations'),list):
            raise ValueError('Proposal contract invalid')
        ast.parse(proposal['code'])
        team.save(a.output/'proposal.json',proposal)
        record.update(status='PROPOSAL_RECEIVED_REQUIRES_CODEX_REVIEW',elapsed_seconds=round(time.perf_counter()-start,3),
            python_syntax='PASS',execution_performed=False,tests_status='NOT_RUN')
        persist()
        print(json.dumps({'actual_model':record.get('actual_model'),'seconds':record['elapsed_seconds'],
                          'json':'PASS','python_syntax':'PASS','tests':'NOT_RUN'}))
    except Exception as exc:
        record.update(status='ERROR',error_type=type(exc).__name__,http_code=team.http_code(exc))
        persist();print('Writer smoke failed; inspect sanitized record.json');return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
