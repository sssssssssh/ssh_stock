"""TEST_ONLY inventory for the original missing real adapters. No deployment adapter."""


def real_components():
    from scripts.a4236_g1_harness_contract import TrustedHarness
    from scripts.a4236_g1_probe import run_live
    from scripts.a4236_grant_verifier import IndependentVerifier, PersistentConsumer

    return (IndependentVerifier, PersistentConsumer, TrustedHarness, run_live)
