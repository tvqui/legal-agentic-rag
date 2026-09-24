from __future__ import annotations
import json,os
from pathlib import Path
from .models import Trace
def persist(trace:Trace,directory:str)->None:
    path=Path(directory); path.mkdir(parents=True,exist_ok=True); target=path/f'{trace.trace_id}.json'; tmp=target.with_suffix('.tmp')
    tmp.write_text(trace.model_dump_json(indent=2),encoding='utf-8'); os.replace(tmp,target)
