# Live-data checkpoints

These are supplied reference answers. Learners build their own `query.py`
under the root `labs/live_data/` directory.

`query.py` is the current integration entry point. `checkpoints/v0.py` through
`v3.py` are complete historical source snapshots, retained for tutorial replay;
the current code does not import or forward to them.

| Version | Added behavior | Replay |
| --- | --- | --- |
| v0 | Fixed SKU lookup and observation timestamp | `reference/tests/test_live_data_checkpoints.py -k v0` |
| v1 | SKU/category contract and bounded deterministic pagination | `reference/tests/test_live_data_checkpoints.py -k v1` |
| v2 | Real read-only bounded SQL execution | `reference/tests/test_live_data_checkpoints.py -k v2` |
| v3 | Dated source-owned policy evidence and conflict checks | `reference/tests/test_live_data_checkpoints.py -k v3` |

Run from repository root:

```bash
uv sync --locked
PYTHONPATH=reference uv run python -P -m pytest --import-mode=importlib -q tests/test_live_data.py reference/tests/test_live_data_checkpoints.py
```

The database is local SQLite and test databases are created under pytest's
temporary directory. The policy fixture is self-authored. No API key or external
service is used. `open_database` and `seed` prepare experiment data; the Agent's
general query tool is `query_readonly`, which creates its own read-only connection.
