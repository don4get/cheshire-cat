from cheshire_cat.fundamental_research_jobs import create_run, get_run, save_result


def test_fundamental_research_manifest_and_result_are_persisted(tmp_path):
    url = f"sqlite:///{tmp_path / 'fundamental-runs.sqlite'}"
    run_id = create_run(url, "fixture", {"feature_version": "fundamentals-asof-v1"})
    saved = save_result(url, run_id, {"version": "matched-fundamental-research-v1", "conclusion": {}})
    loaded = get_run(url, run_id)
    assert saved["status"] == "complete"
    assert loaded["manifest"]["feature_version"] == "fundamentals-asof-v1"
    assert loaded["result"]["version"] == "matched-fundamental-research-v1"
