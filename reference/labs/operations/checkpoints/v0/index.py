from __future__ import annotations

import json
import math
from pathlib import Path
import sqlite3
from typing import Sequence

from labs.access.control import Identity
from labs.hybrid.retrieval import Document, vector_rank


class Index:
    """Persistent batch index with an explicit model/chunker configuration."""

    def __init__(self, path: Path, model_version: str, chunk_version: str) -> None:
        self.connection = sqlite3.connect(path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT)")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS documents("
            "tenant TEXT, id TEXT, revision INTEGER, deleted INTEGER, "
            "text TEXT, vector TEXT, PRIMARY KEY(tenant,id))"
        )
        metadata = dict(self.connection.execute("SELECT key,value FROM metadata"))
        wanted = {"model": model_version, "chunker": chunk_version}
        if metadata and metadata != wanted:
            self.connection.close()
            raise ValueError("index configuration mismatch; rebuild explicitly")
        self.connection.executemany("INSERT OR IGNORE INTO metadata VALUES(?,?)", wanted.items())
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def apply(self, tenant: str, doc_id: str, revision: int, text: str,
              vector: Sequence[float]) -> None:
        """Insert one batch document; updates and deletion arrive in v1."""
        if revision < 1 or not tenant or not doc_id or not text:
            raise ValueError("batch document requires identity and text")
        if not vector or any(not math.isfinite(float(value)) for value in vector):
            raise ValueError("batch document requires a finite embedding")
        serialized = json.dumps(list(vector))
        with self.connection:
            self.connection.execute(
                "INSERT INTO documents VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(tenant,id) DO UPDATE SET revision=excluded.revision,"
                "deleted=0,text=excluded.text,vector=excluded.vector",
                (tenant, doc_id, revision, 0, text, serialized),
            )

    def generation(self, tenant: str) -> tuple[tuple[str, int], ...]:
        return tuple(self.connection.execute(
            "SELECT id,revision FROM documents WHERE tenant=? AND deleted=0 ORDER BY id",
            (tenant,),
        ))

    def search(self, identity: Identity, query_vector: Sequence[float], limit: int = 5):
        if not 1 <= limit <= 100:
            raise ValueError("limit must be within 1..100")
        rows = list(self.connection.execute(
            "SELECT id,text,vector FROM documents WHERE tenant=? AND deleted=0 ORDER BY id",
            (identity.tenant,),
        ))
        return vector_rank(
            [Document(row[0], row[1]) for row in rows],
            [json.loads(row[2]) for row in rows],
            query_vector,
        )[:limit] if rows else []
