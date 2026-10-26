# A42362 W00 baseline and exact scope

Baseline / initial HEAD / origin/master: `b32b9271596d92cfbec571fd3170aacbe17370cd`; clean master, independently checked with ls-remote.

This stage authorizes source development and offline processes/IPC only. No G1, PG, Podman,
cloud, business .env, database migration or runtime installation is authorized.
G2 effective warmups=8; G3 not authorized. All production/performance/capacity claims remain false.

## Exact Planned Paths

No prefix exemption. The final overlay must equal these paths; scope adjustments require explicit review.

- `PROJECT_RULES.md`
- `README.md`
- `docs/acceptance/a42362_architecture.md`
- `docs/acceptance/a42362_baseline.md`
- `docs/acceptance/a42362_capability_matrix.md`
- `docs/acceptance/a42362_closeout.md`
- `docs/acceptance/a42362_g1_deployment_request_TEMPLATE.md`
- `docs/acceptance/a42362_method_decisions.md`
- `docs/acceptance/a42362_overlay_manifest.json`
- `docs/acceptance/a42362_recovery_and_faults.md`
- `docs/acceptance/a42362_schema_and_budget.md`
- `docs/acceptance/a42362_test_traceability.md`
- `docs/股票机会发现系统_PRD_V1.0.md`
- `docs/股票机会发现系统_系统设计_V1.0.md`
- `infra/g1_control_plane/002_services.sql`
- `infra/g1_harness/a42362-deployment.md`
- `infra/g1_harness/a42362-installation.example.json`
- `infra/g1_harness/a42362-service@.service`
- `infra/g1_harness/a42362-socket@.socket`
- `infra/g1_harness/owner_bootstrap.sql`
- `infra/g1_harness/owner_role_audit.sql`
- `scripts/a4235_capability_guard.py`
- `scripts/a42361_control_service.py`
- `scripts/a42361_deployment.py`
- `scripts/a42361_fixture_controller.py`
- `scripts/a42361_live_probe_worker.py`
- `scripts/a42361_one_shot_store.py`
- `scripts/a42361_source_guard.py`
- `scripts/a42361_watchdog.py`
- `scripts/a42362_absence_auditor.py`
- `scripts/a42362_approval_registry_service.py`
- `scripts/a42362_contract.py`
- `scripts/a42362_ledger.py`
- `scripts/a42362_pg_owner_service.py`
- `scripts/a42362_reconcile.py`
- `scripts/a42362_service_host.py`
- `scripts/a42362_source_guard.py`
- `scripts/a42362_supervisor_service.py`
- `tests/integration_offline/test_a42362_ipc_process.py`
- `tests/unit/test_a42361_controller_watchdog.py`
- `tests/unit/test_a42361_source_entrypoints.py`
- `tests/unit/test_a42361_worker_evidence.py`
- `tests/unit/test_a42362_approval_ledger.py`
- `tests/unit/test_a42362_audit_supervisor.py`
- `tests/unit/test_a42362_contract.py`
- `tests/unit/test_a42362_owner_recovery.py`
- `tests/unit/test_a42362_source_guard.py`
- `tests/unit/test_a4236_source_guard.py`

## Existing Blob Inventory

The following actual b32b927 tree records were read before any edits; names quoted by Git use its byte escaping.

```text
100644 blob 02f10481f6897f418a2eb7926a42509c41758ebc	PROJECT_RULES.md
100644 blob 29e24bbdbaf8bfa55301de6f1a26c92a64ffa3e1	README.md
100644 blob b14ba0146dcd29144e66e63e468501e057eec0ed	"docs/\350\202\241\347\245\250\346\234\272\344\274\232\345\217\221\347\216\260\347\263\273\347\273\237_PRD_V1.0.md"
100644 blob 5d48b4e702397eccb8fcfb2195154b7f4b4035d5	"docs/\350\202\241\347\245\250\346\234\272\344\274\232\345\217\221\347\216\260\347\263\273\347\273\237_\347\263\273\347\273\237\350\256\276\350\256\241_V1.0.md"
100644 blob ef5877804bb4f2da7473649b48e4d367da96307b	scripts/a4235_capability_guard.py
100644 blob 605ff14b64d1101900e62dc8640ed4564dce49d5	scripts/a42361_control_service.py
100644 blob 9e766b1f8b077c28ebbbadfd9163e7acdda06a18	scripts/a42361_deployment.py
100644 blob 7a40e645fe068a6d5535878c39faec907991538d	scripts/a42361_fixture_controller.py
100644 blob 5d34eeb81008a6d757cb6d941b478e1ed410a82f	scripts/a42361_live_probe_worker.py
100644 blob 7770147cb920942d2495264d13ff009302355089	scripts/a42361_one_shot_store.py
100644 blob c64209628ed88b386960b8e4f7d419172b83cdd8	scripts/a42361_source_guard.py
100644 blob 789fa828af3ffd8f645193c03c973f80ef2dcd30	scripts/a42361_watchdog.py
100644 blob 11bb0637e2cf5de09b8b4baf150d06aeb46219bb	tests/unit/test_a42361_controller_watchdog.py
100644 blob 62718caf39c72fe575f319d54e31995b5222d60a	tests/unit/test_a42361_source_entrypoints.py
100644 blob eb5b20a1cfbc0245b29f57ace289872525654205	tests/unit/test_a42361_worker_evidence.py
100644 blob bd28bcbc7614cab6887a401649aa0bb435a1e4d3	tests/unit/test_a4236_source_guard.py
```

## Initial Gaps and RED

- ControlService has no durable reconciliation call when create ACK is lost.
- Watchdog returns terminated/reaped immediately after the direct child exits, without proving scope empty.
- Probe session validation has no explicit target-session GUC provenance/method decision.
- A/Owner/E/server host/outer artifact supervision and per-resource durable ledger remain incomplete.

First RED tests inspect these actual baseline functions without importing Linux-only fcntl/resource,
starting a process, connecting a database or minting approval. Their results are recorded after execution.
Windows cannot provide SO_PEERCRED/cgroup evidence. New L1 Linux results must be collected separately
on the final commit's existing ordinary CI; no skip/xfail is a substitute for them.

Actual baseline portable regression: `test_a4236_probe_prepared.py` 59 passed (5.23s), exit0.
Actual RED: `test_a42362_contract.py` 3 failed (2.91s), exit1, reproducing the three gaps above.
Raw JUnit is kept in the local ignored diagnostic directory; these are source tests, not physical proof.

