# WORKER 02 R5 Baseline

Input HEAD and remote work branch: `2bf219a0d05c0aa8090d9050e043c60343db684d`.
Master and merge-base: `75076eac443d935d622bf59e12aad20ce5aba85e`.
Historical valid source: `2779a2a7a7120c86f67b4991bce196c652b5ebb0`.
PR #1 is Open / Draft; merge checkout `4c0d0b57f784067089dc20518527ef79ead4eaa9`
has the same tree `aa0b07cec1ca4b3d9fb990a8ccb8b52e592d3c33` as input HEAD.

The initial worktree is clean. Fetch confirms both remote refs unchanged.
`git diff --name-status 2bf219a0 HEAD` is empty. Existing work branch only:
no new branch/PR, master modification, merge, branch deletion or deployment.
The two R3 reports were deleted at the user's preceding explicit request;
R5 does not recreate them or alter R4 evidence.

## Original Results And Native Jobs

R4 full Linux: 5209 collected, 5027 passed, 45 failed, 137 setup errors,
zero skipped. Its 174 source-contract refusals, six platform failures and
two unclassified failures are input evidence, not new R5 execution results.
All 87 Worker nodes passed; that does not mean the full suite passed.

| Original run | Native first failure / downstream |
| --- | --- |
| [PR CI 40810024032](https://github.com/sssssssssh/ssh_stock/actions/runs/40810024032) | Archive 142/143; lookup 106/107; full suite not entered; capacity/release gate skipped |
| [A4-1 40810024047](https://github.com/sssssssssh/ssh_stock/actions/runs/40810024047) | 48 passed, one exact FROZEN_FILE_CHANGED; isolated baseline skipped |
| [A4-2 40810024039](https://github.com/sssssssssh/ssh_stock/actions/runs/40810024039) | Frozen sources/formal parent migration step 7; safety and laboratory/gate not run |
| [Publication 40810024253](https://github.com/sssssssssh/ssh_stock/actions/runs/40810024253) | 85 contract tests passed; performance skipped, not qualified |

Fresh API job metadata, original ZIP/XML/job-log hashes and retrieval methods
are in `evidence_index.json`. Per-node original first errors and commands are
in `failure_matrix.csv`; raw traceback remains in the indexed XML and JSON.
The Archive native redaction is retained, not relabelled a full stack trace;
clean Linux replay identifies its old exact-path guard failure separately.
Master has matching named native refusals, not a passing full-suite baseline.

## Two Unclassified Failures

The original order places restricted-role observer at zero-based position 4
and conditional statistics stabilization at position 867. Original raw XML
SHA256: `9f82418832b55e1719e5f4bdedbb42310c629ec59f876c514ba786e8150f6aec`.
Independent R4 standalone input/head probes passed; these do not close either
full-context failure. R5 must collect order, safe context and first-error
facts without weakening the original assertions or clocks.

## Available Environment And Stop Lines

The existing isolated-test VM reports Linux 3.10.0-1160.el7.x86_64, total RAM
3,953,963,008 bytes and currently available 1,859,084,288 bytes. No usable
Docker CLI or WSL distribution was discovered on the Windows host. A Python
pidfd symbol is not kernel capability. Test-only tool installation may fix
missing tools, never Linux 3.10's unsupported pidfd or formal qualification.

The exact workflow inventory is protected by an existing contract test.
R5 does not add an unreviewed workflow or edit the governance inventory to
bypass approval. Independently supported Linux runner access remains a
separate requirement if no authorized existing runner can execute the suite.

No business `.env`, production database, TuShare, cloud executor, historical
task state or physical G1/L2 is accessed. Million-row x3 workload is not
authorized. Historical guards/manifests/defaults/SQL/schema remain untouched.
