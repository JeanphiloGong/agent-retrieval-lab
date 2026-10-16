from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest

from labs.live_data.query import (
    InventoryResult,
    QueryBudgetExceeded,
    QueryRejected,
    QueryRowLimitExceeded,
    combine_with_policy,
    get_product,
    list_products,
    load_policy,
    open_database,
    query_readonly,
    seed,
)


NOW = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
FIXTURES = Path(__file__).parents[1] / "fixtures" / "live_data"


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "inventory.sqlite"
    writer = open_database(path)
    seed(writer, [("A-1", "cable", 12), ("A-2", "cable", 0), ("B-1", "adapter", 4)])
    yield path, writer
    writer.close()


def test_v0_queries_current_values_and_returns_observation_time(database):
    _, writer = database
    before = get_product(writer, "A-1")
    seed(writer, [("A-1", "cable", 5)])
    after = get_product(writer, "A-1")
    assert before.quantity == 12 and after.quantity == 5
    assert datetime.fromisoformat(after.observed_at).tzinfo is not None


def test_v1_zero_stock_is_not_missing(database):
    _, writer = database
    assert get_product(writer, "A-2").quantity == 0
    assert get_product(writer, "UNKNOWN") is None


def test_v1_bound_parameters_do_not_expand_the_query(database):
    _, writer = database
    assert list_products(writer, "cable' OR 1=1 --") == ()
    assert [row.sku for row in list_products(writer, "cable", limit=1, offset=1)] == ["A-2"]


@pytest.mark.parametrize("sku", ["", "a-1", "A' OR 1=1 --", "X" * 33])
def test_v1_invalid_sku_is_rejected(database, sku):
    with pytest.raises(ValueError, match="sku"):
        get_product(database[1], sku)


@pytest.mark.parametrize("limit,offset", [(0, 0), (101, 0), (True, 0), (1, -1), (1, 10001)])
def test_v1_pagination_is_bounded(database, limit, offset):
    with pytest.raises(ValueError):
        list_products(database[1], "cable", limit=limit, offset=offset)


def test_v2_readonly_aggregate_uses_bound_parameter(database):
    result = query_readonly(database[0], "SELECT SUM(quantity) AS total FROM inventory WHERE category = ?", ("cable",))
    assert result.rows == ({"total": 12},)
    assert result.source_id == "inventory"
    assert datetime.fromisoformat(result.observed_at).tzinfo


def test_v2_parameters_remain_data(database):
    result = query_readonly(
        database[0],
        "SELECT COUNT(*) AS n FROM inventory WHERE category = ?",
        ("cable' OR 1=1 --",),
    )
    assert result.rows == ({"n": 0},)


def test_v2_readonly_mode_does_not_create_missing_database(tmp_path):
    missing = tmp_path / "not-created.sqlite"
    with pytest.raises(sqlite3.OperationalError, match="unable to open database"):
        query_readonly(missing, "SELECT 1")
    assert not missing.exists()


@pytest.mark.parametrize("statement", [
    "UPDATE inventory SET quantity = 999",
    "DELETE FROM inventory",
    "CREATE TABLE stolen (value TEXT)",
    "SELECT * FROM inventory; DELETE FROM inventory",
    "PRAGMA query_only = OFF",
    "ATTACH DATABASE ':memory:' AS extra",
    "SELECT * FROM sqlite_master",
    "SELECT load_extension('missing')",
])
def test_v2_boundary_rejects_write_and_escape_attempts(database, statement):
    with pytest.raises(QueryRejected):
        query_readonly(database[0], statement)
    assert get_product(database[1], "A-1").quantity == 12


def test_v2_result_limit_fails_explicitly_instead_of_silent_truncation(database):
    with pytest.raises(QueryRowLimitExceeded):
        query_readonly(database[0], "SELECT * FROM inventory", max_rows=2)


def test_v2_operation_budget_interrupts_expensive_query(database):
    path, writer = database
    seed(writer, [(f"C-{index}", "cable", 1) for index in range(100)])
    with pytest.raises(QueryBudgetExceeded):
        query_readonly(
            path,
            "SELECT COUNT(*) FROM inventory a CROSS JOIN inventory b CROSS JOIN inventory c",
            max_operations=100,
            timeout_seconds=5,
        )
    assert query_readonly(path, "SELECT COUNT(*) AS n FROM inventory").rows == ({"n": 103},)


def test_v2_deadline_is_enforced(database):
    with pytest.raises(QueryBudgetExceeded):
        query_readonly(database[0], "SELECT * FROM inventory", timeout_seconds=1e-12)


def _inventory(observed_at=NOW):
    return InventoryResult("A-1", "cable", 12, observed_at.isoformat())


def _policy():
    return load_policy(FIXTURES / "cable-policy-v1.json")


def test_v3_combines_current_quantity_with_source_owned_threshold():
    decision = combine_with_policy(_inventory(), [_policy()], now=NOW)
    assert decision["answerable"] is True
    assert decision["minimum_stock"] == 10
    assert decision["meets_policy"] is True
    assert decision["sources"][1]["source_version"] == "v1"
    assert "at least 10" in decision["sources"][1]["quote"]


@pytest.mark.parametrize("offset,reason", [(-61, "stale_inventory"), (1, "future_inventory")])
def test_v3_stale_and_future_inventory_do_not_support_answer(offset, reason):
    decision = combine_with_policy(_inventory(NOW + timedelta(seconds=offset)), [_policy()], now=NOW)
    assert decision["answerable"] is False and decision["reason"] == reason


def test_v3_exact_age_boundary_is_accepted():
    decision = combine_with_policy(_inventory(NOW - timedelta(seconds=60)), [_policy()], now=NOW)
    assert decision["answerable"] is True


def test_v3_conflicting_effective_policy_sources_are_reported():
    second = replace(_policy(), source_id="regional-policy", minimum_stock=20, quote="Keep at least 20 cable units.")
    decision = combine_with_policy(_inventory(), [_policy(), second], now=NOW)
    assert decision["answerable"] is False
    assert decision["reason"] == "policy_source_conflict"
    assert len(decision["sources"]) == 3


def test_v3_expired_or_wrong_category_policy_is_not_used():
    expired = replace(_policy(), effective_until="2026-10-15T00:00:00+00:00")
    wrong_category = replace(_policy(), category="adapter")
    decision = combine_with_policy(_inventory(), [expired, wrong_category], now=NOW)
    assert decision["reason"] == "no_current_policy"


def test_v3_missing_product_is_explicit():
    assert combine_with_policy(None, [_policy()], now=NOW)["reason"] == "sku_not_found"


def test_v3_policy_contract_rejects_unsupported_threshold(tmp_path):
    bad = tmp_path / "policy.json"
    bad.write_text('{"minimum_stock": 10}', encoding="utf-8")
    with pytest.raises(ValueError, match="contract"):
        load_policy(bad)


def test_v3_naive_timestamps_are_rejected():
    with pytest.raises(ValueError, match="timezone"):
        combine_with_policy(replace(_inventory(), observed_at="2026-10-16T12:00:00"), [_policy()], now=NOW)
