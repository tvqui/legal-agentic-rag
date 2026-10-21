"""Print safe Gemini diagnostics after startup failed; never prints key/error body."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from online_remote import secret
from vn_labor_online.config import load_config
from vn_labor_online.providers import GeminiProvider
from vn_labor_online.gemini_diagnostics import classify_error
from vn_labor_online.runtime import request_budget, request_timeout


def plain_probe(provider):
    """One optional synthetic request, same RPM gate; no source or user data."""
    try:
        from google import genai
        from google.genai import types
        with request_budget(20):
            provider.rate_limiter.acquire(min(20,provider.rate_policy.max_wait_seconds))
            with genai.Client(api_key=provider.api_key,http_options=types.HttpOptions(
                    timeout=max(1,int(request_timeout(15)*1000)),
                    retry_options=types.HttpRetryOptions(attempts=1))) as client:
                result=client.models.generate_content(model=provider.model,contents='Reply OK.',
                    config=types.GenerateContentConfig(max_output_tokens=1024))
            if not getattr(result,'text',None):
                return {'status':'DEGRADED','check':'PLAIN_PROBE','error_code':'GEMINI_EMPTY_RESPONSE'}
        return {'status':'READY','check':'PLAIN_PROBE'}
    except Exception as exc:
        code=getattr(exc,'code',None)
        safe=f'GEMINI_HTTP_{code}' if type(code) is int and 400<=code<=599 else 'GEMINI_PLAIN_PROBE_FAILED'
        return {'status':'DEGRADED','check':'PLAIN_PROBE','error_code':safe,**classify_error(exc)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model')
    parser.add_argument('--diagnose',action='store_true',help='After HTTP 400 only, try one plain synthetic request. This does not bypass the failed readiness check.')
    parser.add_argument('--config',type=Path,default=Path('config/online_kaggle.yaml'))
    args=parser.parse_args()
    cfg=load_config(args.config)
    model=args.model or os.getenv('GEMINI_MODEL') or cfg.adjudication.review_model
    if not model and cfg.researcher.mode=='gemini': model=cfg.researcher.model
    provider=GeminiProvider(model,secret('GEMINI_API_KEY',required=False),timeout=20,max_output_tokens=1024)
    try:
        report=provider.readiness()
        print(json.dumps(report,ensure_ascii=False),flush=True)
        if args.diagnose and report.get('error_code')=='GEMINI_HTTP_400':
            plain=plain_probe(provider)
            print(json.dumps({'plain_probe':plain,
                'comparison':('STRUCTURED_REQUEST_CONFIGURATION_DIFFERS' if plain['status']=='READY'
                              else 'PLAIN_REQUEST_ALSO_FAILED'),
                'structured_readiness_unchanged':True},ensure_ascii=False),flush=True)
        return 0 if report['status']=='READY' else 1
    finally:
        provider.close()


if __name__=='__main__':
    raise SystemExit(main())
