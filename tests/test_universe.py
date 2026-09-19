import pandas as pd

from cheshire_cat.market_data import DailyRequestBudget, ingest_universe_history
from cheshire_cat.proxy import ProxyPool
from cheshire_cat.universe import FrenchPeaUniverseSource, NasdaqUniverseSource, TickerRecord


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class Session:
    def __init__(self, payload, post_payload=None):
        self.payload = payload
        self.post_payload = post_payload
        self.headers = {}

    def get(self, *args, **kwargs):
        return Response(self.payload)

    def post(self, *args, **kwargs):
        return Response(self.post_payload or self.payload)


def test_nasdaq_and_euronext_parsers_normalize_symbols():
    nasdaq = NasdaqUniverseSource(
        Session({"data": {"headers": ["symbol", "name"], "rows": [["MSFT", "Microsoft"], ["BRK.B", "Berkshire"]]}})
    )
    assert [record.symbol for record in nasdaq.fetch()] == ["MSFT"]

    euronext = FrenchPeaUniverseSource(
        session=Session(
            {
                "iTotalRecords": 1,
                "aaData": [["Air France", "FR001400J770", "AF", "Euronext Paris", "EUR"]],
            }
        )
    )
    assert euronext.fetch()[0].symbol == "AF.PA"
    assert euronext.fetch()[0].pea_eligible is True


def test_euronext_parser_requests_all_pages():
    euronext = FrenchPeaUniverseSource(
        session=Session(
            {
                "iTotalRecords": 2,
                "aaData": [["Air France", "FR001400J770", "AF", "Euronext Paris", "EUR"]],
            },
            post_payload={
                "iTotalRecords": 2,
                "aaData": [
                    ["Air France", "FR001400J770", "AF", "Euronext Paris", "EUR"],
                    ["Alstom", "FR0010220475", "ALO", "Euronext Paris", "EUR"],
                ],
            },
        )
    )
    assert [record.symbol for record in euronext.fetch()] == ["AF.PA", "ALO.PA"]


def test_proxy_pool_retires_bad_endpoints():
    pool = ProxyPool(["1.1.1.1:80", "2.2.2.2:80"], max_failures=1)
    first = pool.next()
    pool.mark_failure(first)
    assert pool.next() != first


def test_universe_history_processes_a_small_due_slice(tmp_path):
    class Provider:
        def history(self, symbol, start, end, interval):
            return pd.DataFrame(
                {"close": [100.0], "volume": [1]},
                index=pd.DatetimeIndex(["2026-09-18"]),
            )

    records = [TickerRecord("AAA", "NASDAQ", name="A", source="test")]
    database_url = f"sqlite:///{tmp_path / 'universe.sqlite'}"
    result = ingest_universe_history(
        records,
        database_url=database_url,
        provider=Provider(),
        request_budget=DailyRequestBudget(max_calls=1),
        max_symbols_per_run=1,
    )
    assert result == {"selected": 1, "succeeded": 1, "rows": 1, "failed": 0}
    next_run = ingest_universe_history(
        records,
        database_url=database_url,
        provider=Provider(),
        request_budget=DailyRequestBudget(max_calls=1),
        max_symbols_per_run=1,
    )
    assert next_run["selected"] == 0
