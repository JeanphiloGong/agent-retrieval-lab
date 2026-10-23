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
    return [document for document in visible_documents(identity, documents) if terms <= set(document.text.lower().split())]


class Catalog:
    """Authoritative document and ACL state for this version."""

    def __init__(self, documents: Iterable[ProtectedDocument]):
        self.documents = {(doc.tenant, doc.id): doc for doc in documents}
        self.revision = 1
        self.audit: list[dict] = []

    def replace(self, document: ProtectedDocument):
        self.documents[document.tenant, document.id] = document
        self.revision += 1

    def read(self, identity: Identity, doc_id: str) -> ProtectedDocument:
        document = self.documents.get((identity.tenant, doc_id))
        allowed = document is not None and authorize(identity, document)
        self.audit.append({"subject": identity.subject, "tool": "read", "id": doc_id, "allowed": allowed})
        if not allowed:
            raise PermissionError("document unavailable")
        return document

    def retrieve(self, identity: Identity, query: str, *, ranker=None) -> list[ProtectedDocument]:
        candidates = visible_documents(identity, self.documents.values())
        if ranker is None:
            from labs.hybrid.retrieval import Document, bm25_rank
            ranked = bm25_rank([Document(doc.id, doc.text) for doc in candidates], query)
            ids = [hit.document.id for hit in ranked]
        else:
            ids = list(ranker(query, candidates))
        allowed_ids = {doc.id for doc in candidates}
        if not set(ids) <= allowed_ids:
            raise PermissionError("ranker returned an unauthorized document")
        return [self.read(identity, doc_id) for doc_id in ids]
