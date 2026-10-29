# WORKER 02 R4 Baseline

baseline_sha: 527f07593fc346f0448165e1f64dd6954eb798b4
base_sha: 75076eac443d935d622bf59e12aad20ce5aba85e
merge_base: 75076eac443d935d622bf59e12aad20ce5aba85e
branch: codex/biz-worker-02 (existing remote branch)
pr: https://github.com/sssssssssh/ssh_stock/pull/1 (Open / Draft)
pr_checkout_sha: 95b47d7b3be891be08e342c4e2894c29d5952bf7
pr_head_and_checkout_tree: 38645ed0802f788bde5363c146b9b607af47f6ea

## W00 State Protection

The initial worktree was master with two untracked R3 read-only reports. Both
remain untouched and are not part of this R4 commit. R4 explicitly authorizes
working on the existing codex/biz-worker-02 branch; no new remote branch,
master edit, merge, deletion or deployment is performed. Fetch confirms the
specified remote SHAs are unchanged. No production .env/database/Writer/TuShare
or physical G1 is used for this task; tests must use a marked isolated PG17.

## Native Baseline

- [Publication V1.3 / pull_request / 527f075](https://github.com/sssssssssh/ssh_stock/actions/runs/40740676293): success, attempt 1
- [A4-1 read baseline diagnosis / pull_request / 527f075](https://github.com/sssssssssh/ssh_stock/actions/runs/40740676306): failure, attempt 1
- [A4-2 isolated read experiments / pull_request / 527f075](https://github.com/sssssssssh/ssh_stock/actions/runs/40740676287): failure, attempt 1
- [CI / pull_request / 527f075](https://github.com/sssssssssh/ssh_stock/actions/runs/40740676266): failure, attempt 1
- [CI / push / 527f075](https://github.com/sssssssssh/ssh_stock/actions/runs/40740668279): failure, attempt 1
- [CI / push / 75076ea](https://github.com/sssssssssh/ssh_stock/actions/runs/40654653164): failure, attempt 1
- [A4-2 isolated read experiments / push / 75076ea](https://github.com/sssssssssh/ssh_stock/actions/runs/40654653213): failure, attempt 1
- [Publication V1.3 / push / 75076ea](https://github.com/sssssssssh/ssh_stock/actions/runs/40654653255): success, attempt 1
- [A4-1 read baseline diagnosis / push / 75076ea](https://github.com/sssssssssh/ssh_stock/actions/runs/40654653235): failure, attempt 1

PR source HEAD and its synthetic merge checkout are recorded separately, even
though their Git trees match. Push CI has exact source HEAD 527f075. Master has
the same named contract failures; they are not new R4 business regressions.
The native full pytest step never ran after targeted failure; missing counts
are UNKNOWN, not zero failures. Linux/platform/toolchain issues from other SHAs
are historical leads, not failures newly reproduced by these native runs.

See failure_matrix.csv and baseline_evidence.json for job/step/node, raw URLs,
artifact digests and redaction limits. Raw logs/ZIP remain ignored under
.codex_tmp/worker02-r3/baseline, recoverable using the recorded API URLs.

## W01 Stop Line

The original 11 manifests are unchanged. Reviewer/signature/approval ID are
absent, activation_allowed=false, dispatcher_implemented=false. The old guard
expects 33 changed paths but the baseline PR checkout contains 78 (45 extra,
none missing). A new inventory is review material only. No migration activates
without independent approval; CONTRACT_MIGRATION_BLOCKED and merge NO remain.
