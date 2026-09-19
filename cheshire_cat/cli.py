"""Command-line entry point for all repository workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .backtest import StrategyConfig, backtest
from .config import settings
from .database import create_schema
from .market_data import DailyRequestBudget, ingest_history, ingest_universe_history
from .proxy import DEFAULT_PROXY_SOURCE, ProxyPool
from .reports import ingest_fundamentals, ingest_reports
from .universe import discover_universe


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cheshire-cat", description="Stock research toolkit")
    parser.add_argument("--database-url", default=settings.database_url)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init-db", help="Create the PostgreSQL schema")
    init.set_defaults(handler=_init_db)

    history = subparsers.add_parser("history", help="Download historical daily bars")
    _symbol_args(history)
    history.add_argument("--start")
    history.add_argument("--end")
    history.add_argument("--interval", default="1d")
    history.add_argument("--proxy-source", default=None, help="Proxy-list URL; enables rotating proxies")
    history.add_argument("--max-requests-per-day", type=int)
    history.add_argument("--request-delay", type=float, default=0.0)
    history.set_defaults(handler=_history)

    universe = subparsers.add_parser(
        "universe",
        help="Refresh Nasdaq/PEA symbols and ingest a small scheduled history slice",
    )
    universe.add_argument("--pea-csv", type=Path, help="Authoritative PEA eligibility CSV")
    universe.add_argument("--no-nasdaq", action="store_true")
    universe.add_argument("--no-french-pea", action="store_true")
    universe.add_argument("--max-symbols", type=int, default=25)
    universe.add_argument("--cadence-days", type=int, default=1)
    universe.add_argument("--interval", default="1wk", choices=("1d", "5d", "1wk", "1mo"))
    universe.add_argument("--start")
    universe.add_argument("--end")
    universe.add_argument("--proxy-source", default=DEFAULT_PROXY_SOURCE)
    universe.add_argument("--no-proxy-rotation", action="store_true")
    universe.add_argument("--max-requests-per-day", type=int, default=25)
    universe.add_argument("--request-delay", type=float, default=1.0)
    universe.add_argument("--dry-run", action="store_true")
    universe.set_defaults(handler=_universe)

    reports = subparsers.add_parser("reports", help="Archive SEC annual and quarterly reports")
    _symbol_args(reports)
    reports.add_argument("--year", type=int, default=2026)
    reports.add_argument("--form", action="append", dest="forms", default=None)
    reports.add_argument("--output-dir", type=Path)
    reports.set_defaults(handler=_reports)

    fundamentals = subparsers.add_parser("fundamentals", help="Import SEC XBRL balance-sheet and other facts")
    _symbol_args(fundamentals)
    fundamentals.add_argument("--filed-year", type=int, default=2026)
    fundamentals.set_defaults(handler=_fundamentals)

    run_backtest = subparsers.add_parser("backtest", help="Backtest the investment agent on a CSV")
    run_backtest.add_argument("csv", type=Path, help="CSV with date,symbol,close or adj_close columns")
    run_backtest.add_argument("--fast-window", type=int, default=50)
    run_backtest.add_argument("--slow-window", type=int, default=200)
    run_backtest.add_argument("--transaction-cost", type=float, default=0.001)
    run_backtest.set_defaults(handler=_backtest)

    dashboard = subparsers.add_parser("dashboard", help="Run the interactive Dash dashboard")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8050)
    dashboard.add_argument("--debug", action="store_true")
    dashboard.set_defaults(handler=_dashboard)

    api = subparsers.add_parser("api", help="Run the JSON API used by the Dioxus dashboard")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    api.add_argument("--reload", action="store_true")
    api.set_defaults(handler=_api)
    return parser


def _symbol_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--symbols", help="Comma-separated ticker symbols")
    group.add_argument("--symbols-file", type=Path, help="One ticker per line")


def _symbols(args: argparse.Namespace) -> list[str]:
    if args.symbols:
        return [item for item in args.symbols.split(",") if item.strip()]
    return [line.strip() for line in args.symbols_file.read_text().splitlines() if line.strip()]


def _init_db(args: argparse.Namespace) -> None:
    create_schema(args.database_url)
    print(f"Database schema ready: {args.database_url}")


def _history(args: argparse.Namespace) -> None:
    create_schema(args.database_url)
    pool = ProxyPool.from_free_proxy_list(args.proxy_source) if args.proxy_source else None
    budget = DailyRequestBudget(args.max_requests_per_day, args.request_delay)
    print(
        json.dumps(
            ingest_history(
                _symbols(args),
                args.start,
                args.end,
                args.interval,
                args.database_url,
                proxy_pool=pool,
                request_budget=budget,
            )
        )
    )


def _universe(args: argparse.Namespace) -> None:
    if args.no_nasdaq and args.no_french_pea:
        raise SystemExit("At least one universe source must be enabled")
    records = discover_universe(
        include_nasdaq=not args.no_nasdaq,
        include_french_pea=not args.no_french_pea,
        pea_csv=args.pea_csv,
    )
    if args.dry_run:
        print(json.dumps({"symbols": len(records), "sample": [record.symbol for record in records[:20]]}))
        return
    pool = None if args.no_proxy_rotation else ProxyPool.from_free_proxy_list(args.proxy_source)
    summary = ingest_universe_history(
        records,
        include_nasdaq=not args.no_nasdaq,
        include_french_pea=not args.no_french_pea,
        pea_csv=str(args.pea_csv) if args.pea_csv else None,
        max_symbols_per_run=args.max_symbols,
        cadence_days=args.cadence_days,
        interval=args.interval,
        start=args.start,
        end=args.end,
        database_url=args.database_url,
        proxy_pool=pool,
        request_budget=DailyRequestBudget(args.max_requests_per_day, args.request_delay),
    )
    print(json.dumps({"universe": len(records), **summary}))


def _reports(args: argparse.Namespace) -> None:
    create_schema(args.database_url)
    print(json.dumps(ingest_reports(_symbols(args), args.year, args.forms or ("10-K", "10-Q", "20-F", "40-F"), args.database_url, output_dir=args.output_dir)))


def _fundamentals(args: argparse.Namespace) -> None:
    create_schema(args.database_url)
    print(json.dumps(ingest_fundamentals(_symbols(args), args.filed_year, database_url=args.database_url)))


def _backtest(args: argparse.Namespace) -> None:
    prices = pd.read_csv(args.csv)
    config = StrategyConfig(args.fast_window, args.slow_window, args.transaction_cost)
    result = backtest(prices, config=config)
    print(json.dumps({"strategy": result.metrics, "benchmark": result.benchmark_metrics}, indent=2))


def _dashboard(args: argparse.Namespace) -> None:
    from .dashboard import run_dashboard

    run_dashboard(args.database_url, args.host, args.port, args.debug)


def _api(args: argparse.Namespace) -> None:
    from .api import run_api

    run_api(args.database_url, args.host, args.port, args.reload)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
