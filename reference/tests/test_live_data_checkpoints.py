from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path

import pytest


@pytest.mark.parametrize("version", ["v0", "v1", "v2", "v3"])
def test_each_historical_source_snapshot_is_runnable(version, tmp_path):
    module = import_module(f"labs.live_data.checkpoints.{version}")
    path = tmp_path / f"{version}.sqlite"
    database = module.open_database(str(path))
    module.seed(database, [("A-1", "cable", 12), ("A-2", "cable", 0)])
    result = module.get_product(database, "A-1")
    assert result.quantity == 12
    assert module.get_product(database, "A-2").quantity == 0
    assert module.get_product(database, "MISSING") is None
    if version != "v0":
        assert len(module.list_products(database, "cable", limit=1)) == 1
    if version in {"v2", "v3"}:
        query = module.query_readonly(path, "SELECT SUM(quantity) AS n FROM inventory")
        assert query.rows == ({"n": 12},)
        with pytest.raises(module.QueryRejected):
            module.query_readonly(path, "DELETE FROM inventory")
    if version == "v3":
        policy = module.load_policy(Path("fixtures/live_data/cable-policy-v1.json"))
        observed = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
        current = module.InventoryResult("A-1", "cable", 12, observed.isoformat())
        decision = module.combine_with_policy(current, [policy], now=observed)
        assert decision["answerable"] is True
    database.close()
