# Cheshire Atlas — measured results

Computed on 2026-09-20 using the original experiment's exact stored price
snapshots, weekly execution, initial 100,000 units, and 10 basis points per-side
transaction costs. [Registered methods and complete search history](challenger-research.md).
Original runs and their audit results were not overwritten.

## Bot selected using training only

| Market | Frozen rule | Rebalance | Target name cap | Training score / incumbent |
| --- | --- | --- | --- | ---: |
| NASDAQ / USD | 12–1 momentum, 40 names, inverse-volatility weights | 13 weeks | 5% | 0.10185 / 0.09465 |
| Paris / EUR | 12–1 momentum, 10 names, equal weights | 4 weeks | 10% | 0.10088 / 0.09048 |

Both rank first on the unchanged training-score leaderboard containing 153
recorded configurations: the original 78 rules and ensemble plus the 24 first-
batch and 48 second-batch Atlas rules, plus two third-batch ensembles. Some parameterizations produce identical
portfolios; configuration count is not a count of independent statistical tests.
Signals remain causal. Original capital, universe, dates, fees and execution
delay are shared, and every Atlas training return was reconciled on full replay.

Atlas holds qualifying names until their signal rank falls below twice the
target portfolio size, then fills vacancies. It allocates within position caps
instead of silently leaving clipped inverse-volatility weights as cash. With
too few eligible stocks, excess capital stays in cash. It does not borrow,
short, use future filings, or insert ticker-specific rules.

## Performance against the four original displayed portfolios

| Market | Atlas full-history CAGR | Original selected bot CAGR | Atlas reviewed-period CAGR | Original selected bot reviewed CAGR |
| --- | ---: | ---: | ---: | ---: |
| NASDAQ | 13.63% | 13.26% | 22.40% | 23.40% |
| Paris | 11.98% | 10.10% | 9.61% | 6.38% |

Atlas ranks first by full-history net return against these four portfolios in
both markets. Paris also ranks first in the reviewed 20%; NASDAQ ranks second.
Full-history values from 100,000 are approximately 1.301 million USD and 0.970
million EUR. Those figures include training and are not independent test results.

The return ranking conceals important risk differences. NASDAQ Atlas's maximum
drawdown is 67.87%, versus 56.86% for the original ensemble. Its full-history
Sharpe is 0.585, below the ensemble's 0.606 and starting-basket buy-and-hold's
0.668. Paris Atlas's drawdown is 51.79% and full-history Sharpe 0.620.
Consequently, Atlas is not a winner on every risk measure, period or basket.
The separate arbitrary-basket playground still uses its existing Sharpe score;
it has not been relabeled to manufacture an Atlas win.

## Robustness evidence

The initial cost-aware selection among the 72 base Atlas rules used annual test blocks following
five years of history and a four-week selection gap. Positions continue between
blocks and switches pay actual transaction costs.

| Market | Expanding CAGR | Rolling-five-year CAGR | Matched benchmark CAGR |
| --- | ---: | ---: | ---: |
| NASDAQ | 11.48% | 13.69% | 13.35% |
| Paris | 10.89% | 9.68% | 7.98% |

NASDAQ remains sensitive to selection-window choice. Its expanding and rolling
selection drawdowns were 58.69% and 64.77%. Paris's were 47.44% and 47.83%.
Every selected Atlas bot's reviewed-period 95% excess-growth interval crosses
zero for each tested 4-, 13- and 26-week bootstrap block length. Thus the audit
does not establish a dependable positive edge despite favorable headline ranks.
The intervals condition on the chosen strategy and dataset; they do not correct
for the full adaptive multi-batch research process.

Batch 3 adds two equal-weight ensembles selected from batch-2 training scores.
Neither beats the batch-2 frozen winner's training score, so neither replaces
it. The full training registry expands to 153 configurations. The dashboard's
latest walk-forward diagnostic also considers these ensemble policies, rebuilding
their members inside every preceding selection window. The table above preserves
the original 72-rule diagnostic rather than overwriting an earlier research result.

With those adaptive ensemble policies included, NASDAQ's expanding/rolling CAGRs
are 13.15% / 14.43%, with drawdowns of 55.37% / 68.86%. Paris's are 10.89% / 9.86%,
with drawdowns of 47.44% / 47.83%. The extra compositions improve some realized
selection returns but do not remove risk or establish statistical certainty.
Both fixed bot selections and their reviewed-period comparisons stay unchanged.

The dashboard retains baseline, double/five-times costs, extra-week execution,
shifted rebalance-calendar and removed-top-training-contributor tests, together
with all trial results. It does not replace the frozen winner with a candidate
that looks better after opening evaluation.

## Operational and research limits

The latest holdings are a simulated historical portfolio, not brokerage orders
or a recommendation to buy immediately. Held weights drift after rebalancing.
Present-day tracked listings still omit delisted companies; adjusted prices
are revised data, and market impact, taxes, FX and cash interest are not modeled.
The final 20% has already been examined and remains retrospective. A genuinely
prospective test needs a separately frozen deployment policy and future data.

Use `just challenger` to read/resume the cached experiments. The dashboard and
`/api/research/{run_id}/challenger` expose the full record, including unsuccessful
batch 1, input fingerprints and the time each selection was frozen.
