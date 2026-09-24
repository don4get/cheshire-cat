# Retrospective robustness protocol v1

This protocol was specified before running the new diagnostics. The original
2022–2026 evaluation has already been inspected and cannot become an untouched
test again. This audit must not modify any saved candidate, selection, training
score or original result. New outcomes are retrospective research evidence.

The original 80/20 split is chronological, but its single late-period window
does not test every market regime. The four score blocks are used for tuning.
The original walk-forward rows splice shadow returns without switching costs.
The 79-way search, correlated strategies and survivor-only universe further
limit what the original comparison can establish.

The expanded protocol uses:

- Expanding and rolling-five-year selection windows. Start with five years,
  exclude the latest four weeks from model-selection scores, select once per
  52-week test block, and continue the executed portfolio between blocks.
  Rebalance into each new selection and charge actual switching costs.
  Indicators may use already observed prices in the four-week selection gap.
  The gap separates selection from evaluation; no overlapping forward labels
  are fitted by these deterministic strategies.
- At every fold, rescore all 78 original base rules using only preceding
  returns. Rebuild that fold's top-three ensemble and compare its preceding
  score with the best single rule, as in the original selection procedure.
  Neither the eventual top-three list nor full-history rankings choose a fold.
- Paired circular-block bootstrap intervals for annualized relative log
  growth on the already-reviewed evaluation period. Use 4-, 13- and 26-week
  blocks, 1,000 replicates and a fixed seed. Intervals are conditional on this
  dataset, chosen strategy and resampling model, not a guarantee or posterior
  probability that the strategy works.
- A joint centered 13-week block-bootstrap maximum-mean test across the 78
  base rules on training, relative to the liquid equal-weight benchmark.
  Joint resampling preserves dependence between strategies. The family-wise
  null is that no base rule has positive expected excess log growth. This
  diagnostic excludes the adaptive ensemble and unrecorded human research;
  it is not a complete correction for all prior experimentation.
- For the three frozen finalists: replay at 1x, 2x and 5x transaction costs;
  an extra week of execution delay; a one-week shifted rebalance calendar;
  and removal of the largest positive training-period P&L contributor, leaving
  its allocation as cash. Baseline costs and timing are matched for each
  comparison. The removed name is identified from training only.
- Report overlapping rolling-one-year results, predefined crisis windows,
  and one-parameter-neighbor training performance. These are sensitivity
  diagnostics, not independent tests or a new optimization objective.

Survivorship bias, current adjusted-price revisions, missing historical
membership/delistings, FX, and a calibrated market-impact model remain data or
execution gaps. Retrospective checks cannot close them. A new independently
frozen strategy needs genuinely future observations after the last stored bar.

Design references: [chronological splits with a gap](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html),
[selection bias and non-normal return concerns](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf),
and [transaction-cost and market-impact models](https://www.cvxportfolio.com/en/stable/costs.html).
The implementation uses a joint block-bootstrap test, not the Deflated Sharpe
Ratio formula; these references motivate the audit rather than validate it.
