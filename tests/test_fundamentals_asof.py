from datetime import date

import pandas as pd

from cheshire_cat.fundamentals_asof import (
    AsOfPolicy,
    asof_snapshot_key,
    compute_asof_features,
    compute_asof_fundamental_ratios,
    load_asof_snapshot,
    select_asof_facts,
    store_asof_snapshot,
)


def _fact(**overrides):
    row = {
        "symbol": "ACME",
        "taxonomy": "us-gaap",
        "concept": "NetIncomeLoss",
        "unit": "USD",
        "period_start": date(2024, 1, 1),
        "period_end": date(2024, 12, 31),
        "form": "10-K",
        "value": 100.0,
        "available_on": date(2025, 2, 15),
        "availability_status": "date_only",
        "source_document_id": "0001-24-000001",
        "source_version": "0001-24-000001",
        "context_ref": "annual",
        "statement_kind": "duration",
        "duration_days": 366,
    }
    row.update(overrides)
    return row


def test_asof_excludes_unknown_publication_and_future_restatement():
    facts = [
        _fact(value=100.0),
        _fact(
            value=120.0,
            available_on=date(2025, 4, 1),
            source_document_id="0001-25-000001",
            source_version="0001-25-000001",
        ),
        _fact(
            value=999.0,
            available_on=None,
            availability_status="unknown",
            source_document_id="provider-snapshot",
        ),
    ]

    selected = select_asof_facts(facts, date(2025, 3, 1))
    assert selected.loc[selected["selected"], "value"].tolist() == [100.0]
    assert "published_on_or_after_decision" in set(selected["excluded_reason"])
    assert "unknown_publication_date" in set(selected["excluded_reason"])


def test_asof_features_have_formula_and_provenance():
    facts = [
        _fact(concept="NetIncomeLoss", value=100.0),
        _fact(concept="StockholdersEquity", value=500.0),
        _fact(concept="EntityCommonStockSharesOutstanding", unit="shares", value=10.0),
    ]
    prices = pd.DataFrame([{"symbol": "ACME", "date": date(2025, 2, 28), "close": 20.0}])
    result = compute_asof_features(facts, prices, date(2025, 3, 1))
    earnings = result[result["feature"] == "earnings_yield"].iloc[0]
    book = result[result["feature"] == "book_to_price"].iloc[0]
    assert earnings["value"] == 0.5
    assert book["value"] == 2.5
    assert earnings["status"] == "usable"
    assert earnings["source_document_id"] == "0001-24-000001"
    assert earnings["feature_version"] == "fundamentals-asof-v1"


def test_stale_facts_are_reported_not_used():
    result = compute_asof_features(
        [_fact(available_on=date(2020, 2, 15))],
        [{"symbol": "ACME", "date": date(2025, 2, 28), "close": 20.0}],
        date(2025, 3, 1),
        policy=AsOfPolicy(max_staleness_days=365),
    )
    assert result["status"].eq("excluded").all()
    assert not result["status"].eq("usable").any()


def test_financial_sector_policy_is_explicit():
    result = compute_asof_features(
        [_fact()],
        [{"symbol": "ACME", "date": date(2025, 2, 28), "close": 20.0}],
        date(2025, 3, 1),
        sector_by_symbol={"ACME": "Financial Services"},
    )
    assert result["excluded_reason"].eq("financial_sector_policy").all()


def test_asof_ratio_wrapper_derives_multiples_without_current_snapshots():
    result = compute_asof_fundamental_ratios(
        [_fact(concept="NetIncomeLoss", value=100.0), _fact(concept="EntityCommonStockSharesOutstanding", unit="shares", value=10.0)],
        [{"symbol": "ACME", "date": date(2025, 2, 28), "close": 20.0}],
        date(2025, 3, 1),
    )
    pe = result[result["ratio"] == "pe"].iloc[0]
    assert pe["value"] == 2.0


def test_asof_snapshot_key_is_reproducible_and_cutoff_specific():
    facts = [_fact()]
    assert asof_snapshot_key(facts, date(2025, 3, 1)) == asof_snapshot_key(facts, date(2025, 3, 1))
    assert asof_snapshot_key(facts, date(2025, 3, 1)) != asof_snapshot_key(facts, date(2025, 3, 2))


def test_asof_rejects_mixed_price_and_statement_currencies_with_provenance():
    facts = [
        _fact(concept="StockholdersEquity", unit="EUR", currency="EUR", value=500.0),
        _fact(concept="EntityCommonStockSharesOutstanding", unit="shares", value=10.0),
    ]
    result = compute_asof_features(
        facts,
        [{"symbol": "ACME", "date": date(2025, 2, 28), "close": 20.0, "currency": "USD"}],
        date(2025, 3, 1),
    )
    book = result[result["feature"] == "book_to_price"].iloc[0]
    assert book["status"] == "excluded"
    assert book["excluded_reason"] == "currency_mismatch"
    assert book["input_provenance"]["equity"]["source_version"] == "0001-24-000001"
    assert book["price_basis"] == "close"


def test_asof_records_split_adjusted_price_basis_instead_of_mixing_series():
    result = compute_asof_features(
        [
            _fact(concept="NetIncomeLoss", value=100.0),
            _fact(concept="EntityCommonStockSharesOutstanding", unit="shares", value=10.0),
        ],
        [{"symbol": "ACME", "date": date(2025, 2, 28), "close": 10.0, "adj_close": 20.0}],
        date(2025, 3, 1),
    )
    earnings = result[result["feature"] == "earnings_yield"].iloc[0]
    assert earnings["value"] == 0.5
    assert earnings["price_basis"] == "adjusted_close"


def test_ttm_requires_four_distinct_contiguous_quarters_and_does_not_sum_ytd():
    facts = [
        _fact(
            concept="NetIncomeLoss", period_start=start, period_end=end,
            form="10-Q",
            duration_days=(end - start).days + 1, value=10.0 + index,
            source_version=f"q{index}", source_document_id=f"q{index}", context_ref=f"q{index}",
        )
        for index, (start, end) in enumerate(
            ((date(2024, 1, 1), date(2024, 3, 31)),
             (date(2024, 4, 1), date(2024, 6, 30)),
             (date(2024, 10, 1), date(2024, 12, 31)))
        )
    ]
    features = compute_asof_features(
        facts,
        [{"symbol": "ACME", "date": date(2025, 2, 28), "close": 20.0}],
        date(2025, 3, 1),
    )
    earnings = features[features["feature"] == "earnings_yield"].iloc[0]
    assert earnings["status"] == "excluded"
    assert earnings["excluded_reason"] == "missing_input:net_income,market_cap"


def test_later_filing_does_not_change_an_earlier_snapshot():
    original = [_fact(value=100.0)]
    later = original + [_fact(value=900.0, available_on=date(2025, 4, 1), source_version="later", source_document_id="later")]
    prices = [{"symbol": "ACME", "date": date(2025, 2, 28), "close": 20.0}]
    first = compute_asof_features(original, prices, date(2025, 3, 1))
    second = compute_asof_features(later, prices, date(2025, 3, 1))
    assert first[["feature", "value", "status", "excluded_reason"]].equals(
        second[["feature", "value", "status", "excluded_reason"]]
    )


def test_asof_snapshot_cache_is_immutable_and_reproducible(tmp_path):
    url = f"sqlite:///{tmp_path / 'feature-cache.sqlite'}"
    facts = [_fact()]
    prices = [{"symbol": "ACME", "date": date(2025, 2, 28), "close": 20.0}]
    features = compute_asof_features(facts, prices, date(2025, 3, 1))
    key = asof_snapshot_key(facts, date(2025, 3, 1), prices=prices)
    assert store_asof_snapshot(features, key=key, decision_date=date(2025, 3, 1), database_url=url) == key
    changed = features.copy()
    changed["value"] = 999.0
    store_asof_snapshot(changed, key=key, decision_date=date(2025, 3, 1), database_url=url)
    loaded = load_asof_snapshot(key, url)
    assert loaded is not None
    assert len(loaded) == len(features)
    assert not (loaded["value"] == 999.0).any()
