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
uv run cheshire-cat fundamentals --symbols AAPL
uv run cheshire-cat api
cd dashboard && dx serve --platform web
```

For the PostgreSQL-backed Dioxus dashboard and its API together, use:

```bash
just dashboard
```

The reports command keeps the downloaded source under
`data/reports/<SYMBOL>/<YEAR>/` and writes a Markdown rendering next to it.
SEC requests require a real identifying `SEC_USER_AGENT` containing a contact
address; do not use a made-up browser identity.

The fundamentals command imports all available SEC XBRL observations for the
requested symbols by default. Use `--filed-year YYYY` only when a narrower
filing-year slice is wanted.

Euronext issuers are not generally covered by SEC XBRL. Their source-labelled
annual statements can be loaded in batches with `yahoo-fundamentals`:

```bash
uv run cheshire-cat yahoo-fundamentals --symbols MC.PA,OR.PA
uv run cheshire-cat amf-reports --symbols MC.PA,OR.PA
```

The Dioxus overview calculates major valuation and profitability ratios from
the stored observations, compares them with same-sector companies, and offers
1W, 1M, 1Y, 2Y, 5Y, and MAX price windows. For large issuers the dashboard
loads the newest 2,000 raw fact rows for the ledger while retaining and using
the complete fact history in PostgreSQL.

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

## Strategy playground

The default **Investor research · 80 / 20** tab displays the trained portfolio
bot. Run `just research` once to train and save both the Nasdaq/USD and
Paris/EUR experiments; `just dashboard` serves their saved results. The page
can also start research and follow its progress. Results survive restarts.

Across the playground, green means a positive return or benchmark advantage,
red means a loss or benchmark shortfall, and amber marks uncertainty intervals
that include zero. Explicit signs and labels accompany the colors; zero and
unavailable values stay neutral. Chart colors identify strategies, not gains.

The earliest 80% of weekly investment periods select the rule; the latest 20%
evaluate the frozen choice. A fixed search of 78 rules plus a top-three
ensemble targets compounded return after costs, penalizing dependence on one
training era. Validation never selects parameters or the leaderboard winner.
The page shows separate training, validation and full-history comparisons,
annual returns, holdings and a double-cost stress check. Full-history returns
include training and must not be interpreted as an independent test.

See [the research methodology and measured results](docs/investor-research.md)
for exact dates, assumptions, data limitations and the selected algorithms.

The original experiment's **Robustness & validation** view remains available. Run `just validate`
to audit both saved markets (or `just validate NASDAQ`); the dashboard can also
launch and resume an audit. **Performance & portfolios** retains the original
curves and the top-three historical portfolio time slider.

Audits add expanding and rolling-five-year selection with a four-week gap and
annual test blocks, actual bot-switching costs, joint multiple-comparison
diagnostics, serial-dependence-aware uncertainty intervals, execution/cost/
concentration stresses, crisis windows and parameter-neighbor comparisons.
Each audit is separately versioned and cached in PostgreSQL. Reads do not
recompute it or change the original winner. A changed price fingerprint blocks
reconstruction rather than silently substituting different data.

The original evaluation has already been reviewed: these new checks are
**retrospective**, not a new untouched test. They expose substantial weaknesses
in the original selection procedure. See the [audit protocol](docs/validation-protocol.md)
and [measured robustness findings](docs/validation-results.md).

The API exposes `GET /api/research/{run_id}/validation` for status/results and
`POST /api/research/{run_id}/validation` to launch or resume an idempotent audit.
Incomplete audits can be resumed after a restart; cross-process database leases
prevent two workers from publishing competing results.

### Cheshire Atlas challenger

The default research view now opens **Cheshire Atlas · challenger**. Run
`just challenger` to build or resume both markets' challenger experiments.
Atlas uses established momentum signals, stock-level trend filters, bounded
allocation and a rank buffer that reduces unnecessary replacement of holdings.
Its choices are frozen using the original training score; the later evaluation
period never changes the chosen parameters.

All 74 new parameter configurations from three registered batches remain visible
alongside the original 79. The dashboard shows a combined training leaderboard,
period-specific performance against the four original displayed portfolios,
cost-aware expanding/rolling selection, uncertainty intervals, execution
stresses and the latest simulated holdings. The original experiment and its
portfolio timeline are preserved under the adjacent tabs.

Atlas leads the recorded training score and the full-history return comparison
in both markets. The third batch tests two training-adaptive ensembles; their
members are rebuilt inside each walk-forward window, not imported from the final
selection. **This is not a universal or prospective win:** NASDAQ's
original ensemble remains ahead in the reviewed evaluation period, and Atlas's
NASDAQ full-history drawdown is 67.87%. The favorable rankings do not establish
a dependable live edge. No brokerage orders are placed.

See the [registered research and methods](docs/challenger-research.md) and
[measured challenger results](docs/challenger-results.md). The cached API is
`GET /api/research/{run_id}/challenger`; use `POST` on the same route to launch
or resume. Batches, failed trials and frozen selections survive restarts.

The dashboard's Playground page replays the available real price history over
the selected horizon and ranks the built-in bots on the same basket, starting
capital, and transaction cost. The current catalog includes an equal-weight
benchmark plus fast, classic, defensive, and long-cycle trend bots. Results
include total and annualized return, volatility, Sharpe, drawdown, turnover,
exposure, and a normalized equity-curve comparison. New strategies can be
added to `cheshire_cat/playground.py` without changing the dashboard contract.

The portfolio timeline labels these incumbents as price-only and records the
decision cutoff, execution date, lookback periods, target weights, and price
source for each historical snapshot. It never attaches today's fundamentals
to an older holding; fundamental candidates are shown in their separate
matched research cohort.

The API can also be queried directly:

```bash
curl 'http://127.0.0.1:8000/api/playground?symbols=MC.PA,OR.PA&years=20&initial_cash=100000&transaction_cost=0.001'
```

The API reports the actual date window and data frequency used. It does not
fill gaps with invented prices; if the database only contains weekly history,
the simulation is explicitly reported and annualized as weekly.

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

## Dioxus dashboard and large-universe ingestion

The primary dashboard frontend is now the Dioxus 0.7.10 app in `dashboard/`.
It consumes only rows returned by `/api/dashboard`; when the API or database is
unavailable it shows an explicit no-data state. The Python Dash app remains
available as a compatibility frontend.

To refresh all Nasdaq symbols plus the French PEA candidate universe without
hammering Yahoo or growing the database unnecessarily:

```bash
uv run cheshire-cat universe --max-symbols 5000 --workers 8 --interval 1wk \
  --max-requests-per-day 5000 --request-delay 0.05 --no-proxy-rotation
```

This retrieves the complete discovered universe and stores the actual Yahoo
Finance weekly history in PostgreSQL. Subsequent runs process only symbols
whose cursor is due. For an authoritative broker/issuer eligibility list,
provide a CSV with `symbol`, `isin`, `name`, `exchange`, and `pea_eligible`
columns:

```bash
uv run cheshire-cat universe --pea-csv data/pea_eligible.csv
```

Use owned proxies in production; the public proxy-list fallback is intended
only for low-volume research.

## Point-in-time fundamentals

Fundamental research separates fiscal periods from public availability. SEC
facts keep their accession/version/context and date-only filing evidence;
Yahoo statement rows remain `unknown` for publication timing and are excluded
from historical as-of features. Run the coverage audit before evaluating
returns:

```bash
uv run cheshire-cat fundamental-coverage \
  --dates 2018-01-01,2020-01-01,2022-01-01
```

The interactive coverage endpoint uses a bounded 100-symbol default cohort;
pass `symbols=...` for an explicit batch or run the CLI for a larger audit.

The API provides `/api/fundamentals/readiness`,
`/api/fundamentals/coverage`, and `/api/fundamentals/research`. The latter
compares predeclared value, profitability, balance-sheet, quality/value,
hybrid-momentum, price-momentum, and benchmark candidates on matched dates,
prices, universe eligibility, and costs. Its report includes a frozen
training selection, validation replay, feature provenance, ablations,
concentration, doubled-cost stress, and seeded uncertainty.

Read [the provenance contract](docs/fundamentals-provenance.md) and
[the matched research protocol](docs/fundamental-research.md) before treating
any result as evidence. Current ticker sources can be saved as explicit
`current_snapshot_only` universe snapshots, but they are not silently treated
as historical membership.

The source-pilot record and go/no-go template are in
[docs/fundamental-pilot.md](docs/fundamental-pilot.md). A matched research
request may provide `universe_snapshot_id`; the same effective-dated
eligibility mask is then applied to every candidate in that experiment.

## Portfolio suggestions and Saxo

`/api/recommendations?portfolio=long-term&amount=1000` creates a no-side-effect
allocation preview from recorded holdings and stored prices. It does not place
or record trades; see [investment suggestions](docs/investment-suggestions.md).

The optional `cheshire_cat.saxo` adapter is read-only by default, uses SIM by
default, and requires two explicit opt-ins before order placement. Follow the
[Saxo setup guide](docs/saxo-openapi.md); live credentials are not required
for research or dashboard use.
