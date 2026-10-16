# Live-data checkpoints

`query.py` is the current integration entry point. `checkpoints/v0.py` through
`v3.py` are complete historical source snapshots, retained for tutorial replay;
the current code does not import or forward to them.

| Version | Added behavior | Replay |
| --- | --- | --- |
| v0 | Fixed SKU lookup and observation timestamp | `tests/test_live_data_checkpoints.py -k v0` |
| v1 | SKU/category contract and bounded deterministic pagination | `tests/test_live_data_checkpoints.py -k v1` |
| v2 | Real read-only bounded SQL execution | `tests/test_live_data_checkpoints.py -k v2` |
| v3 | Dated source-owned policy evidence and conflict checks | `tests/test_live_data_checkpoints.py -k v3` |

Run from repository root:

```bash
uv sync --locked
uv run python -m pytest -q tests/test_live_data.py tests/test_live_data_checkpoints.py
```

The database is local SQLite and test databases are created under pytest's
temporary directory. The policy fixture is self-authored. No API key or external
service is used. `open_database` and `seed` prepare experiment data; the Agent's
general query tool is `query_readonly`, which creates its own read-only connection.
