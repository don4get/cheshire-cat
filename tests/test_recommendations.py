from cheshire_cat.recommendations import suggest_investments


def test_suggestions_only_use_known_portfolio_and_explain_allocations():
    result = suggest_investments(
        [{"symbol": "AAA", "quantity": 10}, {"symbol": "BBB", "quantity": 0}],
        1000,
        prices={"AAA": 100, "BBB": 50, "CCC": 1},
    )
    assert {row["symbol"] for row in result["suggestions"]} <= {"AAA", "BBB"}
    assert result["method"].startswith("No sells")
    assert all(row["reason"] for row in result["suggestions"])
