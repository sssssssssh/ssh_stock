"""A42361 RED inventory: old default refusals are correct, real implementations absent."""

import pytest

from scripts.a42361_offline_cases import real_components


@pytest.mark.parametrize('position,required', [
    (0, 'verify_signature'), (1, 'consume_transaction'),
    (2, 'create_owned_fixture'), (3, 'terminate_owned'),
])
def test_RED_four_real_implementation_gaps_not_fake_positive(position, required):
    # No adapter is constructed or called; this is a code-gap inventory, not G1 proof.
    assert callable(getattr(real_components()[position], required, None))
