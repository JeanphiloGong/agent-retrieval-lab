# Documents checkpoints

These are supplied reference modules. Learners build the corresponding files
under the root `labs/documents/` directory.

Each version remains a separate runnable module. Later versions import earlier
versions instead of replacing them, so v0-v3 remain replayable without Git tags.

| Checkpoint | Entry point | Test |
| --- | --- | --- |
| v0 | `v0_extract.extract_document` | `test_v0_extract.py` |
| v1 | `v1_structure.structure_document` | `test_v1_structure.py` |
| v2 | `v2_chunk.fixed_window_chunks`, `structure_chunks` | `test_v2_chunk.py` |
| v3 | `v3_citations.make_citation`, `VersionedDocumentStore` | `test_v3_citations.py` |

Run from the repository root:

```bash
uv sync --locked
PYTHONPATH=reference uv run python -P -m pytest --import-mode=importlib -q tests/documents
```

Verified on 2026-10-16: 23 passed. PDF fixtures are real, self-generated PDFs;
regenerate them with `uv run python fixtures/documents/build_pdfs.py`.

The fixture builder uses pypdf to create deterministic source assets. It is not
part of the extraction API. No model calls, credentials, network services, or
OCR engine are involved in this checkpoint.
