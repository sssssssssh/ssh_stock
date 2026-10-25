# A42351 — Reviewer contract and G1 preflight delivery

This is the versioned **pre-push** receipt. CI for the eventual final SHA is PENDING
until independently fetched; no previous SHA's green result is inherited. The final
delivery message/ignored local audit receipt will identify that exact SHA/run/attempt
and downloaded artifact hashes without a recursive post-CI documentation commit.

## Scope and staged evidence

Baseline `55bd6328c3481f2b2ce767fcb843caaa8e0a2ad8`, master, clean and equal to origin
at start. User explicitly authorized staged commits and one final push. No branch
switch, history rewrite, real probe, new PG/container, /proc or manual dispatch.

- W00: baseline CI freshly rechecked, pure-memory exploit reproduced. RED commit
  `448a9acfc1512d13c53ae667fcc7ecb8fe5156ca`; 1 failed/133 deselected, exit1. Details in
  [baseline and RED](a42351_baseline_and_red.md).
- W01: independent ON joined/unjoined and OFF authenticity checks, unchanged raw
  partial validation and cleanup cross-checks. Initial repair commit `a1e472c`;
  `a1e472cabcf2d4dbcc560482736eb2c5ad6964e9`; initial 170-case Reviewer regression
  passed (25.36s), including RED→GREEN.
- W02: exact source/test overlay and independent HEAD/blob/working-byte binding;
  actual committed-tree and complete unit verification PASS locally (details below).
- W03/W04: pure design guard, [trust runbook](a42351_g1_runbook_and_trust.md),
  [decision matrix](a42351_capability_decision_matrix.md); initial offline design
  run 85 passed (0.73s). No physical evidence claimed.
- W05: targeted/full unit, Ruff and diff checks PASS locally; final-SHA ordinary CI
  PENDING before push. Existing workflows unchanged; no capacity run requested.

### Local execution update before final push

At `fa55e4ee78c6433b17983afedd4b6400e4aa4e07`, the combined seven-file target
returned **600 passed in 77.00s**, zero failures/skips: A42341 279 (old241 +38),
A4235 236 (old221 +15), new G1 design85. A42341+design separately:364 passed40.98s.
Actual frozen tree and new independent overlay/source fingerprint construction passed
on that clean committed tree. Additional index-hidden byte/HEAD-race regressions were
then committed in `8c6d859ea823c92659633e106de298d9d9b80714`.

At that latter SHA, **all unit tests: 2871 passed, 5 existing warnings in 114.33s**,
zero failures/errors/skips. All 602 target cases were included (A42341 279, A4235 238,
G1 design85), as well as all old A4233/A4234 unit regressions. Ruff over backend/tests/
migrations/scripts/.github/actions and git diff --check passed. The safety pytest
plugin was retained; .env loading was disabled before pytest import, with only an
unreachable synthetic loopback test URL. No local PostgreSQL/container was created or
connected. Existing isolated PG17 integration, migration, frontend and browser
verification is deliberately left to the unchanged ordinary push CI, not run locally.

Exact changed path set: 16, matching declared scope. Business/workflow/dependency
diffs are empty. All four historical authority document bodies remain verbatim;
numstat has 11/10/7/11 additions and **zero deletions** respectively.
Two initial read-only scope-audit assertions were overly strict (quoted Unicode Git
paths, then inserted-section contiguity); corrected unquoted exact-set/body-preservation
checks passed. No source was altered to accommodate those audit assertions.

Manifest SHA256: `ea795278e3fb84e4eebabeba737d23a92a4a0c42e6402cc828bf3801d3c9f648`.
At 8c6d859, independently calculated overlay SHA256:
`5192b1a422dffb31d7d9464c7bfbd38cb3567937762e6196f11a0e28b7fdf5f4`;
source SHA256 `cd30c8c235668911997c848a8fff678401b0c577a61ca6e44c5bbcacea2415b1`.
These fingerprints bind **that SHA**, not the later final documentation commit.
Final fingerprints must be read again at the actual final HEAD. No real probes used.

## Exact changed-file inventory

Modified source: `scripts/a42341_calibration_review.py`,
`scripts/a4235_capability_guard.py`.
New source: `scripts/a42351_g1_preflight_contract.py`.
Modified tests: `tests/unit/test_a42341_runner_review.py`,
`tests/unit/test_a4235_pg_identity.py`, `tests/unit/test_a4235_capability_review.py`.
New tests: `tests/unit/test_a42351_g1_preflight.py`.
New acceptance docs: `a42351_baseline_and_red.md`,
`a42351_reviewer_overlay_manifest.json`, `a42351_g1_runbook_and_trust.md`,
`a42351_capability_decision_matrix.md`, `a42351_closeout.md`.
Append-only notes: README.md, PROJECT_RULES.md,
`docs/股票机会发现系统_PRD_V1.0.md`, `docs/股票机会发现系统_系统设计_V1.0.md`.
No other paths are part of this task; no workflow edit or new dependency.

## AT01–AT28 executable traceability

Numbers refer to this taskbook, not older AT numbering. Tests are in runner_review,
pg_identity, capability_review and new g1_preflight files. No old test is deleted,
skipped or weakened. Explicit final execution evidence is recorded below after run.

| AT | Executable coverage | Actual local status (CI separately pending) |
|---|---|---|
| 01 | baseline/old receipt byte equality, production/workflow boundary, pure imports | PASS |
| 02 | original OBSERVER_INVALID false join/cleanup asserts fixed Fault | RED observed; GREEN in initial 170 |
| 03–06 | joined end/lifecycle/state/CPU/elapsed/tick/bracket contradictions | GREEN in initial 170 |
| 07–08 | unjoined end/CPU/elapsed/local/top cleanup/partial prefix | GREEN in initial 170 |
| 09 | OFF worker/tick/lifecycle/CPU/JOIN_TIMEOUT and legal OFF failure | GREEN in initial 170 |
| 10 | stable raw unjoined and joined payload-failure snapshots | GREEN in initial 170 |
| 11 | SQL_TIMEOUT/CANCELLED/SIGNAL sticky first error with cleanup | GREEN in initial 170 |
| 12 | original 128-point cleanup-only failure without failed_point | GREEN in initial 170 |
| 13 | unchanged 128/64, slow/negative and Decimal-inclusive cases | GREEN in initial 170 |
| 14–15 | fixed redacted schema/source faults; old identity parsed, never upgraded/resealed | PASS |
| 16 | actual clean overlay/new source fingerprint/historical frozen SHA separation | PASS |
| 17 | extra old source/production/workflow/protocol/test rejects | PASS |
| 18 | manifest/hash/path-set/byte drift rejects | PASS |
| 19 | full HEAD, dirty tree, blob mismatch, independent remote/target checks | PASS |
| 20 | READY/true flags/unknown fields rejected | PASS |
| 21 | nonce/expiry/replay/profile/allowlist/budget non-authority | PASS |
| 22 | nonlocal/existing/possibly business endpoint and excess-role rejection | GREEN in 85 |
| 23 | no physical/cleanup proof; all seven capabilities NOT_RUN/NOT_PROVEN | GREEN in 85 |
| 24 | C0/C1/cache/zero-filled CPU/cleanup self-upgrade rejects | GREEN in 85 |
| 25 | model-only full bracket and missing/timing/budget failure | GREEN in 85 |
| 26 | hard-denying CLI/event/env; old real adapter remains denied | PASS |
| 27 | final targeted/full unit/Ruff and existing CI PG17/migration/browser | Local PASS; final CI PENDING |
| 28 | independent exact SHA/run/attempt/source tests and final CI audit | Identity tests PASS; CI/artifacts PENDING |

## Overlay and historical identities

Manifest carries exact paths and patch SHA256. Guard pins its bytes. HEAD is read
independently from Git; the containing commit SHA cannot be embedded in its own
manifest without a hash cycle. Static CLI binds caller target==HEAD==origin/master,
and requires committed/worktree bytes and a clean tree. It still exits2, not 0.
Guard verifies all protected HEAD objects too, so assume-unchanged cannot hide bytes.
There is no arbitrary script or directory exemption.

Historical baseline 7681b57 and its ls-tree SHA256
`b7aecb955fb32bf285ae71ff3bdf6cfdc6aa15828e70bb46c507d31bfc1418e9`
keep their original meaning. Current A4235 source digest adds exact HEAD/manifest/
patch fingerprint; it cannot reuse the old A4235 identity. Old artifacts are never
re-signed. This proves static integrity relative to reviewed source, not a trusted
human signature or execution approval. Raw source/manifest hashes are mechanically
available in the new manifest and final independent audit.

## Unchanged boundaries and remaining gaps

Production/backend/config/model/migrations/frontend and all workflows remain byte
unchanged. A4233/A4234 sources, historical protocols/input/one-shot records, A42341
runner/schema/guard/thresholds and other A4235 measurement/Grant/RealAdapter sources
remain frozen. Four authority documents only gain the new stage section.

| Domain | Maximum after actual code CI verification | Physical state |
|---|---|---|
| Reviewer | REVIEWER_CONTRACT_FIXED, contingent on final CI | no real experiment |
| Freeze overlay | STATIC_OVERLAY_VERIFIED, contingent on committed check | not human authorization |
| G1 | G1_PREFLIGHT_READY_FOR_REVIEW | NOT_RUN_NOT_AUTHORIZED |
| G2 | PENDING, effective warmups total8 | 16/32 NOT_APPROVED |
| G3 | NOT_AUTHORIZED | 128 real points NOT_RUN |
| C1/P95/L2/production | INSUFFICIENT_EVIDENCE | NOT_AUTHORIZED |

Real signature verification/persistent consumption, physical fixture/least-role
visibility, same-session prepared sufficiency, cached-plan structure, backend CPU
mapping, long-window coverage and independently audited cleanup are NOT_PROVEN.
No unique repair candidate, performance result or capacity pass is asserted.
Stop here for human code review; no later stage is automatically authorized.
