import gzip
import hashlib
import json

from scripts.business_recalc_matrix import summarize


def test_missing_or_failed_samples_never_become_financial_success(tmp_path):
    samples = []
    for optimized in (False, True):
        sample = tmp_path / f"{optimized}.json"
        sample.write_text(json.dumps(dict(optimized=optimized, months=1, stocks=4,
                                          runs=[], failure_class="synthetic-failure")))
        samples.append(sample)
    summarize(samples, tmp_path / "receipts")
    golden = json.loads((tmp_path / "receipts/financial_golden.json").read_text())
    assert golden["status"] == "PERFORMANCE_OPEN"
    assert golden["pairs"] == [dict(months=1, dataset_equal=False, tables_equal=False,
                                    identity_equal=False)]


def test_report_retains_slow_runs_and_cannot_grant_cloud_authorization(tmp_path):
    samples = []
    for optimized, durations in ((False, [100, 999, 100]), (True, [30, 90, 30])):
        for repeat, duration in enumerate(durations):
            sample = tmp_path / f"{optimized}-{repeat}.json"
            sample.write_text(json.dumps(dict(optimized=optimized, months=1,
                stocks=4, dataset_sha256="same", tables={"factors": "same"},
                runs=[dict(overall=duration)], financial_identity={"factor": "same"})))
            samples.append(sample)
    summarize(samples, tmp_path / "receipts")
    result = json.loads((tmp_path / "receipts/after.json").read_text())
    baseline = json.loads((tmp_path / "receipts/baseline.json").read_text())
    assert baseline["samples"][1]["runs"][0]["overall"] == 999
    assert result["comparisons"][0]["after_runs"] == 3
    assert result["comparisons"][0]["improvement"] == 0.7
    assert result["status"] == "PERFORMANCE_OPEN"
    assert result["cloud_status"] == "REAL_CLOUD_RECALC_NOT_AUTHORIZED"
    receipt = baseline["samples"][0]["raw_artifact"]
    packed = (tmp_path / "receipts" / receipt["path"]).read_bytes()
    assert hashlib.sha256(packed).hexdigest() == receipt["sha256"]
    assert hashlib.sha256(gzip.decompress(packed)).hexdigest() == receipt["uncompressed_sha256"]


def test_cloud_diagnostic_plan_never_connects(capsys):
    from scripts.business_cloud_diagnostic_plan import main

    main()
    plan = json.loads(capsys.readouterr().out)
    assert plan["connects"] is False
    assert plan["status"] == "REAL_CLOUD_RECALC_NOT_AUTHORIZED"
    assert plan["proposed_queries"][0] == "BEGIN READ ONLY"
    assert plan["proposed_queries"][-1] == "ROLLBACK"
