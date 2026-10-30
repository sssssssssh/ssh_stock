# WORKER-02 revision baseline (2026-10-28)

PR #1 / codex/biz-worker-02 starts clean at
4d183857cdf42e4f9e75bd2a78c792f0ef3847e3; master baseline is
75076eac443d935d622bf59e12aad20ce5aba85e. No merge/deployment approval.

The [per-node inventory](WORKER_02_revision_failures.json) preserves all 53 failures
and 137 setup errors, original trace hashes and unmodified XML/log/archive hashes.
173 outcomes involve FROZEN_FILE_CHANGED; the historical test-blob contract is
separate. Other categories are Linux kernel capability, external tools, Unix
socket path length and the owned process hang. Classification of an observed
exception is not proof that it reproduces on supported Linux. No business
regression is silently reclassified as a contract issue; unknowns stay unverified.

Original PR workflow results at review HEAD:

| Workflow | Run | Result |
|---|---|---|
| CI | https://github.com/sssssssssh/ssh_stock/actions/runs/40696842813 | failed; full suite not reached |
| A4-1 | https://github.com/sssssssssh/ssh_stock/actions/runs/40696842716 | 48 passed, 1 failed |
| A4-2 | https://github.com/sssssssssh/ssh_stock/actions/runs/40696842975 | source CLI failed; no experiment |
| Publication | https://github.com/sssssssssh/ssh_stock/actions/runs/40696842932 | 85 passed |

PR checkout was merge SHA e748f581da4a1693fa39b9698dae7627116268d3, not branch HEAD.
The push CI at https://github.com/sssssssssh/ssh_stock/actions/runs/40696736914
used actual 4d183857 and also failed before full suite. No same-SHA all-green claim.

Independent contract signer/approval ID are still missing. Existing ADR and
PROPOSED_ONLY source list remain inactive: CONTRACT_MIGRATION_BLOCKED. No old
guard/test/manifest/workflow is changed. Signature, explicit source scope, exact
base, negative tests and rollback approval must precede any contract dispatch.

Supported Linux local runtime is unavailable (Docker daemon not running); no
daemon/G1 installation is attempted. Linux full pytest remains NOT_VERIFIED if
native CI stops at the unchanged contract gate. Large-scale capacity remains
RESOURCE_DEFERRED/PERFORMANCE_OPEN until an authorized resource precheck passes.

Revision scope: heartbeat health and failed-commit evidence; independent recovery
proof proposal and approval expiry checks; real Worker diagnostic lifecycle/CAS
snapshot persistence; observed PG backend identities. No finance SQL/algorithm,
schema, original timeout, queue fencing or automatic stale recovery changes.
