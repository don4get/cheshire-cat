# Dashboard acronym glossary

This glossary covers abbreviations and shorthand shown in the dashboard UI,
including values that can arrive dynamically from the fundamentals and research
APIs. Company tickers, run IDs, CSS classes, and internal field names are not
acronyms and are not listed here.

## Financial metrics and ratios

| Label | Meaning | What it means in the dashboard |
| --- | --- | --- |
| **CAGR** | Compound Annual Growth Rate | The constant yearly compounded growth rate over a period. It is calculated as `(ending value / starting value)^(1 / years) - 1`; it is not the same as a simple average of yearly returns. |
| **P/E** | Price-to-Earnings | Share price divided by earnings per share. A higher value means investors are paying more for each unit of reported earnings. |
| **P/S** | Price-to-Sales | Market value divided by revenue, or equivalently price per share divided by sales per share. |
| **P/B** | Price-to-Book | Market value divided by shareholders’ equity, or equivalently price per share divided by book value per share. |
| **EV** | Enterprise Value | An estimate of the value of the operating business: market capitalization plus debt minus cash. It appears in **EV/EBITDA**. |
| **EBITDA** | Earnings Before Interest, Taxes, Depreciation, and Amortization | A pre-interest, pre-tax operating earnings measure. It is useful for comparison, but it is not the same as cash flow. |
| **EV/EBITDA** | Enterprise Value / Earnings Before Interest, Taxes, Depreciation, and Amortization | Enterprise value divided by EBITDA; a valuation multiple that includes debt and cash in the numerator. |
| **EPS** | Earnings Per Share | Profit allocated to each share. Fundamental records may identify **Basic EPS** or **Diluted EPS**. |
| **ROE** | Return on Equity | Net income divided by shareholders’ equity; a measure of the return generated on owners’ capital. |
| **ROA** | Return on Assets | Net income divided by total assets; a measure of how efficiently the asset base generates profit. |
| **FCF** | Free Cash Flow | Cash generated after the cash needed to operate and maintain the business. The dashboard shows **FCF margin**, which is FCF divided by revenue. |
| **P&L** | Profit and Loss | The income or loss produced by a position or portfolio. The research audit uses training P&L when describing its stock-removal stress test. |
| **bps** | Basis points | A unit for small rates: 1 bp is 0.01%, so 100 bps equals 1%. The transaction-cost fields use bps per unit of turnover. |
| **pp** | Percentage points | The difference between two percentages. For example, 8% minus 5% is 3 pp, not a 3% relative return. |
| **p-value** | Probability-value (usually written with a lowercase *p*) | A measure calculated under a specified null hypothesis. The dashboard explicitly warns that its p estimate is not the probability of future live success. |

## Data, storage, and web terms

| Label | Meaning | What it means in the dashboard |
| --- | --- | --- |
| **API** | Application Programming Interface | The service the dashboard calls to load prices, fundamentals, filings, portfolios, and research results. |
| **HTTP** | Hypertext Transfer Protocol | The web protocol named in connection errors such as “API returned HTTP 500.” The number is the server’s status code. |
| **JSON** | JavaScript Object Notation | The structured data format returned by the API; the research pages also offer complete research JSON links. |
| **SEC** | U.S. Securities and Exchange Commission | The U.S. regulator and source for the issuer filings and company facts shown in the reports and fundamentals views. |
| **XBRL** | eXtensible Business Reporting Language | A structured reporting format used to tag financial facts, allowing the dashboard to display and calculate from concepts such as revenue, assets, and EPS. |
| **SQL** | Structured Query Language | The language used to query relational databases. It is part of the name **PostgreSQL**, the database displayed in the dashboard’s connection and data-source labels. |
| **PostgreSQL** | A relational database system (not itself an acronym) | The database that stores the dashboard’s prices, fundamentals, filings, portfolio data, and research results. “SQL” is the acronym contained in the name. |

## Markets, currencies, and time windows

| Label | Meaning | What it means in the dashboard |
| --- | --- | --- |
| **NASDAQ / Nasdaq** | Historically, National Association of Securities Dealers Automated Quotations | The Nasdaq market universe. “Nasdaq” is now the brand’s normal styling rather than an expansion users need to interpret literally. |
| **USD** | United States dollar | The standardized currency code used for the Nasdaq research universe and dollar-denominated portfolio values. |
| **EUR** | Euro | The standardized currency code used for the Paris research universe and euro-denominated portfolio values. |
| **1W** | One week | The price-chart window containing roughly one week of sessions. |
| **1M** | One month | The price-chart window containing roughly one month of sessions. In this chart control, **M means month**, not million. |
| **1Y** | One year | The one-year chart or return window. |
| **2Y** | Two years | The two-year price-chart window. |
| **5Y** | Five years | The five-year price-chart window; the research audit also uses five-year rolling windows. |
| **20Y** | Twenty years | The full research horizon requested or displayed by the research views. |
| **MAX** | Maximum available history | The price-chart option that uses all stored observations rather than a fixed time window. |
| **80/20** | 80% training / 20% evaluation | The chronological research split: the bot is selected using the first 80% and then reviewed on the later 20%. The dashboard also calls the second portion “validation.” |

`PA` in examples such as `MC.PA` and `OR.PA` is a Paris-market ticker suffix,
not a financial acronym. `Euronext Paris` is the exchange name; `EUR` is the
currency code.

## Related labels that are not acronyms

- **Sharpe ratio:** a risk-adjusted return measure based on return relative to volatility. The dashboard’s “zero cash yield” wording means it uses a zero reference cash/risk-free yield in that display.
- **Drawdown:** the decline from a previous peak; maximum drawdown is the worst such decline in the selected period.
- **Volatility:** the variability of returns, annualized when the dashboard says “annualized.”
- **Exposure:** the average fraction of capital invested rather than held as cash.
- **Turnover:** the amount of the portfolio traded during a period, used to apply transaction costs.
- **Benchmark:** a reference portfolio used for comparison.
