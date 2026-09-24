from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import yaml


def load_yaml(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def project_root_from_config(config_path: str | Path) -> Path:
    p = Path(config_path).resolve()
    return p.parent.parent if p.parent.name == "config" else p.parent


def resolve_paths(cfg: dict, config_path: str | Path) -> dict:
    validate_config(cfg)
    root = project_root_from_config(config_path)
    cfg = dict(cfg)
    for key in ("data_dir", "output_dir"):
        p = Path(cfg[key])
        if not p.is_absolute():
            p = root / p
        cfg[key] = p.resolve()
    cfg["project_root"] = root
    return cfg


CONFIG_KEYS={
    'extraction':{'min_text_chars_before_ocr','use_docling','ocr_languages','ocr_use_gpu','document_timeout_seconds','document_timeout_attempts'},
    'cleaning':{'unicode_form','repeated_line_page_ratio','repeated_line_max_chars'},
    'parsing':{'keep_unparsed_preamble','minimum_provision_chars'},
    'knowledge':{'checklist_mode','ollama_model','issue_min_score','relation_confidence_threshold'},
    'retrieval':{'embedding_model','embedding_model_path','embedding_device','embedding_batch_size','embedding_chunk_size','embedding_max_length','embedding_use_fp16','bm25_method','case_knn_k','community_algorithm'},
    'neo4j':{'load_batch_size'},
}


def validate_config(cfg):
    unknown=set(cfg)-set(CONFIG_KEYS)-{'data_dir','output_dir','project_root'}
    if unknown: raise ValueError(f'Unknown config sections: {sorted(unknown)}')
    for section,allowed in CONFIG_KEYS.items():
        extra=set(cfg.get(section,{}))-allowed
        if extra: raise ValueError(f'Unused/unknown {section} config keys: {sorted(extra)}')
