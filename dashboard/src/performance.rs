use dioxus::prelude::*;

// Classify the displayed precision, so a rounded 0.00% is never a red loss.
fn displayed_percent(value: f64) -> f64 {
    (value * 10_000.0).round() / 100.0
}

pub fn return_class(value: f64) -> &'static str {
    let displayed = displayed_percent(value);
    if !displayed.is_finite() || displayed == 0.0 {
        "return-neutral"
    } else if displayed > 0.0 {
        "return-gain"
    } else {
        "return-loss"
    }
}

fn return_label(value: f64, points: bool) -> String {
    let displayed = displayed_percent(value);
    if !displayed.is_finite() {
        return "—".into();
    }
    let unit = if points { " pp" } else { "%" };
    if displayed == 0.0 {
        format!("0.00{unit}")
    } else {
        format!("{displayed:+.2}{unit}")
    }
}

#[component]
pub fn ReturnValue(value: f64, #[props(default)] points: bool) -> Element {
    let class = return_class(value);
    let label = return_label(value, points);
    let description = if !value.is_finite() {
        "Not available"
    } else if class == "return-neutral" {
        "No change at displayed precision"
    } else if points && value > 0.0 {
        "Above benchmark"
    } else if points {
        "Below benchmark"
    } else if value > 0.0 {
        "Positive return"
    } else {
        "Negative return / decline"
    };
    rsx! { span { class: "return-value {class}", title: "{description}", "{label}" } }
}

fn interval_state(lower: f64, upper: f64) -> (&'static str, &'static str) {
    if !lower.is_finite() || !upper.is_finite() || lower > upper {
        ("return-neutral", "Interval unavailable")
    } else if lower <= 0.0 && upper >= 0.0 {
        ("return-uncertain", "Uncertain · interval includes zero")
    } else if lower > 0.0 {
        ("return-gain", "Positive interval in this sample")
    } else {
        ("return-loss", "Negative interval in this sample")
    }
}

#[component]
pub fn IntervalValues(estimate: f64, lower: f64, upper: f64) -> Element {
    let (class, label) = interval_state(lower, upper);
    rsx! {
        span { class: "audit-ci-value return-value {class}", "{return_label(estimate, false)}" }
        span { ReturnValue { value: lower }, " to ", ReturnValue { value: upper } }
        small { class: "return-status {class}", "{label}" }
    }
}

#[component]
pub fn PerformanceLegend() -> Element {
    rsx! {
        div { class: "performance-legend", aria_label: "Performance color key",
            span { class: "return-gain", "+ Gain / above benchmark" }
            span { class: "return-loss", "− Loss / below benchmark" }
            span { class: "return-neutral", "0 No change · — unavailable" }
            span { class: "return-uncertain", "± Uncertain interval" }
            small { "Returns use signs as well as color. Chart colors identify strategies." }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn gains_losses_and_displayed_zero_have_consistent_signs() {
        assert_eq!(return_class(0.1234), "return-gain");
        assert_eq!(return_label(0.1234, false), "+12.34%");
        assert_eq!(return_class(-0.4567), "return-loss");
        assert_eq!(return_label(-0.4567, false), "-45.67%");
        for value in [0.0, -0.0, 0.000001, -0.000001] {
            assert_eq!(return_class(value), "return-neutral");
            assert_eq!(return_label(value, false), "0.00%");
        }
        assert_eq!(return_label(-0.01, true), "-1.00 pp");
        assert_eq!(return_label(0.01, true), "+1.00 pp");
    }

    #[test]
    fn missing_or_invalid_values_are_not_gains_or_zero_filled() {
        for value in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            assert_eq!(return_class(value), "return-neutral");
            assert_eq!(return_label(value, false), "—");
        }
    }

    #[test]
    fn intervals_use_bounds_not_the_point_estimate() {
        assert_eq!(interval_state(-0.1, 0.2).0, "return-uncertain");
        assert_eq!(interval_state(0.0, 0.2).0, "return-uncertain");
        assert_eq!(interval_state(-0.1, 0.0).0, "return-uncertain");
        assert_eq!(interval_state(0.01, 0.2).0, "return-gain");
        assert_eq!(interval_state(-0.2, -0.01).0, "return-loss");
        assert_eq!(interval_state(f64::NAN, 0.2).0, "return-neutral");
        assert_eq!(interval_state(0.2, 0.1).0, "return-neutral");
    }
}
