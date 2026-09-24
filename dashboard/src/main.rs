use dioxus::prelude::*;
use serde::Deserialize;

mod challenger;
mod performance;
mod portfolio_timeline;
mod research;
mod validation;

use performance::{PerformanceLegend, ReturnValue};

const GOLD: &str = "#d6a84f";
const API_BASE: &str = match option_env!("CHESHIRE_CAT_API_URL") {
    Some(value) => value,
    None => "",
};

#[derive(Clone, Copy, PartialEq)]
enum View {
    Overview,
    Fundamentals,
    Reports,
    Portfolio,
    Universe,
    Playground,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct DashboardSnapshot {
    symbols: Vec<String>,
    universe: Vec<UniverseSymbol>,
    selected_symbol: Option<String>,
    selected_exchange: Option<String>,
    prices: Vec<PricePoint>,
    metrics: Vec<Metric>,
    fundamentals: Vec<Fundamental>,
    fundamental_total: usize,
    fundamentals_truncated: bool,
    reports: Vec<Report>,
    portfolio: Vec<PortfolioPoint>,
    sector: Option<String>,
    fundamental_ratios: Vec<RatioMetric>,
    sector_peers: Vec<SectorPeer>,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct PlaygroundSnapshot {
    requested_years: usize,
    actual_years: f64,
    start_date: String,
    end_date: String,
    annualization: usize,
    frequency: String,
    symbols: Vec<String>,
    observations: usize,
    initial_cash: f64,
    transaction_cost: f64,
    strategies: Vec<PlaygroundStrategy>,
    fundamental_readiness: Option<FundamentalReadiness>,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct FundamentalReadiness {
    as_of: String,
    feature_version: String,
    status: String,
    symbols: Vec<String>,
    cohorts: FundamentalCohorts,
    cohort_rows: Vec<FundamentalCohortRow>,
    feature_names: Vec<String>,
    explanation: String,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
#[serde(default)]
struct MatchedFundamentalReport {
    manifest: MatchedFundamentalManifest,
    trials: Vec<MatchedFundamentalTrial>,
    conclusion: MatchedFundamentalConclusion,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
#[serde(default)]
struct MatchedFundamentalManifest {
    feature_version: String,
    currency: String,
    decision_dates: MatchedDecisionDates,
    transaction_cost: f64,
    search_budget: usize,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
#[serde(default)]
struct MatchedDecisionDates {
    start: String,
    training_end: String,
    validation_start: Option<String>,
    end: String,
    matched_periods: usize,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
#[serde(default)]
struct MatchedFundamentalTrial {
    id: String,
    score: f64,
    training: PlaygroundMetrics,
    validation: PlaygroundMetrics,
    feature_coverage: FeatureCoverage,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
#[serde(default)]
struct FeatureCoverage {
    rate: f64,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
#[serde(default)]
struct MatchedFundamentalConclusion {
    status: String,
    text: String,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct FundamentalCohorts {
    price_only: Vec<String>,
    fundamental: Vec<String>,
    hybrid: Vec<String>,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct FundamentalCohortRow {
    symbol: String,
    usable_features: Vec<String>,
    usable_feature_count: usize,
    feature_count: usize,
    missing_features: Vec<String>,
    sources: Vec<String>,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct PlaygroundStrategy {
    id: String,
    name: String,
    description: String,
    family: String,
    is_benchmark: bool,
    metrics: PlaygroundMetrics,
    curve: Vec<EquityPoint>,
    rank: usize,
    score: f64,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct PlaygroundMetrics {
    total_return: f64,
    annualized_return: f64,
    annualized_volatility: f64,
    sharpe: f64,
    max_drawdown: f64,
    final_value: f64,
    exposure: f64,
    average_turnover: f64,
    profitable_periods: f64,
    calmar: f64,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct EquityPoint {
    date: String,
    value: f64,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct UniverseSymbol {
    symbol: String,
    exchange: String,
    name: Option<String>,
    sector: Option<String>,
    price_rows: usize,
    fundamental_rows: usize,
    report_rows: usize,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct PricePoint {
    date: String,
    symbol: String,
    close: Option<f64>,
    adj_close: Option<f64>,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct Metric {
    symbol: String,
    last_price: Option<f64>,
    return_1y: Option<f64>,
    volatility: Option<f64>,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct Fundamental {
    symbol: String,
    taxonomy: String,
    concept: String,
    unit: String,
    period_start: Option<String>,
    period_end: String,
    filed: Option<String>,
    form: String,
    frame: Option<String>,
    value: Option<f64>,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct Report {
    symbol: String,
    form: String,
    filing_date: Option<String>,
    period_end: Option<String>,
    accession_number: String,
    source_url: String,
    markdown_path: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct PortfolioPoint {
    date: String,
    value: Option<f64>,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct RatioMetric {
    key: String,
    label: String,
    value: Option<f64>,
    kind: String,
    source: Option<String>,
    period_end: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct SectorPeer {
    symbol: String,
    name: Option<String>,
    exchange: String,
    sector: Option<String>,
    last_price: Option<f64>,
    ratios: Vec<RatioMetric>,
}

#[derive(Clone, Copy, PartialEq)]
enum ChartPeriod {
    Week,
    Month,
    Year,
    TwoYears,
    FiveYears,
    Max,
}

impl ChartPeriod {
    fn options() -> [Self; 6] {
        [
            Self::Week,
            Self::Month,
            Self::Year,
            Self::TwoYears,
            Self::FiveYears,
            Self::Max,
        ]
    }

    fn label(self) -> &'static str {
        match self {
            Self::Week => "1W",
            Self::Month => "1M",
            Self::Year => "1Y",
            Self::TwoYears => "2Y",
            Self::FiveYears => "5Y",
            Self::Max => "MAX",
        }
    }

    fn observations(self) -> Option<usize> {
        match self {
            Self::Week => Some(5),
            Self::Month => Some(22),
            Self::Year => Some(252),
            Self::TwoYears => Some(504),
            Self::FiveYears => Some(1260),
            Self::Max => None,
        }
    }
}

fn main() {
    dioxus::launch(App);
}

#[component]
fn App() -> Element {
    let mut dark = use_signal(|| true);
    let mut search = use_signal(String::new);
    let mut selected = use_signal(String::new);
    let mut view = use_signal(|| View::Overview);
    let mut playground_request = use_signal(String::new);
    let snapshot = use_resource(move || {
        let symbol = selected();
        async move { load_snapshot(symbol).await }
    });
    let playground = use_resource(move || {
        let symbol = selected();
        let request = playground_request();
        async move { load_playground(request, symbol).await }
    });

    let snapshot_state = snapshot.read();
    let is_loading = snapshot_state.is_none();
    let load_error = snapshot_state
        .as_ref()
        .and_then(|result| result.as_ref().err())
        .cloned();
    let data = snapshot_state
        .as_ref()
        .and_then(|result| result.as_ref().ok())
        .cloned()
        .unwrap_or_default();
    drop(snapshot_state);

    let active_symbol = if selected().is_empty() {
        data.selected_symbol.clone().unwrap_or_default()
    } else {
        selected().to_uppercase()
    };
    let selected_metadata = data
        .universe
        .iter()
        .find(|entry| entry.symbol == active_symbol)
        .cloned()
        .unwrap_or_default();
    let global_matches: Vec<(String, String)> = data
        .universe
        .iter()
        .filter(|entry| {
            let needle = search().trim().to_uppercase();
            needle.is_empty()
                || entry.symbol.contains(&needle)
                || entry
                    .name
                    .as_deref()
                    .unwrap_or_default()
                    .to_uppercase()
                    .contains(&needle)
        })
        .take(8)
        .map(|entry| {
            (
                entry.symbol.clone(),
                entry
                    .name
                    .clone()
                    .unwrap_or_else(|| "Tracked instrument".to_string()),
            )
        })
        .collect();
    let selected_prices: Vec<PricePoint> = data
        .prices
        .iter()
        .filter(|point| point.symbol == active_symbol)
        .cloned()
        .collect();
    let active_metric = data
        .metrics
        .iter()
        .find(|metric| metric.symbol == active_symbol)
        .cloned()
        .unwrap_or_default();
    let is_live = !is_loading && load_error.is_none();
    let view_name = match view() {
        View::Overview => "OVERVIEW",
        View::Fundamentals => "FUNDAMENTALS",
        View::Reports => "REPORTS",
        View::Portfolio => "PORTFOLIO",
        View::Universe => "UNIVERSE",
        View::Playground => "PLAYGROUND",
    };
    let shell_class = if dark() {
        "app-shell dark"
    } else {
        "app-shell"
    };
    let playground_state = playground.read();
    let playground_loading = playground_state.is_none();
    let playground_error = playground_state
        .as_ref()
        .and_then(|result| result.as_ref().err())
        .cloned();
    let playground_data = playground_state
        .as_ref()
        .and_then(|result| result.as_ref().ok())
        .cloned();
    drop(playground_state);

    rsx! {
        document::Stylesheet { href: asset!("/assets/tailwind.css") }
        div { class: "{shell_class}",
            aside { class: "sidebar",
                div { class: "brand",
                    div { class: "brand-mark", "C" }
                    div {
                        div { class: "brand-name", "CHESHIRE" }
                        div { class: "brand-subtitle", "MARKET INTELLIGENCE" }
                    }
                }
                div { class: "sidebar-label", "WORKSPACE" }
                button {
                    class: if view() == View::Overview { "nav-item active" } else { "nav-item" },
                    onclick: move |_| view.set(View::Overview),
                    span { class: "nav-icon", "◈" }
                    "Overview"
                }
                button {
                    class: if view() == View::Fundamentals { "nav-item active" } else { "nav-item" },
                    onclick: move |_| view.set(View::Fundamentals),
                    span { class: "nav-icon", "∑" }
                    "Fundamentals"
                }
                button {
                    class: if view() == View::Reports { "nav-item active" } else { "nav-item" },
                    onclick: move |_| view.set(View::Reports),
                    span { class: "nav-icon", "▤" }
                    "Reports"
                }
                button {
                    class: if view() == View::Portfolio { "nav-item active" } else { "nav-item" },
                    onclick: move |_| view.set(View::Portfolio),
                    span { class: "nav-icon", "◒" }
                    "Portfolio"
                }
                button {
                    class: if view() == View::Universe { "nav-item active" } else { "nav-item" },
                    onclick: move |_| view.set(View::Universe),
                    span { class: "nav-icon", "⌁" }
                    "Universe"
                }
                button {
                    class: if view() == View::Playground { "nav-item active" } else { "nav-item" },
                    onclick: move |_| view.set(View::Playground),
                    span { class: "nav-icon", "♜" }
                    "Playground"
                }
                div { class: "sidebar-spacer" }
                div { class: "api-card",
                    div { class: if is_live { "api-dot online" } else { "api-dot offline" } }
                    div {
                        div { class: "api-title", if is_live { "Live database" } else { "API unavailable" } }
                        div { class: "api-copy", if is_live { "PostgreSQL connected" } else { "Start cheshire-cat api" } }
                    }
                }
                div { class: "sidebar-footer", "v0.1 · Research terminal" }
            }
            main { class: "main-content",
                header { class: "topbar",
                    div { class: "topbar-heading",
                        div { class: "eyebrow", "MARKET TERMINAL / {view_name}" }
                        h1 { class: "page-title", match view() {
                            View::Overview => "Market overview",
                            View::Fundamentals => "Fundamentals ledger",
                            View::Reports => "Filing archive",
                            View::Portfolio => "Your portfolio",
                            View::Universe => "Tracked universe",
                            View::Playground => "Strategy playground",
                        }}
                        if !active_symbol.is_empty() {
                            div { class: "active-context", "Viewing {active_symbol} · {selected_metadata.exchange}" }
                        }
                    }
                    div { class: "topbar-actions",
                        div { class: "global-search-wrap",
                            span { class: "search-icon", "⌕" }
                            input {
                                class: "global-search-input",
                                value: "{search()}",
                                placeholder: "Search symbols or companies…",
                                aria_label: "Search symbols or companies",
                                oninput: move |event| search.set(event.value()),
                            }
                            if !search().trim().is_empty() && !global_matches.is_empty() {
                                div { class: "search-menu",
                                    for (symbol, name) in global_matches {
                                        button {
                                            class: "search-result",
                                            key: "search-{symbol}",
                                            onclick: move |_| {
                                                selected.set(symbol.clone());
                                                search.set(String::new());
                                                view.set(View::Overview);
                                            },
                                            span { class: "search-result-symbol", "{symbol}" }
                                            span { class: "search-result-name", "{name}" }
                                        }
                                    }
                                }
                            }
                        }
                        div { class: "market-status", span { class: if is_live { "pulse" } else { "pulse offline" } }, if is_live { "LIVE DATA" } else { "NO LIVE DATA" } }
                        button { class: "theme-button", onclick: move |_| dark.toggle(), aria_label: "Toggle dark mode", if dark() { "☼" } else { "☾" } }
                    }
                }
                if is_loading {
                    LoadingState {}
                } else if let Some(error) = load_error {
                    ErrorState { message: error }
                } else if view() == View::Overview {
                    Overview {
                        selected: active_symbol.clone(),
                        exchange: selected_metadata.exchange.clone(),
                        selected_prices: selected_prices.clone(),
                        metric: active_metric.clone(),
                        reports: data.reports.clone(),
                        fundamentals: data.fundamentals.clone(),
                        fundamental_total: data.fundamental_total,
                        fundamentals_truncated: data.fundamentals_truncated,
                        sector: data.sector.clone(),
                        ratios: data.fundamental_ratios.clone(),
                        peers: data.sector_peers.clone(),
                        on_fundamentals: move |_| view.set(View::Fundamentals),
                        on_reports: move |_| view.set(View::Reports),
                    }
                } else if view() == View::Fundamentals {
                    FundamentalsView {
                        facts: data.fundamentals.clone(),
                        selected: active_symbol.clone(),
                        total: data.fundamental_total,
                        truncated: data.fundamentals_truncated,
                    }
                } else if view() == View::Reports {
                    ReportsView { reports: data.reports.clone(), selected: active_symbol.clone() }
                } else if view() == View::Portfolio {
                    PortfolioView { points: data.portfolio.clone() }
                } else if view() == View::Playground {
                    PlaygroundView {
                        data: playground_data.clone(),
                        loading: playground_loading,
                        error: playground_error.clone(),
                        default_symbol: active_symbol.clone(),
                        on_run: move |request: String| playground_request.set(request),
                    }
                } else {
                    UniverseView {
                        entries: data.universe.clone(),
                        selected: active_symbol.clone(),
                        on_select: move |symbol: String| {
                            selected.set(symbol);
                            view.set(View::Overview);
                        },
                    }
                }
            }
        }
    }
}

#[component]
fn Overview(
    selected: String,
    exchange: String,
    selected_prices: Vec<PricePoint>,
    metric: Metric,
    reports: Vec<Report>,
    fundamentals: Vec<Fundamental>,
    fundamental_total: usize,
    fundamentals_truncated: bool,
    sector: Option<String>,
    ratios: Vec<RatioMetric>,
    peers: Vec<SectorPeer>,
    on_fundamentals: EventHandler<()>,
    on_reports: EventHandler<()>,
) -> Element {
    let mut period = use_signal(|| ChartPeriod::Year);
    let last_price = selected_prices
        .last()
        .and_then(|point| point.adj_close.or(point.close));
    let chart_prices = period_prices(&selected_prices, period());
    let first_price = chart_prices
        .first()
        .and_then(|point| point.adj_close.or(point.close));
    let change = first_price
        .zip(last_price)
        .filter(|(first, _)| *first > 0.0)
        .map(|(first, last)| last / first - 1.0);
    let recent_reports: Vec<Report> = reports
        .into_iter()
        .filter(|report| report.symbol == selected)
        .take(5)
        .collect();
    let latest_date = selected_prices
        .last()
        .map(|point| point.date.clone())
        .unwrap_or_else(|| "—".to_string());
    let first_date = chart_prices
        .first()
        .map(|point| point.date.clone())
        .unwrap_or_else(|| "—".to_string());
    let visible_facts: Vec<&Fundamental> = fundamentals.iter().take(8).collect();
    let chart_points = sparkline_points(&chart_prices);

    rsx! {
        section { class: "content-stack",
            div { class: "instrument-hero",
                div { class: "instrument-identity",
                    span { class: "section-kicker", "SELECTED INSTRUMENT" }
                    div { class: "instrument-symbol", if selected.is_empty() { "No symbol selected" } else { "{selected}" } }
                    div { class: "instrument-exchange", if exchange.is_empty() { "Tracked universe" } else { "{exchange}" } }
                }
                div { class: "instrument-price-block",
                    div { class: "instrument-price", if let Some(price) = last_price { "{format_price(price)}" } else { "—" } }
                    div { class: "instrument-price-label", "Latest stored close · {latest_date}" }
                }
                if let Some(change) = change {
                    div { class: if change >= 0.0 { "change positive" } else { "change negative" }, "{format_percent(change)} over window" }
                }
                div { class: "source-chip", "POSTGRESQL · REAL OBSERVATIONS" }
            }
            div { class: "stat-grid",
                StatCard { label: "1Y RETURN", value: metric.return_1y.map(format_percent).unwrap_or_else(|| "—".to_string()), caption: "252-session window", accent: "gold" }
                StatCard { label: "VOLATILITY", value: metric.volatility.map(format_percent).unwrap_or_else(|| "—".to_string()), caption: "Annualized from returns", accent: "blue" }
                StatCard { label: "PRICE OBSERVATIONS", value: selected_prices.len().to_string(), caption: "Stored daily rows", accent: "green" }
                StatCard { label: "FUNDAMENTAL FACTS", value: fundamental_total.to_string(), caption: if fundamentals_truncated { "Latest rows loaded below" } else { "Stored observations" }, accent: "violet" }
            }
            if selected_prices.is_empty() {
                EmptyPanel { title: "No price observations for this symbol", copy: "This instrument is tracked, but no historical prices are stored for it yet." }
            } else {
                div { class: "panel chart-panel",
                    div { class: "panel-header",
                        div { h2 { "Price history" }, p { "Adjusted close when available · {first_date} to {latest_date}" } }
                        div { class: "chart-toolbar",
                            span { class: "panel-badge", "{selected}" }
                            div { class: "period-switcher",
                                for option in ChartPeriod::options() {
                                    button { class: if period() == option { "period-button active" } else { "period-button" }, onclick: move |_| period.set(option), "{option.label()}" }
                                }
                            }
                        }
                    }
                    svg { class: "price-chart", view_box: "0 0 900 240", preserve_aspect_ratio: "none",
                        defs { linearGradient { id: "gold-gradient", x1: "0", x2: "0", y1: "0", y2: "1",
                            stop { offset: "0%", stop_color: GOLD, stop_opacity: "0.32" }
                            stop { offset: "100%", stop_color: GOLD, stop_opacity: "0" }
                        }}
                        path { d: "{chart_points.area}", fill: "url(#gold-gradient)" }
                        path { d: "{chart_points.line}", fill: "none", stroke: GOLD, stroke_width: "3", stroke_linecap: "round", stroke_linejoin: "round" }
                    }
                    div { class: "chart-axis", span { "{first_date}" }, span { "{latest_date}" } }
                }
            }
            div { class: "ratio-layout",
                div { class: "panel",
                    div { class: "panel-header",
                        div { h2 { "Major fundamental ratios" }, p { "Latest compatible annual observation · calculated from stored source data." } }
                        span { class: "panel-badge", "{ratio_source(&ratios)}" }
                    }
                    div { class: "ratio-grid",
                        for ratio in ratios {
                            RatioCard { ratio: ratio }
                        }
                    }
                }
                div { class: "panel",
                    if let Some(sector_name) = sector.clone() {
                        div { class: "panel-header", div { h2 { "{sector_name} comparison" }, p { "Companies classified in the same sector with available facts." } }, span { class: "panel-badge", "{peers.len()} PEERS" } }
                        if peers.is_empty() {
                            div { class: "empty-state", "No same-sector peers have compatible fundamentals stored yet." }
                        } else {
                            SectorPeerTable { peers: peers }
                        }
                    } else {
                        div { class: "panel-header", div { h2 { "Sector comparison" }, p { "Sector metadata is not available for this instrument." } } }
                        div { class: "empty-state", "No sector comparison is shown without source sector metadata." }
                    }
                }
            }
            div { class: "two-column",
                div { class: "panel",
                    div { class: "panel-header",
                        div { h2 { "Latest XBRL observations" }, p { "The newest eight stored facts are shown here." } }
                        button { class: "panel-link-button", onclick: move |_| on_fundamentals.call(()), "VIEW ALL →" }
                    }
                    if visible_facts.is_empty() {
                        div { class: "empty-state", "No fundamental facts are stored for this symbol." }
                    } else {
                        div { class: "table-scroll fundamentals-table-wrap",
                            table { class: "data-table fundamentals-table",
                                thead { tr { th { "Concept" } th { "Period" } th { "Form" } th { "Value" } } }
                                tbody {
                                    for fact in visible_facts {
                                        FundamentalPreviewRow { fact: fact.clone() }
                                    }
                                }
                            }
                        }
                        div { class: "data-footnote", if fundamentals_truncated { "Showing the latest 2,000 stored observations for speed. Ratios use the full compatible source set; use the database/API for the complete ledger." } else { "Fundamentals view contains every stored observation, with taxonomy, unit, filing and frame filters." } }
                    }
                }
                div { class: "panel",
                        div { class: "panel-header", div { h2 { "Recent filings" }, p { "Direct links to the original issuer or SEC source." } }, button { class: "panel-link-button", onclick: move |_| on_reports.call(()), "OPEN ARCHIVE →" } }
                    if recent_reports.is_empty() {
                        div { class: "empty-state", "No reports are stored for this symbol." }
                    } else {
                        div { class: "report-list",
                            for report in recent_reports {
                                ReportRow { report: report }
                            }
                        }
                    }
                }
            }
        }
    }
}

#[component]
fn FundamentalsView(
    facts: Vec<Fundamental>,
    selected: String,
    total: usize,
    truncated: bool,
) -> Element {
    let mut query = use_signal(String::new);
    let mut taxonomy = use_signal(String::new);
    let mut form = use_signal(String::new);
    let mut page = use_signal(|| 0usize);
    let needle = query().trim().to_lowercase();
    let selected_facts: Vec<Fundamental> = facts
        .iter()
        .filter(|fact| selected.is_empty() || fact.symbol == selected)
        .filter(|fact| taxonomy().is_empty() || fact.taxonomy == taxonomy())
        .filter(|fact| form().is_empty() || fact.form == form())
        .filter(|fact| {
            needle.is_empty()
                || fact.concept.to_lowercase().contains(&needle)
                || fact.unit.to_lowercase().contains(&needle)
                || fact
                    .frame
                    .as_deref()
                    .unwrap_or_default()
                    .to_lowercase()
                    .contains(&needle)
        })
        .cloned()
        .collect();
    let page_size = 100usize;
    let pages = selected_facts.len().div_ceil(page_size);
    let current_page = page().min(pages.saturating_sub(1));
    let start = current_page * page_size;
    let visible = selected_facts.iter().skip(start).take(page_size);
    let taxonomies = unique_sorted(facts.iter().map(|fact| fact.taxonomy.clone()));
    let forms = unique_sorted(facts.iter().map(|fact| fact.form.clone()));

    rsx! {
        section { class: "content-stack",
            div { class: "section-intro",
                div { class: "section-kicker", "FUNDAMENTALS / {selected}" }
                h2 { if truncated { "Latest stored fundamentals" } else { "Every stored fundamental observation" } }
                p { if truncated { "The dashboard loads the newest 2,000 rows for responsiveness; PostgreSQL retains the complete ledger." } else { "Search concepts and narrow the ledger by taxonomy or filing form." } }
            }
            div { class: "filter-bar",
                input { class: "filter-search", value: "{query()}", placeholder: "Search concept, unit, or frame…", aria_label: "Search fundamentals", oninput: move |event| { query.set(event.value()); } }
                select { class: "filter-select", value: "{taxonomy()}", aria_label: "Filter by taxonomy", onchange: move |event| taxonomy.set(event.value()), option { value: "", "All taxonomies" }, for value in taxonomies { option { value: "{value}", "{value}" } } }
                select { class: "filter-select", value: "{form()}", aria_label: "Filter by form", onchange: move |event| form.set(event.value()), option { value: "", "All forms" }, for value in forms { option { value: "{value}", "{value}" } } }
                span { class: "filter-count", if truncated { "{selected_facts.len()} of {total} loaded" } else { "{selected_facts.len()} observations" } }
            }
            div { class: "panel data-panel",
                if selected_facts.is_empty() {
                    EmptyPanel { title: "No fundamentals match these filters", copy: "Try clearing the search or selecting a different instrument." }
                } else {
                    div { class: "table-scroll ledger-scroll",
                        table { class: "data-table ledger-table",
                            thead { tr { th { "Concept" } th { "Taxonomy" } th { "Unit" } th { "Period end" } th { "Filed" } th { "Form" } th { "Frame" } th { "Value" } } }
                            tbody {
                                for fact in visible {
                                    FundamentalLedgerRow { fact: fact.clone() }
                                }
                            }
                        }
                    }
                    Pagination {
                        page: current_page,
                        pages: pages,
                        total: selected_facts.len(),
                        on_previous: move |_| page.set(current_page.saturating_sub(1)),
                        on_next: move |_| page.set((current_page + 1).min(pages.saturating_sub(1))),
                    }
                }
            }
        }
    }
}

#[component]
fn ReportsView(reports: Vec<Report>, selected: String) -> Element {
    let mut query = use_signal(String::new);
    let mut form = use_signal(String::new);
    let mut page = use_signal(|| 0usize);
    let needle = query().trim().to_lowercase();
    let selected_reports: Vec<Report> = reports
        .iter()
        .filter(|report| selected.is_empty() || report.symbol == selected)
        .filter(|report| form().is_empty() || report.form == form())
        .filter(|report| {
            needle.is_empty()
                || report.form.to_lowercase().contains(&needle)
                || report.accession_number.to_lowercase().contains(&needle)
                || report
                    .filing_date
                    .as_deref()
                    .unwrap_or_default()
                    .contains(&needle)
        })
        .cloned()
        .collect();
    let page_size = 100usize;
    let pages = selected_reports.len().div_ceil(page_size);
    let current_page = page().min(pages.saturating_sub(1));
    let start = current_page * page_size;
    let visible = selected_reports.iter().skip(start).take(page_size);
    let forms = unique_sorted(reports.iter().map(|report| report.form.clone()));

    rsx! {
        section { class: "content-stack",
            div { class: "section-intro",
                div { class: "section-kicker", "REPORTS / {selected}" }
                h2 { "Filing archive" }
                p { "Browse reports actually downloaded into PostgreSQL and open the authoritative issuer or SEC source." }
            }
            div { class: "filter-bar",
                input { class: "filter-search", value: "{query()}", placeholder: "Search form, accession, or date…", aria_label: "Search reports", oninput: move |event| query.set(event.value()) }
                select { class: "filter-select", value: "{form()}", aria_label: "Filter by filing form", onchange: move |event| form.set(event.value()), option { value: "", "All forms" }, for value in forms { option { value: "{value}", "{value}" } } }
                span { class: "filter-count", "{selected_reports.len()} reports" }
            }
            div { class: "panel data-panel",
                if selected_reports.is_empty() {
                    EmptyPanel { title: "No reports match these filters", copy: "This symbol may be tracked without a downloaded filing archive." }
                } else {
                    div { class: "table-scroll ledger-scroll",
                        table { class: "data-table ledger-table",
                            thead { tr { th { "Form" } th { "Filed" } th { "Period end" } th { "Accession" } th { "Source" } } }
                            tbody {
                                for report in visible {
                                    ReportArchiveRow { report: report.clone() }
                                }
                            }
                        }
                    }
                    Pagination {
                        page: current_page,
                        pages: pages,
                        total: selected_reports.len(),
                        on_previous: move |_| page.set(current_page.saturating_sub(1)),
                        on_next: move |_| page.set((current_page + 1).min(pages.saturating_sub(1))),
                    }
                }
            }
        }
    }
}

#[component]
fn UniverseView(
    entries: Vec<UniverseSymbol>,
    selected: String,
    on_select: EventHandler<String>,
) -> Element {
    let mut query = use_signal(String::new);
    let mut exchange = use_signal(String::new);
    let mut coverage = use_signal(String::new);
    let needle = query().trim().to_lowercase();
    let exchanges = unique_sorted(entries.iter().map(|entry| entry.exchange.clone()));
    let filtered: Vec<UniverseSymbol> = entries
        .iter()
        .filter(|entry| exchange().is_empty() || entry.exchange == exchange())
        .filter(|entry| match coverage().as_str() {
            "prices" => entry.price_rows > 0,
            "fundamentals" => entry.fundamental_rows > 0,
            "reports" => entry.report_rows > 0,
            "missing-fundamentals" => entry.fundamental_rows == 0,
            "missing-reports" => entry.report_rows == 0,
            _ => true,
        })
        .filter(|entry| {
            needle.is_empty()
                || entry.symbol.to_lowercase().contains(&needle)
                || entry
                    .name
                    .as_deref()
                    .unwrap_or_default()
                    .to_lowercase()
                    .contains(&needle)
        })
        .cloned()
        .collect();
    let prices = entries.iter().filter(|entry| entry.price_rows > 0).count();
    let fundamentals = entries
        .iter()
        .filter(|entry| entry.fundamental_rows > 0)
        .count();
    let reports = entries.iter().filter(|entry| entry.report_rows > 0).count();
    let filtered_is_empty = filtered.is_empty();

    rsx! {
        section { class: "content-stack",
            div { class: "hero-panel",
                div { class: "hero-copy", span { class: "hero-kicker", "UNIVERSE" }, h2 { "Choose an instrument." }, p { "Coverage counts below come directly from stored price, XBRL, and report rows." } }
                div { class: "universe-count", span { "TRACKED" }, strong { "{entries.len()}" }, small { "symbols" } }
            }
            div { class: "coverage-grid",
                CoverageCard { label: "Price history", count: prices, total: entries.len(), accent: "green" }
                CoverageCard { label: "XBRL facts", count: fundamentals, total: entries.len(), accent: "violet" }
                CoverageCard { label: "Reports", count: reports, total: entries.len(), accent: "gold" }
            }
            div { class: "panel",
                div { class: "filter-bar universe-filters",
                    input { class: "filter-search", value: "{query()}", placeholder: "Search ticker or company…", aria_label: "Search universe", oninput: move |event| query.set(event.value()) }
                    select { class: "filter-select", value: "{exchange()}", aria_label: "Filter by exchange", onchange: move |event| exchange.set(event.value()), option { value: "", "All exchanges" }, for value in exchanges { option { value: "{value}", "{value}" } } }
                    select { class: "filter-select", value: "{coverage()}", aria_label: "Filter by data coverage", onchange: move |event| coverage.set(event.value()), option { value: "", "Any coverage" }, option { value: "prices", "Has prices" }, option { value: "fundamentals", "Has fundamentals" }, option { value: "reports", "Has reports" }, option { value: "missing-fundamentals", "Missing fundamentals" }, option { value: "missing-reports", "Missing reports" } }
                    span { class: "filter-count", "{filtered.len()} shown" }
                }
                div { class: "universe-list",
                    for entry in filtered {
                        UniverseRow { entry: entry, selected: selected.clone(), on_select: on_select }
                    }
                }
                if filtered_is_empty {
                    EmptyPanel { title: "No tracked symbols match", copy: "Adjust the search or coverage filters." }
                }
            }
        }
    }
}

#[component]
fn PortfolioView(points: Vec<PortfolioPoint>) -> Element {
    rsx! {
        section { class: "content-stack",
            div { class: "section-intro",
                div { class: "section-kicker", "PORTFOLIO" }
                h2 { "Your portfolio" }
                p { "Portfolio valuation is calculated only from transactions persisted in PostgreSQL." }
            }
            if let Some(value) = points.last().and_then(|point| point.value) {
                div { class: "portfolio-hero",
                    div { class: "hero-kicker", "LATEST STORED VALUATION" }
                    div { class: "portfolio-value", "{format_price(value)}" }
                    div { class: "portfolio-note", "As of {points.last().map(|point| point.date.clone()).unwrap_or_default()}" }
                }
            }
            div { class: "panel",
                div { class: "panel-header", div { h2 { "Valuation history" }, p { "Replay of persisted portfolio transactions against stored prices." } }, span { class: "panel-badge", "POSTGRESQL" } }
                if points.is_empty() {
                    EmptyPanel { title: "Your portfolio is empty", copy: "Record a trade to see valuation here. No positions or returns are invented." }
                } else {
                    div { class: "table-scroll",
                        table { class: "data-table ledger-table",
                            thead { tr { th { "Date" } th { "Value" } } }
                            tbody {
                                for point in points {
                                    PortfolioRow { point: point }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

#[component]
fn PlaygroundView(
    data: Option<PlaygroundSnapshot>,
    loading: bool,
    error: Option<String>,
    default_symbol: String,
    on_run: EventHandler<String>,
) -> Element {
    let mut research_mode = use_signal(|| true);
    let mut symbols = use_signal(|| default_symbol.clone());
    let mut years = use_signal(|| "20".to_string());
    let mut initial_cash = use_signal(|| "100000".to_string());
    let mut transaction_cost = use_signal(|| "0.001".to_string());
    let mut fundamental_request = use_signal(|| String::new());
    let fundamental_state = use_resource(move || {
        let request = fundamental_request();
        async move {
            if request.is_empty() {
                Ok(None)
            } else {
                load_fundamental_research(request).await.map(Some)
            }
        }
    });
    let data = data.unwrap_or_default();
    let has_data = !data.strategies.is_empty();
    let fundamental_loading = fundamental_state.read().is_none();
    let fundamental_error = fundamental_state
        .read()
        .as_ref()
        .and_then(|result| result.as_ref().err())
        .cloned();
    let fundamental_report = fundamental_state
        .read()
        .as_ref()
        .and_then(|result| result.as_ref().ok())
        .cloned()
        .flatten();
    let fundamental_validation = fundamental_report
        .as_ref()
        .and_then(|report| report.manifest.decision_dates.validation_start.clone())
        .unwrap_or_else(|| "—".to_string());

    rsx! {
        section { class: "content-stack playground-page",
            div { class: "section-intro",
                div { class: "section-kicker", "RESEARCH PLAYGROUND" }
                h2 { "Put every bot on the same track." }
                p { "Run the registered strategies against stored market history, compare risk and return, and keep the leaderboard honest about the period and data actually available." }
            }
            PerformanceLegend {}
            div { class: "research-tabs", role: "tablist", aria_label: "Playground mode",
                button { role: "tab", aria_selected: "{research_mode()}", class: if research_mode() { "period-button active" } else { "period-button" }, onclick: move |_| research_mode.set(true), "Investor research · 80 / 20" }
                button { role: "tab", aria_selected: "{!research_mode()}", class: if !research_mode() { "period-button active" } else { "period-button" }, onclick: move |_| research_mode.set(false), "Basket comparison" }
            }
            if research_mode() {
                research::ResearchLab {}
            } else {
            div { class: "panel playground-controls",
                div { class: "playground-control-head",
                    div { h2 { "Build a simulation" }, p { "No forecasts or demo prices — only adjusted closes stored in PostgreSQL." } }
                    span { class: "panel-badge", "REPRODUCIBLE RUN" }
                }
                div { class: "playground-form",
                    label { class: "playground-field wide",
                        span { "Symbols / basket" }
                        input {
                            class: "filter-search",
                            value: "{symbols()}",
                            placeholder: "MC.PA, OR.PA or one symbol",
                            aria_label: "Symbols or basket",
                            oninput: move |event| symbols.set(event.value()),
                        }
                        small { "Leave one symbol to compare bots on that instrument; separate a basket with commas." }
                    }
                    label { class: "playground-field",
                        span { "Initial capital" }
                        input { class: "playground-number", type: "number", min: "1", step: "1000", value: "{initial_cash()}", oninput: move |event| initial_cash.set(event.value()) }
                        small { "Simulation units" }
                    }
                    label { class: "playground-field",
                        span { "Transaction cost" }
                        input { class: "playground-number", type: "number", min: "0", max: "0.2", step: "0.0005", value: "{transaction_cost()}", oninput: move |event| transaction_cost.set(event.value()) }
                        small { "0.001 = 10 bps per turnover" }
                    }
                    div { class: "playground-field",
                        span { "History horizon" }
                        div { class: "horizon-switcher",
                            for horizon in [5usize, 10usize, 20usize] {
                                button {
                                    class: if years() == horizon.to_string() { "period-button active" } else { "period-button" },
                                    onclick: move |_| years.set(horizon.to_string()),
                                    "{horizon}Y"
                                }
                            }
                        }
                        small { "Maximum available window is used when history is shorter." }
                    }
                    button {
                        class: "primary-button playground-run",
                        onclick: move |_| {
                            let parsed_years = years().parse::<usize>().unwrap_or(20).clamp(1, 20);
                            let parsed_cash = initial_cash().parse::<f64>().unwrap_or(100000.0).max(1.0);
                            let parsed_cost = transaction_cost().parse::<f64>().unwrap_or(0.001).clamp(0.0, 0.2);
                            on_run.call(format!(
                                "symbols={}&years={}&initial_cash={:.2}&transaction_cost={:.6}",
                                query_value(&symbols()), parsed_years, parsed_cash, parsed_cost
                            ));
                        },
                        "Run simulation →"
                    }
                }
            }
            if loading {
                div { class: "panel loading-state", div { class: "loading-spinner" }, h2 { "Running the playground" }, p { "Loading the requested real price history and replaying every bot…" } }
            } else if let Some(error) = error {
                div { class: "panel error-state", div { class: "hero-kicker", "SIMULATION UNAVAILABLE" }, h2 { "This run needs more price history" }, p { "{error}" }, div { class: "error-help", "Try another symbol or a shorter horizon." } }
            } else if !has_data {
                EmptyPanel { title: "No simulation run yet", copy: "Choose a real symbol or basket, then run the comparison." }
            } else {
                div { class: "playground-run-summary",
                    div { class: "playground-summary-main",
                        span { class: "section-kicker", "ACTUAL DATA WINDOW" }
                        strong { "{data.start_date} → {data.end_date}" }
                        span { "{data.actual_years:.1} years · {data.observations} {data.frequency} observations · {data.symbols.len()} symbols" }
                    }
                    div { class: "playground-summary-meta",
                        span { "Initial capital" }
                        strong { "{format_cash(data.initial_cash)}" }
                        span { "Annualized at {data.annualization} periods · {format_percent(data.transaction_cost)} cost" }
                    }
                }
                if let Some(readiness) = data.fundamental_readiness.clone() {
                    div { class: "panel fundamentals-readiness-panel",
                        div { class: "panel-header",
                            div { h2 { "Fundamentals readiness" }, p { "Point-in-time feature availability for this exact playground cohort." } }
                            span { class: if readiness.status == "ready" { "panel-badge positive" } else { "panel-badge" }, "{readiness.status}" }
                        }
                        div { class: "readiness-summary",
                            div { strong { "As of" }, span { "{readiness.as_of}" } }
                            div { strong { "Fundamental cohort" }, span { "{readiness.cohorts.fundamental.len()} / {readiness.symbols.len()} symbols" } }
                            div { strong { "Hybrid cohort" }, span { "{readiness.cohorts.hybrid.len()} / {readiness.symbols.len()} symbols" } }
                            div { strong { "Feature contract" }, span { "{readiness.feature_version}" } }
                        }
                        p { class: "research-note", "{readiness.explanation}" }
                        div { class: "table-scroll",
                            table { class: "data-table",
                                thead { tr { th { "Symbol" } th { "Usable features" } th { "Missing" } th { "Sources" } } }
                                tbody {
                                    for row in readiness.cohort_rows.clone() {
                                        tr {
                                            td { class: "ticker-cell", "{row.symbol}" }
                                            td { "{row.usable_feature_count} / {row.feature_count}" }
                                            td { class: "muted-cell", if row.missing_features.is_empty() { "—" } else { "{row.missing_features.join(\", \")}" } }
                                            td { class: "muted-cell", "{row.sources.len()} provenance record(s)" }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                div { class: "panel matched-fundamental-panel",
                    div { class: "panel-header",
                        div { h2 { "Matched fundamentals track" }, p { "A separate, bounded comparison on the same requested cohort, dates, execution delay and costs." } }
                        span { class: "panel-badge", "POINT-IN-TIME ONLY" }
                    }
                    p { class: "research-note", "This track is not merged into the price-only leaderboard. Unknown publication dates, stale facts and unsupported ratios remain excluded; no current snapshot is used for an earlier decision." }
                    button {
                        class: "period-button",
                        disabled: fundamental_loading,
                        onclick: move |_| {
                            let selected_years = years().parse::<usize>().unwrap_or(5).clamp(5, 20);
                            let query = format!("symbols={}&years={}&initial_cash={}&transaction_cost={}&search_budget=8", query_value(&symbols()), selected_years, initial_cash(), transaction_cost());
                            fundamental_request.set(query);
                        },
                        if fundamental_loading { "Running matched track…" } else { "Run matched fundamentals comparison →" }
                    }
                    if let Some(message) = fundamental_error {
                        p { class: "negative", "{message}" }
                    } else if let Some(report) = fundamental_report {
                        div { class: "readiness-summary",
                            div { strong { "Window" }, span { "{report.manifest.decision_dates.start} → {report.manifest.decision_dates.end}" } }
                            div { strong { "Validation" }, span { "{fundamental_validation}" } }
                            div { strong { "Feature contract" }, span { "{report.manifest.feature_version}" } }
                            div { strong { "Conclusion" }, span { "{report.conclusion.status}" } }
                        }
                        p { class: "research-note", "{report.conclusion.text} Same {report.manifest.currency} cohort, {report.manifest.transaction_cost * 10000.0:.0} bps cost, {report.manifest.decision_dates.matched_periods} matched periods, and {report.manifest.search_budget} predeclared candidates." }
                        div { class: "table-scroll",
                            table { class: "data-table",
                                thead { tr { th { "Candidate" } th { "Training CAGR" } th { "Validation CAGR" } th { "Coverage" } } }
                                tbody { for trial in report.trials {
                                    tr { key: "fundamental-{trial.id}", td { strong { "{trial.id}" } }, td { ReturnValue { value: trial.training.annualized_return } }, td { ReturnValue { value: trial.validation.annualized_return } }, td { "{trial.feature_coverage.rate * 100.0:.1}%" } }
                                } }
                            }
                        }
                    }
                }
                div { class: "panel",
                    div { class: "panel-header",
                        div { h2 { "Risk-adjusted leaderboard" }, p { "Ranked by Sharpe ratio; raw return and drawdown remain visible." } }
                        span { class: "panel-badge", "{data.requested_years}Y REQUESTED" }
                    }
                    LeaderboardTable { strategies: data.strategies.clone() }
                }
                div { class: "panel playground-chart-panel",
                    div { class: "panel-header",
                        div { h2 { "Growth of simulation capital" }, p { "Every line starts at 100 so the paths are directly comparable." } }
                        span { class: "panel-badge", "NORMALIZED" }
                    }
                    PlaygroundChart { strategies: data.strategies.clone() }
                }
                div { class: "strategy-grid",
                    for strategy in data.strategies.clone() {
                        StrategyCard { strategy: strategy }
                    }
                }
                div { class: "panel methodology-panel",
                    div { class: "panel-header", div { h2 { "How to read this" } }, span { class: "panel-badge", "METHOD" } }
                    div { class: "methodology-grid",
                        div { strong { "Leakage-safe signals" }, p { "Signals are shifted by one stored period before returns are applied." } }
                        div { strong { "Real costs" }, p { "Turnover is charged using the configured transaction cost on every replay." } }
                        div { strong { "Same starting line" }, p { "Every strategy receives the same symbols, dates and initial capital." } }
                        div { strong { "Extensible registry" }, p { "New bots can be added to the strategy catalog without changing the leaderboard contract." } }
                    }
                }
            }
            }
        }
    }
}

#[component]
fn LeaderboardTable(strategies: Vec<PlaygroundStrategy>) -> Element {
    rsx! {
        div { class: "table-scroll",
            table { class: "data-table leaderboard-table",
                thead { tr { th { "Rank" } th { "Strategy" } th { "Annualized" } th { "Total return" } th { "Sharpe" } th { "Max drawdown" } th { "Ending value" } } }
                tbody {
                    for strategy in strategies {
                        tr { key: "leader-{strategy.id}",
                            td { class: "rank-cell", "#{strategy.rank}" }
                            td { strong { "{strategy.name}" }, div { class: "table-subtle", "{strategy.family}" } }
                            td { class: "number", ReturnValue { value: strategy.metrics.annualized_return } }
                            td { class: "number", ReturnValue { value: strategy.metrics.total_return } }
                            td { class: "number", "{strategy.metrics.sharpe:.2}" }
                            td { class: "number", ReturnValue { value: strategy.metrics.max_drawdown } }
                            td { class: "number", "{format_cash(strategy.metrics.final_value)}" }
                        }
                    }
                }
            }
        }
    }
}

#[component]
fn PlaygroundChart(strategies: Vec<PlaygroundStrategy>) -> Element {
    let normalized: Vec<Vec<f64>> = strategies.iter().map(normalized_curve).collect();
    let all_values: Vec<f64> = normalized
        .iter()
        .flat_map(|values| values.iter().copied())
        .collect();
    let min = all_values.iter().copied().fold(f64::INFINITY, f64::min);
    let max = all_values.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let low = if min.is_finite() { min } else { 0.0 };
    let high = if max.is_finite() { max } else { 100.0 };
    let colors = ["#d6a84f", "#77b7d8", "#7fc49b", "#b99be8", "#e18e84"];
    rsx! {
        svg { class: "playground-chart", view_box: "0 0 900 300", preserve_aspect_ratio: "none",
            line { x1: "0", y1: "255", x2: "900", y2: "255", stroke: "#302d27", stroke_width: "1" }
            line { x1: "0", y1: "145", x2: "900", y2: "145", stroke: "#302d27", stroke_width: "1" }
            line { x1: "0", y1: "35", x2: "900", y2: "35", stroke: "#302d27", stroke_width: "1" }
            text { x: "8", y: "29", fill: "#9c978d", font_size: "10", "{high:.0}" }
            text { x: "8", y: "139", fill: "#9c978d", font_size: "10", "{((high + low) / 2.0):.0}" }
            text { x: "8", y: "249", fill: "#9c978d", font_size: "10", "{low:.0}" }
            for (index, strategy) in strategies.iter().enumerate() {
                path { d: "{chart_path(&strategy.curve, low, high)}", fill: "none", stroke: "{colors[index % colors.len()]}", stroke_width: if strategy.is_benchmark { "2" } else { "3" }, stroke_linecap: "round", stroke_linejoin: "round", opacity: if strategy.is_benchmark { "0.72" } else { "0.95" } }
            }
        }
        div { class: "chart-legend",
            for (index, strategy) in strategies.iter().enumerate() {
                div { class: "legend-item", span { class: "legend-swatch", style: "background:{colors[index % colors.len()]}" }, "{strategy.name}" }
            }
        }
    }
}

#[component]
fn StrategyCard(strategy: PlaygroundStrategy) -> Element {
    rsx! {
        div { class: if strategy.is_benchmark { "strategy-card benchmark" } else { "strategy-card" },
            div { class: "strategy-card-top", span { class: "strategy-family", "{strategy.family}" }, span { class: "strategy-rank", "#{strategy.rank}" } }
            h3 { "{strategy.name}" }
            p { "{strategy.description}" }
            div { class: "strategy-metrics",
                div { span { "CAGR" }, strong { ReturnValue { value: strategy.metrics.annualized_return } } }
                div { span { "Sharpe" }, strong { "{strategy.metrics.sharpe:.2}" } }
                div { span { "Drawdown" }, strong { ReturnValue { value: strategy.metrics.max_drawdown } } }
                div { span { "Exposure" }, strong { "{format_percent(strategy.metrics.exposure)}" } }
            }
        }
    }
}

#[component]
fn RatioCard(ratio: RatioMetric) -> Element {
    let value = ratio
        .value
        .map(|value| {
            if ratio.kind == "percent" {
                format_percent(value)
            } else {
                format!("{value:.2}x")
            }
        })
        .unwrap_or_else(|| "—".to_string());
    let source = ratio
        .source
        .unwrap_or_else(|| "No compatible observation".to_string());
    rsx! {
        div { class: "ratio-card",
            div { class: "ratio-label", "{ratio.label}" }
            strong { "{value}" }
            span { "{source}" }
            if let Some(period_end) = ratio.period_end {
                small { "As of {period_end}" }
            }
        }
    }
}

#[component]
fn SectorPeerTable(peers: Vec<SectorPeer>) -> Element {
    rsx! {
        div { class: "table-scroll peer-table-wrap",
            table { class: "data-table peer-table",
                thead { tr { th { "Company" } th { "Price" } th { "P/E" } th { "P/S" } th { "P/B" } th { "Net margin" } th { "ROE" } } }
                tbody {
                    for peer in peers {
                        SectorPeerRow { peer: peer }
                    }
                }
            }
        }
    }
}

#[component]
fn SectorPeerRow(peer: SectorPeer) -> Element {
    let name = peer
        .name
        .clone()
        .unwrap_or_else(|| "Name unavailable".to_string());
    let price = peer
        .last_price
        .map(format_price)
        .unwrap_or_else(|| "—".to_string());
    let pe = peer_ratio(&peer, "pe");
    let ps = peer_ratio(&peer, "ps");
    let pb = peer_ratio(&peer, "pb");
    let net_margin = peer_ratio(&peer, "net_margin");
    let roe = peer_ratio(&peer, "roe");
    rsx! {
        tr { key: "peer-{peer.symbol}",
            td { strong { "{peer.symbol}" }, div { class: "table-subtle", "{name}" } }
            td { class: "number", "{price}" }
            td { class: "number", "{pe}" }
            td { class: "number", "{ps}" }
            td { class: "number", "{pb}" }
            td { class: "number", "{net_margin}" }
            td { class: "number", "{roe}" }
        }
    }
}

#[component]
fn FundamentalPreviewRow(fact: Fundamental) -> Element {
    rsx! {
        tr { key: "{fact.taxonomy}-{fact.concept}-{fact.unit}-{fact.period_end}-{fact.filed:?}-{fact.form}",
            td { strong { "{fact.concept}" }, div { class: "table-subtle", "{fact.taxonomy} · {fact.unit}" } }
            td { class: "muted", "{fact.period_end}" }
            td { class: "muted", "{fact.form}" }
            td { class: "number", "{fundamental_value(&fact)}" }
        }
    }
}

#[component]
fn FundamentalLedgerRow(fact: Fundamental) -> Element {
    let frame = fact.frame.clone().unwrap_or_else(|| "—".to_string());
    rsx! {
        tr { key: "{fact.symbol}-{fact.taxonomy}-{fact.concept}-{fact.unit}-{fact.period_end}-{fact.filed:?}-{fact.form}",
            td { strong { "{fact.concept}" } }
            td { class: "muted", "{fact.taxonomy}" }
            td { class: "muted", "{fact.unit}" }
            td { class: "muted", "{fact.period_end}" }
            td { class: "muted", "{fact.filed.clone().unwrap_or_else(|| \"unknown\".to_string())}" }
            td { class: "muted", "{fact.form}" }
            td { class: "muted", "{frame}" }
            td { class: "number", "{fundamental_value(&fact)}" }
        }
    }
}

#[component]
fn ReportArchiveRow(report: Report) -> Element {
    let filing_date = report
        .filing_date
        .clone()
        .unwrap_or_else(|| "—".to_string());
    let period_end = report.period_end.clone().unwrap_or_else(|| "—".to_string());
    rsx! {
        tr { key: "{report.symbol}-{report.accession_number}",
            td { strong { "{report.form}" } }
            td { class: "muted", "{filing_date}" }
            td { class: "muted", "{period_end}" }
            td { class: "muted accession", "{report.accession_number}" }
            td { a { class: "source-link", href: "{report.source_url}", target: "_blank", rel: "noopener noreferrer", "Open source ↗" } }
        }
    }
}

#[component]
fn UniverseRow(
    entry: UniverseSymbol,
    selected: String,
    on_select: EventHandler<String>,
) -> Element {
    let symbol = entry.symbol.clone();
    let name = entry
        .name
        .clone()
        .unwrap_or_else(|| "Name not available".to_string());
    let class = if symbol == selected {
        "universe-row selected"
    } else {
        "universe-row"
    };
    rsx! {
        button { class: "{class}", key: "universe-{symbol}", onclick: move |_| on_select.call(symbol.clone()),
            div { class: "universe-primary", strong { "{entry.symbol}" }, span { "{name}" } }
            span { class: "exchange-badge", "{entry.exchange}" }
            div { class: "coverage-badges",
                span { class: if entry.price_rows > 0 { "data-badge available" } else { "data-badge" }, "{entry.price_rows} prices" }
                span { class: if entry.fundamental_rows > 0 { "data-badge available" } else { "data-badge" }, "{entry.fundamental_rows} facts" }
                span { class: if entry.report_rows > 0 { "data-badge available" } else { "data-badge" }, "{entry.report_rows} reports" }
            }
            span { class: "row-arrow", "→" }
        }
    }
}

#[component]
fn PortfolioRow(point: PortfolioPoint) -> Element {
    let value = point
        .value
        .map(format_price)
        .unwrap_or_else(|| "—".to_string());
    rsx! { tr { key: "portfolio-{point.date}", td { "{point.date}" }, td { class: "number", "{value}" } } }
}

#[component]
fn ReportRow(report: Report) -> Element {
    let filing_date = report
        .filing_date
        .clone()
        .unwrap_or_else(|| "—".to_string());
    let period_end = report
        .period_end
        .clone()
        .unwrap_or_else(|| "period unavailable".to_string());
    rsx! {
        div { class: "report-row", key: "{report.symbol}-{report.accession_number}",
            div { class: "report-icon", "▤" }
            div { class: "report-info", strong { "{report.form}" }, span { "Filed {filing_date} · {period_end}" } }
            a { class: "report-open", href: "{report.source_url}", target: "_blank", rel: "noopener noreferrer", "Open ↗" }
        }
    }
}

#[component]
fn StatCard(label: &'static str, value: String, caption: String, accent: &'static str) -> Element {
    rsx! {
        div { class: "stat-card {accent}",
            div { class: "stat-label", "{label}" }
            div { class: "stat-value", "{value}" }
            div { class: "stat-caption", "{caption}" }
            div { class: "stat-line" }
        }
    }
}

#[component]
fn CoverageCard(label: &'static str, count: usize, total: usize, accent: &'static str) -> Element {
    let percent = if total > 0 {
        count as f64 / total as f64 * 100.0
    } else {
        0.0
    };
    rsx! {
        div { class: "coverage-card {accent}",
            span { class: "coverage-label", "{label}" }
            strong { "{count}" }
            span { "of {total} symbols · {percent:.1}%" }
        }
    }
}

#[component]
fn Pagination(
    page: usize,
    pages: usize,
    total: usize,
    on_previous: EventHandler<()>,
    on_next: EventHandler<()>,
) -> Element {
    rsx! {
        div { class: "pagination",
            span { "{total} records · page {page + 1} of {pages.max(1)}" }
            div {
                button { class: "pagination-button", disabled: page == 0, onclick: move |_| on_previous.call(()), "Previous" }
                button { class: "pagination-button", disabled: pages == 0 || page + 1 >= pages, onclick: move |_| on_next.call(()), "Next" }
            }
        }
    }
}

#[component]
fn EmptyPanel(title: &'static str, copy: &'static str) -> Element {
    rsx! { div { class: "empty-panel", div { class: "empty-panel-icon", "—" }, h3 { "{title}" }, p { "{copy}" } } }
}

#[component]
fn LoadingState() -> Element {
    rsx! { section { class: "content-stack", div { class: "panel loading-state", div { class: "loading-spinner" }, h2 { "Loading live data" }, p { "Reading the selected instrument from PostgreSQL…" } } } }
}

#[component]
fn ErrorState(message: String) -> Element {
    rsx! { section { class: "content-stack", div { class: "panel error-state", div { class: "hero-kicker", "DATA CONNECTION" }, h2 { "The API is unavailable" }, p { "{message}" }, div { class: "error-help", "Start the stack with `just dashboard`, then reload this page." } } } }
}

fn period_prices(points: &[PricePoint], period: ChartPeriod) -> Vec<PricePoint> {
    let Some(observations) = period.observations() else {
        return points.to_vec();
    };
    let start = points.len().saturating_sub(observations);
    points[start..].to_vec()
}

fn ratio_source(ratios: &[RatioMetric]) -> String {
    ratios
        .iter()
        .find_map(|ratio| ratio.source.clone())
        .unwrap_or_else(|| "NO COMPATIBLE DATA".to_string())
}

fn peer_ratio(peer: &SectorPeer, key: &str) -> String {
    let Some(ratio) = peer.ratios.iter().find(|ratio| ratio.key == key) else {
        return "—".to_string();
    };
    let Some(value) = ratio.value else {
        return "—".to_string();
    };
    if ratio.kind == "percent" {
        format_percent(value)
    } else {
        format!("{value:.2}x")
    }
}

struct Sparkline {
    line: String,
    area: String,
}

fn sparkline_points(points: &[PricePoint]) -> Sparkline {
    let values: Vec<f64> = points
        .iter()
        .filter_map(|point| point.adj_close.or(point.close))
        .collect();
    if values.len() < 2 {
        return Sparkline {
            line: "M 0 120 L 900 120".to_string(),
            area: "M 0 120 L 900 120 L 900 240 L 0 240 Z".to_string(),
        };
    }
    let min = values.iter().copied().fold(f64::INFINITY, f64::min);
    let max = values.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let range = (max - min).max(0.0001);
    let coords: Vec<(f64, f64)> = values
        .iter()
        .enumerate()
        .map(|(index, value)| {
            let x = index as f64 / (values.len() - 1) as f64 * 900.0;
            let y = 205.0 - ((value - min) / range * 170.0);
            (x, y)
        })
        .collect();
    let line = coords
        .iter()
        .enumerate()
        .map(|(index, (x, y))| format!("{} {:.1} {:.1}", if index == 0 { "M" } else { "L" }, x, y))
        .collect::<Vec<_>>()
        .join(" ");
    let area = format!("{line} L 900 240 L 0 240 Z");
    Sparkline { line, area }
}

fn unique_sorted(values: impl Iterator<Item = String>) -> Vec<String> {
    let mut values: Vec<String> = values.collect();
    values.sort();
    values.dedup();
    values
}

fn format_percent(value: f64) -> String {
    format!("{:+.2}%", value * 100.0)
}

fn format_price(value: f64) -> String {
    format!("{value:.2}")
}

fn format_cash(value: f64) -> String {
    if value.abs() >= 1_000_000_000.0 {
        format!("{:.2}B", value / 1_000_000_000.0)
    } else if value.abs() >= 1_000_000.0 {
        format!("{:.2}M", value / 1_000_000.0)
    } else if value.abs() >= 1_000.0 {
        format!("{:.1}k", value / 1_000.0)
    } else {
        format!("{value:.0}")
    }
}

fn format_number(value: f64) -> String {
    if value.abs() >= 1_000_000_000.0 {
        format!("{:.2}B", value / 1_000_000_000.0)
    } else if value.abs() >= 1_000_000.0 {
        format!("{:.2}M", value / 1_000_000.0)
    } else {
        format!("{value:.2}")
    }
}

fn fundamental_value(fact: &Fundamental) -> String {
    fact.value
        .map(format_number)
        .unwrap_or_else(|| "—".to_string())
}

fn query_value(value: &str) -> String {
    value
        .trim()
        .replace('%', "%25")
        .replace(' ', "%20")
        .replace('#', "%23")
        .replace('&', "%26")
}

fn normalized_curve(strategy: &PlaygroundStrategy) -> Vec<f64> {
    let Some(first) = strategy.curve.first().map(|point| point.value) else {
        return Vec::new();
    };
    if first <= 0.0 {
        return strategy.curve.iter().map(|point| point.value).collect();
    }
    strategy
        .curve
        .iter()
        .map(|point| point.value / first * 100.0)
        .collect()
}

fn chart_path(curve: &[EquityPoint], low: f64, high: f64) -> String {
    if curve.len() < 2 {
        return "M 0 145 L 900 145".to_string();
    }
    let first = curve.first().map(|point| point.value).unwrap_or(1.0);
    let values: Vec<f64> = if first > 0.0 {
        curve
            .iter()
            .map(|point| point.value / first * 100.0)
            .collect()
    } else {
        curve.iter().map(|point| point.value).collect()
    };
    let range = (high - low).max(0.0001);
    values
        .iter()
        .enumerate()
        .map(|(index, value)| {
            let x = index as f64 / (values.len() - 1) as f64 * 900.0;
            let y = 255.0 - ((*value - low) / range * 220.0);
            format!(
                "{} {:.1} {:.1}",
                if index == 0 { "M" } else { "L" },
                x,
                y.clamp(25.0, 265.0)
            )
        })
        .collect::<Vec<_>>()
        .join(" ")
}

async fn load_snapshot(symbol: String) -> Result<DashboardSnapshot, String> {
    #[cfg(target_arch = "wasm32")]
    {
        let path = if symbol.is_empty() {
            "/api/dashboard".to_string()
        } else {
            format!("/api/dashboard?symbol={symbol}")
        };
        let endpoint = if API_BASE.is_empty() {
            path
        } else {
            format!("{API_BASE}{path}")
        };
        let response = gloo_net::http::Request::get(&endpoint)
            .send()
            .await
            .map_err(|error| error.to_string())?;
        if !response.ok() {
            return Err(format!("API returned HTTP {}", response.status()));
        }
        response.json().await.map_err(|error| error.to_string())
    }
    #[cfg(not(target_arch = "wasm32"))]
    {
        let _ = symbol;
        Err("dashboard data is loaded by the browser".to_string())
    }
}

async fn load_playground(request: String, symbol: String) -> Result<PlaygroundSnapshot, String> {
    #[cfg(target_arch = "wasm32")]
    {
        let query = if request.is_empty() {
            format!("symbols={}", query_value(&symbol))
        } else {
            request
        };
        let path = format!("/api/playground?{query}");
        let endpoint = if API_BASE.is_empty() {
            path
        } else {
            format!("{API_BASE}{path}")
        };
        let response = gloo_net::http::Request::get(&endpoint)
            .send()
            .await
            .map_err(|error| error.to_string())?;
        if !response.ok() {
            return Err(format!("API returned HTTP {}", response.status()));
        }
        response.json().await.map_err(|error| error.to_string())
    }
    #[cfg(not(target_arch = "wasm32"))]
    {
        let _ = (request, symbol);
        Err("playground data is loaded by the browser".to_string())
    }
}

async fn load_fundamental_research(request: String) -> Result<MatchedFundamentalReport, String> {
    #[cfg(target_arch = "wasm32")]
    {
        let path = format!("/api/fundamentals/research?{request}");
        let endpoint = if API_BASE.is_empty() {
            path
        } else {
            format!("{API_BASE}{path}")
        };
        let response = gloo_net::http::Request::get(&endpoint)
            .send()
            .await
            .map_err(|error| error.to_string())?;
        if !response.ok() {
            return Err(format!("API returned HTTP {}", response.status()));
        }
        response.json().await.map_err(|error| error.to_string())
    }
    #[cfg(not(target_arch = "wasm32"))]
    {
        let _ = request;
        Err("fundamental research is loaded by the browser".to_string())
    }
}
