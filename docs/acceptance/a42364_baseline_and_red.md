# A42364 Baseline and RED

Client date: 2026-10-27 (Asia/Shanghai).
Baseline/master/origin/master verified clean and equal:
`60eeb0f123d61c082a6bb9bab53cd0f45b45202f`. Pull used fast-forward only; no branch switch or reset.
Taskbook: G1 Engineering Closeout v2, A4-2.3.6.4.
Baseline CI4725 is taskbook-reported until independently downloaded; never new-SHA proof.

## Authorization

Source, static checks and controlled offline L0/L1 only. No business .env/DSN, real
G1/PG17/Podman/cgroup/host installation/cloud resources or performance dispatch.
D1/D2/D3 are unsigned proposals, not runtime approval; old8 SQL/12commands/2s intact.
All consumption history and seven historical overlays remain immutable.

## Reviewed Contract Exception

User explicitly approved adapting only AT57/AT59 in
tests/unit/test_a42363_review_guard.py: exact new infra overlay rather than an
impossible blanket no-infra-change assertion, with the self-test exception pinned.
New AST test must prove every other function and all other old tests unchanged.
No original assertion is deleted to hide a regression.

## Frozen Stage Paths (66)

Exact files, not directory exemptions:

```text
PROJECT_RULES.md
README.md
docs/acceptance/a42364_ADR_BOOTSTRAP_AND_BUDGET.md
docs/acceptance/a42364_ADR_SAFE_VOLUME_DISPOSAL.md
docs/acceptance/a42364_ADR_TARGET_SESSION_GUC.md
docs/acceptance/a42364_L2_NOT_RUN.md
docs/acceptance/a42364_architecture.md
docs/acceptance/a42364_baseline_and_red.md
docs/acceptance/a42364_capability_matrix.md
docs/acceptance/a42364_closeout.md
docs/acceptance/a42364_cost_ledger.md
docs/acceptance/a42364_overlay_manifest.json
docs/acceptance/a42364_runbook.md
docs/acceptance/a42364_test_matrix.md
docs/股票机会发现系统_PRD_V1.0.md
docs/股票机会发现系统_系统设计_V1.0.md
infra/g1_manager/README.md
infra/g1_manager/install_manifest.schema.json
infra/g1_manager/read_only_auditor.service
infra/g1_manager/root_manager.service
infra/g1_manager/worker.service
infra/g1_pg17_image/Containerfile
infra/g1_pg17_image/README.md
infra/g1_pg17_image/bootstrap.c
infra/g1_pg17_image/bootstrap.sh
infra/g1_pg17_image/build_offline.sh
infra/g1_pg17_image/healthcheck.sh
infra/g1_pg17_image/pg_hba.template
infra/g1_pg17_image/supply_chain_manifest.schema.json
infra/g1_pg17_image/verify_supply_chain.sh
scripts/a4235_capability_guard.py
scripts/a42363_absence.py
scripts/a42363_complete_guard.py
scripts/a42363_harness.py
scripts/a42363_installation.py
scripts/a42363_owner.py
scripts/a42363_proposals.py
scripts/a42363_resources.py
scripts/a42363_review.py
scripts/a42363_review_guard.py
scripts/a42363_services.py
scripts/a42363_supervisor.py
scripts/a42364_bootstrap_builder.py
scripts/a42364_collector.py
scripts/a42364_costs.py
scripts/a42364_entry.py
scripts/a42364_evidence_gate.py
scripts/a42364_installation_verify.py
scripts/a42364_manager.py
scripts/a42364_owner.py
scripts/a42364_protocol_decision.py
scripts/a42364_session.py
scripts/a42364_source_guard.py
scripts/a42364_volume_exclusion.py
tests/integration_offline/test_a42364_chain.py
tests/integration_offline/test_a42364_process.py
tests/unit/test_a42363_review_guard.py
tests/unit/test_a42364_bootstrap.py
tests/unit/test_a42364_evidence.py
tests/unit/test_a42364_installation.py
tests/unit/test_a42364_owner.py
tests/unit/test_a42364_protocol.py
tests/unit/test_a42364_red.py
tests/unit/test_a42364_session.py
tests/unit/test_a42364_source_guard.py
tests/unit/test_a42364_volume.py
```

## RED Evidence

Five positive engineering regressions in test_a42364_red.py are run before source:
missing real bootstrap/auth source, explicit budget protocol, name-only Volume
exclusion contract, install package and four-slot candidate execution specification.
Actual command/results/node IDs recorded after execution, not inferred from names.
Existing successful denial tests are not counted as RED.

Actual baseline execution: python -m pytest tests/unit/test_a42364_red.py -q
--junitxml=.codex_tmp/a42364-red.xml; exit1,5 failed,0 skipped,2.23s.
Each failed with ModuleNotFoundError for the not-yet-implemented engineering adapter:

- test_RED_AT05_image_entrypoint_and_authentication_source_exist
- test_RED_AT13_candidate_has_explicit_costs_without_changing_active_budget
- test_RED_AT21_volume_target_is_name_only_under_separate_exclusion_contract
- test_RED_AT33_trusted_install_package_has_separate_principals
- test_RED_AT17_candidate_four_slots_have_real_execution_specification
