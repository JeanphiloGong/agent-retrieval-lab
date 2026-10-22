from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Identity:
    subject: str
    tenant: str
    roles: frozenset[str] = frozenset()
    policy_version: int = 1

    def __post_init__(self):
        if not self.subject or not self.tenant or self.policy_version < 1:
            raise ValueError("trusted identity requires subject, tenant and policy version")


@dataclass(frozen=True)
class ProtectedDocument:
    id: str
    tenant: str
    text: str
    roles: frozenset[str] = frozenset()


def authorize(identity: Identity | None, document: ProtectedDocument) -> bool:
    return bool(identity and identity.tenant == document.tenant and document.roles <= identity.roles)


def visible_documents(identity: Identity | None, documents: Iterable[ProtectedDocument]) -> list[ProtectedDocument]:
    if identity is None:
        raise PermissionError("identity is required")
    return [document for document in documents if authorize(identity, document)]


def search(identity: Identity | None, documents: Iterable[ProtectedDocument], query: str) -> list[ProtectedDocument]:
    if not isinstance(query, str) or len(query) > 256:
        raise ValueError("query is invalid")
    terms = {term.lower() for term in query.split()}
    return [document for document in visible_documents(identity, documents)
            if terms <= set(document.text.lower().split())]

class ScopedCache:
    def __init__(self, ttl_seconds: float = 30.0) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl must be positive")
        self.ttl_seconds = ttl_seconds
        self._entries: dict[tuple, tuple[float, tuple[str, ...]]] = {}

    def _key(self, identity: Identity, query: str) -> tuple:
        return (identity.tenant, identity.subject, tuple(sorted(identity.roles)),
                identity.policy_version, query)

    def get(self, identity: Identity, query: str) -> tuple[str, ...] | None:
        import time
        key = self._key(identity, query)
        entry = self._entries.get(key)
        if entry is None or time.monotonic() - entry[0] >= self.ttl_seconds:
            self._entries.pop(key, None)
            return None
        return entry[1]

    def put(self, identity: Identity, query: str, document_ids: Iterable[str]) -> None:
        import time
        self._entries[self._key(identity, query)] = (time.monotonic(), tuple(document_ids))
