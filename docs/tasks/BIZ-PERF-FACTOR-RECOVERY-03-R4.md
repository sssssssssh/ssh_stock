# BIZ-PERF-FACTOR-RECOVERY-03-R4 — break frozen T26 mixed-test deadlock, fix actual Worker

Date 2026-11-16. Center goal: normal factor calculation, Worker reliability, candidate write performance. R3 closed PHASE_A_FROZEN_CHAIN_BLOCKED. This task explicitly authorizes the minimal expansion to tests/unit/test_r1_reviewed_snapshot_v2.py, which R3 could not edit. Do not spend another round on generic audit.

Baseline HEAD=origin/master=232baf9e13cd7b23731e59188c86e0e253c3a394. Read AGENTS, governance, R1-R3 closeouts and source. Inspect git status and preserve all preexisting untracked files, including test_source_contract_r1_history.py. Do not concurrently run another Codex writer.

## Decision: preserve every historical assertion, but separate historical byte verification from current behavior verification
T26 is a MIXED test: its FROZEN map asserts historical byte identity of eight files (including scripts/r1_integration_seed_loader.py), while the same test asserts CURRENT oracle approval/reviewer/authorship and fixture hashes. Do NOT simply replace FROZEN hashes, delete an assertion, use an OR for new bytes, or route the entire T26 to a historical checkout.

Explicitly permitted: minimally refactor tests/unit/test_r1_reviewed_snapshot_v2.py so that:
- The old eight FROZEN entries and exact hashes remain literally unchanged.
- A separate test checks these original frozen files as bytes from an exact pinned historical Git commit/tree, verifying the Git object identity and no network/checkout/mutation. Fail closed if object missing or unexpected, and verify source path and sha. This is explicitly HISTORICAL_ONLY, never current execution authority. Historical original test code/fixtures should remain preserved. Keep original T26 test name if feasible but split frozen and current assertions into separate tests with clearly distinguishable names.
- The CURRENT oracle approval/reviewer/authorship/fixture checks remain in a CURRENT test, always executed on current worktree and never routed to historical commit.
- Add explicit CURRENT source-version integrity tests for changed seed/controller and Worker: v2 manifest checks exact current file bytes, unknown version/tamper/symlink reject. Historical test success never implies current Worker safety.
- If this refactor changes the test file's own upstream hash pin, identify the exact next reference and stop rather than recursively altering frozen audit chain without authorization.

## Business source versioning
Keep old r1_business_compare_schema_v1.json and v1 verify_business_sources() behavior exactly unchanged. Add explicit v2 current source manifest and version dispatch, no implicit fallback, no optional hash bypass, no dynamic hashes from current git HEAD alone. Ensure current controller and seed use explicit v2 and still run current behavior tests. Old v1 historical checks must remain executable on pinned old tree with strict isolated routing; pure historical AC31 only if required. Do not historical-route current controller or seed tests.

## Worker minimal patch
Once A is protected, fix backend/app/services/job_worker.py start failure cleanup: only join if heartbeat thread actually started; preserve normal join timeout and normal join exception propagation, fail-closed cleanup and job FAILED semantics, cancellation/ownership CAS, publication, no replay. Add real current-module pytest tests in tests/unit/test_job_worker.py (not AST simulation) with RED/GREEN start fail, no join, normal join, join error, cleanup, subsequent poll, cancellation, no publication.

## Whitelist
scripts/r1_integration_evidence.py
docs/acceptance/r1_current_business_sources_v2.json (new)
scripts/r1_integration_controller.py
scripts/r1_integration_seed_loader.py
scripts/source_contract_governance.py
scripts/source_contract_history.py
scripts/source_contract_pytest.py
tests/unit/test_source_contract_r1_history.py (existing untracked)
tests/unit/test_r1_integration_controller.py
tests/unit/test_r1_integration_seed_loader.py
tests/unit/test_r1_reviewed_snapshot_v2.py (new explicit authorization)
backend/app/services/job_worker.py
tests/unit/test_job_worker.py
docs/acceptance/BIZ_PERF_FACTOR_RECOVERY03_R4_CLOSEOUT.md (new).
Do not edit old manifests/schema/hash constants, original A42366, old security plugins, CI, dependencies, migration, production data, Raw/Derived, original test assertions other than moving exact checks into separate historical/current test. Never force push.

## Validation / gates
- First prove T26 historical byte check and current oracle/fixture check separately; add negative cases for tamper/missing commit/version/path, unchanged old v1 tests.
- Prove current controller/seed behavior remains tested, not merely historical.
- Worker current-module RED/GREEN and regressions; preserve all unchanged frozen blobs; git diff --check; ruff and pytest if available, ENV_BLOCKED if dependencies missing, no installing/upgrading.
- No real business PG17 connection, Worker service, SQL, migrations, cloud performance, Raw redownload. B_GATE=NOT_APPROVED and TARGETED_PG17_GATE=NOT_APPROVED.
- If a NEW frozen upstream link outside whitelist appears, STOP and report exact reference, not another generic framework.
- Do not commit or push; report precise changed files, exact diff, tests, old vs current semantic coverage, untested environment, and next ChatGPT review.
