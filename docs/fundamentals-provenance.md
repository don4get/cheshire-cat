# Point-in-time fundamentals and coverage

The fundamentals ledger separates a fiscal period from the moment an
observation became usable to research. A period end is not a filing date, and
a provider retrieval timestamp is not publication evidence.

## Fact contract

Each observation stores:

- `period_start` and `period_end`: the fiscal interval or instant described by
  the fact;
- `available_on`: the conservative public date at which the observation can be
  used by a historical run;
- `available_at`: an optional timestamp, only populated when the source gives
  time-of-day evidence;
- `availability_status`: `verified`, `date_only`, or `unknown`;
- `source_document_id`, `source_version`, and `context_ref`: filing/accession,
  revision, and statement context identifiers;
- `unit` and `currency`: the reported measurement and currency, kept separate
  from the price currency so incompatible ratios are excluded rather than FX-
  converted silently;
- `statement_kind` and `duration_days`: instant versus flow and its duration;
- source URL and retrieval time.

SEC company facts currently provide filing dates but not a trustworthy public
timestamp, so SEC rows are marked `date_only`. Yahoo statement rows do not
provide publication evidence in this importer and remain `unknown`; their
fiscal period is not used as a substitute.

The unique identity preserves quarter, year-to-date, annual, amended, and
source-version observations together. An amendment that becomes known after a
decision date cannot rewrite an earlier run.

## As-of rule

For a decision date `D`, the feature engine requires:

1. a known availability date;
2. an allowed status (`verified` or `date_only`);
3. `available_on < D` (strict prior-day boundary);
4. a fiscal period that has ended by `D`;
5. freshness within the declared maximum staleness window.

Rows that fail are retained with an exclusion reason such as
`unknown_publication_date`, `published_on_or_after_decision`,
`superseded_version_at_decision`, or `stale_at_decision`. No current snapshot
is silently substituted.

The versioned implementation is in `cheshire_cat/fundamentals_asof.py` and the
coverage report is in `cheshire_cat/fundamental_coverage.py`. Both produce
JSON-serializable manifests suitable for a saved experiment.
`asof_snapshot_key` provides a deterministic cache key from the normalized fact
ledger, price observations, dataset version, decision date, and policy.
`store_asof_snapshot` and `load_asof_snapshot` persist the resulting feature
rows immutably; rerunning a key never overwrites its earlier decision snapshot.

## Coverage before returns

`/api/fundamentals/coverage?dates=2025-03-01,2025-06-01` reports denominators,
usable symbols, missing symbols, stale/unknown rows, source inventory, and
per-source ingestion progress (`not_started`, `in_progress`, `complete`,
`empty`, `unavailable`, or `failed`) for each market. It does not calculate
returns. A research window should be chosen from the exact qualifying dates in
this report before a fundamental or hybrid portfolio is evaluated.

Universe snapshots are stored separately from the current ticker table. If no
effective-dated listing feed is supplied, a snapshot is labelled
`current_snapshot_only`; it is not presented as historical membership.
