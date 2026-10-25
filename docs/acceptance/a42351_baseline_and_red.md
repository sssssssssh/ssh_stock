# A42351 W00 — baseline and RED evidence

Scope: Reviewer authenticity repair, exact static overlay and offline G1 preparation only.
Human authorization: staged commits on master, one final push; no real probes.

## Independently checked starting point

`git status --short --branch`: `## master...origin/master` (clean).
`git rev-parse HEAD origin/master`: both
`55bd6328c3481f2b2ce767fcb843caaa8e0a2ad8`.
`git ls-remote origin refs/heads/master` was independently checked at that SHA.

GitHub jobs freshly queried: main run **40150203524**, test job **121039973844**,
and Observer run **40150203544**, contracts job **121039973677**: success, attempt 1.
Existing downloaded ZIPs were reverified offline (exit 0): main 3558 tests,
221 A4235 cases, six sanitized JUnit files, 19 owned migration cleanup receipts;
special 319/109/241 tests, 20 frozen files, 128 mock samples/64 pairs, nine migration
cleanup receipts. This is baseline CI, not new-patch CI or real capability evidence.
Main safe artifact 12583058379 SHA256:
`e7b009e9827008887177b31cd9cceec0d0b1f985f5f6a393e0a5c2b8577f1d92`;
special mock artifact 12581942638 SHA256:
`6acb8a95200d648ff38b1adc39ae54b1c24f05d7cfb681aba6679b8d3496c7d2`.
An initial audit-helper invocation using `python -m` with a relative filename failed
before running; corrected file invocation with `PYTHONPATH=.` returned the results above.

## Fresh pure-memory reproduction (before repair)

Construct `e=c.identity()`, then `simulate(e, observer=MockObserver(fail_at=1,
failure_code='A42341_OBSERVER_INVALID'))`. Change only failed partial observation
`joined=True`, partial and top-level `cleanup_complete=True`, and top-level
`cleanup_failure_codes=[]`; reseal with `c.seal(v)`, call `review(v,e)`.

Actual stdout (exit **0**):

```json
{"result":"SIMULATED_REJECT","status":"INCOMPLETE","first_failure_code":"A42341_OBSERVER_INVALID","cleanup_complete":true}
```

The raw point still had STOP_TIMEOUT, no worker end, three lifecycle states
INIT/RUNNING/STOP_REQUESTED, unknown worker CPU and elapsed, and a final partial tick.
The Reviewer wrongly treated contradictory input as a valid failed collection.
Identity: head as above, run `local`, attempt 1, source SHA256
`3edf9ad70bb8a0f20a3afa3078a00e5fe0fe72969a4c97aac772da12c203bdc9`.
No historical artifact or identity was rewritten.

## RED test (before any Reviewer edit)

Command: use the project virtualenv, disable `Settings.model_config['env_file']`
before pytest import, set only an unreachable synthetic loopback DATABASE_URL,
then `pytest -p scripts.a42331_pytest_safety -q
tests/unit/test_a42341_runner_review.py -k a42351 --tb=short --show-capture=no -rN`.
No database connections, observer threads or socket operations are used by this test.

Actual stdout, exit **1**:

```text
F                                                                        [100%]
_____ test_a42351_AT02_observer_invalid_cannot_mask_false_join_and_cleanup _____
A42331_TEST_FAILURE
1 failed, 133 deselected in 0.98s
```

The safety plugin intentionally sanitizes the assertion traceback. The test asserts
`Fault('A42341_FAILED_POINT_INVALID')`, not merely a non-authorizing decision.
This document and the RED test are committed before implementation; that commit
is intentionally RED and is not pushed independently.

## Exact implementation boundary

Allowed old patch paths: `scripts/a42341_calibration_review.py`,
`tests/unit/test_a42341_runner_review.py`, optionally
`tests/unit/test_a42341_environment_guard.py`.
New-stage support: `scripts/a4235_capability_guard.py`, the existing A4235 identity
and review tests, new `scripts/a42351_g1_preflight_contract.py`, new A42351 tests and
the explicitly named baseline/manifest/runbook/decision/closeout documents.
Append current-stage notes to README, PROJECT_RULES, PRD and system design only.

Unchanged: production, model/migration/frontend, configuration/dependencies,
all workflows, old protocols/inputs/authorization records, A42341 runner/schema/guard,
and other A4235 measurement/Grant/RealAdapter sources. No G1/G2/G3, /proc, Docker,
database, cloud operation or manual CI dispatch is authorized.
