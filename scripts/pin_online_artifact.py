"""Validate an OFFLINE artifact and create a pinned ONLINE config copy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

import yaml

from vn_labor_online.artifact_store import ArtifactStore
from vn_labor_online.config import OnlineConfig


def create_pinned_config(artifact: Path, base_config: Path, output: Path, force: bool = False) -> dict:
    artifact = artifact.expanduser().resolve()
    if not artifact.exists():
        raise FileNotFoundError(artifact)
    if output.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {output}; pass --force after reviewing it")
    raw = yaml.safe_load(base_config.read_text(encoding="utf-8")) or {}
    values = dict(raw.get("online", raw))
    with tempfile.TemporaryDirectory(prefix="vn_labor_pin_") as temporary:
        probe = dict(values)
        probe.update({
            "artifact_source": str(artifact),
            "cache_dir": str(Path(temporary) / "cache"),
            "expected_archive_sha256": None,
            "expected_build_id": None,
            "expected_retrieval_unit_fingerprint": None,
            "expected_dense_fingerprint": None,
        })
        store = ArtifactStore(OnlineConfig.model_validate(probe))
        report = store.report
        archive_sha256 = store.archive_sha256
    values.update({
        "artifact_source": str(artifact),
        "expected_archive_sha256": archive_sha256,
        "expected_build_id": report.build_id,
        "expected_retrieval_unit_fingerprint": report.retrieval_unit_fingerprint,
        "expected_dense_fingerprint": report.dense_fingerprint,
    })
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump({"online": values}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    result = {
        "artifact": str(artifact),
        "config": str(output.resolve()),
        "archive_sha256": archive_sha256,
        "build_id": report.build_id,
        "retrieval_unit_fingerprint": report.retrieval_unit_fingerprint,
        "dense_fingerprint": report.dense_fingerprint,
        "compatible": report.compatible,
        "provisional_reasons": report.provisional_reasons,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--base-config", default="config/online_kaggle.yaml")
    parser.add_argument("--output", default="/kaggle/working/online_pinned.yaml")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    create_pinned_config(Path(args.artifact), Path(args.base_config), Path(args.output), args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
