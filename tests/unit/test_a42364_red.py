"""W00 positive engineering gaps, executed RED before any implementation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_RED_AT05_image_entrypoint_and_authentication_source_exist():
    from scripts.a42364_bootstrap_builder import validate_image_source

    result = validate_image_source(ROOT)
    assert result["bootstrap_image"] == "SOURCE_IMPLEMENTED_UNDEPLOYED"
    assert result["physical"] == "NOT_RUN_NOT_AUTHORIZED"


def test_RED_AT13_candidate_has_explicit_costs_without_changing_active_budget():
    from scripts.a42364_costs import protocol_versions

    values = protocol_versions()
    assert values["active"] == dict(sql=8, commands=12, window_ms=2000)
    assert values["candidate"] == dict(sql=12, commands=32, window_ms=30000)
    assert values["approved"] is False


def test_RED_AT21_volume_target_is_name_only_under_separate_exclusion_contract():
    from scripts.a42364_volume_exclusion import volume_delete_plan

    result = volume_delete_plan("a42361-" + "a" * 32 + "-data")
    assert result["operation"] == ("volume", "rm", "a42361-" + "a" * 32 + "-data")
    assert result["requires"] == "EXCLUSIVE_ALL_WRITERS_CAPABILITY"


def test_RED_AT33_trusted_install_package_has_separate_principals():
    from scripts.a42364_installation_verify import installation_layout

    result = installation_layout()
    assert result["manager_uid"] == 0
    assert len(result["distinct_nonroot_principals"]) == 9
    assert result["auto_start_g1"] is False


def test_RED_AT17_candidate_four_slots_have_real_execution_specification():
    from scripts.a42364_session import candidate_schedule

    schedule = candidate_schedule()
    assert len(schedule) == 16
    assert [i for i, item in enumerate(schedule, 1) if item["kind"] == "PROJECTION"] == [
        6,
        8,
        14,
        16,
    ]
    assert all(item["budget_ms"] == 100 for item in schedule)
