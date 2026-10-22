from __future__ import annotations

from collections import OrderedDict
import json
import math
from pathlib import Path
import sqlite3
from typing import Callable, Sequence

from labs.access.control import Identity
from labs.hybrid.retrieval import Document, vector_rank


class Index:
    """One local index generation with transactional updates and tombstones."""

    def __init__(self, path: Path, model_version: str, chunk_version: str) -> None:
        self.connection = sqlite3.connect(path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS documents(tenant TEXT, id TEXT, revision INTEGER, deleted INTEGER, text TEXT, vector TEXT, PRIMARY KEY(tenant,id))")
        metadata = dict(self.connection.execute("SELECT key,value FROM metadata"))
        wanted = {"model": model_version, "chunker": chunk_version}
        if metadata and metadata != wanted:
            self.connection.close()
            raise ValueError("index configuration mismatch; rebuild explicitly")
        self.connection.executemany("INSERT OR IGNORE INTO metadata VALUES(?,?)", wanted.items())
        self.connection.commit()

    def close(self):
        self.connection.close()

    def apply(self, tenant: str, doc_id: str, revision: int, text: str | None, vector: Sequence[float] = ()) -> bool:
        if revision < 1 or not tenant or not doc_id:
            raise ValueError("event requires identity and positive revision")
        if text is not None and (not vector or any(not math.isfinite(float(value)) for value in vector)):
            raise ValueError("live documents require a finite embedding")
        serialized = json.dumps(list(vector)) if text is not None else "[]"
        with self.connection:
            old = self.connection.execute("SELECT revision,deleted,text,vector FROM documents WHERE tenant=? AND id=?", (tenant, doc_id)).fetchone()
            desired = (revision, int(text is None), text or "", serialized)
            if old and revision == old[0]:
                if tuple(old) != desired:
                    raise ValueError("conflicting event at the same revision")
                return False
            if old and revision < old[0]:
                return False
            self.connection.execute("INSERT INTO documents VALUES(?,?,?,?,?,?) ON CONFLICT(tenant,id) DO UPDATE SET revision=excluded.revision,deleted=excluded.deleted,text=excluded.text,vector=excluded.vector", (tenant, doc_id, *desired))
        return True

    def generation(self, tenant: str) -> tuple[tuple[str, int], ...]:
        return tuple(self.connection.execute("SELECT id,revision FROM documents WHERE tenant=? ORDER BY id", (tenant,)))

    def search(self, identity: Identity, query_vector: Sequence[float], limit: int = 5):
        if not 1 <= limit <= 100:
            raise ValueError("limit must be within 1..100")
        rows = list(self.connection.execute("SELECT id,text,vector FROM documents WHERE tenant=? AND deleted=0 ORDER BY id", (identity.tenant,)))
        if not rows:
            return []
        return vector_rank([Document(row[0], row[1]) for row in rows], [json.loads(row[2]) for row in rows], query_vector)[:limit]


class QueryCache:
    def __init__(self, capacity: int = 32) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self.entries = OrderedDict()

    def query(self, identity: Identity, generation: tuple, question: str, compute: Callable):
        key = (identity.tenant, identity.subject, tuple(sorted(identity.roles)), identity.policy_version, generation, question)
        if key in self.entries:
            self.entries.move_to_end(key)
            return self.entries[key], True
        value = tuple(compute())
        self.entries[key] = value
        self.entries.move_to_end(key)
        while len(self.entries) > self.capacity:
            self.entries.popitem(last=False)
        return value, False
