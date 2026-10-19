from copy import deepcopy

import pytest

from scripts.publication_v13_receipt import compare


def measurement():
    return dict(
        head_sha="synthetic-sha",
        working_tree_dirty=False,
        measurement_version="v13-2-excludes-input-build",
        environment=dict(
            platform="synthetic",
            python="3.12",
            logical_cpus=2,
            processor="synthetic",
            packages={},
            disk_free_bytes=1000,
        ),
        results=[
            dict(
                rows=rows,
                repeat=repeat,
                synthetic=True,
                production_validation="UNPROVEN",
                reader_errors=[],
                candidate_digest=f"synthetic-{rows}",
                staged=rows,
                postgres="17",
                database_settings={},
                public_a=True,
                existing_candidates=0,
                prepare_seconds=10,
                sql_count=100,
                peak_process_rss_bytes=1000,
                wal_bytes=1000,
            )
            for rows in (1000, 100000, 500000)
            for repeat in range(3)
        ],
    )


def test_dynamic_free_disk_does_not_change_hardware_identity():
    old = measurement()
    new = deepcopy(old)
    new["environment"]["disk_free_bytes"] = 900
    for row in new["results"]:
        row["prepare_seconds"] = 1
        row["sql_count"] = 75
    result = compare(old, new, "synthetic-sha")
    assert all(row["time_target_met"] for row in result)
    assert not any(row["sql_target_met"] for row in result)


@pytest.mark.parametrize("damage", ["sha", "dirty", "digest", "reader", "repeat", "hardware"])
def test_receipt_rejects_invalid_evidence(damage):
    old = measurement()
    new = deepcopy(old)
    if damage == "sha":
        new["head_sha"] = "other"
    elif damage == "dirty":
        new["working_tree_dirty"] = True
    elif damage == "digest":
        new["results"][0]["candidate_digest"] = "other"
    elif damage == "reader":
        new["results"][0]["reader_errors"] = ["OperationalError"]
    elif damage == "repeat":
        new["results"].pop()
    else:
        new["environment"]["logical_cpus"] = 4
    with pytest.raises(AssertionError):
        compare(old, new, "synthetic-sha")
