"""P0 immutable historical evidence; no application imports or measurements."""

import json
from pathlib import Path

from scripts.publication_lookup_tail_review_a423 import C0_SOURCE, SOURCE_DIGEST


def test_historical_replay_preserves_prior_evidence_without_promoting_it():
    current = json.loads(Path("docs/acceptance/evidence/a4231_historical_replay.json").read_text())
    previous = json.loads(Path("docs/acceptance/evidence/v14_a423_tail_baseline.json").read_text())
    assert current["original_review"] == previous
    assert current["source_zip_sha256"] == SOURCE_DIGEST
    assert current["evidence_kind"] == "HISTORICAL_NOT_ACCEPTANCE"
    assert current["capacity_ready"] is False and current["production_read_authorized"] is False
    assert current["p2"] == current["p3"] == "NOT_AUTHORIZED"


def test_all_seven_c1_anomalies_have_same_repeat_and_real_order_c0_neighbours():
    data = json.loads(Path("docs/acceptance/evidence/a4231_historical_replay.json").read_text())
    rows = data["analyzed_c1_anomalies_with_c0_neighbours"]
    assert [row["c1"]["repeat"] for row in rows] == [5, 13, 19, 25, 41, 66, 81]
    original = data["original_review"]["control_timelines"]
    for row in rows:
        c1, c0 = row["c1"], row["c0_same_repeat"]
        assert c1["variant"] == "C1" and c0["variant"] == "C0"
        assert c1["repeat"] == c0["repeat"]
        assert row["c0_previous"]["source_sample_index"] < c1["source_sample_index"]
        assert row["c0_following"]["source_sample_index"] > c1["source_sample_index"]
        for item in row.values():
            prior = next(s for s in original if s["statistics"] == "analyzed"
                         and s["variant"] == item["variant"] and s["repeat"] == item["repeat"])
            assert {k:item[k] for k in prior} == prior


def test_protocol_does_not_change_production_or_authorize_formal_capacity():
    import hashlib

    from scripts.business_source_contract import historical_bytes

    source = historical_bytes("backend/app/services/data_publication.py")
    assert hashlib.sha256(source).hexdigest() == C0_SOURCE
    text = Path("docs/acceptance/v14_a4_2_3_1_attribution_protocol.md").read_text()
    assert "128次总计" in text and "只干预一个因素" in text
    assert "P2/P3 NOT_AUTHORIZED" in text

    from scripts.business_source_contract import verify as verify_current_business

    assert len(verify_current_business()) == 64
