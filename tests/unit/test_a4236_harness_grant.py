"""A4236 fixed refusal contracts: run RED first, keep these assertions for GREEN."""

import pytest

from scripts.a4236_g1_harness_contract import Fault
from scripts.a4236_mock import refusal_case


@pytest.mark.parametrize('threat', ['forged_grant', 'replay', 'pid_drift', 'cache_key',
    'false_join', 'false_cleanup', 'sql_budget', 'history_write'])
def test_a4236_RED_AT07_AT08_AT21_AT25_AT30_AT15_AT17_AT03(threat):
    # Returning NOT_AUTHORIZED is not sufficient for contradictory input: fixed Fault.
    with pytest.raises(Fault, match='^A4236_'):
        refusal_case(threat)
