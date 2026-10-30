# WORKER-02 R6 Bounded Review

**MERGE_BLOCKED; no merge or deployment permission.** Production-code blockers
closed: **0**. A diagnostic replay or this document is not a code fix.
No new diagnostic framework, source selector, approval signature or test is
added. The only delivery paths are this handoff and the bounded
[independent decision page](worker02_r6_approval_decision.md).

## W00 Baseline And First Failure

Fetch and fast-forward-only pull found the existing work branch up to date:
`codex/biz-worker-02`, input `fc8f4e4655aa780ae100dbb564164e6d1bf8d9a4`,
tree `68f1c0a3f7fcc35520059bc561fc99377b04ca42`. Master remains
`75076eac443d935d622bf59e12aad20ce5aba85e`. PR #1 is Open/Draft; its input
merge checkout `d8a47698dc669a457840d79baf9618a3ae642291` has the same tree.
The initial worktree was clean. No branch switch, merge, deployment or
business environment/database/Worker access was performed.

The R6 taskbook SHA256 is
`fe1a84820e23471e1cac67d01a64896635bb74aae28daf9ac45abfa51e70795a`.
Fresh GitHub job metadata and decoded raw logs reproduce the R5 outcomes;
the four first-failure job logs match the previously retrieved decoded content
exactly; this is not a comparison of raw HTTP archive bytes.

| Input PR run / first failing job and step | Actual outcome |
| --- | --- |
| [CI 40839036072](https://github.com/sssssssssh/ssh_stock/actions/runs/40839036072), job 123330673760 step 22 | Archive 142 passed / 1 failed; original observer frozen-source node. Native XML retains A42331_TEST_FAILURE redaction; it is not a raw traceback. Full pytest/coverage not entered. |
| Same CI, job 123330673944 step 6 | Lookup 106 passed / 1 failed; exact old frozen-source assertion. |
| [A4-1 40839036125](https://github.com/sssssssssh/ssh_stock/actions/runs/40839036125), job 123330674129 step 6 | 48 passed / 1 failed; original diagnostic frozen-source node. |
| [A4-2 40839035904](https://github.com/sssssssssh/ssh_stock/actions/runs/40839035904), job 123330673547 step 7 | Static source/formal-parent check refused; downstream safety/laboratory/release gate not run. |
| [Publication 40839036238](https://github.com/sssssssssh/ssh_stock/actions/runs/40839036238), job 123330674842 | 85 contracts passed; performance skipped, not qualified. |

One clean Linux replay of the four requested original nodes: **4 failed,
0 passed / errors / skipped; exit 1; 2.57s**. Full tracebacks are retained,
not reduced to error-code strings. The immutability node asserts that changed
tests remain within the historical path set. The other three call the
unchanged `a42366_source_guard.verify`, line 78:
`changed == set(data["stage_paths"])`; `require`, line 35, raises
`A4235_FROZEN_FILE_CHANGED`. Native A4-2 trace: experiment main:620 ->
business_source_contract:96,318 -> source_guard:78 -> require:35.
This is the same legal contract refusal as R5, not a newly proven bug.
Historical raw artifacts/hashes remain indexed in the existing R5 receipt;
no duplicate failure matrix was generated.

## Work Packages

| Package | Original failure -> cause -> change -> regression -> closed? |
| --- | --- |
| W01 | Exact 33-path contract -> required business identity/metadata changes plus later accepted Worker work -> all seven first-added paths and old-authority diffs reviewed; no safe accidental rollback proved -> original guards/tests/manifests unchanged by R6 -> NO; independent decision missing. |
| W02 | Two R4 full-context failures -> not causally explained -> two unchanged full-import original-prefix replays, existing opt-in R5 evidence -> both watched nodes PASS twice, no causal RED/GREEN -> UNCLASSIFIED_BLOCKER. |
| W03 | Linux safety/tool prerequisites -> actual Linux 3.10 pidfd ENOSYS -> tools installed only in disposable test container; no host/kernel/production change -> capability report remains PLATFORM_BLOCKED -> NO. |
| W04 | Protect accepted Worker/financial behavior -> no production/test/default/SQL/schema changes in R6 -> final-SHA Worker, ledger, tool and historical-guard results belong in the post-push PR receipt, not a subsequent document commit. |
| W05 | Native source gates/full/capacity/field -> independent approval/resources/authorization absent -> no weakening, rerun or fabricated qualification -> final post-push receipt only on PR #1 -> MERGE_BLOCKED. |

## Replay Evidence

The new owned PG17.6 instance has independent UUID marker and physical
system identifier verified before migrations/fixture writes. No business
dotenv was loaded. Test image, PostgreSQL image, resource limits, kernel,
tool versions, source SHA, collection order and raw XML/logs are retained
with the execution evidence. Isolation is not inferred from a loopback DSN.

Both five-node probes fully collected **5239** test nodes and imported the
full project's test modules
before executing the original first five: **5 passed each**, 46.68s / 46.53s.
The first probe overlapped test-tool downloading; it is preliminary evidence,
not a controlled timing qualification. No assertion or SQL budget changed.
The subsequent continuous 868-node schedules run serially after tool setup;
they retain every preceding node, including failures, rather than selecting
only the two disputed tests. Observer index 4 and statistics index 867 are
asserted against the unchanged full collection. These are diagnostic prefixes,
**not an unfiltered full-suite or coverage result**.

First 868-node replay: **768 passed / 5 failed / 95 setup errors / 0 skipped**,
exit 1, 3575.46s. Both watched original nodes passed. All 100 remaining
failures/errors are the unchanged A4235_FROZEN_FILE_CHANGED refusal; the
corresponding R4 prefix was 766 passed / 7 failed / 95 setup errors. This
comparison does not prove a code fix: no code was changed.

Second 868-node replay: **768 passed / 5 failed / 95 setup errors / 0 skipped**,
exit 1, 3310.46s. Both watched nodes passed again; all 100 failures/errors
again contain the unchanged frozen-contract refusal. No code/fixture was
changed to obtain these results. Both historical failures remain
**UNCLASSIFIED_BLOCKER**; no third global-diagnostics round is authorized.
The preceding unchanged regression schedule includes synthetic capacity and
retention tests; those are not the formal A4 1,443,097-row x3 experiment.

These replays test the pinned R6 input SHA above, not the later documentation
commit. Exact final SHA/tree/blob identities, fresh regression results and
native CI links will be recorded in a [PR #1 receipt](https://github.com/sssssssssh/ssh_stock/pull/1)
without another commit changing the tested identity.

## Acceptance Checklist

| Item | Result / remaining gate |
| --- | --- |
| AT01 | Baseline, original first errors and four native workflow types reviewed; minimal four-node replay remains RED. |
| AT02 | Seven-path causal review and bounded decision supplied; no safe rollback proved, independent approval absent: CONTRACT_MIGRATION_BLOCKED. |
| AT03 | Two full-import original 868-node prefixes executed; historical causes unproven: UNCLASSIFIED_BLOCKER. |
| AT04 | Disposable tools available, actual pidfd ENOSYS: PLATFORM_BLOCKED; no host modification or fabricated support. |
| AT05 | Existing Worker and three complete ledger pairs unchanged; final exact-SHA execution results required in PR receipt. |
| AT06 | Supported-Linux unfiltered pytest/coverage cannot run here; native CI evidence must not be substituted with prefix results. |
| AT07 | Capacity x3 not executed, field not retested, recovery not installed, PR remains Draft: MERGE_BLOCKED. |

## Stop And Handoff

Final-SHA unfiltered supported-Linux pytest/coverage is blocked, not passed;
the unchanged coverage threshold is 70%. The available VM's actual pidfd
call returns ENOSYS despite working Git/compiler/Node/shellcheck, /proc and
peer UID. A container cannot supply the missing host-kernel syscall.
The user confirmed that no independent test machine/runner is currently
available. An independently controlled pidfd-capable Linux runner with Python 3.12,
the locked dependencies, tools and separately marked PG17 is required.

The original 1,443,097-row x3 capacity requirement is unchanged; measured
rounds this task: 0. Separate resources and explicit execution authorization
are still absent. FIELD_NOT_RETESTED; production recovery authority is not
installed. No source-contract signature is invented or activated.

One next owner action: appoint an independent maintainer to resolve the
[bounded decision](worker02_r6_approval_decision.md) and arrange the required
isolated supported runner. Keep PR #1 Draft; do not merge, delete the branch,
deploy, force-unlock, replay a task, or automatically start another round.
