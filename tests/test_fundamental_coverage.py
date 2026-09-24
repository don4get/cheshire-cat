from datetime import date

from cheshire_cat.fundamental_coverage import (
    audit_fundamental_coverage,
    build_pilot_manifest,
    recommend_coverage_windows,
)


def test_pilot_manifest_quarantines_unknown_or_untraceable_records():
    manifest = build_pilot_manifest(
        ["acme"],
        ["2024-12-31"],
        ["SEC-XBRL"],
        publication_policy="filing date-only",
        source_evidence=[
            {
                "issuer": "ACME",
                "period": "2024-12-31",
                "source": "SEC-XBRL",
                "source_document_id": "acc-1",
                "source_url": "https://example.test/acc-1",
                "checksum": "sha256:abc",
                "publication_status": "date_only",
            },
            {
                "issuer": "ACME",
                "period": "2024-12-31",
                "source": "SEC-XBRL",
                "publication_status": "unknown",
            },
        ],
        reconciliation=[{"issuer": "ACME", "period": "2024-12-31", "status": "passed"}],
    )
    assert manifest["version"] == "fundamental-pilot-v1"
    assert manifest["admitted_records"] == 1
    assert manifest["unknown_or_quarantined_records"] == 1
    assert manifest["source_evidence"][1]["quarantine_reason"] == "publication_timing_unknown"
    assert manifest["go_no_go"]["ready_for_scale"] is False


def test_coverage_keeps_denominator_and_exclusion_reasons_visible():
    facts = [
        {
            "symbol": "USABLE",
            "concept": "Revenue",
            "period_end": date(2024, 12, 31),
            "available_on": date(2025, 2, 1),
            "availability_status": "date_only",
            "value": 10,
            "form": "10-K",
            "source_version": "a",
        },
        {
            "symbol": "UNKNOWN",
            "concept": "Revenue",
            "period_end": date(2024, 12, 31),
            "available_on": None,
            "availability_status": "unknown",
            "value": 10,
            "form": "YAHOO-12M",
            "source_version": "b",
        },
    ]
    report = audit_fundamental_coverage(
        facts,
        [date(2025, 3, 1)],
        universe=[{"symbol": "USABLE", "market": "US"}, {"symbol": "UNKNOWN", "market": "US"}],
        required_concepts=["Revenue"],
        reports=[{"symbol": "USABLE", "form": "10-K", "filing_date": date(2025, 2, 1), "source_url": "fixture"}],
    )
    snapshot = report["snapshots"][0]
    assert snapshot["universe_symbols"] == 2
    assert snapshot["symbols_ready_for_required_concepts"] == 1
    assert snapshot["coverage_rate"] == 0.5
    assert snapshot["exclusion_reasons"]["unknown_publication_date"] == 1
    assert {row["symbol"] for row in report["observed_fact_inventory"]} == {"USABLE", "UNKNOWN"}
    assert report["report_inventory"][0]["form"] == "10-K"


def test_coverage_windows_split_when_a_decision_date_is_missing():
    snapshots = [
        {"market": "US", "decision_date": day, "coverage_rate": 1.0}
        for day in ("2025-01-01", "2025-01-08", "2025-04-01")
    ]
    windows = recommend_coverage_windows(snapshots, max_gap_days=31)
    assert [window["decision_dates_exact"] for window in windows] == [
        ["2025-01-01", "2025-01-08"],
        ["2025-04-01"],
    ]


def test_coverage_reports_ingestion_state_categories():
    report = audit_fundamental_coverage(
        [],
        [date(2025, 1, 1)],
        universe=[{"symbol": "DONE", "market": "US"}, {"symbol": "FAILED", "market": "US"}],
        ingestion_states=[
            {"symbol": "DONE", "source": "SEC-XBRL", "status": "complete"},
            {"symbol": "FAILED", "source": "SEC-XBRL", "status": "failed", "last_error": "timeout"},
        ],
    )
    progress = report["snapshots"][0]["ingestion_progress"]
    assert progress["complete"] == 1
    assert progress["failed"] == 1
