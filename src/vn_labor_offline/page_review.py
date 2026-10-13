"""CPU-only audit of every suspicious page against SHA-bound PDF images."""
from __future__ import annotations
import argparse, difflib, hashlib, html, json, re, zipfile
from collections import Counter
from pathlib import Path
from .page_quality import compare_native_ocr, text_layer_metrics
from .page_content import refresh_document_notes, validated_notes
from .util import write_jsonl


def source_path(document,root):
    attachment=document.get('text_source') or {}
    path=(root/attachment['path']).resolve() if attachment.get('path') else (root/'data'/document['relative_path']).resolve()
    allowed=(root/'review/attachments').resolve() if attachment else (root/'data').resolve()
    if not path.is_relative_to(allowed): raise ValueError('Source outside corpus/attachment root')
    expected=attachment.get('sha256',document['sha256'])
    with path.open('rb') as stream: actual=hashlib.file_digest(stream,'sha256').hexdigest()
    if actual!=expected: raise ValueError('Review source SHA mismatch')
    return path,actual


def audit_archive(archive:Path,root:Path,output:Path):
    import pymupdf
    output=output.resolve(); canonical=(root/'artifacts').resolve()
    if output==canonical or output in canonical.parents: raise ValueError('Use an isolated review output directory')
    output.mkdir(parents=True,exist_ok=True); previews=output/'images'; previews.mkdir(exist_ok=True)
    with archive.open('rb') as stream: archive_sha=hashlib.file_digest(stream,'sha256').hexdigest()
    selected_cache={}
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        if len(names)!=len(set(names)): raise ValueError('Duplicate ZIP entries')
        docs=[json.loads(l) for l in z.read('artifacts/01_extracted/documents.jsonl').splitlines() if l.strip()]
        for name in names:
            if '/page_cache/' not in name or not name.endswith('.json') or name.endswith('.layout.json'): continue
            try:
                text=json.loads(z.read(name)).get('text')
                if isinstance(text,str): selected_cache[hashlib.sha256(text.encode()).hexdigest()]=text
            except (ValueError,TypeError): pass
    rows=[]; source_errors=[]; all_notes=[]; sections=[]; expected=0
    for doc in docs:
        suspect=[p for p in doc.get('page_provenance',[]) if p.get('page_quality_status') in {'REVIEW_REQUIRED','ERROR'}]
        expected+=len(suspect)
        if not doc.get('page_provenance'): continue
        try: path,source_sha=source_path(doc,root)
        except (OSError,ValueError) as exc:
            source_errors.append({'file_id':doc['file_id'],'relative_path':doc['relative_path'],'reason':type(exc).__name__})
            continue
        if doc.get('page_content_schema')!='page-content-v1': refresh_document_notes(doc,path)
        all_notes.extend({**n,'file_id':doc['file_id'],'relative_path':doc['relative_path']} for n in validated_notes(doc))
        print('PAGE_REVIEW '+json.dumps({'file_id':doc['file_id'],'suspicious_pages':len(suspect),'audited_so_far':len(rows)},ensure_ascii=False),flush=True)
        with pymupdf.open(path) as pdf:
            for p in suspect:
                page=pdf[p['page']-1]; native=page.get_text('text') or ''
                native_sha=hashlib.sha256(native.encode()).hexdigest()
                selected=p.get('selected_text')
                if not isinstance(selected,str): selected=selected_cache.get(p.get('selected_text_sha256'))
                if selected is None and native_sha==p.get('selected_text_sha256'): selected=native
                raw_available=selected is not None
                cleaned=doc['text'][p['text_start']:p['text_end']]
                compared=selected if raw_available else cleaned
                agreement=compare_native_ocr(native,compared)
                native_quality=text_layer_metrics(native); chosen_quality=text_layer_metrics(compared)
                numbers_native=Counter(re.findall(r'\d+(?:[.,/]\d+)*',native))
                numbers_selected=Counter(re.findall(r'\d+(?:[.,/]\d+)*',compared))
                numeric_diff={'native_only':dict(numbers_native-numbers_selected),'selected_only':dict(numbers_selected-numbers_native)}
                native_abnormal=any(native_quality[k]>threshold for k,threshold in
                    [('replacement_fraction',.02),('control_fraction',.01),('dominant_character_fraction',.35)]) or native_quality['alnum_fraction']<.45
                if 'PAGE_NUMBER_ONLY_REMOVED' in p.get('quality_reason_codes',[]): finding='PAGINATION_ONLY_GEOMETRY_EVIDENCE'
                elif ('Email:' in native and re.search(r'(?:Ký bởi|Người ký|Thời gian ký)',native) and
                        not re.search(r'Điều\s+\d',native) and len(native)<600): finding='SIGNATURE_ONLY_NATIVE_LAYER_OCR_REVIEW'
                elif native_abnormal: finding='ABNORMAL_NATIVE_LAYER_COMPARE_WITH_IMAGE'
                elif numbers_native!=numbers_selected: finding='NUMERIC_DIFFERENCE_COMPARE_WITH_IMAGE'
                elif agreement['token_dice']<.35: finding='LOW_TEXT_AGREEMENT_COMPARE_WITH_IMAGE'
                else: finding='CONTENT_OR_LAYOUT_REVIEW_REQUIRED'
                name=f"{doc['file_id']}_p{p['page']:04d}.png"; destination=previews/name
                page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5),alpha=False).save(destination)
                diff='\n'.join(difflib.unified_diff(native.splitlines(),compared.splitlines(),fromfile='native',tofile='selected',lineterm=''))
                row={'schema':'page-review-evidence-v1','file_id':doc['file_id'],'relative_path':doc['relative_path'],
                    'page':p['page'],'source_sha256':source_sha,'input_archive_sha256':archive_sha,
                    'original_status':p.get('page_quality_status'),'review_status':'REVIEW_REQUIRED',
                    'reason_codes':p.get('quality_reason_codes',[]),'finding':finding,
                    'native_text':native,'selected_text':selected,'cleaned_text':cleaned,
                    'raw_selected_available':raw_available,'comparison_target':'RAW_SELECTED' if raw_available else 'CLEANED_SELECTED',
                    'native_metrics':native_quality,'selected_metrics':chosen_quality,'agreement':agreement,
                    'numeric_difference':numeric_diff,'text_diff':diff,'preview_path':'images/'+name,
                    'page_notes':[n for n in validated_notes(doc) if n['page']==p['page']],
                    'reviewer':None,'reviewed_at':None}
                rows.append(row)
                title=html.escape(f"{doc['relative_path']} — trang {p['page']} — {finding}")
                sections.append(f'<article><h2>{title}</h2><p>Chờ duyệt; SHA {source_sha}. Raw selected: {raw_available}</p>'
                    f'<img loading="lazy" src="images/{name}" alt="Trang nguồn">'
                    f'<details><summary>Native / selected / cleaned và khác biệt</summary><div class="columns">'
                    f'<pre>{html.escape(native)}</pre><pre>{html.escape(compared)}</pre><pre>{html.escape(cleaned)}</pre></div>'
                    f'<pre>{html.escape(diff)}</pre></details></article>')
    write_jsonl(output/'page_review_evidence.jsonl',rows)
    write_jsonl(output/'footnote_evidence.jsonl',all_notes)
    write_jsonl(output/'documents_with_annotations.jsonl',docs)
    summary={'schema_version':1,'input_archive_sha256':archive_sha,'expected_suspicious_pages':expected,
        'audited_pages':len(rows),'source_errors':source_errors,'raw_selected_available':sum(r['raw_selected_available'] for r in rows),
        'finding_counts':dict(Counter(r['finding'] for r in rows)),'geometry_aligned_footnotes':len(all_notes),
        'auto_approved_pages':0,'complete_evidence_audit':len(rows)==expected and not source_errors,
        'note':'This proves audit coverage and source identity, not human legal/OCR approval.'}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'index.html').write_text('<!doctype html><html lang="vi"><meta charset="utf-8"><title>Đối chiếu trang nguồn</title>'
        '<style>body{font-family:Arial;margin:24px}article{border-bottom:2px solid #ddd;padding:20px 0}img{max-width:650px;width:100%}'
        '.columns{display:flex;gap:15px}.columns pre{flex:1;min-width:0}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
        '<h1>Bộ đối chiếu các trang cần kiểm tra</h1><p>Mọi trang vẫn REVIEW_REQUIRED. Không có approval tự động.</p>'
        +''.join(sections)+'</html>',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--root',type=Path,default=Path.cwd())
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); result=audit_archive(args.archive,args.root.resolve(),args.output)
    return 0 if result['complete_evidence_audit'] else 1


if __name__=='__main__': raise SystemExit(main())
