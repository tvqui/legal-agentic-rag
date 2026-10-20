"""Print safe Gemini diagnostics after startup failed; never prints key/error body."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from online_remote import secret
from vn_labor_online.config import load_config
from vn_labor_online.providers import GeminiProvider


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model')
    parser.add_argument('--config',type=Path,default=Path('config/online_kaggle.yaml'))
    args=parser.parse_args()
    cfg=load_config(args.config)
    model=args.model or os.getenv('GEMINI_MODEL') or cfg.adjudication.review_model
    if not model and cfg.researcher.mode=='gemini': model=cfg.researcher.model
    provider=GeminiProvider(model,secret('GEMINI_API_KEY',required=False),timeout=20,max_output_tokens=1024)
    try:
        report=provider.readiness()
        print(json.dumps(report,ensure_ascii=False),flush=True)
        return 0 if report['status']=='READY' else 1
    finally:
        provider.close()


if __name__=='__main__':
    raise SystemExit(main())
