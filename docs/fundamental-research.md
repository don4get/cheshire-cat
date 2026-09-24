# Matched fundamental research

`cheshire_cat.fundamental_research` evaluates a small predeclared candidate
catalog on the same dates, price observations, universe mask, cash, execution
delay, and transaction cost.

The catalog contains value, value-plus-sales, profitability, balance-sheet,
quality/value, hybrid quality-plus-momentum, price-momentum, and equal-weight
benchmark families. Candidate formulas and feature versions are persisted in a
manifest before the report is produced. Missing or stale fundamentals exclude
the symbol on that decision date; they are never replaced by a current value.

The report includes training/validation metrics, concentration and sector
exposure, feature coverage, feature ablations, doubled-cost and extra-delay
stresses, and a seeded block-bootstrap uncertainty interval. It also emits
expanding and rolling five-year diagnostics with a four-week selection gap and
annual test blocks; these are retrospective robustness checks, not an
untouched holdout. The selected candidate is frozen from the training period;
the primary validation period is a single replay. This is research evidence,
not an investment recommendation or an order instruction.

Add `persist=true` to the API research request to save the immutable manifest
and result in `fundamental_research_runs`; subsequent reads can use the run
helpers in `cheshire_cat.fundamental_research_jobs`.
