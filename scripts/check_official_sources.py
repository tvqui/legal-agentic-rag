"""Read public official pages and retain reproducible evidence, without approvals."""
import argparse,concurrent.futures,hashlib,html,json,re,time,urllib.request,urllib.parse
from datetime import datetime,timezone
from pathlib import Path


def allowed(url):
    parsed=urllib.parse.urlparse(url);host=(parsed.hostname or '').lower()
    return parsed.scheme=='https' and not parsed.username and not parsed.password and (
        host=='vbpl.vn' or host.endswith('.vbpl.vn') or host.endswith('.gov.vn')
        or host=='chinhphu.vn' or host.endswith('.chinhphu.vn'))


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not allowed(newurl):raise ValueError('Non-official redirect')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def check(row,output):
    url=row.get('source_url') or ''
    if url.startswith('http://'):url='https://'+url[7:]
    result={'document_id':row['document_id'],'document_number':row.get('document_number'),
        'requested_url':url,'checked_at':datetime.now(timezone.utc).isoformat(),
        'review_status':'DRAFT','human_approved':False}
    if not allowed(url):return {**result,'status':'MISSING_OR_NON_OFFICIAL_URL'}
    started=time.monotonic()
    try:
        opener=urllib.request.build_opener(OfficialRedirect())
        with opener.open(urllib.request.Request(url,headers={'User-Agent':'PhapDienAI-source-audit/1.0'}),timeout=10) as response:
            data=response.read(2*1024*1024+1)
            if len(data)>2*1024*1024:raise ValueError('Official page exceeds audit byte limit')
            final=response.geturl();content_type=response.headers.get('Content-Type','')
            if not allowed(final):raise ValueError('Non-official final URL')
        digest=hashlib.sha256(data).hexdigest()
        # Content-addressed filenames cannot escape the supplied output directory.
        suffix='.pdf' if data.startswith(b'%PDF-') else '.html'
        path=output/(digest+suffix);path.write_bytes(data)
        text=data.decode('utf-8',errors='replace')
        compact=re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',text))).upper()
        number=(row.get('document_number') or '').upper()
        identity=bool(number and number in compact)
        return {**result,'status':'IDENTIFIER_MATCH_CANDIDATE' if identity else 'IDENTITY_NOT_CONFIRMED',
            'http_fetch_status':'FETCHED','final_url':final,'content_type':content_type,
            'response_sha256':digest,'response_file':path.name,'bytes':len(data),
            'number_seen_in_page':identity,'elapsed_seconds':round(time.monotonic()-started,3),
            'note':'HTTP success and document-number occurrence are not legal identity/effectivity approval.'}
    except Exception as exc:
        return {**result,'status':'FETCH_FAILED','error_type':type(exc).__name__,
            'http_status':getattr(exc,'code',None),'elapsed_seconds':round(time.monotonic()-started,3)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    rows=[json.loads(s) for s in a.input.read_text(encoding='utf-8-sig').splitlines() if s.strip()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda row:check(row,a.output),rows))
    (a.output/'results.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in results),encoding='utf-8')
    from collections import Counter
    summary={'records':len(rows),'statuses':dict(Counter(r['status'] for r in results)),
        'number_seen':sum(r.get('number_seen_in_page',False) for r in results),'human_approvals_created':0}
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary))

if __name__=='__main__':main()
