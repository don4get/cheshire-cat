use crate::performance::{IntervalValues, ReturnValue};
use crate::{
    format_cash, format_percent, EquityPoint, PlaygroundChart, PlaygroundMetrics,
    PlaygroundStrategy,
};
use dioxus::prelude::*;
use serde::Deserialize;

#[derive(Clone, Default, Deserialize, PartialEq)]
#[serde(default)]
struct AuditState {
    status: String,
    progress: String,
    error: Option<String>,
    report: Option<Audit>,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
struct Audit {
    version: String,
    data_fingerprint: String,
    completed_at: String,
    currency: String,
    evaluation_start: String,
    evaluation_end: String,
    walk_forward: Vec<WalkForward>,
    family_test: FamilyTest,
    finalists: Vec<Finalist>,
    candidates: Vec<CandidateDiagnostic>,
    limitations: Vec<String>,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
struct WalkForward {
    name: String,
    metrics: PlaygroundMetrics,
    benchmark: PlaygroundMetrics,
    winning_folds: usize,
    switches: usize,
    fees: f64,
    folds: Vec<Fold>,
    curve: Vec<AuditPoint>,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
struct Fold {
    train_start: String,
    train_end: String,
    test_start: String,
    test_end: String,
    test_weeks: usize,
    partial: bool,
    members: Vec<String>,
    total_return: f64,
    benchmark_return: f64,
    fees: f64,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
struct AuditPoint {
    date: String,
    value: f64,
    benchmark: f64,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
struct FamilyTest {
    candidate_count: usize,
    replicates: usize,
    p_value: f64,
    scope: String,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
struct Finalist {
    id: String,
    name: String,
    rank: usize,
    selected: bool,
    removed_contributor: Option<String>,
    intervals: Vec<Interval>,
    stresses: Vec<Stress>,
    neighbors: Vec<Neighbor>,
    crises: Vec<Crisis>,
    rolling: Rolling,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
struct Interval {
    block_weeks: usize,
    observations: usize,
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
    applicable: bool,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
struct Neighbor {
    member: String,
    count: usize,
    minimum: f64,
    median: f64,
    maximum: f64,
    own: f64,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
struct Crisis {
    name: String,
    start: String,
    end: String,
    weeks: usize,
    total_return: f64,
    benchmark_return: f64,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
struct Rolling {
    worst: f64,
    median: f64,
    positive_fraction: f64,
    benchmark_win_fraction: f64,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
struct CandidateDiagnostic {
    id: String,
    rank: usize,
    training_cagr: f64,
    evaluation_cagr: f64,
    max_drawdown: f64,
    worst: f64,
    benchmark_win_fraction: f64,
}

#[component]
pub fn ValidationLab(run_id: String) -> Element {
    let mut state = use_signal(AuditState::default);
    let mut error = use_signal(|| None::<String>);
    let mut launch = use_signal(|| 0usize);
    let request_id = run_id.clone();
    let _loader = use_resource(move || {
        let id = request_id.clone();
        let attempt = launch();
        async move {
            error.set(None);
            if attempt > 0 {
                if let Err(message) = audit_request(&id, true).await {
                    error.set(Some(message));
                    return;
                }
            }
            loop {
                match audit_request(&id, false).await {
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
            }
        }
    });
    let saved = state();
    rsx! {
        if let Some(data) = saved.report {
            AuditResults { data, run_id }
        } else {
            section { class: "panel audit-intro",
                span { class: "section-kicker", "ROBUSTNESS & VALIDATION" }
                h2 { "Does the result survive a harder test?" }
                p { "Audit the frozen experiment with cost-aware walk-forward selection, uncertainty intervals and execution stress tests. The original winner and portfolios stay unchanged." }
                p { class: "audit-caution", "The final 20% has already been reviewed. These are retrospective checks, not a new untouched test." }
                if let Some(message) = error().or(saved.error) { p { class: "negative", "{message}" } }
                p { role: "status", aria_live: "polite", "{saved.progress}" }
                button { class: "primary-button", onclick: move |_| launch += 1,
                    if saved.status == "building" { "Resume / check audit worker" } else { "Run robustness audit" }
                }
                p { class: "research-note", "The first run can take several minutes. Results are saved in PostgreSQL; returning to this page does not recompute them." }
            }
        }
    }
}

#[component]
fn AuditResults(data: Audit, run_id: String) -> Element {
    let mut finalist_index = use_signal(|| 0usize);
    let mut fold_index = use_signal(|| 0usize);
    let mut filter = use_signal(String::new);
    let finalist = data
        .finalists
        .get(finalist_index())
        .cloned()
        .unwrap_or_default();
    let contributor = finalist
        .removed_contributor
        .clone()
        .unwrap_or_else(|| "none".into());
    let protocol = data
        .walk_forward
        .get(fold_index())
        .cloned()
        .unwrap_or_default();
    let uncertain = data
        .finalists
        .iter()
        .filter(|row| {
            row.intervals
                .iter()
                .any(|ci| ci.lower <= 0.0 && ci.upper >= 0.0)
        })
        .count();
    let mut curves: Vec<PlaygroundStrategy> = data
        .walk_forward
        .iter()
        .map(|row| PlaygroundStrategy {
            id: row.name.clone(),
            name: row.name.clone(),
            curve: row
                .curve
                .iter()
                .map(|point| EquityPoint {
                    date: point.date.clone(),
                    value: point.value,
                })
                .collect(),
            ..Default::default()
        })
        .collect();
    if let Some(first) = data.walk_forward.first() {
        curves.push(PlaygroundStrategy {
            id: "matched-benchmark".into(),
            name: "Liquid equal-weight benchmark".into(),
            is_benchmark: true,
            curve: first
                .curve
                .iter()
                .map(|point| EquityPoint {
                    date: point.date.clone(),
                    value: point.benchmark,
                })
                .collect(),
            ..Default::default()
        });
    }
    let query = filter().to_lowercase();
    let rows: Vec<_> = data
        .candidates
        .iter()
        .filter(|row| row.id.to_lowercase().contains(&query))
        .collect();
    rsx! {
        section { class: "panel audit-intro",
            div { class: "panel-header",
                div { span { class: "section-kicker", "EVIDENCE, NOT A NEW WINNER" }, h2 { "Robustness & validation" } }
                span { class: "audit-status", "RETROSPECTIVE AUDIT" }
            }
            p { "A profitable backtest is not enough. Compare how selection behaves across eras, how fragile the finalists are, and what the data cannot establish." }
            div { class: "audit-caution",
                strong { "No untouched test remains in this dataset." }
                p { "The original 80/20 split was chronological, but the last 20% has now been reviewed. The four original training blocks were used for tuning. All findings below are retrospective; the saved selection is unchanged." }
            }
            div { class: "audit-findings",
                div { strong { "{uncertain} / {data.finalists.len()}" }, span { "finalists have an interval crossing zero" }, small { "Across the three block-length assumptions" } }
                div { strong { "{data.family_test.p_value:.3}" }, span { "family-wise null p estimate" }, small { "{data.family_test.candidate_count} base rules · {data.family_test.replicates} joint block resamples" } }
                div { strong { "Unresolved" }, span { "survivorship & execution realism" }, small { "Missing delistings and calibrated market impact" } }
            }
            p { class: "research-note", "The null test asks whether the strongest base-rule excess log growth could arise under a centered no-edge model. A small estimate is not a probability of live success. {data.family_test.scope}." }
        }
        section { class: "panel",
            div { class: "panel-header", div { h2 { "1. Select in the past. Execute in the next year." }, p { "Both protocols rescore every base rule and rebuild the top-three ensemble at each fold. Neither uses the final winner to choose earlier portfolios." } } }
            div { class: "audit-protocol", aria_label: "Five years of training, four week selection gap, fifty two week test, repeat",
                div { strong { "260+ weeks" }, span { "Past selection window" } }
                span { class: "audit-arrow", "→" }
                div { strong { "4-week gap" }, span { "Excluded from selection scores" } }
                span { class: "audit-arrow", "→" }
                div { strong { "52-week test" }, span { "Trade, carry positions, repeat" } }
            }
            p { class: "research-note", "Expanding keeps all preceding history; rolling uses only the last five years. Signals may use observed gap-week prices. Actual reallocations pay trading costs, including bot switches. This replaces the old shadow-return splice diagnostic." }
            div { class: "audit-protocol-cards",
                for row in &data.walk_forward {
                    article { class: "audit-protocol-card",
                        h3 { "{row.name}" }
                        div { class: "audit-return", ReturnValue { value: row.metrics.annualized_return }, small { "annualized net return" } }
                        div { class: "research-check", span { "Benchmark CAGR" }, strong { ReturnValue { value: row.benchmark.annualized_return } } }
                        div { class: "research-check", span { "Excess CAGR" }, strong { ReturnValue { value: row.metrics.annualized_return - row.benchmark.annualized_return, points: true } } }
                        div { class: "research-check", span { "Maximum drawdown" }, strong { ReturnValue { value: row.metrics.max_drawdown } } }
                        div { class: "research-check", span { "Blocks beating benchmark" }, strong { "{row.winning_folds} / {row.folds.len()}" } }
                        p { class: "research-note", "{row.switches} selection changes · {format_cash(row.fees)} {data.currency} total simulated fees" }
                    }
                }
            }
            PlaygroundChart { strategies: curves }
            div { class: "audit-chart-dates",
                span { "{protocol.curve.first().map(|point| point.date.clone()).unwrap_or_default()}" }
                span { "Portfolio value rebased to 100 · weekly observations" }
                span { "{protocol.curve.last().map(|point| point.date.clone()).unwrap_or_default()}" }
            }
            details { class: "audit-folds",
                summary { "Inspect every chronological test block" }
                div { class: "audit-tabs", role: "group", aria_label: "Walk-forward protocol",
                    for (i, row) in data.walk_forward.iter().enumerate() {
                        button { class: if fold_index() == i { "period-button active" } else { "period-button" }, aria_pressed: "{fold_index() == i}", onclick: move |_| fold_index.set(i), "{row.name}" }
                    }
                }
                div { class: "table-scroll", table { class: "data-table audit-table audit-fold-table",
                    thead { tr { th { "Selection window" }, th { "Next test · 4-week gap" }, th { "Rules selected at that time" }, th { "Net return" }, th { "Benchmark" }, th { "Fees" } } }
                    tbody { for row in &protocol.folds {
                        tr {
                            td { "{row.train_start}", br {}, "{row.train_end}" }
                            td { "{row.test_start}", br {}, "{row.test_end}", small { "{row.test_weeks} weeks", if row.partial { " · partial block" } } }
                            td { for member in &row.members { small { "{member}" } } }
                            td { ReturnValue { value: row.total_return } }, td { ReturnValue { value: row.benchmark_return } }, td { "{format_cash(row.fees)}" }
                        }
                    } }
                } }
            }
        }
        section { class: "panel audit-finalists",
            div { class: "panel-header", div { h2 { "2. Challenge the three frozen finalists" }, p { "Ranking stays fixed by the original training score. Every stress replays the saved rules without retuning." } } }
            div { class: "audit-tabs", role: "group", aria_label: "Frozen finalist",
                for (i, row) in data.finalists.iter().enumerate() {
                    button { class: if finalist_index() == i { "period-button active" } else { "period-button" }, aria_pressed: "{finalist_index() == i}", onclick: move |_| finalist_index.set(i),
                        "#{row.rank} {row.name}", if row.selected { " · selected" }
                    }
                }
            }
            p { class: "audit-rule", "{finalist.id}" }
            p { class: "research-note", "Already-reviewed evaluation: {data.evaluation_start} — {data.evaluation_end}. Performance is measured on continuously carried positions, not a fresh start at this boundary." }
            h3 { "How uncertain is the excess growth?" }
            p { class: "research-note", "95% paired circular-block bootstrap intervals for annualized relative growth versus the benchmark: exp(mean(log bot − log benchmark) × 52) − 1. This is not the difference of CAGRs. Longer blocks preserve longer runs of related returns." }
            div { class: "audit-intervals",
                for ci in &finalist.intervals {
                    article { class: "audit-interval",
                        strong { "{ci.block_weeks}-week blocks" }
                        IntervalValues { estimate: ci.estimate, lower: ci.lower, upper: ci.upper }
                        small { "{ci.observations} observed weeks · conditional estimate" }
                    }
                }
            }
            h3 { "Do costs, timing or a single stock explain the result?" }
            div { class: "table-scroll", table { class: "data-table audit-table",
                thead { tr { th { "Assumption" }, th { "Net return" }, th { "CAGR" }, th { "Benchmark CAGR" }, th { "Excess CAGR" }, th { "Drawdown" } } }
                tbody { for row in &finalist.stresses {
                    tr {
                        td { "{row.label}", if !row.applicable { small { "Not applicable: no positive training contributor" } } }
                        td { ReturnValue { value: row.metrics.total_return } }, td { ReturnValue { value: row.metrics.annualized_return } }, td { ReturnValue { value: row.benchmark.annualized_return } }
                        td { ReturnValue { value: row.excess_cagr, points: true } }, td { ReturnValue { value: row.metrics.max_drawdown } }
                    }
                } }
            } }
            p { class: "research-note", "Costs and timing are matched for the benchmark. Removed stock: {contributor}, chosen by positive dollar P&L in training only. Its allocation stays in cash; the benchmark remains unchanged for this stock-removal stress." }
            div { class: "audit-rolling",
                div { span { "Worst rolling year" }, strong { ReturnValue { value: finalist.rolling.worst } } }
                div { span { "Median rolling year" }, strong { ReturnValue { value: finalist.rolling.median } } }
                div { span { "Profitable rolling years" }, strong { "{format_percent(finalist.rolling.positive_fraction)}" } }
                div { span { "Rolling years beating benchmark" }, strong { "{format_percent(finalist.rolling.benchmark_win_fraction)}" } }
            }
            p { class: "research-note", "Full-history 52-week windows overlap and include training. They are descriptive, not independent wins or out-of-sample tests." }
            details { class: "audit-folds",
                summary { "Market shocks & parameter sensitivity" }
                p { class: "research-note", "These periods helped shape the final selection. The selected bot's crisis returns are retrospective, not a claim that it was chosen before the crisis." }
                div { class: "table-scroll", table { class: "data-table audit-table",
                    thead { tr { th { "Predefined event" }, th { "Observed dates" }, th { "Net return" }, th { "Benchmark" } } }
                    tbody { for row in &finalist.crises { tr { td { "{row.name}" }, td { "{row.start} — {row.end}", small { "{row.weeks} observed weeks" } }, td { ReturnValue { value: row.total_return } }, td { ReturnValue { value: row.benchmark_return } } } } }
                } }
                h3 { "One-parameter neighbors · training CAGR" }
                p { class: "research-note", "Rules differing in exactly one field from each member. A large drop to neighboring rules suggests parameter sensitivity; these values do not change the selection." }
                if finalist.neighbors.is_empty() { p { class: "research-note", "No one-parameter neighbors in the saved catalog." } }
                div { class: "table-scroll", table { class: "data-table audit-table",
                    thead { tr { th { "Member" }, th { "Neighbors" }, th { "Own CAGR" }, th { "Minimum" }, th { "Median" }, th { "Maximum" } } }
                    tbody { for row in &finalist.neighbors { tr { td { "{row.member}" }, td { "{row.count}" }, td { ReturnValue { value: row.own } }, td { ReturnValue { value: row.minimum } }, td { ReturnValue { value: row.median } }, td { ReturnValue { value: row.maximum } } } } }
                } }
            }
        }
        details { class: "panel research-details",
            summary { "3. Inspect all {data.candidates.len()} base candidates · original training order" }
            p { "No re-ranking by evaluation return. Rolling measures use overlapping full-history years, including training." }
            input { class: "timeline-filter", r#type: "search", aria_label: "Filter candidate diagnostics", placeholder: "Filter by signal or configuration…", value: "{filter}", oninput: move |event| filter.set(event.value()) }
            div { class: "table-scroll training-table", table { class: "data-table audit-table",
                thead { tr { th { "Training rank / rule" }, th { "Training CAGR" }, th { "Reviewed evaluation CAGR" }, th { "Worst rolling year" }, th { "Rolling benchmark wins" }, th { "Full drawdown" } } }
                tbody { for row in rows { tr { td { "#{row.rank} {row.id}" }, td { ReturnValue { value: row.training_cagr } }, td { ReturnValue { value: row.evaluation_cagr } }, td { ReturnValue { value: row.worst } }, td { "{format_percent(row.benchmark_win_fraction)}" }, td { ReturnValue { value: row.max_drawdown } } } } }
            } }
        }
        section { class: "panel audit-limitations",
            h2 { "What still needs to be proven" }
            for limitation in &data.limitations { p { "{limitation}" } }
            details { class: "audit-folds",
                summary { "Reproducibility & methods" }
                p { "Protocol: {data.version} · seed 20260920 · {data.family_test.replicates} bootstrap replicates · completed {data.completed_at}" }
                p { class: "audit-rule", "Price snapshot: {data.data_fingerprint}" }
                p { "Separate cached audit; all base training returns reconciled against the saved experiment. No candidate, original selection or original result was overwritten." }
                a { href: "{crate::API_BASE}/api/research/{run_id}/validation", target: "_blank", rel: "noopener noreferrer", "Open audit JSON ↗" }
                p { "Methods: ", a { href: "https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html", target: "_blank", rel: "noopener noreferrer", "temporal gaps" }, " · ", a { href: "https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf", target: "_blank", rel: "noopener noreferrer", "selection bias" }, " · ", a { href: "https://www.cvxportfolio.com/en/stable/costs.html", target: "_blank", rel: "noopener noreferrer", "execution-cost models" }, ". Our diagnostic is a joint centered block-bootstrap test, not the Deflated Sharpe Ratio formula." }
            }
        }
    }
}

async fn audit_request(run_id: &str, submit: bool) -> Result<AuditState, String> {
    #[cfg(target_arch = "wasm32")]
    {
        let endpoint = format!("{}/api/research/{run_id}/validation", crate::API_BASE);
        let request = if submit {
            gloo_net::http::Request::post(&endpoint)
        } else {
            gloo_net::http::Request::get(&endpoint)
        };
        let response = request.send().await.map_err(|error| error.to_string())?;
        if !response.ok() {
            return Err(format!(
                "Validation API returned HTTP {}",
                response.status()
            ));
        }
        response.json().await.map_err(|error| error.to_string())
    }
    #[cfg(not(target_arch = "wasm32"))]
    {
        let _ = (run_id, submit);
        Err("Validation is loaded in the browser".into())
    }
}
