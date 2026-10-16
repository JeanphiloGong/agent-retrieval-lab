from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Identity:
    subject: str
    tenant: str

    def __post_init__(self):
        if not self.subject or not self.tenant:
            raise ValueError("trusted identity requires subject and tenant")


@dataclass(frozen=True)
class ProtectedDocument:
    id: str
    tenant: str
    text: str


def authorize(identity: Identity | None, document: ProtectedDocument) -> bool:
    return bool(identity and identity.tenant == document.tenant)


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
