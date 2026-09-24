from __future__ import annotations
import json, os, shutil, subprocess, sys, tempfile, hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any
import pymupdf as fitz
from bs4 import BeautifulSoup
from docx import Document
from .cleaning import clean_text, remove_repeated_page_lines
from .util import write_jsonl, stable_id

EXTRACTION_SCHEMA = 'page-v4-legal-markers'


def extract_pdf_native(path: Path) -> tuple[str, list[str]]:
    doc = fitz.open(path)
    pages = [page.get_text("text") or "" for page in doc]
    return "\n\n".join(pages), pages


@lru_cache(maxsize=2)
def _docling_converter(ocr_languages: tuple[str,...], use_gpu: bool):
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    except Exception as e:
        raise RuntimeError("Docling/OCR extras are not installed. Run RUN_0_SETUP_FULL.bat") from e
    opts = PdfPipelineOptions()
    opts.do_ocr = True
    opts.do_table_structure = False
    opts.generate_parsed_pages = True
    opts.ocr_options = EasyOcrOptions(lang=list(ocr_languages), use_gpu=use_gpu, force_full_page_ocr=True)
    # Docling's native parser cannot open its resources under accented Windows paths.
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(
        pipeline_options=opts, backend=PyPdfiumDocumentBackend)})
    return converter


def extract_pdf_docling(path: Path, ocr_languages: list[str], use_gpu: bool, page_number: int | None=None, layout_cache: Path | None=None, rotation: int=0) -> str:
    converter=_docling_converter(tuple(ocr_languages),use_gpu)
    # Docling/PyPdfium can fail to open resources from accented Windows paths.
    # Use an ASCII temporary path while preserving the original path as provenance.
    temporary_path = None
    source_path = path
    if rotation or any(ord(char) > 127 for char in str(path)):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            temporary_path = Path(handle.name)
        if rotation:
            if page_number is None: raise ValueError('Rotation requires a page number')
            with fitz.open(path) as original, fitz.open() as rotated:
                rotated.insert_pdf(original,from_page=page_number-1,to_page=page_number-1)
                rotated[0].set_rotation((rotated[0].rotation+rotation)%360)
                rotated.save(temporary_path)
        else:
            shutil.copyfile(path, temporary_path)
        source_path = temporary_path
    try:
        selected=1 if rotation else page_number
        result=converter.convert(source_path,**({'page_range':(selected,selected)} if selected else {}))
        from .ocr_serialization import conversion_text
        text, pages = conversion_text(result)
        if rotation:
            for page in pages: page.update(page=page_number,rotation=rotation)
        if layout_cache is not None:
            layout_cache.write_text(json.dumps({'schema':EXTRACTION_SCHEMA,'pages':pages},ensure_ascii=False),encoding='utf-8')
        return text
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def extract_pdf_pages(path: Path, row: dict, cfg: dict, output_dir: Path):
    from .page_reviews import reviewed_pages
    reviews=reviewed_pages(row,cfg)
    settings=cfg['extraction']; mode=str(settings.get('use_docling','auto')).lower()
    # Retry count controls the parent worker only; it must not invalidate OCR
    # page caches produced with otherwise identical extraction settings.
    cache_settings={key:value for key,value in settings.items() if key!='document_timeout_attempts'}
    if mode not in {'auto','always','never'}: raise ValueError('Invalid use_docling mode')
    threshold=int(settings.get('min_text_chars_before_ocr',1200)); pages=[]; provenance=[]
    cache=output_dir/'01_extracted'/'page_cache'; cache.mkdir(parents=True,exist_ok=True)
    with fitz.open(path) as pdf:
        if any(number>len(pdf) for number in reviews): raise ValueError('Reviewed page exceeds PDF page count')
        for i,page in enumerate(pdf):
            review=reviews.get(i+1,{})
            rotation=review.get('degrees',0) if review.get('action')=='ROTATE' else 0
            native=page.get_text('text') or ''; count=len(''.join(native.split()))
            images=page.get_image_info()
            image_area=max((fitz.Rect(image['bbox']).get_area() for image in images),default=0)
            coverage=image_area/max(page.rect.get_area(),1)
            blank=review.get('action')=='NO_BODY_TEXT' or (count==0 and not images and not page.get_drawings())
            bad_fraction=(native.count('\ufffd')+native.count('\x00'))/max(len(native),1)
            needs=not blank and (rotation or mode=='always' or count<40 or
                (count<threshold and coverage>.25) or (coverage>.6 and count<2000) or bad_fraction>.02)
            text=native; method='pymupdf'; error=None; status='NOT_NEEDED'
            key=stable_id(EXTRACTION_SCHEMA,row['sha256'],str(i+1),json.dumps(cache_settings,sort_keys=True),json.dumps(review,sort_keys=True),prefix='page')
            cached=cache/(key+'.json')
            if needs and mode!='never':
                try:
                    if cached.exists():
                        text=json.loads(cached.read_text(encoding='utf-8'))['text']; method='docling_easyocr_cached'
                    else:
                        text=extract_pdf_docling(path,settings.get('ocr_languages',['vi','en']),bool(settings.get('ocr_use_gpu',False)),i+1,layout_cache=cached.with_suffix('.layout.json'),rotation=rotation)
                        if not text.strip(): raise RuntimeError('OCR returned empty text')
                        temporary=cached.with_suffix('.tmp')
                        temporary.write_text(json.dumps({'text':text},ensure_ascii=False),encoding='utf-8'); os.replace(temporary,cached)
                        method='docling_easyocr'
                    status='COMPLETE'
                except Exception as exc:
                    error=str(exc); status='FAILED'; text=native
            elif needs: status='DISABLED'
            if review.get('action')=='NO_BODY_TEXT':
                text=''; method='reviewed_no_body_text'; status='REVIEWED_NO_BODY_TEXT'
            pages.append(text)
            provenance.append({'page':i+1,'method':method,'chars':len(text),'native_chars':count,
                'image_coverage':round(coverage,3),'bad_character_fraction':bad_fraction,'ocr':method.startswith('docling'),'ocr_status':status,
                'blank':blank,'error':error,'file_id':row['file_id'],'sha256':row['sha256'],'page_review':review})
    return pages,provenance


def extract_docx(path: Path) -> str:
    from docx.table import Table
    doc = Document(path)
    blocks: list[str] = []
    # Legal headers often live in a table. Appending all tables at the end
    # moved the document's own number/issuer out of the header search window.
    for block in doc.iter_inner_content():
        if isinstance(block,Table):
            for row in block.rows:
                blocks.append(" | ".join(cell.text.strip() for cell in row.cells))
        elif block.text.strip():
            blocks.append(block.text)
    return "\n".join(blocks)


def convert_legacy_doc(path: Path, cache_dir: Path) -> Path | None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / (path.stem + ".docx")
    if out.exists() and out.stat().st_size > 100:
        return out
    # Microsoft Word COM is the most reliable on the user's Windows environment.
    if sys.platform == "win32":
        try:
            import win32com.client  # type: ignore
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            doc = word.Documents.Open(str(path.resolve()))
            doc.SaveAs2(str(out.resolve()), FileFormat=16)  # wdFormatDocumentDefault (.docx)
            doc.Close(False)
            word.Quit()
            if out.exists(): return out
        except Exception:
            try:
                word.Quit()  # type: ignore[name-defined]
            except Exception:
                pass
    # LibreOffice fallback.
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        try:
            subprocess.run([soffice, "--headless", "--convert-to", "docx", "--outdir", str(cache_dir), str(path)],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
            if out.exists(): return out
        except Exception:
            pass
    # antiword fallback gives plain text; caller handles separately.
    return None


def extract_doc(path: Path, cache_dir: Path) -> tuple[str, str]:
    converted = convert_legacy_doc(path, cache_dir)
    if converted:
        return extract_docx(converted), "word_or_libreoffice_conversion"
    antiword = shutil.which("antiword")
    if antiword:
        proc = subprocess.run([antiword, str(path)], capture_output=True, timeout=120)
        for enc in ("utf-8", "cp1258", "latin-1"):
            try:
                return proc.stdout.decode(enc), "antiword"
            except Exception:
                continue
    raise RuntimeError("Cannot read legacy .doc. Install Microsoft Word, LibreOffice, or antiword.")


def extract_html(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        tag.decompose()
    return soup.get_text("\n")


def extract_one(row: dict, cfg: dict, output_dir: Path) -> dict:
    path = Path(row["path"])
    ext = path.suffix.lower()
    method = ""
    pages: list[str] = []
    needs_ocr = False
    error = None
    raw = ""
    page_provenance=[]
    text_source=None
    try:
        # A SHA-bound official attachment may replace a landing page or a scan
        # while the original corpus file remains the document identity.
        import yaml
        catalog=Path(cfg['project_root'])/'config/source_attachments.yaml'
        mapping=(yaml.safe_load(catalog.read_text(encoding='utf-8')) or {}).get('attachments',{}) if catalog.exists() else {}
        attachment=mapping.get(row['relative_path'])
        if attachment:
            expected_source_sha=attachment.get('source_sha256',attachment.get('html_sha256'))
            if expected_source_sha!=row['sha256']:
                raise ValueError('Source attachment mapping SHA mismatch')
            path=(Path(cfg['project_root'])/attachment['path']).resolve()
            allowed=(Path(cfg['project_root'])/'review/attachments').resolve()
            if not path.is_relative_to(allowed): raise ValueError('Attachment outside review/attachments')
            if path.suffix.lower()!='.pdf': raise ValueError('Full-text attachment must be a PDF')
            with path.open('rb') as stream:
                digest=hashlib.file_digest(stream,'sha256').hexdigest()
            if digest!=attachment['sha256']: raise ValueError('Full-text PDF SHA mismatch')
            text_source=dict(attachment); ext='.pdf'
        if ext == ".pdf":
            page_row={**row,'sha256':text_source['sha256']} if text_source else row
            pages,page_provenance=extract_pdf_pages(path,page_row,cfg,output_dir)
            method='hybrid_page_pdf'; needs_ocr=any(p['ocr_status'] in {'FAILED','DISABLED'} for p in page_provenance)
            if needs_ocr: error='One or more pages require OCR; see page_provenance.'
        elif ext == ".docx":
            raw = extract_docx(path); pages = [raw]; method = "python-docx"
        elif ext == ".doc":
            raw, method = extract_doc(path, output_dir / "01_extracted" / "converted_docx"); pages = [raw]
        elif ext in {".html", ".htm"}:
            raw = extract_html(path); pages = [raw]; method = "beautifulsoup"
        elif ext == ".txt":
            raw = path.read_text(encoding="utf-8", errors="ignore"); pages = [raw]; method = "text"
        elif ext == ".json":
            raw = json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False, indent=2); pages=[raw]; method="json"
        else:
            raise RuntimeError(f"Unsupported file type {ext}")
        if pages:
            pages = remove_repeated_page_lines(
                pages,
                float(cfg["cleaning"].get("repeated_line_page_ratio", .55)),
                int(cfg["cleaning"].get("repeated_line_max_chars", 120)),
            )
        cleaned_pages=[clean_text(p, cfg['cleaning'].get('unicode_form','NFC')) for p in pages]
        cleaned = '\n\n'.join(cleaned_pages) if pages else clean_text(raw,cfg['cleaning'].get('unicode_form','NFC'))
        offset=0
        for p,content in zip(page_provenance,cleaned_pages):
            p['text_start']=offset; p['text_end']=offset+len(content); p['cleaned_chars']=len(content); offset+=len(content)+2
    except Exception as e:
        cleaned = ""; error = str(e)
    out = {
        **row,
        "extraction_method": method,
        "text": cleaned,
        "text_chars": len(cleaned),
        "needs_ocr": needs_ocr,
        "extraction_error": error,
        'page_provenance':page_provenance,'page_count':len(page_provenance),'extraction_schema':EXTRACTION_SCHEMA,
        'text_source':text_source,
    }
    return out


def _load_extraction_catalogs(cfg: dict) -> tuple[dict, dict]:
    """Load the two SHA-bound catalogs once for document-cache checks."""
    import yaml
    config_dir=Path(cfg['project_root'])/'config'
    attachment_path=config_dir/'source_attachments.yaml'
    review_path=config_dir/'page_reviews.yaml'
    attachments=(yaml.safe_load(attachment_path.read_text(encoding='utf-8')) or {}).get('attachments',{}) if attachment_path.exists() else {}
    reviews=(yaml.safe_load(review_path.read_text(encoding='utf-8')) or {}).get('documents',{}) if review_path.exists() else {}
    return attachments,reviews


def _cache_matches_current_sources(result: dict, row: dict, attachments: dict, reviews: dict) -> bool:
    """Allow a checkpoint hit only when this document's bound inputs still match."""
    if result.get('extraction_schema')!=EXTRACTION_SCHEMA:
        return False
    if result.get('file_id')!=row.get('file_id') or result.get('sha256')!=row.get('sha256'):
        return False
    if result.get('extraction_error') or not result.get('text'):
        return False
    if any(page.get('ocr_status') in {'FAILED','DISABLED'} for page in result.get('page_provenance',[])):
        return False

    attachment=attachments.get(row.get('relative_path'))
    text_source=result.get('text_source')
    if bool(attachment)!=bool(text_source):
        return False
    if attachment:
        expected_source_sha=attachment.get('source_sha256',attachment.get('html_sha256'))
        if expected_source_sha!=row.get('sha256'):
            return False
        for field in ('path','sha256'):
            if attachment.get(field)!=text_source.get(field):
                return False

    review=reviews.get(row.get('relative_path'))
    expected_reviews=review.get('pages',{}) if review else {}
    expected_sha=attachment.get('sha256') if attachment else row.get('sha256')
    if review and review.get('sha256')!=expected_sha:
        return False
    cached_reviews={page.get('page_number',page.get('page')):page.get('page_review')
                    for page in result.get('page_provenance',[]) if page.get('page_review')}
    normalized_reviews={int(number):rule for number,rule in expected_reviews.items()}
    return cached_reviews==normalized_reviews


def extract_all(manifest: list[dict], cfg: dict, output_dir: Path) -> list[dict]:
    from tqdm import tqdm
    rows=[]
    timeout=float(cfg['extraction'].get('document_timeout_seconds',180))
    attempts=int(cfg['extraction'].get('document_timeout_attempts',1))
    if timeout<=0: raise ValueError('document_timeout_seconds must be positive')
    if attempts<1: raise ValueError('document_timeout_attempts must be at least 1')
    cache=output_dir/'01_extracted'/'document_cache'; cache.mkdir(parents=True,exist_ok=True)
    attachments,reviews=_load_extraction_catalogs(cfg)
    checkpoint_cache={}
    for cache_file in cache.glob('*.json'):
        try:
            candidate=json.loads(cache_file.read_text(encoding='utf-8'))
            identity=(candidate.get('file_id'),candidate.get('sha256'))
            checkpoint_cache.setdefault(identity,[]).append(candidate)
        except (OSError,ValueError,TypeError):
            # A corrupt cache entry is never trusted and will be regenerated.
            continue
    for row in tqdm(manifest,desc='Extract/Clean'):
        configs=[Path(cfg['project_root'])/'config'/name for name in ('source_attachments.yaml','page_reviews.yaml')]
        attachment_hash=':'.join(hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else '' for p in configs)
        # Worker retries do not change document content. Excluding only this
        # orchestration option preserves compatibility with v4 checkpoints.
        extraction_settings={key:value for key,value in cfg['extraction'].items() if key!='document_timeout_attempts'}
        key=stable_id(EXTRACTION_SCHEMA,row['file_id'],row['sha256'],attachment_hash,json.dumps({'extraction':extraction_settings,'cleaning':cfg['cleaning']},sort_keys=True),prefix='extract')
        cached=cache/(key+'.json')
        if cached.exists():
            result=json.loads(cached.read_text(encoding='utf-8'))
        else:
            result=next((candidate for candidate in checkpoint_cache.get((row.get('file_id'),row.get('sha256')),[])
                         if _cache_matches_current_sources(candidate,row,attachments,reviews)),None)
            if result is not None:
                # Materialize the current key so later runs avoid scanning legacy keys.
                cached.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
            else:
                with tempfile.TemporaryDirectory(dir=cache) as work:
                    request=Path(work)/'request.json'; response=Path(work)/'response.json'
                    request.write_text(json.dumps({'row':row,'cfg':cfg,'output_dir':str(output_dir),'response':str(response)},default=str),encoding='utf-8')
                    exc=None; result=None
                    for attempt in range(1,attempts+1):
                        try:
                            process=subprocess.run([sys.executable,'-m','vn_labor_offline.extraction_worker',str(request)],capture_output=True,timeout=timeout)
                            if process.returncode or not response.exists(): raise RuntimeError(process.stderr.decode('utf-8',errors='replace')[-1500:])
                            result=json.loads(response.read_text(encoding='utf-8'))
                            break
                        except (subprocess.TimeoutExpired,RuntimeError) as error:
                            exc=error
                            if attempt==attempts: break
                    if result is None:
                        result={**row,'text':'','text_chars':0,'needs_ocr':row['extension']=='.pdf','extraction_method':'failed_worker',
                            'page_provenance':[],'extraction_schema':EXTRACTION_SCHEMA,
                            'extraction_error':f'{type(exc).__name__} after {attempts} attempt(s): {exc}'}
            if not result.get('extraction_error') and not any(p.get('ocr_status')=='FAILED' for p in result.get('page_provenance',[])):
                cached.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
        rows.append(result)
        write_jsonl(output_dir/'01_extracted'/'documents.jsonl',rows)
    write_jsonl(output_dir / "01_extracted" / "documents.jsonl", rows)
    failures = [r for r in rows if r.get("extraction_error") or r.get("text_chars", 0) < 100]
    write_jsonl(output_dir / "reports" / "extraction_issues.jsonl", failures)
    return rows
