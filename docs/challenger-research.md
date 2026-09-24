# Cheshire Atlas: challenger research registry

## Scope and unchanged comparison rules

Develop a new causal, long-only investment bot and compete against the existing
playground candidates on the same stored observations, currencies, start dates,
initial capital, liquidity screen and 10 bp per-side fees. No leverage, shorts,
hand-picked symbols, future fundamentals or retrospective changes to incumbents.
The current history has already been inspected: this is explicitly retrospective
research, even when parameters are selected using only the first 80%.

Research selection retains the original score: annualized mean log growth minus
0.25 times the dispersion of four training-block log-growth rates. The basket
leaderboard retains its original Sharpe score. Neither ranking metric will be
changed to manufacture a win. A higher historical score cannot establish future
dominance. Existing runs and their negative robustness findings remain visible.

## Batch 1 — specified before evaluating these candidates

24 candidates: four signal families × 10/20/40 holdings × two risk policies.
All rebalance every four weeks, cap each name at min(10%, 1/holdings), use
inverse-volatility sizing with a 10% volatility floor, and retain unallocated
capital as cash. Candidates require the same 52 weeks of uninterrupted quotes,
historical liquidity eligibility and positive 12–1 momentum as the incumbents.
Each name must also be above its 40-week moving average.

Signal families, ranked only among currently eligible names:

1. Risk-adjusted momentum: equally weighted percentile ranks of 6–1 and 12–1
   returns divided by observed 26-week volatility.
2. Continuous momentum: half 12–1 momentum rank, half rank of the proportion of
   positive weekly returns during the same formation window. This is a weekly
   adaptation inspired by continuous-information research, not its exact daily
   long/short portfolio replication.
3. Near-high momentum: half momentum rank, half proximity-to-52-week-high rank;
   both formation measures skip the latest four weeks.
4. Consensus: equal blend of the three signal ranks above.

Risk policies: (a) stock-level trend and diversification alone, (b) additionally
halve exposure when a causally constructed broad-market basket is below its
40-week average. Both apply an unlevered 20% annualized volatility ceiling based
on 26 trailing weekly returns of lagged target portfolios; unavailable estimates
use 50% exposure. No fitted future covariance matrix or target-return promise.

Every target uses observed data only and executes at the following weekly close,
earning its first return one week after execution. All candidate scores and
parameters are retained, including failures. The training winner must be frozen
before opening the already-reviewed last 20%; no swapping to an evaluation winner.
Subsequent batches, if needed, must be registered separately with their rationale,
not silently added to an unreported search.

## Batch 2 — training-driven portfolio construction experiment

Batch 1 failed to beat the incumbent training score in either market: best
scores 0.06728 (NASDAQ) and 0.06224 (Paris), versus 0.09465 and 0.09048.
Its winners averaged only 69% and 81% stock exposure. The reviewed final 20%
has not been used to choose this second batch.

Register 48 candidates before execution: signals 6–1 momentum, 12–1 momentum,
risk-adjusted momentum and continuous momentum; 10/20/40 names; four-/13-week
rebalances; equal/inverse-volatility weighting. Retain the same entry filters,
universe and timing. Replace the batch-1 clipped allocations with capped
proportional allocation that redistributes excess weight, using maximum name
weight min(10%, 2/holdings). With too few eligible names, residual capital stays
in cash. Remove the additional portfolio volatility ceiling and market exposure
overlay to test whether stock-level trend/diversification suffice; this can
increase drawdowns and must be measured, not described as an improvement a priori.
At rebalance retain qualifying holdings until they fall below twice the target
rank, then fill vacancies. This fixed rank buffer seeks to lower unnecessary
turnover. Batch 1 remains immutable under `atlas-batch1-v1`; batch 2 is
`atlas-batch2-v1`. The cumulative new search now contains 72 rules per market.

## Batch 3 — registered ensemble extension

Batch 2 leads full-history return and training scores in both markets, but its
NASDAQ frozen winner trails the original ensemble in the already-reviewed
evaluation period (22.40% versus 23.40% CAGR) and has a 67.87% full drawdown.
The decision to research ensembles is made with that knowledge. This adds
researcher-level hindsight; it must not be presented as a clean holdout result.

Register exactly two compositions, with no optimized mixture coefficients:
(1) equally weight the three best structurally distinct batch-2 rules by the
unchanged training score; (2) equally weight the highest-scoring batch-2 rule
from each of its four signal families. Ten-name equal and inverse-volatility
rules are structurally identical under the 10% cap, so count as one sleeve.
Members retain their own target calendars; the combined portfolio rebalances
weekly, paying actual drift/reallocation costs. No leverage or added assets.
Compare their training scores with the two earlier frozen batch winners before
evaluating the chosen result. Retain all previous trial records. Cumulative
search: 74 Atlas configurations plus the original 79, or 153 configurations.

For walk-forward diagnostics, reconstruct these ensembles separately inside
each eligible preceding selection window. Never reuse the final ensemble's
2022-selected members when simulating an earlier selection decision. Compare
each reconstructed ensemble's preceding score against the best base rule,
then execute the chosen composition in the next test block.

## Research grounding and transfer limits

- [Ken French momentum construction](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor_daily.html): established prior 2–12 month formation convention. Our portfolios are long-only, not the academic long/short factor.
- [Da, Gurun & Warachka, continuous information and momentum](https://business.uq.edu.au/sites/default/files/events/files/mitch-warachka-paper.pdf): motivates checking whether gains arrived gradually rather than through isolated jumps. Weekly observations are a coarser proxy.
- [George & Hwang, the 52-week high](https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf): motivates the near-high signal. This does not validate our blend or cash policy.
- [Moreira & Muir, volatility-managed portfolios](https://www.nber.org/papers/w22208): motivates reducing exposure as estimated risk rises. Our unlevered volatility ceiling is not their exact strategy.
- [Hurst, Ooi & Pedersen, trend-following evidence](https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing): motivates trend diversification and defensive exposure. Their multi-asset futures evidence does not directly establish a long-only stock-market edge.

Survivorship bias, revised adjusted prices, uncalibrated impact, cash yield, taxes
and missing point-in-time fundamentals remain limitations. This work produces
research portfolios and suggested allocations, never brokerage orders.
