"""Non-secret code identity for reproducible ONLINE evaluation."""
import hashlib
import json
from pathlib import Path


def source_fingerprint(root=None):
    root=Path(root) if root is not None else Path(__file__).parent
    digest=hashlib.sha256()
    for path in sorted(root.rglob('*.py')):
        digest.update(path.relative_to(root).as_posix().encode('utf-8')+b'\0')
        digest.update(path.read_bytes()+b'\0')
    return digest.hexdigest()


def config_fingerprint(config):
    values=config.model_dump(mode='json')
    def safe(value):
        if isinstance(value,dict):
            return {key:safe(item) for key,item in value.items()
                if key not in {'api_key','password','token','secret'}}
        if isinstance(value,list):return [safe(item) for item in value]
        return value
    return hashlib.sha256(json.dumps(safe(values),sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
