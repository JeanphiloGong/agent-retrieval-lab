# Code Search reference

This is supplied reference code. Write your own implementation in the root
`labs/` directory; replaying these files does not complete a learner checkpoint.

`reader.py` is the v0 workspace boundary; `grep_search.py` adds v1 literal
search; `ast_search.py` adds v2 definition ranges; `symbols.py` adds the v3
conservative Python symbol index. The package contains no model calls and
does not execute the indexed Python source.

From the repository root:

```bash
PYTHONPATH=reference uv run python -P -m pytest --import-mode=importlib -q tests/code_search reference/tests/test_code_search_checkpoints.py
```

The fixed teaching tree is `fixtures/code_search/repository/`. Its source is
never imported by the search implementation. Readers should pass that tree
as the workspace and receive only its relative paths and line numbers.

`checkpoints/v0/` through `checkpoints/v3/` preserve each complete version.
For example, `from labs.code_search.checkpoints.v0 import read_range` replays
the v0 source rather than importing the current complete package. Later
versions add one module, preserving all previously taught behavior.
