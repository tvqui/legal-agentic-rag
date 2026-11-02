"""Export/edit/import source URLs through a SHA-bound Excel workbook.

Requires openpyxl (pip install -e ".[review]"). No network calls, artifact
mutation, legal approvals, PDF replacement or deletion of blank URLs.
"""
from __future__ import annotations
import argparse,copy,csv,hashlib,json,re,os,ipaddress,uuid,zipfile
from datetime import datetime,timezone,timedelta
from pathlib import Path,PurePosixPath
from urllib.parse import urlsplit
import yaml

VERSION='source-links-v1'
CONFIRMED='DA_DOI_CHIEU'
HEADERS=['STT','Số / ký hiệu','Tên văn bản / bản án','Nhóm dữ liệu','Link trang hiện tại (cấu hình)',
         'LINK TRANG VĂN BẢN MỚI — ĐIỀN Ở ĐÂY','Xác nhận đúng văn bản','Ghi chú của bạn',
         'Link gợi ý — CHƯA xác minh','File dữ liệu gốc','Mã hồ sơ']
DOWNLOAD_HEADERS=['STT','Số / ký hiệu','Tài liệu','Link tải hiện tại',
                  'LINK TẢI MỚI — KHÔNG BẮT BUỘC','Xác nhận đúng văn bản','Ghi chú','File dữ liệu gốc','Mã hồ sơ']
CONFIGS=['source_catalog.yaml','source_attachments.yaml','metadata_overrides.yaml']
GROUP_LABELS={'LEGAL_DOCUMENT':'Văn bản pháp luật','CONSOLIDATED':'Văn bản hợp nhất',
              'JUDICIAL':'Bản án / án lệ','SUPPLEMENTARY':'Tài liệu bổ sung'}

def digest(data):return hashlib.sha256(data).hexdigest()
def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,default=str)
def rows(z,name):return [json.loads(s) for s in z.read(name).decode('utf-8-sig').splitlines() if s.strip()]
def config(root,name):
    path=Path(root)/'config'/name
    return yaml.safe_load(path.read_text(encoding='utf-8')) or {} if path.exists() else {}
def corpus_file(root,relative):
    part=PurePosixPath(relative)
    if part.is_absolute() or '..' in part.parts or '\\' in relative or ':' in relative:raise ValueError('Unsafe source path')
    allowed=(Path(root)/'data').resolve();path=(allowed/relative).resolve()
    if not path.is_relative_to(allowed) or not path.is_file():raise ValueError('Source file missing/outside corpus: '+relative)
    return path
def check_attachment(root,spec):
    allowed=(Path(root)/'review/attachments').resolve()
    path=(Path(root)/spec.get('path','')).resolve()
    if not path.is_relative_to(allowed) or not path.is_file() or sha(path)!=spec.get('sha256'):
        raise ValueError('PDF đính kèm thiếu/khác SHA: '+str(spec.get('path')))
def url(value):
    value=str(value or '').strip()
    if not value or any(c.isspace() for c in value):raise ValueError('URL trống hoặc chứa khoảng trắng')
    p=urlsplit(value)
    if p.scheme not in {'http','https'} or not p.hostname or p.username or p.password:raise ValueError('Cần URL http/https, không có tài khoản/mật khẩu')
    if p.hostname.lower()=='localhost' or p.hostname.lower().endswith('.local'):raise ValueError('Không dùng URL nội bộ')
    try:
        if not ipaddress.ip_address(p.hostname).is_global:raise ValueError('Không dùng địa chỉ IP nội bộ')
    except ValueError as exc:
        if 'địa chỉ IP' in str(exc):raise
    return value

def export_book(root,artifact,output,seed=None):
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill,Alignment,Protection
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.comments import Comment
    from openpyxl.formatting.rule import FormulaRule
    root=Path(root);output=Path(output)
    if output.exists():raise FileExistsError('Không ghi đè Excel đã điền: '+str(output))
    catalog=config(root,'source_catalog.yaml').get('sources',{})
    attachments=config(root,'source_attachments.yaml').get('attachments',{})
    with zipfile.ZipFile(artifact) as z:
        manifest=rows(z,'artifacts/00_manifest/files.jsonl');registry=rows(z,'artifacts/02_registry/documents.jsonl')
        provisions=rows(z,'artifacts/03_structure/provisions.jsonl')
    docs={r['file_id']:r for r in registry};counts={}
    for p in provisions:counts[p['document_id']]=counts.get(p['document_id'],0)+1
    suggestions={}
    if seed and Path(seed).exists():
        with Path(seed).open(encoding='utf-8-sig',newline='') as stream:
            suggestions={r.get('corpus_sha256'):r for r in csv.DictReader(stream)}
    records=[]
    for item in manifest:
        relative=item['relative_path'];d=docs.get(item['file_id'],{})
        if sha(corpus_file(root,relative))!=item['sha256']:raise ValueError('Corpus khác artifact: '+relative)
        key=relative if relative in catalog else Path(relative).name if Path(relative).name in catalog else None
        c=catalog.get(key,{})
        if c.get('sha256') and c['sha256']!=item['sha256']:raise ValueError('Catalog SHA mismatch: '+relative)
        candidate=suggestions.get(item['sha256'],{})
        suggested=candidate.get('exact_source_url') or candidate.get('current_candidate_url') or d.get('source_url') or ''
        number=c.get('document_number') or d.get('document_number') or d.get('case_number') or c.get('instrument_number') or ''
        records.append({'id':digest((relative+'\0'+item['sha256']).encode())[:24],
            'relative_path':relative,'sha256':item['sha256'],'catalog_key':key,
            'catalog_url':c.get('source_url') or '', 'catalog_url_raw':c.get('source_url'),
            'artifact_url':d.get('source_url') or '', 'number':number,
            'title':c.get('title') or d.get('title') or item.get('filename'),
            'group':item.get('source_group',''),'document_id':d.get('document_id'),
            'issuer':c.get('issuer') or d.get('issuer') or '',
            'promulgated_date':str(c.get('promulgated_date') or d.get('promulgated_date') or ''),
            'effective_from':str(c.get('effective_from') or d.get('effective_from') or ''),
            'effective_to':str(c.get('effective_to') or d.get('effective_to') or ''),
            'legal_status':c.get('legal_status') or d.get('legal_status') or '',
            'provisions':counts.get(d.get('document_id'),0),'suggestion':suggested,
            'attachment':copy.deepcopy(attachments.get(relative))})
    records.sort(key=lambda r:(bool(r['catalog_url']),r['group'],r['relative_path']))
    wb=Workbook();guide=wb.active;guide.title='HUONG_DAN'
    main=wb.create_sheet('DIEN_LINK_MOI');download=wb.create_sheet('LINK_TAI_FILE');info=wb.create_sheet('THONG_TIN_DATA')
    meta=wb.create_sheet('_BASELINE')
    body=[
        ('MỤC ĐÍCH','Điền link chính xác cho các tài liệu trước khi chốt build OFFLINE. Không cần sửa YAML bằng tay.'),
        ('1. Điền link','Mở DIEN_LINK_MOI. Điền cột F (ô vàng). Link phải trỏ đúng văn bản và phiên bản, không phải trang chủ hoặc kết quả tìm kiếm.'),
        ('2. Xác nhận','Sau khi đối chiếu số/ký hiệu và nội dung, chọn DA_DOI_CHIEU ở cột G. Chưa chắc thì chọn CHUA_DOI_CHIEU và ghi chú.'),
        ('Giữ link cũ','Để trống link mới = giữ nguyên. Không cần chép lại link cũ. Không xóa, thêm dòng hoặc sửa cột xám.'),
        ('Link tải PDF','Chỉ điền LINK_TAI_FILE nếu muốn đổi URL tải file đính kèm. Mỗi URL một dòng. Đổi link không thay file PDF hay SHA của nó.'),
        ('Link gợi ý','Cột I là ứng viên từ dữ liệu cũ, CHƯA được xác minh. Không tự động dùng những link này.'),
        ('Metadata','THONG_TIN_DATA chứa file, SHA, ngày/hiệu lực theo metadata, link artifact cũ và các thông tin nhận diện. Không phải xác nhận pháp lý.'),
        ('Sau khi điền','Lưu thành một file .xlsx mới rồi gửi lại. Có thể dùng lệnh import trong docs/offline/source-links-workbook.md để xem diff/apply.'),
        ('Tác động OFFLINE','Áp dụng Excel cập nhật cấu hình, chưa sửa ZIP đang chạy. Phải đóng gói code lại và rebuild metadata/graph/index liên quan; AI-resume giữ artifact cũ sẽ không tự đổi link.'),
        ('Kiểm chứng','Công cụ không tải link, không sửa nội dung luật/ngày hiệu lực và không tự tạo human legal approval.'),
        ('Nếu PDF đổi','Nếu thay nội dung/PDF hoặc corpus build khác: xuất Excel mới và kiểm lại. Không sửa SHA trong file này.'),
        ('Tổng tài liệu',len(records)),('Nguồn hiện có link',sum(bool(r['catalog_url']) for r in records)),
        ('Tệp có PDF đính kèm',sum(bool(r['attachment']) for r in records)),
        ('Artifact gốc',str(Path(artifact).resolve())),('SHA artifact',sha(artifact)),
        ('Phiên bản biểu mẫu',VERSION),('Ngày tạo (Việt Nam)',datetime.now(timezone(timedelta(hours=7))).isoformat(timespec='seconds'))]
    guide.append(['HƯỚNG DẪN CẬP NHẬT LINK NGUỒN — PHÁP ĐIỂN AI',''])
    for label,text in body:guide.append([label,text])
    guide.column_dimensions['A'].width=28;guide.column_dimensions['B'].width=115
    for row in guide:
        for cell in row:cell.alignment=Alignment(vertical='top',wrap_text=True)
        guide.row_dimensions[row[0].row].height=45 if row[0].row!=1 else 32
        row[0].font=Font(name='Calibri',bold=True,color='153B50')
    guide.merge_cells('A1:B1');guide['A1'].font=Font(name='Calibri',size=15,bold=True,color='FFFFFF')
    guide['A1'].fill=PatternFill('solid',fgColor='153B50');guide.freeze_panes='B2';guide.sheet_view.showGridLines=False
    def sheet(ws,headers,widths,editable):
        ws.append([ws.title.replace('_',' ')]);ws.append(['Chỉ điền ô vàng. Link trống = giữ nguyên; DA_DOI_CHIEU chỉ xác nhận link, không duyệt pháp lý.']);ws.append([]);ws.append(headers)
        ws.merge_cells(start_row=1,start_column=1,end_row=1,end_column=len(headers)-1)
        ws.merge_cells(start_row=2,start_column=1,end_row=2,end_column=len(headers)-1)
        for i,width in enumerate(widths,1):ws.column_dimensions[__import__('openpyxl').utils.get_column_letter(i)].width=width
        ws.freeze_panes='E5';ws.sheet_view.showGridLines=False
        for row in (1,2,4):
            ws.row_dimensions[row].height=32
            for cell in ws[row]:
                cell.fill=PatternFill('solid',fgColor='153B50' if row!=2 else 'DCEAF2')
                cell.font=Font(name='Calibri',bold=True,color='FFFFFF' if row!=2 else '153B50',size=12 if row==1 else 11)
                cell.alignment=Alignment(wrap_text=True,vertical='center')
        ws.sheet_properties.pageSetUpPr.fitToPage=True
        ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3
        ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0;ws.print_title_rows='1:4'
    sheet(main,HEADERS,[6,25,54,20,46,56,24,42,46,48,28],[6,7,8])
    for index,r in enumerate(records,1):
        main.append([index,r['number'],r['title'],GROUP_LABELS.get(r['group'],r['group']),r['catalog_url'],'','CHUA_DOI_CHIEU','',r['suggestion'],r['relative_path'],r['id']])
    attached=[r for r in records if r['attachment']]
    sheet(download,DOWNLOAD_HEADERS,[6,25,54,64,64,24,42,50,28],[5,6,7])
    for index,r in enumerate(attached,1):
        spec=r['attachment'];links=spec.get('download_urls') or [spec.get('download_url','')]
        download.append([index,r['number'],r['title'],'\n'.join(links),'','CHUA_DOI_CHIEU','',r['relative_path'],r['id']])
    info_headers=['Mã hồ sơ','File gốc','SHA-256 file gốc','Số / ký hiệu','Tên','Nhóm','Cơ quan ban hành','Ngày ban hành theo metadata',
        'Hiệu lực từ theo metadata','Hiệu lực đến theo metadata','Trạng thái theo metadata','Số đơn vị điều khoản trong build','Link đang lưu trong artifact','Link cấu hình hiện tại','PDF dùng làm nguồn text','SHA PDF đính kèm']
    sheet(info,info_headers,[28,55,70,26,58,22,35,23,23,23,25,22,60,60,55,70],[])
    for r in records:
        a=r['attachment'] or {}
        info.append([r['id'],r['relative_path'],r['sha256'],r['number'],r['title'],GROUP_LABELS.get(r['group'],r['group']),r['issuer'],r['promulgated_date'],
            r['effective_from'],r['effective_to'],r['legal_status'],r['provisions'],r['artifact_url'],r['catalog_url'],a.get('path',''),a.get('sha256','')])
    for ws,editable,decision,last_key in [(main,{6,7,8},7,11),(download,{5,6,7},6,9),(info,set(),None,None)]:
        for row in ws.iter_rows(min_row=5):
            ws.row_dimensions[row[0].row].height=62
            for c in row:
                if isinstance(c.value,str):c.data_type='s'  # Never create executable formulas from document titles/URLs.
                c.font=Font(name='Calibri',size=11,color='143340')
                c.alignment=Alignment(wrap_text=True,vertical='top')
                c.fill=PatternFill('solid',fgColor='FFF2CC' if c.column in editable else ('F0F4F7' if c.row%2 else 'FFFFFF'))
                c.protection=Protection(locked=c.column not in editable)
                if c.column not in editable and isinstance(c.value,str) and c.value.startswith(('https://','http://')) and '\n' not in c.value:
                    c.hyperlink=c.value;c.font=Font(name='Calibri',size=11,color='0563C1',underline='single')
        ws.auto_filter.ref=f'A4:{__import__("openpyxl").utils.get_column_letter(ws.max_column)}{ws.max_row}'
        ws.protection.sheet=True;ws.protection.autoFilter=False;ws.protection.sort=False
        if last_key:ws.column_dimensions[__import__('openpyxl').utils.get_column_letter(last_key)].hidden=True
        if decision:
            dv=DataValidation(type='list',formula1='"CHUA_DOI_CHIEU,DA_DOI_CHIEU,KHONG_KHOP"');dv.errorTitle='Chọn trạng thái trong danh sách';dv.error='Chỉ dùng ba giá trị có sẵn.';dv.showErrorMessage=True
            ws.add_data_validation(dv);dv.add(f'{__import__("openpyxl").utils.get_column_letter(decision)}5:{__import__("openpyxl").utils.get_column_letter(decision)}{max(5,ws.max_row)}')
    main['F4'].comment=Comment('Chỉ dán URL trang mô tả/toàn văn chính xác. Không nhập link trang chủ, API key hoặc token.','Pháp Điển AI')
    main.conditional_formatting.add(f'F5:G{main.max_row}',FormulaRule(formula=['AND($F5<>"",$G5="DA_DOI_CHIEU")'],fill=PatternFill('solid',fgColor='DDF0DF')))
    metadata={'schema':VERSION,'artifact_sha256':sha(artifact),'records':records}
    meta.append(['metadata',encode({'schema':VERSION,'artifact_sha256':metadata['artifact_sha256'],'records_sha256':digest(encode(records).encode())})])
    for r in records:meta.append([r['id'],encode(r)])
    meta.sheet_state='veryHidden'
    output.parent.mkdir(parents=True,exist_ok=True);wb.save(output);wb.close()
    return {'workbook':str(output),'documents':len(records),'attachment_records':len(attached),'changed_configs':0}


def import_book(root,artifact,workbook,output,apply=False):
    from openpyxl import load_workbook
    root=Path(root).resolve();output=Path(output)
    with zipfile.ZipFile(workbook) as z:
        if len(z.infolist())>200 or sum(i.file_size for i in z.infolist())>25*1024**2:raise ValueError('Excel quá lớn')
        if any(n.lower().endswith('vbaproject.bin') for n in z.namelist()):raise ValueError('Không nhận Excel có macro')
    wb=load_workbook(workbook,data_only=False,keep_links=False)
    try:
        meta=wb['_BASELINE'];header=json.loads(meta.cell(1,2).value)
        records=[json.loads(row[1]) for row in meta.iter_rows(min_row=2,values_only=True) if row[1]]
        if header.get('schema')!=VERSION or digest(encode(records).encode())!=header.get('records_sha256'):raise ValueError('Sai phiên bản/baseline Excel')
        if sha(artifact)!=header['artifact_sha256']:raise ValueError('Artifact đã đổi: hãy xuất Excel mới cho đúng build')
        by_id={r['id']:r for r in records}
        if len(by_id)!=len(records):raise ValueError('Trùng hồ sơ baseline')
        with zipfile.ZipFile(artifact) as z:manifest={r['relative_path']:r for r in rows(z,'artifacts/00_manifest/files.jsonl')}
        if set(manifest)!={r['relative_path'] for r in records}:raise ValueError('Excel không bao phủ đúng manifest')
        for r in records:
            if manifest[r['relative_path']]['sha256']!=r['sha256']:raise ValueError('SHA baseline khác artifact')
        current={name:config(root,name) for name in CONFIGS}
        proposed=copy.deepcopy(current);changes=[];warnings=[];seen=set();target_urls={}
        provider_cfg=config(root,'source_provider_registry.yaml').get('providers',[])
        def provider_for(link):
            host=urlsplit(link).hostname.lower()
            return next((p['id'] for p in provider_cfg if any(host==d or host.endswith('.'+d) for d in p['allowed_domains'])),None)
        def cells(ws,row):
            values=[]
            for cell in ws[row]:
                if cell.data_type=='f':raise ValueError(f'Không dùng công thức ở {ws.title}!{cell.coordinate}')
                values.append(str(cell.value or '').strip())
            return values
        main=wb['DIEN_LINK_MOI']
        for number in range(5,main.max_row+1):
            v=cells(main,number)
            if not any(v):continue
            if len(v)<11 or v[10] not in by_id or v[10] in seen:raise ValueError('Thiếu/trùng mã hồ sơ ở dòng '+str(number))
            seen.add(v[10]);r=by_id[v[10]]
            expected_labels=[str(r['number'] or '').strip(),str(r['title'] or '').strip(),GROUP_LABELS.get(r['group'],r['group']),r['catalog_url']]
            if v[1:5]!=expected_labels or v[9]!=r['relative_path']:
                raise ValueError('Cột nhận diện bị sửa/sắp xếp lệch ở dòng '+str(number))
            if not v[5]:continue
            if v[6]!=CONFIRMED:
                warnings.append({'path':r['relative_path'],'reason':'NEW_LINK_NOT_CONFIRMED_NOT_APPLIED'});continue
            new=url(v[5]);key=r['catalog_key'] or r['relative_path']
            live=current['source_catalog.yaml'].get('sources',{}).get(key,{})
            if (live.get('source_url') or '')!=r['catalog_url']:raise ValueError('Link cấu hình đã đổi sau lúc xuất Excel: '+r['relative_path'])
            if sha(corpus_file(root,r['relative_path']))!=r['sha256'] or live.get('sha256',r['sha256'])!=r['sha256']:
                raise ValueError('File nguồn đã đổi: '+r['relative_path'])
            if key in target_urls and target_urls[key]!=new:raise ValueError('Hai dòng cập nhật khác nhau cho cùng catalog key')
            target_urls[key]=new
            if new==r['catalog_url']:continue
            entry=proposed['source_catalog.yaml'].setdefault('sources',{}).setdefault(key,{})
            entry.update(sha256=r['sha256'],source_url=new,source_provider=provider_for(new),official_source=False)
            for field in ('collected_at','reviewer','reviewed_at','review_evidence'):entry.pop(field,None)
            # Never reuse an old source's human approval for a new URL.
            for field in ('legal_reviewer','legal_reviewed_at','legal_review_evidence'):entry.pop(field,None)
            if r['attachment'] is not None:
                if encode(current['source_attachments.yaml'].get('attachments',{}).get(r['relative_path']))!=encode(r['attachment']):
                    raise ValueError('Attachment config đã đổi: '+r['relative_path'])
                check_attachment(root,r['attachment'])
                proposed['source_attachments.yaml']['attachments'][r['relative_path']]['source_url']=new
            changes.append({'kind':'SOURCE_PAGE','relative_path':r['relative_path'],'old_url':r['catalog_url'],
                'new_url':new,'note':v[7],'legal_approval_created':False})
            if not provider_for(new):warnings.append({'path':r['relative_path'],'reason':'PROVIDER_NOT_REGISTERED'})
        if seen!=set(by_id):raise ValueError('Excel bị thiếu dòng: cần giữ đầy đủ danh sách')
        seen_download=set();download=wb['LINK_TAI_FILE'];expected={r['id'] for r in records if r['attachment']}
        for number in range(5,download.max_row+1):
            v=cells(download,number)
            if not any(v):continue
            if len(v)<9 or v[8] not in expected or v[8] in seen_download:raise ValueError('Sai/trùng dòng PDF đính kèm')
            seen_download.add(v[8]);r=by_id[v[8]];spec=r['attachment']
            if v[1]!=str(r['number']) or v[7]!=r['relative_path']:raise ValueError('Nhận diện PDF bị thay đổi')
            if not v[4]:continue
            if v[5]!=CONFIRMED:warnings.append({'path':r['relative_path'],'reason':'DOWNLOAD_NOT_CONFIRMED_NOT_APPLIED'});continue
            links=[url(s) for s in v[4].splitlines() if s.strip()]
            if not 1<=len(links)<=10 or len(links)!=len(set(links)):raise ValueError('Cần 1–10 link tải khác nhau, mỗi link một dòng')
            if encode(current['source_attachments.yaml'].get('attachments',{}).get(r['relative_path']))!=encode(spec):raise ValueError('Attachment config đã đổi')
            old=spec.get('download_urls') or [spec.get('download_url','')]
            if old==links:continue
            if sha(corpus_file(root,r['relative_path']))!=r['sha256']:raise ValueError('File nguồn đã đổi')
            check_attachment(root,spec)
            entry=proposed['source_attachments.yaml']['attachments'][r['relative_path']]
            entry.pop('download_urls',None);entry.pop('download_url',None)
            entry['download_url' if len(links)==1 else 'download_urls']=links[0] if len(links)==1 else links
            changes.append({'kind':'ATTACHMENT_DOWNLOAD','relative_path':r['relative_path'],'old_urls':old,
                'new_urls':links,'note':v[6],'binary_replaced':False,'sha_replaced':False})
        if seen_download!=expected:raise ValueError('Excel thiếu dòng PDF đính kèm')
    finally:wb.close()
    files={name:yaml.safe_dump(value,allow_unicode=True,sort_keys=False).encode('utf-8') for name,value in proposed.items() if value!=current[name]}
    if output.exists():raise FileExistsError('Chọn thư mục output mới để giữ lịch sử')
    output.mkdir(parents=True)
    original={name:(root/'config'/name).read_bytes() for name in files}
    for name,data in original.items():(output/('before_'+name)).write_bytes(data)
    for name,data in files.items():(output/name).write_bytes(data)
    import difflib
    diff=''.join(''.join(difflib.unified_diff(original[name].decode('utf-8').splitlines(True),data.decode('utf-8').splitlines(True),fromfile='before/'+name,tofile='after/'+name)) for name,data in files.items())
    (output/'changes.diff').write_text(diff,encoding='utf-8')
    report={'schema':VERSION,'changes':changes,'warnings':warnings,'config_files':list(files),
        'applied':False,'artifact_modified':False,'human_legal_approvals_created':0}
    if apply:
        for name,data in original.items():
            if (root/'config'/name).read_bytes()!=data:raise ValueError('Concurrent config edit: '+name)
        written=[]
        try:
            for name,data in files.items():
                target=root/'config'/name;temp=target.with_name(target.name+'.links_'+uuid.uuid4().hex+'.tmp')
                temp.write_bytes(data);os.replace(temp,target);written.append(name)
        except BaseException:
            for name in written:
                target=root/'config'/name;temp=target.with_name(target.name+'.restore_'+uuid.uuid4().hex+'.tmp')
                temp.write_bytes(original[name]);os.replace(temp,target)
            raise
        report['applied']=True
    (output/'import_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def main():
    try:import openpyxl
    except ModuleNotFoundError:raise SystemExit('Cài thư viện Excel một lần: python -m pip install -e ".[review]"')
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for name in ('export','import'):
        c=sub.add_parser(name);c.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);c.add_argument('--artifact',type=Path,required=True);c.add_argument('--output',type=Path,required=True)
        if name=='export':c.add_argument('--seed',type=Path)
        else:c.add_argument('--workbook',type=Path,required=True);c.add_argument('--apply',action='store_true')
    a=p.parse_args()
    result=export_book(a.root,a.artifact,a.output,a.seed) if a.command=='export' else import_book(a.root,a.artifact,a.workbook,a.output,a.apply)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
