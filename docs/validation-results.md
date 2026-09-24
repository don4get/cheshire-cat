# Robustness audit findings

Computed 2026-09-20 from the exact saved real-price snapshots. Protocol:
[`robustness-audit-v1`](validation-protocol.md). No original selection, training
score or result was changed. All 78 base rules per market reconciled against
their saved training returns before the audit proceeded.

## The original result was insufficient evidence

The original chronological split avoids selecting parameters on the last 20%,
but it offers only one late-period evaluation window (2022-09-23 to 2026-09-18).
The four training blocks are tuning diagnostics, not independent tests. The
old walk-forward summary splices shadow-strategy returns without paying to
switch portfolios. Searching 78 base rules plus an adaptive ensemble also
creates selection bias. Today's survivor-only universe compounds these limits.

Because the original evaluation has been inspected, none of the new results
should be called an untouched holdout. Even chronological walk-forward here
is a retrospective audit of an algorithm designed with historical knowledge.

## Cost-aware walk-forward selection

Both protocols start with 260 selection weeks, leave a four-week selection
gap, and test the next 52 weeks. At each boundary they rescore the saved base
rules on the eligible past and rebuild that fold's top-three ensemble. A
single continuing portfolio executes the selected targets and pays fees for
all reallocations. Benchmark entry and test dates match. There are 15 annual
blocks per market, starting in September 2011 and ending September 2026.

| Market | Expanding CAGR | Rolling 5Y CAGR | Benchmark CAGR | Expanding / rolling max drawdown |
| --- | ---: | ---: | ---: | ---: |
| NASDAQ / USD | 9.73% | 8.47% | 13.35% | −69.49% / −62.68% |
| Paris / EUR | 8.99% | 5.85% | 7.98% | −52.07% / −47.62% |

NASDAQ beat the benchmark in only 5/15 blocks under either protocol. Paris
won 9/15 expanding and 6/15 rolling blocks. The benchmark drawdowns were 41.27%
and 36.35%, respectively. These results do not support a claim that the current
selection algorithm reliably improves on equal weighting. Paris's small
expanding advantage is sensitive to the selection window and comes with a
larger drawdown.

## Uncertainty and model-search bias

For each market, all three frozen finalists have a 95% excess-growth interval
crossing zero for at least one of the 4-, 13- and 26-week block lengths.
The NASDAQ ensemble's reviewed-period annualized relative growth was 7.49%;
its 13-week-block interval is −1.80% to +18.90%. Its 26-week interval is barely
positive, illustrating sensitivity to the dependence assumption. The selected
Paris rule's estimate was −0.20%, with a 13-week interval of −13.40% to +14.19%.
Relative growth here is exp(mean(log bot − log benchmark) × 52) − 1, not the
arithmetic difference between their CAGRs.

The joint centered 13-week block-bootstrap maximum-mean diagnostic across 78
base rules yielded p estimates of 0.970 for NASDAQ and 0.383 for Paris (1,000
replicates). Neither provides compelling evidence against its no-base-rule-edge
null. This diagnostic does not correct for adaptive ensembles or unrecorded
human experimentation; it is not DSR or a probability of future success.

## Execution sensitivity

The selected NASDAQ ensemble still beats its matched benchmark in the reviewed
period under all five stresses, but shifting rebalances by one week reduces
its excess CAGR from 8.60 to 4.24 percentage points. Its much weaker historical
selection process remains an important counterweight to that recent result.

The selected Paris rule's excess CAGR ranges from −3.52 points at five-times
costs to +7.08 points with a shifted calendar. That spread is a warning about
timing sensitivity, not a reason to optimize the calendar on these observations.

The largest positive training contributors were MARA (NASDAQ finalists) and
VLA.PA (Paris finalists). Removing their allocations leaves cash rather than
selecting replacement stocks. VLA.PA removal does not change the Paris finalists'
reviewed-period returns: it did not drive those returns. This does not establish
that training performance was independent of that stock.

## What would strengthen the evidence next?

Obtain historical membership and delisted-security data, point-in-time price
and corporate-action archives, and a calibrated execution/market-impact model.
Predeclare any revised algorithm and risk constraints, then collect genuinely
future observations after the last stored bar. Do not choose a new model by
maximizing the audit scores on this same already-examined history.

Reproduce or read the cached audits with `just validate`; inspect them in
Playground → Robustness & validation. Full fold ledgers, candidate diagnostics,
stress results and input fingerprints are available through the audit API.
