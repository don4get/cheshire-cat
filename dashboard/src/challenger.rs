use crate::performance::{return_class, IntervalValues, ReturnValue};
use crate::{format_cash, EquityPoint, PlaygroundChart, PlaygroundMetrics, PlaygroundStrategy};
use dioxus::prelude::*;
use serde::Deserialize;

#[derive(Clone, Default, Deserialize, PartialEq)]
#[serde(default)]
struct State {
    status: String,
    progress: String,
    error: Option<String>,
    report: Option<Report>,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
struct Report {
    version: String,
    currency: String,
    initial_cash: f64,
    transaction_cost: f64,
    training_rank: usize,
    training_competitors: usize,
    performance_competitors: usize,
    selection: Selection,
    split: Split,
    performance_ranks: Ranks,
    strategies: Vec<Strategy>,
    leaderboard: Vec<TrainingRow>,
    trials: Vec<Trial>,
    walk_forward: Vec<WalkForward>,
    intervals: Vec<Interval>,
    stresses: Vec<Stress>,
    holdings: Vec<Holding>,
    holdings_date: String,
    cash_weight: f64,
    removed_contributor: Option<String>,
    limitations: Vec<String>,
    data_fingerprint: String,
    completed_at: String,
}
#[derive(Clone, Default, Deserialize, PartialEq)]
struct Split {
    training_periods: usize,
    training_start: String,
    training_end: String,
    validation_start: String,
    validation_end: String,
}
#[derive(Clone, Default, Deserialize, PartialEq)]
struct Selection {
    winner: Winner,
    frozen_at: String,
}
#[derive(Clone, Default, Deserialize, PartialEq)]
struct Winner {
    id: String,
    score: f64,
    parameters: Rule,
}
#[derive(Clone, Default, Deserialize, PartialEq)]
#[serde(default)]
struct Rule {
    signal: String,
    holdings: usize,
    rebalance: usize,
    weighting: String,
    construction: String,
}
#[derive(Clone, Default, Deserialize, PartialEq)]
struct Ranks {
    training: usize,
    validation: usize,
    full: usize,
}
#[derive(Clone, Default, Deserialize, PartialEq)]
struct Strategy {
    id: String,
    name: String,
    training: PlaygroundMetrics,
    validation: PlaygroundMetrics,
    full: PlaygroundMetrics,
    curve: Vec<EquityPoint>,
}
#[derive(Clone, Default, Deserialize, PartialEq)]
struct TrainingRow {
    rank: usize,
    id: String,
    score: f64,
    source: String,
}
#[derive(Clone, Default, Deserialize, PartialEq)]
struct Trial {
    id: String,
    score: f64,
    training: PlaygroundMetrics,
    validation: PlaygroundMetrics,
    full: PlaygroundMetrics,
}
#[derive(Clone, Default, Deserialize, PartialEq)]
struct WalkForward {
    name: String,
    metrics: PlaygroundMetrics,
    benchmark: PlaygroundMetrics,
    winning_folds: usize,
    folds: Vec<Fold>,
}
#[derive(Clone, Default, Deserialize, PartialEq)]
struct Fold {
    selected_id: String,
    members: Vec<String>,
    train_end: String,
    test_start: String,
    test_end: String,
    total_return: f64,
    benchmark_return: f64,
}
#[derive(Clone, Default, Deserialize, PartialEq)]
struct Interval {
    block_weeks: usize,
    estimate: f64,
    lower: f64,
    upper: f64,
}
#[derive(Clone, Default, Deserialize, PartialEq)]
struct Stress {
    label: String,
    metrics: PlaygroundMetrics,
    benchmark: PlaygroundMetrics,
    excess_cagr: f64,
}
#[derive(Clone, Default, Deserialize, PartialEq)]
struct Holding {
    symbol: String,
    weight: f64,
}

#[component]
pub fn ChallengerLab(run_id: String) -> Element {
    let mut state = use_signal(State::default);
    let mut error = use_signal(|| None::<String>);
    let mut launch = use_signal(|| 0usize);
    let request_id = run_id.clone();
    let _reader = use_resource(move || {
        let id = request_id.clone();
        let attempt = launch();
        async move {
            error.set(None);
            if attempt > 0 {
                if let Err(message) = request(&id, true).await {
                    error.set(Some(message));
                    return;
                }
            }
            loop {
                match request(&id, false).await {
                    Ok(loaded) => {
                        let done =
                            matches!(loaded.status.as_str(), "ready" | "failed" | "not_started");
                        state.set(loaded);
                        if done {
                            break;
                        }
                    }
                    Err(message) => {
                        error.set(Some(message));
                        break;
                    }
                }
                #[cfg(target_arch = "wasm32")]
                gloo_timers::future::TimeoutFuture::new(2000).await;
                #[cfg(not(target_arch = "wasm32"))]
                break;
            }
        }
    });
    let saved = state();
    rsx! {
        if let Some(report) = saved.report {
            ChallengerResults { report, run_id }
        } else {
            section { class: "panel audit-intro",
                span { class: "section-kicker", "NEW CHALLENGER" }, h2 { "Cheshire Atlas" }
                p { "Momentum with explicit position limits, a rank buffer to reduce turnover, and a fully recorded research history. Compete against the original bots without changing their results." }
                p { class: "audit-caution", "This is retrospective research, not a new untouched evaluation. No brokerage orders are placed." }
                if let Some(message) = error().or(saved.error) { p { class: "negative", "{message}" } }
                p { role: "status", aria_live: "polite", "{saved.progress}" }
                button { class: "primary-button", onclick: move |_| launch += 1, "Run / resume Atlas research" }
            }
        }
    }
}

#[component]
pub fn ChallengerSummary(run_id: String, on_open: EventHandler<()>) -> Element {
    let mut state = use_signal(State::default);
    let mut error = use_signal(|| None::<String>);
    let mut launch = use_signal(|| 0usize);
    let request_id = run_id.clone();
    let _reader = use_resource(move || {
        let id = request_id.clone();
        let attempt = launch();
        async move {
            error.set(None);
            if attempt > 0 {
                if let Err(message) = request(&id, true).await {
                    error.set(Some(message));
                    return;
                }
            }
            loop {
                match request(&id, false).await {
                    Ok(loaded) => {
                        let done =
                            matches!(loaded.status.as_str(), "ready" | "failed" | "not_started");
                        state.set(loaded);
                        if done {
                            break;
                        }
                    }
                    Err(message) => {
                        error.set(Some(message));
                        break;
                    }
                }
                #[cfg(target_arch = "wasm32")]
                gloo_timers::future::TimeoutFuture::new(2000).await;
                #[cfg(not(target_arch = "wasm32"))]
                break;
            }
        }
    });
    let saved = state();
    rsx! {
        if let Some(report) = saved.report {
            ChallengerSummaryResults { report, on_open }
        } else {
            section { class: "panel atlas-summary",
                div { class: "panel-header",
                    div { h2 { "Cheshire Atlas challenger" }, p { "The frozen portfolio comparison is also available alongside the performance and portfolio timeline." } }
                    span { class: "audit-status", "RESEARCH ONLY" }
                }
                if let Some(message) = error().or(saved.error) { p { class: "negative", "{message}" } }
                p { role: "status", aria_live: "polite", "{saved.progress}" }
                button { class: "primary-button", onclick: move |_| launch += 1, "Run / resume Atlas research" }
            }
        }
    }
}

#[component]
fn ChallengerSummaryResults(report: Report, on_open: EventHandler<()>) -> Element {
    let candidate_id = report.selection.winner.id.clone();
    let atlas = report
        .strategies
        .iter()
        .find(|strategy| strategy.id == candidate_id)
        .cloned()
        .or_else(|| report.strategies.first().cloned())
        .unwrap_or_default();
    let mut ordered = report.strategies.clone();
    ordered.sort_by(|a, b| b.full.total_return.total_cmp(&a.full.total_return));
    let atlas_rank = ordered
        .iter()
        .position(|strategy| strategy.id == atlas.id)
        .map(|rank| rank + 1)
        .unwrap_or_default();
    rsx! {
        section { class: "panel atlas-summary",
            div { class: "panel-header",
                div { h2 { "Cheshire Atlas challenger" }, p { "Atlas versus the incumbent portfolios, shown here without leaving Performance & portfolios." } }
                span { class: "audit-status", "RESEARCH ONLY" }
            }
            div { class: "atlas-summary-stats",
                div { span { "Full-history rank" }, strong { "#{atlas_rank} / {ordered.len()}" } }
                div { span { "Atlas CAGR" }, strong { ReturnValue { value: atlas.full.annualized_return } } }
                div { span { "Atlas drawdown" }, strong { ReturnValue { value: atlas.full.max_drawdown } } }
                div { span { "Atlas Sharpe" }, strong { "{atlas.full.sharpe:.2}" } }
            }
            div { class: "table-scroll", table { class: "data-table atlas-summary-table",
                thead { tr { th { "Rank / strategy" }, th { "Full CAGR" }, th { "Drawdown" }, th { "Sharpe" }, th { "Ending value" } } }
                tbody { for (rank, strategy) in ordered.iter().enumerate() {
                    tr { class: if strategy.id == atlas.id { "atlas-selected" } else { "" },
                        td { strong { "#{rank + 1} {strategy.name}" }, if strategy.id == atlas.id { small { "Atlas" } } }
                        td { ReturnValue { value: strategy.full.annualized_return } }
                        td { ReturnValue { value: strategy.full.max_drawdown } }
                        td { "{strategy.full.sharpe:.2}" }
                        td { "{format_cash(strategy.full.final_value)} {report.currency}" }
                    }
                } }
            } }
            button { class: "period-button atlas-summary-open", onclick: move |_| on_open.call(()), "Open full Atlas challenger →" }
        }
    }
}

fn period_metrics(strategy: &Strategy, period: &str) -> PlaygroundMetrics {
    match period {
        "training" => strategy.training.clone(),
        "validation" => strategy.validation.clone(),
        _ => strategy.full.clone(),
    }
}

#[component]
fn ChallengerResults(report: Report, run_id: String) -> Element {
    let mut period = use_signal(|| "full".to_string());
    let mut filter = use_signal(String::new);
    let mut show_trials = use_signal(|| false);
    let chosen = report.strategies.first().cloned().unwrap_or_default();
    let rule = report.selection.winner.parameters.clone();
    let signal_label = rule.signal.replace('_', " ");
    let weighting_label = rule.weighting.replace('_', " ");
    let candidate_id = report.selection.winner.id.clone();
    let contributor = report
        .removed_contributor
        .clone()
        .unwrap_or_else(|| "none".into());
    let mut ordered = report.strategies.clone();
    ordered.sort_by(|a, b| {
        period_metrics(b, &period())
            .total_return
            .total_cmp(&period_metrics(a, &period()).total_return)
    });
    let start = if period() == "validation" {
        report.split.training_periods
    } else {
        0
    };
    let chart: Vec<PlaygroundStrategy> = report
        .strategies
        .iter()
        .map(|row| {
            let end = if period() == "training" {
                1 + report.split.training_periods
            } else {
                row.curve.len()
            };
            PlaygroundStrategy {
                id: row.id.clone(),
                name: row.name.clone(),
                is_benchmark: row.id != candidate_id,
                curve: row
                    .curve
                    .iter()
                    .skip(start)
                    .take(end - start)
                    .cloned()
                    .collect(),
                ..Default::default()
            }
        })
        .collect();
    let query = filter().to_lowercase();
    let leaderboard: Vec<_> = report
        .leaderboard
        .iter()
        .filter(|row| {
            row.id.to_lowercase().contains(&query) || row.source.to_lowercase().contains(&query)
        })
        .collect();
    let metrics = period_metrics(&chosen, &period());
    rsx! {
        section { class: "panel atlas-hero",
            div { class: "panel-header", div { span { class: "section-kicker", "THE NEW CHALLENGER" }, h2 { "Cheshire Atlas" } }, span { class: "audit-status", "RESEARCH ONLY" } }
            p { "Established momentum ideas, explicit portfolio construction, and an honest comparison with the incumbent bots." }
            div { class: "audit-findings",
                div { strong { "#{report.training_rank} / {report.training_competitors}" }, span { "unchanged training-score ranking" }, small { "Includes all recorded batches and original candidates" } }
                div { strong { "#{report.performance_ranks.full} / {report.performance_competitors}" }, span { "full-history return ranking" }, small { "Against the four previously displayed portfolios" } }
                div { strong { "#{report.performance_ranks.validation} / {report.performance_competitors}" }, span { "already-reviewed evaluation ranking" }, small { "Not used to replace the frozen training winner" } }
            }
            div { class: "audit-caution",
                strong { "A historical lead is not proof of a dependable edge." }
                p { "Full-history drawdown: ", ReturnValue { value: chosen.full.max_drawdown }, ". Bootstrap intervals and walk-forward results below can contradict the headline ranking. This history has already been used in research." }
            }
            p { class: "audit-rule", "{candidate_id}" }
            div { class: "atlas-rule-grid",
                div { strong { "Signal" }, span { "{signal_label}" } }
                div { strong { "Portfolio" }, span { "Up to {rule.holdings} names · {weighting_label}" } }
                div { strong { "Rebalance" }, span { "Every {rule.rebalance} weeks · one-week execution delay" } }
                div { strong { "Construction" }, span { if rule.construction == "bounded" { "Long-only, no leverage · bounded allocations · rank buffer" } else if rule.construction == "ensemble" { "Equal-weight model sleeves · each retains its own target calendar" } else { "Long-only, no leverage · clipped weights · volatility ceiling" } } }
            }
            if rule.construction == "bounded" {
                p { class: "research-note", "The winning batch keeps qualifying stocks until they leave the top twice-target rank, then fills vacancies. Excess allocations are redistributed within name limits; genuinely unallocated capital stays in cash. No ticker-specific exceptions." }
            } else {
                p { class: "research-note", if rule.construction == "ensemble" { "Component rules are selected using training scores only. Their target weights are averaged without leverage, and the combined portfolio pays actual weekly reallocation costs." } else { "The first batch clips allocations at position limits and reduces exposure using trailing volatility. All unallocated capital stays in cash. No ticker-specific exceptions." } }
            }
        }
        section { class: "panel atlas-performance",
            div { class: "panel-header", div { h2 { "Atlas versus the incumbent portfolios" }, p { "Same stored prices, currency, capital and trading costs. Sorted by net return for the selected period; the bot's parameters stay frozen." } } }
            div { class: "audit-tabs", role: "group", aria_label: "Atlas comparison period",
                for (key,label) in [("full","Full 20Y · includes training"),("training","Training"),("validation","Reviewed evaluation")] {
                    button { class: if period() == key { "period-button active" } else { "period-button" }, aria_pressed: "{period() == key}", onclick: move |_| period.set(key.into()), "{label}" }
                }
            }
            div { class: "audit-rolling",
                div { class: "performance-tile {return_class(metrics.total_return)}", span { "Atlas net return" }, strong { ReturnValue { value: metrics.total_return } } }
                div { class: "performance-tile {return_class(metrics.annualized_return)}", span { "Annualized return" }, strong { ReturnValue { value: metrics.annualized_return } } }
                div { class: "performance-tile {return_class(metrics.max_drawdown)}", span { "Maximum drawdown" }, strong { ReturnValue { value: metrics.max_drawdown } } }
                div { span { "Sharpe · zero cash yield" }, strong { "{metrics.sharpe:.2}" } }
            }
            div { class: "table-scroll", table { class: "data-table audit-table atlas-comparison",
                thead { tr { th { "Rank / strategy" }, th { "Net return" }, th { "CAGR" }, th { "Drawdown" }, th { "Sharpe" }, th { "Ending value" } } }
                tbody { for (i,row) in ordered.iter().enumerate() {
                    tr { class: if row.id == candidate_id { "atlas-selected" } else { "" },
                        td { strong { "#{i + 1} {row.name}" }, if row.id == candidate_id { small { "Frozen Atlas choice" } } }
                        td { ReturnValue { value: period_metrics(row, &period()).total_return } }, td { ReturnValue { value: period_metrics(row, &period()).annualized_return } }
                        td { ReturnValue { value: period_metrics(row, &period()).max_drawdown } }, td { "{period_metrics(row, &period()).sharpe:.2}" }, td { "{format_cash(period_metrics(row, &period()).final_value)} {report.currency}" }
                    }
                } }
            } }
            PlaygroundChart { strategies: chart }
            p { class: "research-note", "Curves rebased to 100. Capital: {format_cash(report.initial_cash)} {report.currency}; {report.transaction_cost * 10000.0:.0} basis points per side. Segment ending values rebase carried returns to the same starting capital; positions do not reset at evaluation." }
        }
        section { class: "panel",
            div { class: "panel-header", div { h2 { "Does selection work across time?" }, p { "Every fold selects from all recorded Atlas configurations using only preceding returns: five years minimum history, a four-week selection gap, then a 52-week test. Actual portfolio-switching costs are charged." } } }
            div { class: "audit-protocol-cards",
                for row in &report.walk_forward {
                    article { class: "audit-protocol-card",
                        h3 { "{row.name}" }
                        div { class: "audit-return", ReturnValue { value: row.metrics.annualized_return }, small { "annualized net return" } }
                        div { class: "research-check", span { "Benchmark CAGR" }, strong { ReturnValue { value: row.benchmark.annualized_return } } }
                        div { class: "research-check", span { "Excess CAGR" }, strong { ReturnValue { value: row.metrics.annualized_return - row.benchmark.annualized_return, points: true } } }
                        div { class: "research-check", span { "Maximum drawdown" }, strong { ReturnValue { value: row.metrics.max_drawdown } } }
                        div { class: "research-check", span { "Blocks beating benchmark" }, strong { "{row.winning_folds} / {row.folds.len()}" } }
                        details { class: "audit-folds", summary { "Inspect fold selections" }, div { class: "table-scroll", table { class: "data-table atlas-fold-table",
                            thead { tr { th { "Training ends" }, th { "Next test" }, th { "Selected rule" }, th { "Return / benchmark" } } }
                            tbody { for fold in &row.folds { tr { td { "{fold.train_end}" }, td { "{fold.test_start} — {fold.test_end}" }, td { "{fold.selected_id}", if fold.members.len() > 1 { for member in &fold.members { small { "{member}" } } } }, td { ReturnValue { value: fold.total_return }, " / ", ReturnValue { value: fold.benchmark_return } } } } }
                        } } }
                    }
                }
            }
            p { class: "research-note", "These are retrospective selection diagnostics, not the historical performance of the final fixed bot chosen using data through 2022. Ensemble members are rebuilt inside each earlier selection window. The strategy family itself was designed with historical knowledge." }
        }
        section { class: "panel",
            h2 { "Uncertainty and execution stress" }
            p { class: "research-note", "Already-reviewed evaluation only. Paired circular-block bootstrap: 95% intervals for annualized relative growth exp(mean(log bot − log benchmark) × 52) − 1. Conditional estimates, not adjusted for the whole adaptive research search." }
            div { class: "audit-intervals", for ci in &report.intervals {
                article { class: "audit-interval", strong { "{ci.block_weeks}-week blocks" }, IntervalValues { estimate: ci.estimate, lower: ci.lower, upper: ci.upper } }
            } }
            div { class: "table-scroll", table { class: "data-table audit-table",
                thead { tr { th { "Stress" }, th { "Net return" }, th { "CAGR" }, th { "Benchmark CAGR" }, th { "Excess CAGR" }, th { "Drawdown" } } }
                tbody { for row in &report.stresses { tr { td { "{row.label}" }, td { ReturnValue { value: row.metrics.total_return } }, td { ReturnValue { value: row.metrics.annualized_return } }, td { ReturnValue { value: row.benchmark.annualized_return } }, td { ReturnValue { value: row.excess_cagr, points: true } }, td { ReturnValue { value: row.metrics.max_drawdown } } } } }
            } }
            p { class: "research-note", "Costs and timing are matched for the benchmark. Stock-removal test: {contributor}, selected from training P&L only, with its allocation left in cash; benchmark unchanged in this test." }
        }
        section { class: "panel atlas-training",
            div { class: "panel-header", div { h2 { "The complete training leaderboard" }, p { "Original score unchanged: annualized log growth minus 0.25 × variation across four training eras. All research batches remain visible—including unsuccessful alternatives." } } }
            input { class: "timeline-filter", r#type: "search", aria_label: "Filter Atlas leaderboard", value: "{filter}", placeholder: "Search any original or Atlas rule…", oninput: move |event| filter.set(event.value()) }
            div { class: "table-scroll training-table", table { class: "data-table audit-table atlas-training-table",
                thead { tr { th { "Rank" }, th { "Configuration" }, th { "Recorded batch" }, th { "Training score" } } }
                tbody { for row in leaderboard { tr { class: if row.id == candidate_id { "atlas-selected" } else { "" }, td { "#{row.rank}" }, td { "{row.id}" }, td { "{row.source}" }, td { "{row.score:.5}" } } } }
            } }
            button { class: "period-button atlas-trials-toggle", aria_expanded: "{show_trials()}", onclick: move |_| show_trials.toggle(), "Inspect all {report.trials.len()} new trials" }
            if show_trials() {
                p { class: "research-note", "Recorded order, not evaluation ranking. Some parameter configurations produce identical portfolios. These later-period results do not change the frozen winner." }
                div { class: "table-scroll training-table", table { class: "data-table audit-table",
                    thead { tr { th { "Trial" }, th { "Training score" }, th { "Training CAGR" }, th { "Reviewed CAGR" }, th { "Full CAGR" }, th { "Full drawdown" } } }
                    tbody { for row in &report.trials { tr { td { "{row.id}" }, td { "{row.score:.5}" }, td { ReturnValue { value: row.training.annualized_return } }, td { ReturnValue { value: row.validation.annualized_return } }, td { ReturnValue { value: row.full.annualized_return } }, td { ReturnValue { value: row.full.max_drawdown } } } } }
                } }
            }
        }
        section { class: "panel",
            div { class: "panel-header", div { h2 { "Atlas model portfolio" }, p { "Held positions at {report.holdings_date}. Simulated history—not orders or a current brokerage account." } }, span { class: "panel-badge", "CASH {report.cash_weight * 100.0:.1}%" } }
            div { class: "atlas-holdings", for row in &report.holdings { div { span { "{row.symbol}" }, strong { "{row.weight * 100.0:.2}%" } } } }
            p { class: "research-note", "These are drifted held weights, not fresh target weights. Target name limits apply at rebalance; later price movement can move a position above its original cap." }
        }
        details { class: "panel research-details audit-limitations",
            summary { "Research record, limitations and reproducibility" }
            for limitation in &report.limitations { p { "{limitation}" } }
            p { "Frozen: {report.selection.frozen_at}. Completed: {report.completed_at}. Version: {report.version}." }
            p { class: "audit-rule", "Price snapshot: {report.data_fingerprint}" }
            a { href: "{crate::API_BASE}/api/research/{run_id}/challenger", target: "_blank", rel: "noopener noreferrer", "Open the complete research JSON ↗" }
            p { "Research ideas: ", a { href: "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor_daily.html", target: "_blank", rel: "noopener noreferrer", "momentum formation" }, " · ", a { href: "https://www.nber.org/papers/w22208", target: "_blank", rel: "noopener noreferrer", "volatility management" }, " · ", a { href: "https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf", target: "_blank", rel: "noopener noreferrer", "52-week highs" }, ". These motivate candidates, not a guarantee of this implementation's performance." }
        }
    }
}

async fn request(run_id: &str, submit: bool) -> Result<State, String> {
    #[cfg(target_arch = "wasm32")]
    {
        let endpoint = format!("{}/api/research/{run_id}/challenger", crate::API_BASE);
        let request = if submit {
            gloo_net::http::Request::post(&endpoint)
        } else {
            gloo_net::http::Request::get(&endpoint)
        };
        let response = request.send().await.map_err(|error| error.to_string())?;
        if !response.ok() {
            return Err(format!("Atlas API returned HTTP {}", response.status()));
        }
        response.json().await.map_err(|error| error.to_string())
    }
    #[cfg(not(target_arch = "wasm32"))]
    {
        let _ = (run_id, submit);
        Err("Atlas is loaded in the browser".into())
    }
}
