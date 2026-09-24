use crate::performance::{return_class, ReturnValue};
use crate::{
    format_cash, format_percent, EquityPoint, PlaygroundChart, PlaygroundMetrics,
    PlaygroundStrategy,
};
use dioxus::prelude::*;
use serde::Deserialize;

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
#[serde(default)]
struct ResearchJob {
    id: String,
    status: String,
    progress: String,
    error: Option<String>,
    result: Option<ResearchResult>,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct ResearchResult {
    version: String,
    market: String,
    currency: String,
    initial_cash: f64,
    transaction_cost: f64,
    coverage: Coverage,
    split: Split,
    selection: Selection,
    strategies: Vec<ResearchStrategy>,
    validation_verdict: String,
    validation_excess_return: f64,
    cost_stress: CostStress,
    limitations: Vec<String>,
    completed_at: String,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct Coverage {
    raw_rows: usize,
    symbols: usize,
    invalid_prices: usize,
    duplicate_week_rows: usize,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct Split {
    training_start: String,
    training_end: String,
    validation_start: String,
    validation_end: String,
    training_periods: usize,
    validation_periods: usize,
    warmup_periods: usize,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct Selection {
    selected_id: String,
    selected_name: String,
    candidate_count: usize,
    objective: String,
    frozen_at: String,
    training_fingerprint: String,
    ensemble_score: f64,
    members: Vec<Parameters>,
    leaderboard: Vec<TrainingRow>,
    walk_forward: Vec<Fold>,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct Parameters {
    signal: String,
    holdings: usize,
    trend: bool,
    weighting: String,
    rebalance: usize,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct TrainingRow {
    id: String,
    score: f64,
    training: PlaygroundMetrics,
    folds: Vec<Fold>,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
#[serde(default)]
struct Fold {
    start_date: String,
    end_date: String,
    total_return: f64,
    selected_id: String,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct ResearchStrategy {
    id: String,
    name: String,
    is_benchmark: bool,
    training: PlaygroundMetrics,
    validation: PlaygroundMetrics,
    full: PlaygroundMetrics,
    curve: Vec<EquityPoint>,
    annual_returns: Vec<AnnualReturn>,
    holdings: Vec<Holding>,
    stale_position_writeoffs: usize,
    total_cost: f64,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct AnnualReturn {
    year: usize,
    total_return: f64,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct Holding {
    symbol: String,
    weight: f64,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct CostStress {
    transaction_cost: f64,
    validation: PlaygroundMetrics,
}

#[component]
pub fn ResearchLab() -> Element {
    let mut market = use_signal(|| "NASDAQ".to_string());
    let mut launch = use_signal(|| 0usize);
    let mut job = use_signal(|| None::<ResearchJob>);
    let mut error = use_signal(|| None::<String>);
    let mut period = use_signal(|| "validation".to_string());
    let _loader = use_resource(move || {
        let selected_market = market();
        let launch_number = launch();
        async move {
            job.set(None);
            error.set(None);
            if launch_number > 0 {
                if let Err(message) = start_research(&selected_market).await {
                    error.set(Some(message));
                    return;
                }
            }
            loop {
                match load_research(&selected_market).await {
                    Ok(loaded) => {
                        let running = loaded.status == "running" || loaded.status == "queued";
                        job.set(Some(loaded));
                        if !running {
                            break;
                        }
                    }
                    Err(message) => {
                        error.set(Some(message));
                        break;
                    }
                }
                #[cfg(target_arch = "wasm32")]
                gloo_timers::future::TimeoutFuture::new(2500).await;
                #[cfg(not(target_arch = "wasm32"))]
                break;
            }
        }
    });
    let state = job();
    let result = state.as_ref().and_then(|value| value.result.clone());
    rsx! {
        div { class: "content-stack investor-research",
            div { class: "panel research-intro",
                div {
                    span { class: "section-kicker", "TRAIN, FREEZE, VALIDATE" }
                    h2 { "Can the bot earn its place?" }
                    p { "Explore the frozen 80/20 experiment, then challenge it across time, costs and execution assumptions. Robustness evidence is retrospective—not a promise of future returns." }
                }
                div { class: "horizon-switcher", aria_label: "Research market",
                    for (key, label) in [("NASDAQ", "Nasdaq · USD"), ("EURONEXT_PARIS", "Paris · EUR")] {
                        button { class: if market() == key { "period-button active" } else { "period-button" }, onclick: move |_| { launch.set(0); market.set(key.to_string()); }, "{label}" }
                    }
                }
            }
            if let Some(message) = error() {
                div { class: "panel error-state", h2 { "Research is unavailable" }, p { "{message}" }, button { class: "primary-button", onclick: move |_| launch += 1, "Retry" } }
            } else if let Some(result) = result {
                ResearchResults { run_id: state.as_ref().map(|job| job.id.clone()).unwrap_or_default(), data: result, period: period(), on_period: move |next| period.set(next) }
            } else if let Some(state) = state {
                div { class: "panel research-progress", role: "status", aria_live: "polite",
                    if state.status == "not_started" || state.status == "failed" {
                        h2 { "Research this market" }
                        p { "The first run compares return-focused strategies across the stored twenty-year history. Results are saved so subsequent visits load immediately." }
                        if let Some(message) = state.error { p { class: "negative", "{message}" } }
                        button { class: "primary-button", onclick: move |_| launch += 1, "Train and validate →" }
                    } else {
                        div { class: "loading-spinner" }
                        h2 { "Research in progress" }
                        p { "{state.progress}" }
                        small { "You can leave this page; the experiment continues and its result is saved." }
                        button { class: "period-button", onclick: move |_| launch += 1, "Resume after a restart" }
                    }
                }
            } else {
                div { class: "panel research-progress", role: "status", "Loading saved research…" }
            }
        }
    }
}

#[component]
fn ResearchResults(
    run_id: String,
    data: ResearchResult,
    period: String,
    on_period: EventHandler<String>,
) -> Element {
    let mut result_view = use_signal(|| "atlas".to_string());
    let selected = data.strategies.first().cloned().unwrap_or_default();
    let chosen_metrics = segment_metrics(&selected, &period);
    let mut ordered = data.strategies.clone();
    ordered.sort_by(|a, b| {
        segment_metrics(b, &period)
            .total_return
            .total_cmp(&segment_metrics(a, &period).total_return)
    });
    let chart: Vec<PlaygroundStrategy> = data
        .strategies
        .iter()
        .map(|strategy| {
            let mut curve: Vec<EquityPoint> = strategy
                .curve
                .iter()
                .filter(|point| {
                    if period == "validation" {
                        point.date >= data.split.training_end
                    } else if period == "training" {
                        point.date <= data.split.training_end
                    } else {
                        true
                    }
                })
                .cloned()
                .collect();
            let base = curve.first().map(|point| point.value).unwrap_or(1.0);
            for point in &mut curve {
                point.value = point.value / base * 100.0;
            }
            PlaygroundStrategy {
                id: strategy.id.clone(),
                name: strategy.name.clone(),
                is_benchmark: strategy.is_benchmark,
                metrics: segment_metrics(strategy, &period),
                curve,
                ..Default::default()
            }
        })
        .collect();
    let member_summary = data
        .selection
        .members
        .iter()
        .map(|member| {
            format!(
                "{} · up to {} holdings · {} · every {} weeks{}",
                member.signal,
                member.holdings,
                member.weighting.replace('_', " "),
                member.rebalance,
                if member.trend { " · trend filter" } else { "" }
            )
        })
        .collect::<Vec<_>>();
    let heading = if period == "validation" {
        "Original 20% evaluation · already reviewed"
    } else if period == "training" {
        "Training · used to select the bot"
    } else {
        "Full history · includes training"
    };
    rsx! {
        div { class: "research-split", aria_label: "Chronological 80 percent training, 20 percent validation",
            div { class: "split-training", strong { "80% TRAINING" }, span { "{data.split.training_start} — {data.split.training_end}" }, small { "{data.split.training_periods} weeks · {data.selection.candidate_count} candidates" } }
            div { class: "split-validation", strong { "20% EVALUATION" }, span { "{data.split.validation_start} — {data.split.validation_end}" }, small { "{data.split.validation_periods} weeks · already reviewed" } }
        }
        if result_view() != "atlas" {
        div { class: "panel research-winner",
            div { class: "panel-header",
                div { span { class: "section-kicker", "SELECTED USING TRAINING ONLY" }, h2 { "{data.selection.selected_name}" } }
                span { class: return_class(data.validation_excess_return), "{data.validation_verdict}" }
            }
            for member in member_summary { p { "{member}" } }
            p { class: "research-note", "Validation excess return: ", ReturnValue { value: data.validation_excess_return, points: true }, " versus the liquid equal-weight portfolio. Selection stays frozen regardless of this outcome." }
            p { class: "research-note", "Coverage limitation: today's tracked listings exclude missing delisted companies. Historical returns can therefore be biased upward." }
        }
        }
        div { class: "research-tabs audit-navigation", role: "group", aria_label: "Research results view",
            button { class: if result_view() == "atlas" { "period-button active" } else { "period-button" }, aria_pressed: if result_view() == "atlas" { "true" } else { "false" }, onclick: move |_| result_view.set("atlas".into()), "Cheshire Atlas · challenger" }
            button { class: if result_view() == "audit" { "period-button active" } else { "period-button" }, aria_pressed: if result_view() == "audit" { "true" } else { "false" }, onclick: move |_| result_view.set("audit".into()), "Robustness & validation" }
            button { class: if result_view() == "performance" { "period-button active" } else { "period-button" }, aria_pressed: if result_view() == "performance" { "true" } else { "false" }, onclick: move |_| result_view.set("performance".into()), "Performance & portfolios" }
        }
        if result_view() == "atlas" {
            crate::challenger::ChallengerLab { key: "{run_id}", run_id: run_id.clone() }
        } else if result_view() == "audit" {
            crate::validation::ValidationLab { key: "{run_id}", run_id: run_id.clone() }
        } else {
        crate::challenger::ChallengerSummary {
            key: "{run_id}-summary",
            run_id: run_id.clone(),
            on_open: move |_| result_view.set("atlas".into()),
        }
        div { class: "timeline-section",
            crate::portfolio_timeline::PortfolioTimeline { key: "{run_id}", run_id: run_id.clone() }
        }
        div { class: "research-result-toolbar",
            h3 { "{heading}" }
            div { class: "horizon-switcher",
                for (key, label) in [("validation", "Validation"), ("training", "Training"), ("full", "Full 20Y")] {
                    button { class: if period == key { "period-button active" } else { "period-button" }, onclick: move |_| on_period.call(key.to_string()), "{label}" }
                }
            }
        }
        div { class: "stat-grid",
            ResearchStat { label: "Selected bot · total return", value: String::new(), change: chosen_metrics.total_return, note: "After simulated trading costs" }
            ResearchStat { label: "Annualized return", value: String::new(), change: chosen_metrics.annualized_return, note: "Compounded at 52 weeks per year" }
            ResearchStat { label: "Maximum drawdown", value: String::new(), change: chosen_metrics.max_drawdown, note: "Largest decline from a prior peak" }
            ResearchStat { label: "Ending capital", value: format!("{} {}", format_cash(chosen_metrics.final_value), data.currency), note: format!("From {} at this period's start", format_cash(data.initial_cash)) }
        }
        div { class: "panel",
            div { class: "panel-header", div { h2 { "Performance leaderboard" }, p { "Sorted by return for this period. The selected badge records the training decision; viewing validation never changes it." } } }
            div { class: "table-scroll", table { class: "data-table leaderboard-table",
                thead { tr { th { "Rank / strategy" } th { "Total return" } th { "Annualized" } th { "Drawdown" } th { "Sharpe" } th { "Exposure" } } }
                tbody {
                    for (rank, strategy) in ordered.iter().enumerate() {
                        tr {
                            td { strong { "#{rank + 1} · {strategy.name}" }, if !strategy.is_benchmark { span { class: "selected-bot-badge", "SELECTED" } } }
                            td { class: "number", ReturnValue { value: segment_metrics(strategy, &period).total_return } }
                            td { class: "number", ReturnValue { value: segment_metrics(strategy, &period).annualized_return } }
                            td { ReturnValue { value: segment_metrics(strategy, &period).max_drawdown } }
                            td { "{segment_metrics(strategy, &period).sharpe:.2}" }
                            td { "{format_percent(segment_metrics(strategy, &period).exposure)}" }
                        }
                    }
                }
            } }
        }
        div { class: "panel playground-chart-panel",
            div { class: "panel-header", div { h2 { "Growth of 100" }, p { "Rebased at the selected period's start. Each line includes its trading costs." } }, span { class: "panel-badge", "{data.currency} · WEEKLY" } }
            PlaygroundChart { strategies: chart }
            div { class: "chart-axis", span { if period == "validation" { "{data.split.training_end}" } else { "{data.split.training_start}" } }, span { if period == "training" { "{data.split.training_end}" } else { "{data.split.validation_end}" } } }
        }
        div { class: "two-column",
            div { class: "panel",
                div { class: "panel-header", div { h2 { "Robustness checks" }, p { "The frozen bot is also replayed with twice the trading cost." } } }
                div { class: "research-check", span { "Validation return at double costs" }, strong { ReturnValue { value: data.cost_stress.validation.total_return } } }
                div { class: "research-check", span { "Validation annualized return at double costs" }, strong { ReturnValue { value: data.cost_stress.validation.annualized_return } } }
                div { class: "research-check", span { "Base / stressed one-way trading cost" }, strong { "{data.transaction_cost * 10000.0:.0} / {data.cost_stress.transaction_cost * 10000.0:.0} bps" } }
                div { class: "research-check", span { "Missing-price write-offs in full history" }, strong { "{selected.stale_position_writeoffs}" } }
            }
            div { class: "panel",
                div { class: "panel-header", div { h2 { "Allocation at the end of the replay" }, p { "Largest 20 of {selected.holdings.len()} holdings · {data.split.validation_end}." } } }
                div { class: "holdings-list",
                    for holding in selected.holdings.iter().take(20) {
                        div { class: "research-check", span { "{holding.symbol}" }, strong { "{holding.weight * 100.0:.1}%" } }
                    }
                    if selected.holdings.is_empty() { p { "The strategy ended this period in cash." } }
                }
            }
        }
        details { class: "panel research-details",
            summary { "Annual returns · selected bot and benchmarks" }
            div { class: "table-scroll", table { class: "data-table research-annual-table",
                thead { tr { th { "Year" } for strategy in &data.strategies { th { "{strategy.name}" } } } }
                tbody { for year in &selected.annual_returns {
                    tr { td { "{year.year}" }, for strategy in &data.strategies {
                        td {
                            if let Some(row) = strategy.annual_returns.iter().find(|row| row.year == year.year) {
                                ReturnValue { value: row.total_return }
                            } else { span { class: "return-neutral", title: "No recorded return for this year", "—" } }
                        }
                    } }
                } }
            } }
            p { class: "research-note", "The first and last calendar years may be partial. The split year contains both training and validation weeks." }
        }
        details { class: "panel research-details",
            summary { "Training leaderboard · all {data.selection.candidate_count} candidates" }
            p { class: "research-note", "Objective: {data.selection.objective}. Four consecutive training blocks measure dependence on one market era. The additional top-three ensemble is compared with the best single rule before opening validation; its selection score was {data.selection.ensemble_score:.4}." }
            div { class: "table-scroll training-table", table { class: "data-table",
                thead { tr { th { "Configuration" } th { "Training return" } th { "Training CAGR" } th { "Selection score" } } }
                tbody { for row in &data.selection.leaderboard {
                    tr { td { "{row.id}" }, td { ReturnValue { value: row.training.total_return } }, td { ReturnValue { value: row.training.annualized_return } }, td { "{row.score:.4}" } }
                } }
            } }
        }
        details { class: "panel research-details",
            summary { "Data coverage, assumptions and reproducibility" }
            p { "{data.coverage.symbols} tracked symbols · {data.coverage.raw_rows} stored rows · {data.coverage.duplicate_week_rows} duplicate weekly rows consolidated · {data.coverage.invalid_prices} nonpositive or invalid prices excluded." }
            p { "{data.split.warmup_periods} earlier weeks initialize signals. Portfolios use only prior information, at most 500 historically liquid names, and weekly close execution one complete bar after each decision." }
            for limitation in &data.limitations { p { "{limitation}" } }
            p { class: "research-note", "Research version: {data.version}. Frozen: {data.selection.frozen_at}. Completed: {data.completed_at}." }
        }
        }
    }
}

#[component]
fn ResearchStat(label: String, value: String, note: String, change: Option<f64>) -> Element {
    rsx! { div { class: "stat-card", div { class: "stat-label", "{label}" }, div { class: "stat-value", if let Some(change) = change { ReturnValue { value: change } } else { "{value}" } }, small { class: "research-note", "{note}" } } }
}

fn segment_metrics(strategy: &ResearchStrategy, period: &str) -> PlaygroundMetrics {
    match period {
        "training" => strategy.training.clone(),
        "full" => strategy.full.clone(),
        _ => strategy.validation.clone(),
    }
}

async fn load_research(market: &str) -> Result<ResearchJob, String> {
    #[cfg(target_arch = "wasm32")]
    {
        let endpoint = format!("{}/api/research?market={market}", crate::API_BASE);
        let response = gloo_net::http::Request::get(&endpoint)
            .send()
            .await
            .map_err(|e| e.to_string())?;
        if !response.ok() {
            return Err(format!("API returned HTTP {}", response.status()));
        }
        response.json().await.map_err(|e| e.to_string())
    }
    #[cfg(not(target_arch = "wasm32"))]
    {
        let _ = market;
        Err("Research is loaded in the browser".to_string())
    }
}

async fn start_research(market: &str) -> Result<(), String> {
    #[cfg(target_arch = "wasm32")]
    {
        let endpoint = format!("{}/api/research?market={market}", crate::API_BASE);
        let response = gloo_net::http::Request::post(&endpoint)
            .send()
            .await
            .map_err(|e| e.to_string())?;
        if !response.ok() {
            return Err(format!("API returned HTTP {}", response.status()));
        }
        Ok(())
    }
    #[cfg(not(target_arch = "wasm32"))]
    {
        let _ = market;
        Err("Research is launched in the browser".to_string())
    }
}
