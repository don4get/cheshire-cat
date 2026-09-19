use dioxus::prelude::*;
use serde::Deserialize;

const GOLD: &str = "#d6a84f";

#[derive(Clone, Copy, PartialEq)]
enum View {
    Overview,
    Portfolio,
    Universe,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct DashboardSnapshot {
    symbols: Vec<String>,
    selected_symbol: Option<String>,
    selected_exchange: Option<String>,
    prices: Vec<PricePoint>,
    metrics: Vec<Metric>,
    fundamentals: Vec<Fundamental>,
    reports: Vec<Report>,
    portfolio: Vec<PortfolioPoint>,
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
    concept: String,
    unit: String,
    period_end: String,
    value: Option<f64>,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct Report {
    symbol: String,
    form: String,
    filing_date: String,
    markdown_path: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
struct PortfolioPoint {
    date: String,
    value: Option<f64>,
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
    let snapshot = use_resource(move || {
        let symbol = selected();
        async move { load_snapshot(symbol).await }
    });

    let live_snapshot = snapshot
        .read()
        .as_ref()
        .and_then(|result| result.as_ref().ok())
        .cloned();
    let is_live = live_snapshot.is_some();
    let data = live_snapshot.unwrap_or_default();
    let active_symbol = if selected().is_empty() {
        data.selected_symbol.clone().unwrap_or_default()
    } else {
        selected()
    };
    let filtered_symbols: Vec<String> = data
        .symbols
        .iter()
        .filter(|symbol| search().is_empty() || symbol.contains(&search().to_uppercase()))
        .take(16)
        .cloned()
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
    let api_status_class = if is_live { "online" } else { "offline" };
    let view_name = match view() {
        View::Overview => "OVERVIEW",
        View::Portfolio => "PORTFOLIO",
        View::Universe => "UNIVERSE",
    };
    let shell_class = if dark() {
        "app-shell dark"
    } else {
        "app-shell"
    };

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
                div { class: "sidebar-spacer" }
                div { class: "api-card",
                    div { class: "api-dot {api_status_class}" }
                    div {
                        div { class: "api-title", if is_live { "Live database" } else { "API unavailable" } }
                        div { class: "api-copy", if is_live { "PostgreSQL connected" } else { "Start cheshire-cat api" } }
                    }
                }
                div { class: "sidebar-footer", "v0.1 · Research terminal" }
            }
            main { class: "main-content",
                header { class: "topbar",
                    div {
                        div { class: "eyebrow", "MARKET TERMINAL / {view_name}" }
                        h1 { class: "page-title", match view() {
                            View::Overview => "Market overview",
                            View::Portfolio => "Your portfolio",
                            View::Universe => "Tracked universe",
                        }}
                    }
                    div { class: "topbar-actions",
                        div { class: "market-status", span { class: "pulse" }, if is_live { "LIVE DATA" } else { "NO LIVE DATA" } }
                        button { class: "theme-button", onclick: move |_| dark.toggle(), aria_label: "Toggle dark mode", if dark() { "☼" } else { "☾" } }
                    }
                }
                if view() == View::Overview {
                    if !is_live {
                        DataState { title: "Live data unavailable", copy: "Start the API and reload the dashboard." }
                    } else if !selected_prices.iter().any(|point| point.adj_close.or(point.close).is_some()) {
                        DataState { title: "No historical data loaded", copy: "Run the universe ingestion command to populate PostgreSQL." }
                    } else {
                        Overview {
                            selected: active_symbol.clone(),
                            exchange: data.selected_exchange.clone().unwrap_or_else(|| "—".to_string()),
                            selected_prices: selected_prices.clone(),
                            metric: active_metric.clone(),
                            reports: data.reports.clone(),
                            fundamentals: data.fundamentals.clone(),
                        }
                    }
                } else if view() == View::Portfolio {
                    PortfolioView { points: data.portfolio.clone() }
                } else {
                    UniverseView {
                        search: search(),
                        symbols: filtered_symbols.clone(),
                        total: data.symbols.len(),
                        selected: active_symbol.clone(),
                        on_search: move |value: String| search.set(value),
                        on_select: move |symbol: String| selected.set(symbol),
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
) -> Element {
    let last_price = selected_prices
        .last()
        .and_then(|point| point.adj_close.or(point.close));
    let first_price = selected_prices
        .first()
        .and_then(|point| point.adj_close.or(point.close));
    let change = first_price
        .zip(last_price)
        .filter(|(first, _)| *first > 0.0)
        .map(|(first, last)| last / first - 1.0);
    let price_label = last_price
        .map(|price| format!("${price:.2}"))
        .unwrap_or_else(|| "—".to_string());
    let chart_points = sparkline_points(&selected_prices);
    let recent_reports: Vec<Report> = reports
        .into_iter()
        .filter(|report| report.symbol == selected)
        .take(4)
        .collect();
    let recent_facts: Vec<Fundamental> = fundamentals
        .into_iter()
        .filter(|fact| fact.symbol == selected)
        .take(5)
        .collect();
    let latest_date = selected_prices
        .last()
        .map(|point| point.date.clone())
        .unwrap_or_else(|| "—".to_string());

    rsx! {
        section { class: "content-stack",
            div { class: "ticker-strip",
                div { class: "ticker-heading",
                    span { class: "ticker-symbol", "{selected}" }
                    span { class: "ticker-exchange", "{exchange}" }
                }
                div { class: "ticker-price", "{price_label}" }
                if let Some(change) = change {
                    div { class: if change >= 0.0 { "change positive" } else { "change negative" }, "{change:+.2}%" }
                }
                div { class: "ticker-meta", "Latest close · {latest_date}" }
            }
            div { class: "stat-grid",
                StatCard { label: "1Y RETURN", value: metric.return_1y.map(format_percent).unwrap_or_else(|| "—".to_string()), accent: "gold" }
                StatCard { label: "VOLATILITY", value: metric.volatility.map(format_percent).unwrap_or_else(|| "—".to_string()), accent: "blue" }
                StatCard { label: "OBSERVATIONS", value: selected_prices.len().to_string(), accent: "green" }
                StatCard { label: "FILINGS", value: recent_reports.len().to_string(), accent: "violet" }
            }
            div { class: "panel chart-panel",
                div { class: "panel-header",
                    div { h2 { "Price performance" }, p { "Adjusted close · historical observations" } }
                    span { class: "panel-badge", "{selected}" }
                }
                svg { class: "price-chart", view_box: "0 0 900 240", preserve_aspect_ratio: "none",
                    defs { linearGradient { id: "gold-gradient", x1: "0", x2: "0", y1: "0", y2: "1",
                        stop { offset: "0%", stop_color: GOLD, stop_opacity: "0.32" }
                        stop { offset: "100%", stop_color: GOLD, stop_opacity: "0" }
                    }}
                    path { d: "{chart_points.area}", fill: "url(#gold-gradient)" }
                    path { d: "{chart_points.line}", fill: "none", stroke: GOLD, stroke_width: "3", stroke_linecap: "round", stroke_linejoin: "round" }
                }
                div { class: "chart-axis", span { "12M AGO" }, span { "6M AGO" }, span { "NOW" } }
            }
            div { class: "two-column",
                div { class: "panel",
                    div { class: "panel-header", h2 { "Latest fundamentals" }, span { class: "panel-link", "SEC XBRL" } }
                    table { class: "data-table",
                        thead { tr { th { "Concept" } th { "Period" } th { "Value" } } }
                        tbody {
                            for fact in recent_facts {
                                tr { key: "{fact.concept}-{fact.period_end}", td { "{fact.concept}" }, td { class: "muted", "{fact.period_end}" }, td { class: "number", "{fundamental_value(&fact)}" } }
                            }
                        }
                    }
                }
                div { class: "panel",
                    div { class: "panel-header", h2 { "Recent publications" }, span { class: "panel-link", "ARCHIVE" } }
                    div { class: "report-list",
                        for report in recent_reports {
                            div { class: "report-row", key: "{report.form}-{report.filing_date}",
                                div { class: "report-icon", "▤" }
                                div { class: "report-info", strong { "{report.form}" }, span { "Filed {report.filing_date}" } }
                                span { class: "report-arrow", "↗" }
                            }
                        }
                    }
                }
            }
        }
    }
}

#[component]
fn StatCard(label: &'static str, value: String, accent: &'static str) -> Element {
    rsx! { div { class: "stat-card {accent}", div { class: "stat-label", "{label}" }, div { class: "stat-value", "{value}" }, div { class: "stat-line" } } }
}

#[component]
fn UniverseView(
    search: String,
    symbols: Vec<String>,
    total: usize,
    selected: String,
    on_search: EventHandler<String>,
    on_select: EventHandler<String>,
) -> Element {
    rsx! {
        section { class: "content-stack",
            div { class: "hero-panel",
                div { class: "hero-copy", span { class: "hero-kicker", "UNIVERSE" }, h2 { "Signal over noise." }, p { "Nasdaq and French PEA candidates, refreshed in small daily slices to respect provider limits." } }
                div { class: "universe-count", span { "TRACKED" }, strong { "{total}" }, small { "symbols" } }
            }
            div { class: "panel",
                div { class: "toolbar", h2 { "Symbols" }, input { class: "search-input", value: "{search}", placeholder: "Search ticker…", oninput: move |event| on_search.call(event.value()) } }
                div { class: "symbol-grid",
                    for symbol in symbols {
                        button { class: if symbol == selected { "symbol-chip selected" } else { "symbol-chip" }, key: "{symbol}", onclick: move |_| on_select.call(symbol.clone()), strong { "{symbol}" }, span { "Equity" } }
                    }
                }
            }
        }
    }
}

#[component]
fn PortfolioView(points: Vec<PortfolioPoint>) -> Element {
    rsx! {
        section { class: "content-stack",
            if let Some(value) = points.last().and_then(|point| point.value) {
                div { class: "portfolio-hero",
                    div { class: "hero-kicker", "TOTAL PORTFOLIO VALUE" }
                    div { class: "portfolio-value", "${value:.2}" }
                }
            }
            div { class: "panel",
                div { class: "panel-header", h2 { "Portfolio curve" }, span { class: "panel-badge", "POSTGRESQL" } }
                div { class: "empty-state", if points.is_empty() { "No portfolio transactions are stored." } else { "Portfolio observations loaded from PostgreSQL." } }
            }
        }
    }
}

#[component]
fn DataState(title: &'static str, copy: &'static str) -> Element {
    rsx! {
        section { class: "content-stack",
            div { class: "panel empty-state",
                div { class: "hero-kicker", "NO FABRICATED DATA" }
                h2 { "{title}" }
                p { "{copy}" }
            }
        }
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

fn format_percent(value: f64) -> String {
    format!("{:+.2}%", value * 100.0)
}
fn format_number(value: f64) -> String {
    if value.abs() >= 1_000_000_000.0 {
        format!("{:.2}B", value / 1_000_000_000.0)
    } else if value.abs() >= 1_000_000.0 {
        format!("{:.2}M", value / 1_000_000.0)
    } else {
        format!("{:.2}", value)
    }
}
fn fundamental_value(fact: &Fundamental) -> String {
    fact.value
        .map(format_number)
        .unwrap_or_else(|| "—".to_string())
}

async fn load_snapshot(symbol: String) -> Result<DashboardSnapshot, String> {
    #[cfg(target_arch = "wasm32")]
    {
        let endpoint = if symbol.is_empty() {
            "/api/dashboard".to_string()
        } else {
            format!("/api/dashboard?symbol={symbol}")
        };
        let response = gloo_net::http::Request::get(&endpoint)
            .send()
            .await
            .map_err(|error| error.to_string())?;
        response.json().await.map_err(|error| error.to_string())
    }
    #[cfg(not(target_arch = "wasm32"))]
    {
        let _ = symbol;
        Err("dashboard data is loaded by the browser".to_string())
    }
}
