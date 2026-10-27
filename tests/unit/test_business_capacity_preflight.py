"""Resource refusal cannot be mistaken for reduced-scale performance acceptance."""

import pytest

from scripts.business_capacity_preflight import decision


@pytest.mark.parametrize("resource", ["memory", "disk"])
def test_capacity_reservation_refuses_without_starting_or_accepting_jobs(resource):
    value = decision(100 if resource == "memory" else 8 * 1024**3,
                     100 if resource == "disk" else 9 * 1024**3,
                     3 * 1024**3, 128 * 1024**2, 8 * 1024**2, 100, 64 * 1024**2)
    assert value["status"] == "RESOURCE_DEFERRED"
    assert value["jobs_started"] == 0
    assert value["capacity_accepted"] is False
    assert value["performance_status"] == "PERFORMANCE_OPEN"


@pytest.mark.parametrize("bad", [True, -1, None])
def test_untrusted_memory_observation_cannot_grant_resource_readiness(bad):
    with pytest.raises(ValueError, match="BUSINESS_RESOURCE_OBSERVATION_INVALID"):
        decision(bad, 9 * 1024**3, 3 * 1024**3, 128, 8, 100, 64)


def test_even_sufficient_resource_floor_never_accepts_capacity_or_performance():
    value = decision(8 * 1024**3, 9 * 1024**3, 3 * 1024**3, 128, 8, 100, 64)
    assert value["status"] == "RESOURCE_FLOOR_OBSERVED"
    assert value["capacity_accepted"] is False
    assert value["performance_status"] == "PERFORMANCE_OPEN"
