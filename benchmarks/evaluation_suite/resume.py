"""Restore a benchmark run archive without accepting executable instructions."""
from pathlib import Path,PurePosixPath
import json,zipfile,stat,shutil

def restore(archive,target):
    archive=Path(archive);target=Path(target)
    if target.exists():raise FileExistsError('Use a new restore directory')
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        required={'run_info.json','settings_resolved.json','state.json','source_manifest.json','protocol.json'}
        if not required.issubset(names):raise ValueError('Not a v2 evaluation archive')
        seen=set();size=0
        for info in z.infolist():
            p=PurePosixPath(info.filename);size+=info.file_size
            if p.is_absolute() or '..' in p.parts or '\\' in info.filename or ':' in info.filename:
                raise ValueError('Unsafe archive path')
            if (info.external_attr>>16)&0o170000==stat.S_IFLNK:raise ValueError('Archive symlink')
            key=info.filename.casefold()
            if key in seen:raise ValueError('Duplicate archive member')
            if size>8*1024**3:raise ValueError('Archive too large')
            seen.add(key)
        if z.testzip():raise ValueError('ZIP CRC failed')
        target.mkdir(parents=True)
        for info in z.infolist():
            path=target/info.filename
            if info.is_dir():path.mkdir(parents=True,exist_ok=True);continue
            path.parent.mkdir(parents=True,exist_ok=True)
            with z.open(info) as source,path.open('wb') as dest:shutil.copyfileobj(source,dest)
    return target
