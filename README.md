# Cheshire Cat

Cheshire Cat is a reproducible stock-research toolkit. It stores historical
market data and SEC filings in PostgreSQL, archives source documents alongside
Markdown copies, provides portfolio accounting and an interactive dashboard,
and backtests a deterministic investment agent without look-ahead bias.

## Quick start with UV

Install [UV](https://docs.astral.sh/uv/), copy `.env.example` to `.env`, and
start PostgreSQL. The default connection is
`postgresql+psycopg://cat:meow@localhost:5432/cheshire_cat`.

```bash
uv sync --extra all --extra dev
uv run cheshire-cat init-db
uv run cheshire-cat history --symbols MSFT,AAPL --start 2015-01-01
uv run cheshire-cat reports --symbols MSFT,AAPL --year 2026
uv run cheshire-cat dashboard
```

The reports command keeps the downloaded source under
`data/reports/<SYMBOL>/<YEAR>/` and writes a Markdown rendering next to it.
SEC requests require a real identifying `SEC_USER_AGENT` containing a contact
address; do not use a made-up browser identity.

## Backtesting

The agent uses delayed moving-average signals and equal-weight allocation. It
is intentionally deterministic and conservative: positions are shifted one
session before returns are applied, transaction costs are charged on turnover,
and results are compared with an equal-weight buy-and-hold benchmark.

```bash
uv run cheshire-cat backtest prices.csv --fast-window 50 --slow-window 200
```

The CSV must contain `date`, `symbol`, and `close` or `adj_close` columns. The
backtester is research tooling, not investment advice; historical performance
does not predict future returns.

## Python API

```python
from cheshire_cat.backtest import backtest
from cheshire_cat.database import get_engine, prices_as_frame
from cheshire_cat.market_data import ingest_history
from sqlalchemy.orm import Session

ingest_history(["MSFT"], start="2020-01-01")
with Session(get_engine()) as session:
    prices = prices_as_frame(session, ["MSFT"])
result = backtest(prices)
print(result.metrics, result.benchmark_metrics)
```

Use `cheshire_cat.dashboard.create_app()` to embed the Dash app in a larger
deployment. Dashboard-only dependencies are optional so ingestion and tests
remain usable in headless environments.
