from __future__ import annotations

import json
from urllib.parse import urlencode,urlparse
from urllib.request import Request,urlopen


class SearxngDiscovery:
    """Bounded, opt-in SearXNG client used only to discover candidates.

    Search results never become approved sources. Every returned URL still has
    to pass the provider registry, identity, binary and SHA checks.
    """

    def __init__(self, endpoint: str, *, network:bool=False, transport=None,
                 timeout:float=15,max_results:int=10):
        self.endpoint=endpoint.rstrip('/')
        if urlparse(self.endpoint).scheme!='https': raise ValueError('SEARXNG_HTTPS_REQUIRED')
        self.network=network; self.transport=transport; self.timeout=timeout
        self.max_results=max(1,min(int(max_results),20))

    def search(self, query: str) -> list[dict]:
        if not query.strip(): return []
        if not self.network and self.transport is None:
            raise RuntimeError('SEARXNG_NETWORK_DISABLED')
        url=f"{self.endpoint}/search?{urlencode({'q':query,'format':'json','categories':'general'})}"
        if self.transport is not None:
            payload=self.transport(url,self.timeout)
        else:
            request=Request(url,headers={'Accept':'application/json','User-Agent':'vn-labor-source-resolver/1.0'})
            with urlopen(request,timeout=self.timeout) as response:
                payload=response.read()
        if isinstance(payload,(bytes,bytearray)): payload=json.loads(payload.decode('utf-8'))
        if isinstance(payload,str): payload=json.loads(payload)
        results=[]; seen=set()
        for row in payload.get('results',[]) if isinstance(payload,dict) else []:
            target=str(row.get('url') or '').strip()
            if not target.startswith('https://') or target in seen: continue
            seen.add(target); results.append({'url':target,'title':str(row.get('title') or ''),
              'content':str(row.get('content') or ''),'source':'SEARXNG_CANDIDATE'})
            if len(results)>=self.max_results: break
        return results
