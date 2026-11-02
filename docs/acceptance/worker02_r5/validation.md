# R5 Validation

This is a diagnostic/evidence delivery, **not a passing merge acceptance**.
`validation.json` separates pre-commit runs from the final-SHA receipt on
[PR #1](https://github.com/sssssssssh/ssh_stock/pull/1).
The containing delivery commit is the final source selector; no R4 SHA is
presented as the R5 tested SHA. Post-commit results must include that exact
HEAD, tree, commands, exit codes, XML digests and native run/job identities.
They are posted without another documentation commit changing the identity.

## Scope And Actual Evidence

Only opt-in pytest diagnostics and a local capability probe are added.
The plugin records collection order, a bounded preceding-test list, fixture
and ContextVar/cache state, and first-error observation/statistics facts.
Only dual-verified, generated test databases on the explicitly marked test
instance may receive a separate read-only snapshot connection. No DSN,
password, raw SQL, settings payload, role name or exception text is exported.
Unknown/missing evidence is not zero or success. Original assertions and
failure outcomes are unchanged; artifact failure cannot turn a failed test
green. No plugin is auto-installed in conftest or any workflow.

| Pre-commit execution | Actual result | Identity / limitation |
| --- | --- | --- |
| New diagnostic/preflight units plus old Worker units | 57 passed | Windows offline, env-file disabled; corrected new socket fixture; collected-project SHA check |
| New real PG17 snapshot tests | 3 passed | Input source plus explicit new-file overlay; not final-SHA proof |
| New ledger plus original financial OFF/ON comparisons | 3 passed, 194.92 seconds | recalculate/daily/catchup; explicit overlay, not capacity |
| Original two disputed nodes | 2 passed, one schedule | Clean R4 input; no full-context root cause |
| Both complete related modules | 13 passed, one schedule | Original assertions unchanged |
| Original Observer five-node order prefix | 5 passed, one schedule | Exact first five R4 XML nodes |
| Historical original guard/native tests | 14 passed | Clean 2779a2a |
| Seven original historical source-guard modules | 73 passed, 88.94 seconds | All tests in those seven files, no selection/skip/xfail |
| Master original guard/native tests | 10 passed / 4 failed | Clean 75076ea; legal refusal retained |
| Input original guard/native tests | 10 passed / 4 failed | Clean 2bf219a; legal refusal retained |
| Original A4-2 contract-only | historical success; master/input refused | Explicit marked PG17; no performance workload |
| Unchanged Worker protection modules | 87 passed, 485.05 seconds | Includes all three OFF/ON claimed-root comparisons |
| Original four missing-tool failures | 4 passed, 1.25 seconds | Compiler, shellcheck, two Node negatives; no assertion edits |
| Entire original Publication preflight | 85 passed, 349.11 seconds | Same eight modules as native workflow; no performance experiment |
| Entire original Archive preflight | 142 passed / 1 failed, 91.47 seconds | Original safety plugin; exact old frozen-source node |
| Entire original Lookup preflight | 106 passed / 1 failed, 172.80 seconds | Same legal guard refusal |
| Entire original A4-1 preflight | 48 passed / 1 failed, 254.85 seconds | Same legal guard refusal |

Raw first attempts are retained, not overwritten: the initial new socket
test mocked SO_PEERCRED but omitted Windows AF_UNIX (55 pass / 1 failure);
the correction completes the new synthetic fixture, not an old assertion.
The original platform/source test failures are never reclassified as that
fixture issue. Old-host-Git checkout and unmarked A4-2 attempts are recorded
separately as invalid harness executions.

Worker protection includes unchanged receipt, unknown-ACK READ ONLY,
57014/55P03/disconnect/CAS/cancel/terminal/late-observation tests and three
real claimed-root OFF/ON lifecycle comparisons. The final receipt supplies
actual counts and exact financial/field/key/ledger JUnit properties. Tiny
synthetic fixtures never satisfy the unchanged capacity requirement.

The new `test_worker02_r5_ledger_parity.py` reuses the complete unchanged
R2 lifecycle function and, before each owned database is dropped, compares
all ledger business columns OFF/ON. It separately validates per-run UUID /
owner-token and creation/start/publish-time invariants. Its explicit column
set prevents silently ignoring future ledger fields. It does not alter
the old financial, dtype, natural-key or diagnostic assertions.

One ancillary `docker top -eo comm` readiness probe was rejected by the old
Docker daemon because it omitted the PID field. That probe is not process
exit evidence or a timing-isolation certificate; no test result relies on
it for qualification. Original assertions and actual XML results are retained.

## Unclosed Context And Platform Gates

Both original R4 full failures remain **UNCLASSIFIED_BLOCKER**. Standalone
and module successes cannot explain the prior full failure. Observer's raw
R4 traceback lacks its first_failure_code; statistics lacks its drift sample.
The plugin collects those fields if a future unchanged assertion fails.
The statistics 868-node original-order prefix and unfiltered full schedule
require a supported independent runner; no reduced schedule is labelled full.

The available isolated VM is Linux 3.10 / Python 3.12.15 / PG17.6. Test-only
compiler, Node and shellcheck installation succeeds offline after cached
downloads. A single package is extracted to supply real Git 2.47.3 after
the combined apt operation's Perl download returned 502. No host toolchain,
system kernel, user container or production service is changed. Both apt
network disconnects and all package logs are retained. Own test processes
have not been manually stopped to manufacture a pass.
The after-probe has /proc and peer UID but **pidfd ENOSYS**, therefore
**PLATFORM_BLOCKED** even with all four tools available. A container cannot
upgrade its host kernel. Windows has no usable local Docker/WSL runner here.

Unfiltered final-SHA Linux pytest/coverage is **BLOCKED**, not zero failures,
not an ignored/deselected pass, and not the old R4 result. Latest prior full
evidence is 5209 collected / 5027 pass / 45 fail / 137 errors / zero skipped;
the R4 coverage attempt was interrupted and is not a valid coverage receipt.
The unchanged full threshold remains 70 percent. Normal Actions also remain
subject to their original Archive/lookup/frozen-source gates.

## Reuse On A Supported Isolated Runner

Provision PG17 separately and set TEST_DATABASE_URL, V14_TEST_INSTANCE and
V14_TEST_SYSTEM_IDENTIFIER from that new owned test instance; do not load
business `.env`. Disable Settings env-file discovery in the invocation.

```bash
python -m scripts.worker02_r5_preflight --output .codex_tmp/r5-platform.json
python -m pytest -p scripts.worker02_r5_diagnostics \
  --r5-evidence-dir=.codex_tmp/r5-full \
  --cov=backend/app --cov-report=term-missing --cov-fail-under=70 \
  --junitxml=.codex_tmp/r5-full.xml -q
```

Use a fresh empty evidence directory for each execution; verify HEAD and
clean checkout before every schedule. Do not copy the new plugin into an
old clean source checkout: load its explicitly indexed external copy instead.
Record seeds/process limits/tool versions and preceding order before drawing
any pollution conclusion. This command is a reuse procedure, not a claim
that this unfiltered full run has executed or passed.
