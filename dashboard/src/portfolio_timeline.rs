use crate::format_cash;
use dioxus::prelude::*;
use serde::Deserialize;

#[derive(Clone, Default, Deserialize, PartialEq)]
#[serde(default)]
struct TimelineState {
    status: String,
    error: Option<String>,
    timeline: Option<Timeline>,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
struct Timeline {
    currency: String,
    initial_cash: f64,
    validation_start: String,
    dates: Vec<String>,
    candidates: Vec<Candidate>,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
struct Candidate {
    id: String,
    name: String,
    rank: usize,
    score: f64,
    selected: bool,
    members: Vec<Parameters>,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
struct Parameters {
    weighting: String,
    rebalance: usize,
    trend: bool,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
struct Snapshot {
    date: String,
    portfolios: Vec<Portfolio>,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
#[serde(default)]
struct Portfolio {
    id: String,
    value: f64,
    total_return: f64,
    cash: f64,
    cash_weight: f64,
    traded: bool,
    turnover: f64,
    cost: f64,
    last_rebalance: Option<String>,
    holdings: Vec<Holding>,
    strategy_family: String,
    decision_date: Option<String>,
    information_cutoff: Option<String>,
    execution_date: Option<String>,
    selection_explanation: String,
    decision_inputs: DecisionInputs,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
#[serde(default)]
struct DecisionInputs {
    fundamentals_used: bool,
    price_source: String,
    lookback_periods: Vec<usize>,
    target_holdings: Vec<TargetHolding>,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
struct TargetHolding {
    symbol: String,
    target_weight: f64,
}

#[derive(Clone, Default, Deserialize, PartialEq)]
struct Holding {
    symbol: String,
    value: f64,
    weight: f64,
    priced: bool,
}

#[derive(Clone, Copy, PartialEq)]
enum HoldingChangeKind {
    Added,
    Removed,
    Increased,
    Decreased,
    Unchanged,
}

#[derive(Clone, PartialEq)]
struct HoldingChange {
    symbol: String,
    current: Option<Holding>,
    previous: Option<Holding>,
    kind: HoldingChangeKind,
}

#[component]
pub fn PortfolioTimeline(run_id: String) -> Element {
    let mut timeline = use_signal(|| None::<Timeline>);
    let mut error = use_signal(|| None::<String>);
    let mut retry = use_signal(|| 0usize);
    let request_id = run_id.clone();
    let _loader = use_resource(move || {
        let id = request_id.clone();
        let attempt = retry();
        async move {
            error.set(None);
            let mut submitted = false;
            if attempt > 0 {
                if let Err(message) = prepare_timeline(&id).await {
                    error.set(Some(message));
                    return;
                }
                submitted = true;
            }
            loop {
                match get_timeline(&id).await {
                    Ok(state) => match state.status.as_str() {
                        "ready" => {
                            timeline.set(state.timeline);
                            break;
                        }
                        "failed" => {
                            error.set(state.error.or(Some("Portfolio replay failed".to_string())));
                            break;
                        }
                        _ => {
                            if !submitted {
                                if let Err(message) = prepare_timeline(&id).await {
                                    error.set(Some(message));
                                    break;
                                }
                                submitted = true;
                            }
                        }
                    },
                    Err(message) => {
                        error.set(Some(message));
                        break;
                    }
                }
                #[cfg(target_arch = "wasm32")]
                gloo_timers::future::TimeoutFuture::new(1500).await;
            }
        }
    });
    rsx! {
        if let Some(data) = timeline() {
            PortfolioExplorer { run_id, data }
        } else {
            section { class: "panel portfolio-timeline", aria_label: "Portfolio timeline",
                h2 { "Portfolios through time" }
                if let Some(message) = error() {
                    p { class: "negative", "{message}" }
                    button { class: "period-button", onclick: move |_| retry += 1, "Retry portfolio history" }
                } else {
                    div { class: "timeline-pending", role: "status", div { class: "loading-spinner" }, p { "Preparing the top three portfolios from the saved rules…" } }
                }
            }
        }
    }
}

#[component]
fn PortfolioExplorer(run_id: String, data: Timeline) -> Element {
    let last = data.dates.len().saturating_sub(1);
    let validation_index = data
        .dates
        .partition_point(|day| day < &data.validation_start)
        .min(last);
    let mut index = use_signal(|| validation_index);
    let mut playing = use_signal(|| false);
    let mut filter = use_signal(String::new);
    let mut snapshot = use_signal(|| None::<Snapshot>);
    let mut previous_snapshot = use_signal(|| None::<Snapshot>);
    let mut error = use_signal(|| None::<String>);
    let mut retry = use_signal(|| 0usize);
    let mut cache = use_signal(std::collections::BTreeMap::<usize, Snapshot>::new);
    let request_id = run_id.clone();
    let dates = data.dates.clone();
    let _reader = use_resource(move || {
        let selected_index = index();
        let _attempt = retry();
        let id = request_id.clone();
        let dates = dates.clone();
        let date = dates.get(selected_index).cloned().unwrap_or_default();
        async move {
            error.set(None);
            let cached = cache.peek().get(&selected_index).cloned();
            // Cancel superseded drag requests before hitting the API.
            let loaded = if let Some(cached) = cached {
                cached
            } else {
                #[cfg(target_arch = "wasm32")]
                gloo_timers::future::TimeoutFuture::new(75).await;
                match get_snapshot(&id, &date).await {
                    Ok(loaded) => {
                        if cache.peek().len() >= 64 {
                            cache.write().clear();
                        }
                        cache.write().insert(selected_index, loaded.clone());
                        loaded
                    }
                    Err(message) => {
                        error.set(Some(message));
                        playing.set(false);
                        return;
                    }
                }
            };
            let previous = if selected_index == 0 {
                None
            } else {
                let previous_index = selected_index - 1;
                let cached_previous = cache.peek().get(&previous_index).cloned();
                if let Some(cached) = cached_previous {
                    Some(cached)
                } else {
                    let previous_date = dates.get(previous_index).cloned().unwrap_or_default();
                    match get_snapshot(&id, &previous_date).await {
                        Ok(previous) => {
                            if cache.peek().len() >= 64 {
                                cache.write().clear();
                            }
                            cache.write().insert(previous_index, previous.clone());
                            Some(previous)
                        }
                        Err(message) => {
                            error.set(Some(message));
                            playing.set(false);
                            return;
                        }
                    }
                }
            };
            snapshot.set(Some(loaded));
            previous_snapshot.set(previous);
        }
    });
    let _playback = use_resource(move || {
        let active = playing();
        async move {
            if !active {
                return;
            }
            loop {
                #[cfg(target_arch = "wasm32")]
                gloo_timers::future::TimeoutFuture::new(700).await;
                #[cfg(not(target_arch = "wasm32"))]
                break;
                #[cfg(target_arch = "wasm32")]
                {
                    let current = *index.peek();
                    if current >= last {
                        playing.set(false);
                        break;
                    }
                    // Wait for each displayed snapshot, even on a slow link.
                    if let Some(loaded) = snapshot.peek().as_ref() {
                        let cached = cache
                            .peek()
                            .get(&current)
                            .map(|point| &point.date == &loaded.date)
                            .unwrap_or(false);
                        if cached {
                            index.set(current + 1);
                        }
                    }
                }
            }
        }
    });
    let selected_date = data.dates.get(index()).cloned().unwrap_or_default();
    let current = snapshot().filter(|point| point.date == selected_date);
    let previous = previous_snapshot();
    let validation = selected_date >= data.validation_start;
    let first_date = data.dates.first().cloned().unwrap_or_default();
    let last_date = data.dates.last().cloned().unwrap_or_default();
    let input_dates = data.dates.clone();
    rsx! {
        section { class: "panel portfolio-timeline", aria_label: "Portfolio timeline",
            div { class: "panel-header",
                div {
                    span { class: "section-kicker", "INSIDE THE TOP THREE" }
                    h2 { "Portfolios through time" }
                    p { "The three best candidates by frozen training score, including the ensemble. Holdings are shown after each week's trades and price changes." }
                }
                span { class: "panel-badge", "FULL HISTORY · WEEKLY" }
            }
            div { class: "timeline-toolbar",
                div { class: "timeline-transport",
                    button { class: "timeline-play", aria_label: if playing() { "Pause portfolio playback" } else { "Play portfolio timeline" }, onclick: move |_| { if index() == last { index.set(0); } playing.toggle(); }, if playing() { "Ⅱ Pause" } else { "▶ Play" } }
                    button { class: "timeline-step", aria_label: "Previous portfolio week", disabled: index() == 0, onclick: move |_| { playing.set(false); index.set(index().saturating_sub(1)); }, "←" }
                    button { class: "timeline-step", aria_label: "Next portfolio week", disabled: index() >= last, onclick: move |_| { playing.set(false); index.set((index() + 1).min(last)); }, "→" }
                }
                label { class: "timeline-date",
                    span { "Portfolio date" }
                    input { type: "date", aria_label: "Portfolio date", min: "{first_date}", max: "{last_date}", value: "{selected_date}",
                        onchange: move |event| {
                            let entered = event.value();
                            if entered.is_empty() { return; }
                            let at = input_dates.partition_point(|day| day <= &entered).saturating_sub(1).min(last);
                            playing.set(false); index.set(at);
                        }
                    }
                }
                span { class: if validation { "timeline-phase validation" } else { "timeline-phase training" }, if validation { "Validation period" } else { "Training period · in sample" } }
            }
            input { class: "portfolio-slider", type: "range", min: "0", max: "{last}", step: "1", value: "{index()}", aria_label: "Portfolio time slider", aria_valuetext: "{selected_date}",
                oninput: move |event| { playing.set(false); index.set(event.value().parse::<usize>().unwrap_or(0).min(last)); }
            }
            div { class: "timeline-landmarks",
                button { class: "period-button", onclick: move |_| { playing.set(false); index.set(0); }, "Start · {first_date}" }
                button { class: "period-button", onclick: move |_| { playing.set(false); index.set(validation_index); }, "Validation starts · {data.validation_start}" }
                button { class: "period-button", onclick: move |_| { playing.set(false); index.set(last); }, "Latest · {last_date}" }
            }
            div { class: "timeline-context",
                p { "{data.dates.len()} saved weekly snapshots · values in {data.currency} · returns since the original {format_cash(data.initial_cash)} starting capital." }
                input { class: "timeline-filter", type: "search", aria_label: "Filter portfolio holdings", placeholder: "Find a holding in all three…", value: "{filter()}", oninput: move |event| filter.set(event.value()) }
            }
            if let Some(message) = error() {
                div { class: "timeline-pending", role: "alert", p { "{message}" }, button { class: "period-button", onclick: move |_| retry += 1, "Retry date" } }
            } else if let Some(current) = current {
                div { class: "portfolio-date-status", role: "status", aria_live: "polite", "Showing holdings at close on {current.date}" }
                div { class: "timeline-portfolios",
                    for candidate in &data.candidates {
                        if let Some(portfolio) = current.portfolios.iter().find(|portfolio| portfolio.id == candidate.id) {
                            PortfolioCard {
                                key: "{candidate.id}",
                                candidate: candidate.clone(),
                                portfolio: portfolio.clone(),
                                previous: previous.as_ref().and_then(|snapshot| snapshot.portfolios.iter().find(|portfolio| portfolio.id == candidate.id)).cloned(),
                                previous_date: previous.as_ref().map(|snapshot| snapshot.date.clone()),
                                currency: data.currency.clone(),
                                filter: filter(),
                            }
                        }
                    }
                }
            } else {
                div { class: "timeline-pending", role: "status", p { "Loading portfolios for {selected_date}…" } }
            }
            p { class: "research-note", "Candidate ranks stay fixed as the date moves. Training-period views are retrospective; the candidates were chosen at the end of training. Dates between weekly observations snap to the preceding close." }
        }
    }
}

#[component]
fn PortfolioCard(
    candidate: Candidate,
    portfolio: Portfolio,
    previous: Option<Portfolio>,
    previous_date: Option<String>,
    currency: String,
    filter: String,
) -> Element {
    let needle = filter.trim().to_uppercase();
    let holdings: Vec<&Holding> = portfolio
        .holdings
        .iter()
        .filter(|holding| holding.symbol.contains(&needle))
        .collect();
    let changes = holding_changes(&portfolio, previous.as_ref());
    let visible_changes: Vec<&HoldingChange> = changes
        .iter()
        .filter(|change| change.symbol.contains(&needle))
        .collect();
    let added = changes
        .iter()
        .filter(|change| change.kind == HoldingChangeKind::Added)
        .count();
    let removed = changes
        .iter()
        .filter(|change| change.kind == HoldingChangeKind::Removed)
        .count();
    let reweighted = changes
        .iter()
        .filter(|change| {
            matches!(
                change.kind,
                HoldingChangeKind::Increased | HoldingChangeKind::Decreased
            )
        })
        .count();
    let changed = added + removed + reweighted;
    let other_weight: f64 = portfolio
        .holdings
        .iter()
        .skip(6)
        .map(|holding| holding.weight)
        .sum();
    let description = if candidate.members.len() > 1 {
        format!(
            "{} rules combined · weekly allocation",
            candidate.members.len()
        )
    } else if let Some(member) = candidate.members.first() {
        format!(
            "{} · every {} weeks{}",
            member.weighting.replace('_', " "),
            member.rebalance,
            if member.trend { " · trend filter" } else { "" }
        )
    } else {
        String::new()
    };
    rsx! {
        article { class: "timeline-portfolio", aria_label: "Rank {candidate.rank} portfolio",
            div { class: "timeline-card-heading", span { class: "timeline-rank", "#{candidate.rank}" }, if candidate.selected { span { class: "selected-bot-badge", "SELECTED BOT" } }, span { class: "timeline-score", "Training score {candidate.score:.3}" } }
            h3 { "{candidate.name}" }
            p { class: "timeline-rule", "{description}" }
            div { class: "timeline-decision-note",
                strong { "Decision-time information · {portfolio.strategy_family}" }
                if let Some(cutoff) = portfolio.information_cutoff.as_ref() {
                    span { " cutoff {cutoff}" }
                } else {
                    span { " no prior decision snapshot" }
                }
                p { "{portfolio.selection_explanation}" }
                small {
                    "Fundamentals used: "
                    if portfolio.decision_inputs.fundamentals_used { "yes" } else { "no" }
                    " · {portfolio.decision_inputs.price_source}"
                }
            }
            div { class: "timeline-value", strong { "{format_cash(portfolio.value)}" }, span { "{currency}" }, crate::performance::ReturnValue { value: portfolio.total_return } }
            div { class: "allocation-strip", role: "img", aria_label: "{portfolio.holdings.len()} holdings and {portfolio.cash_weight * 100.0:.1} percent cash",
                for holding in portfolio.holdings.iter().take(6) {
                    span { style: "width:{holding.weight * 100.0}%;background:{symbol_color(&holding.symbol)}", title: "{holding.symbol}: {holding.weight * 100.0:.2}%" }
                }
                if other_weight > 0.0 { span { style: "width:{other_weight * 100.0}%;background:#646b78", title: "Other holdings: {other_weight * 100.0:.2}%" } }
                if portfolio.cash_weight > 0.0 { span { class: "allocation-cash", style: "width:{portfolio.cash_weight * 100.0}%", title: "Cash: {portfolio.cash_weight * 100.0:.2}%" } }
            }
            div { class: "timeline-cash", span { "Cash" }, strong { "{format_cash(portfolio.cash)} {currency}" }, span { "{portfolio.cash_weight * 100.0:.1}%" } }
            div { class: "timeline-changes",
                if let Some(previous_date) = previous_date.as_ref() {
                    div { class: "timeline-changes-heading", span { "Changes since {previous_date}" }, span { "{added} added · {removed} removed · {reweighted} weight changes" } }
                    if changed == 0 {
                        p { "No holding additions, removals, or material weight changes; movement is from price changes." }
                    } else {
                        div { class: "timeline-change-legend",
                            span { class: "holding-change-added", "Added" }
                            span { class: "holding-change-removed", "Removed" }
                            span { class: "holding-change-reweighted", "Weight change" }
                        }
                    }
                } else {
                    div { class: "timeline-changes-heading", span { "Recent changes" }, span { "No earlier weekly snapshot" } }
                    p { "This is the first available portfolio snapshot." }
                }
            }
            div { class: "timeline-holdings-label", span { "{holdings.len()} of {portfolio.holdings.len()} current holdings" }, span { "Weight / value" } }
            div { class: "timeline-holdings", tabindex: "0", aria_label: "Holdings for rank {candidate.rank}",
                if visible_changes.is_empty() {
                    if portfolio.holdings.is_empty() { p { class: "timeline-empty", "All capital is in cash at this date." } }
                    else { p { class: "timeline-empty", "No matching holdings or recent changes." } }
                }
                else {
                    table { class: "data-table timeline-holdings-table",
                        thead { tr { th { "Symbol" } th { "Change" } th { "Weight" } th { "Value ({currency})" } } }
                        tbody { for change in visible_changes {
                            HoldingChangeRow { key: "{change.symbol}", change: change.clone(), currency: currency.clone() }
                        } }
                    }
                }
            }
            div { class: "timeline-trade",
                if portfolio.traded { strong { "Traded this week" }, span { "{portfolio.turnover * 100.0:.1}% turnover · {format_cash(portfolio.cost)} {currency} fees" } }
                else { strong { "No trades this week" }, span { "Holdings reflect price changes." } }
                if let Some(date) = portfolio.last_rebalance { small { "Last trade: {date}" } }
                if changed > 0 { small { "{changed} recent holding changes highlighted above" } }
            }
        }
    }
}

#[component]
fn HoldingChangeRow(change: HoldingChange, currency: String) -> Element {
    let change_label = holding_change_label(&change);
    rsx! {
        tr { class: "{holding_change_row_class(change.kind)}",
            td {
                span { class: "holding-color", style: "background:{symbol_color(&change.symbol)}" }
                strong { "{change.symbol}" }
                if let Some(current) = change.current.as_ref() {
                    if !current.priced { small { class: "negative", "Last available quote" } }
                }
            }
            td { if !change_label.is_empty() { span { class: "holding-change-label {holding_change_badge_class(change.kind)}", "{change_label}" } } else { "—" } }
            td {
                if let Some(current) = change.current.as_ref() {
                    "{current.weight * 100.0:.2}%"
                } else if let Some(previous) = change.previous.as_ref() {
                    "—"
                    small { "was {previous.weight * 100.0:.2}%" }
                } else {
                    "—"
                }
            }
            td {
                if let Some(current) = change.current.as_ref() {
                    "{format_cash(current.value)}"
                } else if let Some(previous) = change.previous.as_ref() {
                    "—"
                    small { "was {format_cash(previous.value)} {currency}" }
                } else {
                    "—"
                }
            }
        }
    }
}

fn holding_changes(portfolio: &Portfolio, previous: Option<&Portfolio>) -> Vec<HoldingChange> {
    let previous_by_symbol: std::collections::BTreeMap<&str, &Holding> = previous
        .map(|portfolio| {
            portfolio
                .holdings
                .iter()
                .map(|holding| (holding.symbol.as_str(), holding))
                .collect()
        })
        .unwrap_or_default();
    let current_symbols: std::collections::BTreeSet<&str> = portfolio
        .holdings
        .iter()
        .map(|holding| holding.symbol.as_str())
        .collect();
    let mut changes = portfolio
        .holdings
        .iter()
        .map(|current| {
            let previous_holding = previous_by_symbol.get(current.symbol.as_str()).copied();
            HoldingChange {
                symbol: current.symbol.clone(),
                current: Some(current.clone()),
                previous: previous_holding.cloned(),
                kind: match previous_holding {
                    None => HoldingChangeKind::Added,
                    Some(previous) if current.weight - previous.weight > 0.0005 => {
                        HoldingChangeKind::Increased
                    }
                    Some(previous) if current.weight - previous.weight < -0.0005 => {
                        HoldingChangeKind::Decreased
                    }
                    Some(_) => HoldingChangeKind::Unchanged,
                },
            }
        })
        .collect::<Vec<_>>();
    if let Some(previous) = previous {
        changes.extend(
            previous
                .holdings
                .iter()
                .filter(|holding| !current_symbols.contains(holding.symbol.as_str()))
                .map(|previous| HoldingChange {
                    symbol: previous.symbol.clone(),
                    current: None,
                    previous: Some(previous.clone()),
                    kind: HoldingChangeKind::Removed,
                }),
        );
    }
    changes
}

fn holding_change_label(change: &HoldingChange) -> String {
    match change.kind {
        HoldingChangeKind::Added => "Added".to_string(),
        HoldingChangeKind::Removed => "Removed".to_string(),
        HoldingChangeKind::Increased | HoldingChangeKind::Decreased => {
            let delta = change
                .current
                .as_ref()
                .zip(change.previous.as_ref())
                .map(|(current, previous)| (current.weight - previous.weight) * 100.0)
                .unwrap_or_default();
            format!("{delta:+.2} pp")
        }
        HoldingChangeKind::Unchanged => String::new(),
    }
}

fn holding_change_row_class(kind: HoldingChangeKind) -> &'static str {
    match kind {
        HoldingChangeKind::Added => "holding-added",
        HoldingChangeKind::Removed => "holding-removed",
        HoldingChangeKind::Increased | HoldingChangeKind::Decreased => "holding-reweighted",
        HoldingChangeKind::Unchanged => "holding-unchanged",
    }
}

fn holding_change_badge_class(kind: HoldingChangeKind) -> &'static str {
    match kind {
        HoldingChangeKind::Added => "holding-change-added",
        HoldingChangeKind::Removed => "holding-change-removed",
        HoldingChangeKind::Increased | HoldingChangeKind::Decreased => "holding-change-reweighted",
        HoldingChangeKind::Unchanged => "holding-change-unchanged",
    }
}

fn symbol_color(symbol: &str) -> &'static str {
    let palette = [
        "#d6a84f", "#77b7d8", "#7fc49b", "#b99be8", "#e18e84", "#89b9af", "#c995b2",
    ];
    let hash = symbol.bytes().fold(0usize, |value, byte| {
        value.wrapping_mul(31).wrapping_add(byte as usize)
    });
    palette[hash % palette.len()]
}

async fn get_timeline(run_id: &str) -> Result<TimelineState, String> {
    get_json(&format!("/api/research/{run_id}/portfolios")).await
}

async fn get_snapshot(run_id: &str, date: &str) -> Result<Snapshot, String> {
    get_json(&format!("/api/research/{run_id}/portfolios?on_date={date}")).await
}

async fn get_json<T: serde::de::DeserializeOwned>(path: &str) -> Result<T, String> {
    #[cfg(target_arch = "wasm32")]
    {
        let response = gloo_net::http::Request::get(&format!("{}{path}", crate::API_BASE))
            .send()
            .await
            .map_err(|e| e.to_string())?;
        if !response.ok() {
            return Err(format!("Portfolio API returned HTTP {}", response.status()));
        }
        response.json().await.map_err(|e| e.to_string())
    }
    #[cfg(not(target_arch = "wasm32"))]
    {
        let _ = path;
        Err("Portfolio history is loaded in the browser".to_string())
    }
}

async fn prepare_timeline(run_id: &str) -> Result<(), String> {
    #[cfg(target_arch = "wasm32")]
    {
        let response = gloo_net::http::Request::post(&format!(
            "{}/api/research/{run_id}/portfolios",
            crate::API_BASE
        ))
        .send()
        .await
        .map_err(|e| e.to_string())?;
        if !response.ok() {
            return Err(format!("Portfolio API returned HTTP {}", response.status()));
        }
        Ok(())
    }
    #[cfg(not(target_arch = "wasm32"))]
    {
        let _ = run_id;
        Err("Portfolio history is prepared in the browser".to_string())
    }
}
