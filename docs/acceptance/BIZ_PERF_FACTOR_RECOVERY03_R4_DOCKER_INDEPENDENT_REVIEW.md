# FACTOR-RECOVERY-03-R4 independent Docker review

Date: 2026-11-16. Repo: ssh_stock. Baseline HEAD / origin/master / GitHub master at review start:
232baf9e13cd7b23731e59188c86e0e253c3a394.

## Purpose and scope
Independent review of minimal Worker heartbeat Thread.start failure cleanup and R1 historical/current contract compatibility. Offline only. No real PostgreSQL, no real Worker service, no factor job, no SQL, no migration, no source data download, no benchmarks.

## Isolated environment
- Remote computer ssssssh, Docker container ssh-stock-factor-recovery-test.
- python:3.12.14-slim, CPython 3.12.14, requirements-biz-perf-linux-py312-v1.lock installed with --require-hashes --only-binary=:all:.
- Docker inspect: running, Networks={}, mounts /workspace RW=false and /workspace/.codex_tmp RW=true.
- Container environment: no DATABASE/PG credentials/configuration keys. Docker Compose services never started.
- Host Windows Python environment, existing local database/data, and project worktree dependencies unchanged.

## Independent test evidence
1. In initial read-only Windows worktree mount, seven newly added Worker tests all produced fixture errors because the test incorrectly monkeypatched nonexistent performance_diagnostics.get_settings. Codex removed only this bad monkeypatch and the unused import; the effective app.core.config.get_settings patch stayed. This was *not* defect RED.
2. Corrected current source in network-disconnected container: new Worker cases 7 passed / 23 deselected. JUnit /tmp/worker-new-fixed.xml.
3. Full tests/unit/test_job_worker.py: 30 passed. JUnit /tmp/worker-full.xml.
4. True defect RED: copied backend/tests/scripts/config/pyproject into a separate container /tmp/ssh-stock-factor-red, changed only the copy of job_worker.py to its former join condition, and executed the unchanged regression test. Failed 1/1 with RuntimeError: cannot join thread before it is started in heartbeat_thread.join(timeout=5). JUnit /tmp/worker-old-red.xml. No project worktree modification.
5. Contract check in read-only host mount: tests/unit/test_source_contract_r1_history.py + tests/unit/test_r1_reviewed_snapshot_v2.py, 59 passed and 185 subtests passed. JUnit /tmp/contracts-fixed.xml.
6. Broader Controller/SeedLoader/Protocol combination against Windows-mounted files initially had source-contract failures: Windows checked-out docs/acceptance/r1_business_compare_schema_v1.json is CRLF (raw SHA e023206e..., normalized LF SHA f6be0a5d...); pinned SCHEMA_SHA256 is the normalized LF hash. No old SHA was changed.
7. For Linux CI-representative verification, created a local no-network git clone under container /tmp/ssh-stock-linux-check with LF Git checkout, overlaid exact current modified tracked files and 2 required untracked source/test files, normalizing CRLF to LF in the **temporary copy only**. Controller + SeedLoader + Protocol + source contract + reviewed snapshot: 88 passed, 209 subtests passed. JUnit /tmp/source-combined-linux.xml.
8. Original source contract governance tests (test_source_contract_governance.py + test_business_source_contract.py) on same isolated Linux clone: 44 passed, JUnit /tmp/old-governance.xml.
9. Ruff for all backend tests migrations scripts in isolated Linux copy: All checks passed. git diff --check on host: exit 0.
10. HEAD remained baseline throughout independent review. Remote master verified with git ls-remote. No force push, reset, stash, clean or current worktree test source modifications.

## Review decision
- Worker heartbeat fix is small (heartbeat_started only set after Thread.start returns, join gated on success); no broad exception swallowing.
- Original Worker and companion offline source-contract semantics verified on current source and Linux-format duplicate; source-provenance protections not softened.
- Offline targeted RED-to-GREEN gate is PASS. Full GitHub CI and real PostgreSQL 17 factor calculation remain NOT_RUN/PENDING. Windows CRLF mount is unsuitable for raw-byte-pinned historical JSON tests; use Linux-format Git checkout rather than modifying pinned hashes.
- Independent code review: targeted testing PASS. Full production readiness NOT VERIFIED. Do not claim performance speedup, no Worker liveness proof against a real DB, no release approval for live PG17.

B_GATE=NOT_APPROVED
TARGETED_PG17_GATE=NOT_APPROVED
ROOT_ATTEMPTS=0
REAL_FACTOR_RUN=NOT_RUN
REAL_WORKER=NOT_RUN
REAL_PG17=NOT_RUN
NEXT=REVIEWED_COMMIT_THEN_GITHUB_CI
