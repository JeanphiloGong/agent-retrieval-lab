"""Bind real retrieval, file, and SQLite operations to the Agent contract."""
from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from labs.code_search.reader import read_range
from labs.hybrid.retrieval import Document, bm25_rank
from labs.live_data.query import get_product
from .loop import Evidence, Tool, ToolInfo

@dataclass(frozen=True)
class SourceDocument:
    source_id: str
    source_version: str
    text: str

def _arguments(arguments: Mapping[str, Any], expected: Mapping[str, type]) -> None:
    if set(arguments) != set(expected):
        raise ValueError(f"expected exactly {', '.join(sorted(expected))}")
    for name, value_type in expected.items():
        if type(arguments[name]) is not value_type:
            raise ValueError(f'{name} must be {value_type.__name__}')
        if value_type is str and (not arguments[name].strip()):
            raise ValueError(f'{name} must be nonempty')

def lexical_tool(documents: Sequence[SourceDocument], *, limit: int=1) -> Tool:
    """Run the existing BM25 implementation over versioned documents."""
    if limit < 1:
        raise ValueError('limit must be positive')
    by_id = {document.source_id: document for document in documents}
    if len(by_id) != len(documents):
        raise ValueError('source IDs must be unique in a searchable snapshot')
    corpus = [Document(document.source_id, document.text) for document in documents]

    def run(arguments: Mapping[str, Any]) -> tuple[Evidence, ...]:
        _arguments(arguments, {'query': str})
        hits = bm25_rank(corpus, arguments['query'])[:limit]
        evidence: list[Evidence] = []
        for hit in hits:
            document = by_id[hit.document.id]
            evidence.append(Evidence(document.source_id, document.source_version, f'lines:1-{max(1, len(document.text.splitlines()))}', document.text))
        return tuple(evidence)
    return Tool(ToolInfo('bm25_search', 'Search versioned source text using BM25', {'query': 'string'}), run)

def read_tool(documents: Sequence[SourceDocument]) -> Tool:
    """Read a whole small document from a trusted in-memory source registry."""
    by_id = {document.source_id: document for document in documents}
    if len(by_id) != len(documents):
        raise ValueError('source IDs must be unique in a readable snapshot')

    def run(arguments: Mapping[str, Any]) -> tuple[Evidence, ...]:
        _arguments(arguments, {'source_id': str})
        document = by_id.get(arguments['source_id'])
        if document is None:
            return ()
        return tuple([Evidence(document.source_id, document.source_version, f'lines:1-{max(1, len(document.text.splitlines()))}', document.text)])
    return Tool(ToolInfo('read_document', 'Read a known source ID, never an arbitrary path', {'source_id': 'string'}), run)

def code_tool(workspace: Path, *, source_version: str) -> Tool:
    """Reuse the code-search topic's bounded, workspace-confined range reader."""

    def run(arguments: Mapping[str, Any]) -> tuple[Evidence, ...]:
        _arguments(arguments, {'path': str, 'start_line': int, 'end_line': int})
        result = read_range(workspace, arguments['path'], start_line=arguments['start_line'], end_line=arguments['end_line'], max_bytes=65536)
        return tuple([Evidence(result.path, source_version, f'lines:{result.start_line}-{result.end_line}', result.text)])
    return Tool(ToolInfo('read_code', 'Read an inclusive UTF-8 line range inside the fixed workspace', {'path': 'string', 'start_line': 'integer', 'end_line': 'integer'}), run)

def inventory_tool(connection: sqlite3.Connection) -> Tool:
    """Use the real allow-listed inventory lookup; never accept model SQL."""

    def run(arguments: Mapping[str, Any]) -> tuple[Evidence, ...]:
        _arguments(arguments, {'sku': str})
        result = get_product(connection, arguments['sku'])
        if result is None:
            return ()
        text = json.dumps({'sku': result.sku, 'category': result.category, 'quantity': result.quantity, 'observed_at': result.observed_at}, sort_keys=True)
        return tuple([Evidence('inventory', result.observed_at, f'sku:{result.sku}', text)])
    return Tool(ToolInfo('inventory_lookup', 'Read current quantity of a validated product SKU', {'sku': 'string'}), run)
