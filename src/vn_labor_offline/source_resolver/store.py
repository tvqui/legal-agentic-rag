from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable


SCHEMA_VERSION = 3


class EvidenceStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._initialize()

    def _initialize(self) -> None:
        current = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if current > SCHEMA_VERSION:
            raise RuntimeError(f"unsupported evidence store schema {current}")
        has_records = self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='records'").fetchone()
        if has_records and current < SCHEMA_VERSION:
            self.connection.executescript("""
            ALTER TABLE records RENAME TO records_v1;
            ALTER TABLE candidates RENAME TO candidates_v1;
            ALTER TABLE evidence RENAME TO evidence_v1;
            """)
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS records (
          record_id TEXT PRIMARY KEY, relative_path TEXT UNIQUE NOT NULL, source_group TEXT NOT NULL,
          corpus_sha256 TEXT NOT NULL, canonical_identifier TEXT NOT NULL, state TEXT NOT NULL,
          metadata_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS candidates (
          candidate_id TEXT PRIMARY KEY, record_id TEXT NOT NULL, role TEXT NOT NULL,
          requested_url TEXT NOT NULL, final_url TEXT NOT NULL, provider_id TEXT NOT NULL,
          source_class TEXT NOT NULL, state TEXT NOT NULL, reason_codes_json TEXT NOT NULL,
          metadata_json TEXT NOT NULL,
          parent_candidate_id TEXT NOT NULL DEFAULT '',
          discovered_from_candidate_id TEXT NOT NULL DEFAULT '',
          UNIQUE(record_id, role, requested_url),
          FOREIGN KEY(record_id) REFERENCES records(record_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS evidence (
          evidence_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, fetched_at TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id) ON DELETE CASCADE
        );
        """)
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(candidates)")}
        if "parent_candidate_id" not in columns:
            self.connection.execute("ALTER TABLE candidates ADD COLUMN parent_candidate_id TEXT NOT NULL DEFAULT ''")
        if "discovered_from_candidate_id" not in columns:
            self.connection.execute("ALTER TABLE candidates ADD COLUMN discovered_from_candidate_id TEXT NOT NULL DEFAULT ''")
        self.connection.execute("INSERT OR REPLACE INTO schema_meta VALUES ('version', ?)", (str(SCHEMA_VERSION),))
        if has_records and current < SCHEMA_VERSION:
            self.connection.executescript("""
            INSERT OR IGNORE INTO records SELECT * FROM records_v1;
            INSERT OR IGNORE INTO candidates(
              candidate_id, record_id, role, requested_url, final_url, provider_id,
              source_class, state, reason_codes_json, metadata_json)
              SELECT candidate_id, record_id, role, requested_url, final_url, provider_id,
              source_class, state, reason_codes_json, metadata_json FROM candidates_v1;
            INSERT OR IGNORE INTO evidence SELECT * FROM evidence_v1;
            DROP TABLE records_v1;
            DROP TABLE candidates_v1;
            DROP TABLE evidence_v1;
            """)
        self.connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        self.connection.commit()

    def upsert_records(self, records: Iterable[dict]) -> int:
        count = 0
        with self.connection:
            for row in records:
                self.connection.execute(
                    """INSERT INTO records(record_id,relative_path,source_group,corpus_sha256,
                    canonical_identifier,state,metadata_json) VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(record_id) DO UPDATE SET state=excluded.state, metadata_json=excluded.metadata_json""",
                    (row["record_id"], row["relative_path"], row["source_group"], row["corpus_sha256"],
                     row["canonical_identifier"], row["state"], json.dumps(row, ensure_ascii=False, sort_keys=True)),
                )
                count += 1
        return count

    def ensure_records(self, records: Iterable[dict]) -> int:
        """Insert missing seed records without destroying resolver state on resume."""
        count = 0
        with self.connection:
            for row in records:
                self.connection.execute(
                    """INSERT OR IGNORE INTO records(record_id,relative_path,source_group,corpus_sha256,
                    canonical_identifier,state,metadata_json) VALUES(?,?,?,?,?,?,?)""",
                    (row["record_id"], row["relative_path"], row["source_group"], row["corpus_sha256"],
                     row["canonical_identifier"], row["state"],
                     json.dumps(row, ensure_ascii=False, sort_keys=True)),
                )
                count += 1
        return count

    def add_candidate(self, candidate: dict) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT INTO candidates(candidate_id,record_id,role,requested_url,final_url,provider_id,
                source_class,state,reason_codes_json,metadata_json,parent_candidate_id,discovered_from_candidate_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(candidate_id) DO UPDATE SET final_url=excluded.final_url,state=excluded.state,
                reason_codes_json=excluded.reason_codes_json,metadata_json=excluded.metadata_json,
                parent_candidate_id=excluded.parent_candidate_id,
                discovered_from_candidate_id=excluded.discovered_from_candidate_id""",
                (candidate["candidate_id"], candidate["record_id"], candidate["role"], candidate["requested_url"],
                 candidate.get("final_url", ""), candidate.get("provider_id", ""), candidate.get("source_class", "SECONDARY"),
                 candidate["state"], json.dumps(candidate.get("reason_codes", [])),
                 json.dumps(candidate, ensure_ascii=False, sort_keys=True),
                 candidate.get("parent_candidate_id", candidate.get("metadata", {}).get("parent_candidate_id", "")),
                 candidate.get("discovered_from_candidate_id", candidate.get("metadata", {}).get("discovered_from_candidate_id", ""))),
            )

    def update_candidate(self, candidate_id: str, *, state: str, final_url: str = "",
                         reason_codes: list[str] | None = None, metadata: dict | None = None) -> None:
        current = self.connection.execute(
            "SELECT metadata_json FROM candidates WHERE candidate_id=?", (candidate_id,)
        ).fetchone()
        merged = json.loads(current["metadata_json"]) if current else {}
        merged.update(metadata or {})
        merged.update({"state": state, "final_url": final_url,
                       "reason_codes": sorted(set(reason_codes or []))})
        with self.connection:
            self.connection.execute(
                "UPDATE candidates SET state=?, final_url=?, reason_codes_json=?, metadata_json=? WHERE candidate_id=?",
                (state, final_url, json.dumps(sorted(set(reason_codes or []))),
                 json.dumps(merged, ensure_ascii=False, sort_keys=True), candidate_id),
            )

    def update_record_state(self, record_id: str, state: str, metadata: dict | None = None) -> None:
        current = self.connection.execute(
            "SELECT metadata_json FROM records WHERE record_id=?", (record_id,)
        ).fetchone()
        merged = json.loads(current["metadata_json"]) if current else {}
        merged.update(metadata or {})
        merged["state"] = state
        merged["resolution_state"] = state
        with self.connection:
            self.connection.execute(
                "UPDATE records SET state=?, metadata_json=? WHERE record_id=?",
                (state, json.dumps(merged, ensure_ascii=False, sort_keys=True), record_id),
            )

    def record_for_id(self, record_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT state,metadata_json FROM records WHERE record_id=?", (record_id,)
        ).fetchone()
        if not row:
            return None
        return json.loads(row["metadata_json"]) | {"state": row["state"]}

    def add_evidence(self, evidence_id: str, candidate_id: str, fetched_at: str, payload: dict) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO evidence(evidence_id,candidate_id,fetched_at,payload_json) VALUES(?,?,?,?)",
                (evidence_id, candidate_id, fetched_at, json.dumps(payload, ensure_ascii=False, sort_keys=True)),
            )

    def candidates_for_record(self, record_id: str) -> list[dict]:
        return [json.loads(row["metadata_json"]) for row in self.connection.execute(
            "SELECT metadata_json FROM candidates WHERE record_id=? ORDER BY candidate_id", (record_id,))]

    def evidence_for(self, evidence_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT payload_json FROM evidence WHERE candidate_id=? ORDER BY fetched_at DESC, evidence_id DESC LIMIT 1",
            (evidence_id,)).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def export_records(self) -> list[dict]:
        exported = []
        for row in self.connection.execute("SELECT * FROM records ORDER BY relative_path"):
            item = json.loads(row["metadata_json"]) | {"state": row["state"]}
            item.setdefault("resolution_state", row["state"])
            item.setdefault("seed_collection_result", item.get("collection_result", ""))
            item.setdefault("seed_sha_match", item.get("sha_match", ""))
            item.setdefault("seed_downloaded_sha256", item.get("downloaded_sha256", ""))
            item.setdefault("resolved_downloaded_sha256", "")
            item.setdefault("resolved_sha_match", "")
            item.setdefault("resolved_at", "")
            item.setdefault("identity_match", "")
            item.setdefault("identity_source", "")
            item.setdefault("final_identity_url", item.get("identity_url", ""))
            item.setdefault("final_binary_url", item.get("binary_url", ""))
            for ambiguous in ("collection_result", "sha_match", "downloaded_sha256"):
                item.pop(ambiguous, None)
            exported.append(item)
        return exported

    def export_evidence(self) -> list[dict]:
        return [
            json.loads(row["payload_json"]) | {"evidence_id": row["evidence_id"], "candidate_id": row["candidate_id"]}
            for row in self.connection.execute("SELECT * FROM evidence ORDER BY evidence_id")
        ]

    def close(self) -> None:
        self.connection.close()
