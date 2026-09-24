# Investor research

The research engine selects a return-focused, long-only portfolio using stored
adjusted prices and trading volume. It searches a fixed, reviewable set of
rules; it cannot establish a globally optimal investment algorithm. Its honest
performance check is the final chronological holdout, not the full-history fit.

## Run and inspect

```bash
just research                 # both currency universes; reuses completed runs
just research NASDAQ          # or EURONEXT_PARIS
just dashboard
uv run cheshire-cat research --resume RUN_ID
curl 'http://127.0.0.1:8000/api/research?market=NASDAQ'
curl 'http://127.0.0.1:8000/api/research/selection?market=NASDAQ'
```

Open Playground → Investor research. Validation is the default view. Training
and full-history views are explicitly labelled. Research runs, frozen choices,
parameters, progress and results live in PostgreSQL's `research_runs` table.
The frontend polls only while a run is pending; viewing a completed experiment
does not download data, tune parameters or repeat validation. An interrupted
run resumes its persisted selection, if one exists. PostgreSQL advisory locks
prevent simultaneous workers from executing the same run.

The **Portfolios through time** panel prepares a second indexed replay for the
three highest-scoring training candidates, including the ensemble when it is
among those three. The slider, date field, previous/next controls and playback
read one cached weekly snapshot at a time. Each snapshot contains portfolio
value, cash, every position's weight and value, trades, turnover, fees and the
last rebalance date. A holding search filters the three cards without changing
the replay. Candidate ranks are frozen; moving through validation cannot
re-rank or retrain them.

## Split and selection

The current stored window yields 1,044 weekly return periods:

| Purpose | Start | End | Weeks |
| --- | --- | --- | ---: |
| Training | 2006-09-22 | 2022-09-16 | 835 |
| Validation | 2022-09-23 | 2026-09-18 | 209 |

The split is `floor(0.8 × investment periods)`, grouping every symbol on the
same date. No rows are shuffled. Another 56 earlier weeks initialize the
signals and are not included in the measured investment period. Warm-up data
can be used across the split because those observations were already known.

The fixed catalog contains 72 momentum combinations, four defensive/reversal
rules and two baselines. Momentum choices use six months, twelve months, or
the average rank of three/six/twelve-month returns; the most recent four weeks
are excluded from momentum. Variants use 10/20/40 holdings, an optional
40-week trend filter, equal/inverse-volatility allocations and rebalancing
every four/thirteen weeks. The other rules use low volatility, recent reversal,
the liquid equal-weight universe, or a 10/40-week moving-average trend.

Each rule is scored on training only:

`annualized mean log return − 0.25 × standard deviation of training-era log growth`

The dispersion term uses four consecutive blocks after an initial 20% prefix
of training. It penalizes a high return confined to one era. The top three
rules also form an equal-capital ensemble; it replaces the best single rule
only if its **training** score is higher. The resulting 79th candidate has
weekly rebalancing to its averaged target weights. No validation result is
used in this decision.

The engine also records four expanding-prefix selection diagnostics inside
training. Each reports a previously selected shadow strategy's return in the
next block; these are not a separately executed portfolio and exclude costs
of switching between bots. The main reported portfolios include actual costs.

The training fingerprint and selected parameters are persisted **before**
the validation replay. The selected portfolio continues across the boundary;
its validation curve is rebased for comparison, with no reset of signals or
positions. The full return reconciles exactly to
`(1 + training return) × (1 + validation return) − 1`.

## Selected rules and measured results

These results were computed from the local database on 2026-09-20. Starting
capital is 100,000 in the portfolio's own currency, with 10 basis points per
unit of one-way turnover. No exchange-rate conversion is assumed.

The Nasdaq selection is an equal-capital ensemble of:

- Six-month momentum, top 40, trend filter, equal weights, thirteen-week schedule.
- The same rule using inverse-volatility weights.
- The historically liquid equal-weight universe on a four-week schedule.

The Paris selection uses twelve-month momentum, top 10, a trend filter, equal
weights and a four-week rebalance schedule.

| Market / portfolio | Training return | Validation return | Full return | Full CAGR |
| --- | ---: | ---: | ---: | ---: |
| Nasdaq selected ensemble | +423.13% | +132.83% | +1,118.02% | 13.26% |
| Nasdaq liquid equal weight | +360.03% | +74.18% | +701.30% | 10.92% |
| Nasdaq starting basket buy-and-hold | +429.67% | +97.42% | +945.67% | 12.40% |
| Paris selected momentum | +438.06% | +28.23% | +589.95% | 10.10% |
| Paris liquid equal weight | +150.09% | +29.25% | +223.23% | 6.02% |
| Paris starting basket buy-and-hold | +216.01% | +25.66% | +297.11% | 7.11% |

The Nasdaq selection beat both equal-weight baselines in validation. The Paris
selection **did not beat** the rebalanced equal-weight benchmark in validation,
despite its stronger training return. Neither selection was changed after
reading this outcome. At twice the transaction cost, selected validation
returns were +126.96% for Nasdaq and +23.59% for Paris.

Selected full-history maximum drawdowns were 56.86% (Nasdaq) and 52.08%
(Paris). Their validation maximum drawdowns were 29.19% and 18.61%. These are
substantial declines even though compounded returns are positive.

Saved run IDs:

- Nasdaq: `2f7234d8-ef43-4b35-93b7-9f0db84429b6`
- Paris: `a23fd8d0-85cc-43c3-9d83-2961b8e33ce5`

## Execution and data integrity

- Sunday-UTC Paris bars and Monday Nasdaq bars are aligned to their Friday
  close. The earlier whole-week row wins over duplicate terminal daily quotes.
- Returns use positive, finite adjusted closes; invalid prices are missing,
  never replaced by invented prices or backward-filled before an IPO.
- An instrument needs 52 consecutive prior weekly quotes and at least five
  million in median weekly traded value over 13 weeks. Each date uses at most
  the 500 most liquid eligible instruments **at that date**, not today's sizes.
- A signal observed at close `t` is executed at close `t+1` and first earns
  returns at `t+2`. The price-only model deliberately allows a complete weekly
  bar for execution. This is slower than assuming execution at the same close.
- Holdings drift between rebalances. Entry, exits and drift-induced rebalancing
  incur costs. A fixed-point fee calculation keeps the account self-financing.
- Target momentum allocations are capped at `1 / target holding count`; any
  unused allocation stays in cash. There is no borrowing or short selling.
- Missing quotes cannot be traded. If an owned instrument is unpriced for four
  weeks, it is conservatively written down to zero. This valuation assumption
  is disclosed; no fake market sale is assumed. Neither saved selected run
  required such a write-off.
- Baselines use the same history, execution delay, liquidity constraints and
  costs. The starting-basket buy-and-hold baseline makes only its initial trade.
- The separate Basket comparison tab retains its legacy simulation engine.
  Its historical figures are not directly comparable with the research
  portfolios, which use the corrected accounting and full currency universe.

## Limits on what can be concluded

The database tracks **current** Nasdaq and Paris listings. It does not contain
a complete historical membership/delisting database. Survivorship bias can
inflate every portfolio's return, even with a chronological split. Stored
adjusted prices are current provider revisions, not archived point-in-time
quotes. These experiments therefore establish results conditional on the
available dataset, not an unbiased historical market record.

Fundamentals were deliberately excluded from these twenty-year signals. SEC
coverage starts later and Yahoo statement filing fields are not consistently
actual public release dates. Using current company statements retroactively
would risk look-ahead bias. Current sector labels and future reporting coverage
also do not select investments.

The model assumes zero cash interest, no taxes and a flat transaction-cost
rate. A liquidity threshold is not a full market-impact or execution-capacity
model. USD and EUR portfolios are independent because FX history is absent.
The final 20% has now been inspected: further strategy development must use
new data or a newly designated genuinely unseen evaluation period, rather than
repeatedly tune against these same validation results.

## Research basis and verification

The momentum windows are informed by the standard prior-2-to-12-month
construction in [Kenneth French's momentum methodology](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor_daily.html).
The restricted trend/momentum search also draws on
[AQR's momentum research](https://www.aqr.com/Insights/Research/Journal-Article/Fact-Fiction-and-Momentum-Investing).
Chronological expanding-prefix evaluation follows the principle described by
[scikit-learn's TimeSeriesSplit documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).
These references inform the design; their published performance is not used
as a substitute for results from the local database.

Tests cover future-price/IPO invariance, unchanged selection when validation
prices are perturbed, the persisted freeze before evaluation, interrupted-run
resume without retraining, weekly alignment, missing quotes, initial fees,
drift turnover, execution delays, allocation bounds and return reconciliation.
