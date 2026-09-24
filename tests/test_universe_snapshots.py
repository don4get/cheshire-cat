from datetime import date

from cheshire_cat.universe import TickerRecord
from cheshire_cat.universe_snapshots import (
    build_universe_snapshot,
    annotate_eligibility,
    load_universe_snapshot,
    resolve_membership,
    store_universe_snapshot,
)


def test_future_listing_and_sector_change_do_not_rewrite_earlier_snapshot():
    records = [TickerRecord("AAA", "NASDAQ", sector="Technology", source="fixture")]
    events = [
        {"symbol": "BBB", "effective_on": "2026-01-01", "event_type": "ipo", "exchange": "NASDAQ"},
        {"symbol": "AAA", "effective_on": "2027-01-01", "event_type": "sector_change", "sector": "Energy"},
    ]
    earlier = resolve_membership(records, events, date(2026, 6, 1))
    later = resolve_membership(records, events, date(2027, 2, 1))
    assert {row.symbol for row in earlier} == {"AAA", "BBB"}
    assert next(row for row in earlier if row.symbol == "AAA").sector == "Technology"
    assert next(row for row in later if row.symbol == "AAA").sector == "Energy"


def test_snapshot_is_explicit_when_only_current_source_is_available():
    snapshot = build_universe_snapshot(
        [TickerRecord("AAA", "NASDAQ", currency="USD", source="fixture")],
        "2020-01-01",
        "NASDAQ",
    )
    assert snapshot["historical_status"] == "current_snapshot_only"
    assert snapshot["memberships"][0]["price_eligible"] is None
    assert "historical listing membership" in snapshot["metadata"]["limitations"][0]


def test_snapshot_is_append_only_and_reloadable(tmp_path):
    url = f"sqlite:///{tmp_path / 'snapshots.sqlite'}"
    snapshot = build_universe_snapshot(
        [TickerRecord("AAA", "NASDAQ", source="fixture")], "2025-01-01", "NASDAQ"
    )
    assert store_universe_snapshot(snapshot, url) == snapshot["id"]
    assert store_universe_snapshot(snapshot, url) == snapshot["id"]
    loaded = load_universe_snapshot(snapshot["id"], url)
    assert loaded["memberships"][0]["symbol"] == "AAA"


def test_eligibility_records_price_liquidity_freshness_and_completeness():
    snapshot = build_universe_snapshot(
        [TickerRecord("AAA", "NASDAQ", source="fixture")], "2025-01-01", "NASDAQ"
    )
    annotated = annotate_eligibility(
        snapshot,
        {
            "AAA": {
                "price": 10,
                "median_dollar_volume": 1_000_000,
                "price_freshness_days": 1,
                "price_observation_date": "2024-12-31",
                "fundamental_coverage": 0.8,
            }
        },
        min_price=5,
        min_median_dollar_volume=500_000,
        max_price_freshness_days=5,
        min_fundamental_coverage=0.75,
    )
    row = annotated["memberships"][0]
    assert row["price_eligible"] is True
    assert row["liquidity_eligible"] is True
    assert row["completeness_status"] == "complete"
    assert row["exclusion_reason"] is None


def test_effective_dated_ipo_delisting_and_ticker_change_are_point_in_time():
    records = [
        TickerRecord("NEW", "NASDAQ", name="New issuer", source="current"),
        TickerRecord("LIVE", "NASDAQ", source="current"),
    ]
    events = [
        {"symbol": "NEW", "effective_on": "2025-01-01", "event_type": "ipo"},
        {"symbol": "LIVE", "effective_on": "2025-06-01", "event_type": "delisted"},
        {"symbol": "OLD", "new_symbol": "RENAMED", "effective_on": "2025-03-01", "event_type": "ticker_change"},
    ]
    before = resolve_membership(records, events, "2024-12-31")
    after = resolve_membership(records, events, "2025-12-31")
    assert "NEW" not in {item.symbol for item in before}
    assert "LIVE" in {item.symbol for item in before}
    assert "LIVE" not in {item.symbol for item in after}

    current_renamed = [TickerRecord("RENAMED", "NASDAQ", source="current")]
    assert {item.symbol for item in resolve_membership(current_renamed, events, "2024-12-31")} == {"OLD", "LIVE"}
    assert {item.symbol for item in resolve_membership(current_renamed, events, "2025-12-31")} == {"NEW", "RENAMED"}
