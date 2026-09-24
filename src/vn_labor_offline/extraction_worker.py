"""One document per process so the parent can enforce an actual wall-clock timeout."""
import json
import sys
from pathlib import Path
from .extract import extract_one

if __name__=='__main__':
    request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    result=extract_one(request['row'],request['cfg'],Path(request['output_dir']))
    Path(request['response']).write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
