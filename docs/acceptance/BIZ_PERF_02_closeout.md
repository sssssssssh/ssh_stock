# BIZ-PERF-02 Closeout

Status: PARTIAL / BUSINESS_CHANGE_WITHDRAWN. Retention: FAILED.
Performance: PERFORMANCE_OPEN. Capacity: RESOURCE_DEFERRED.
Cloud: REAL_CLOUD_RECALC_NOT_AUTHORIZED.

This new record does not revise earlier BIZ-PERF-01/G1/Worker acceptance records.
Baseline and registered retention rules: [design](BIZ_PERF_02_design.md).
Operations and rollback: [runbook](BIZ_PERF_02_runbook.md).
R1 read-only evidence review: [exact-SHA summary](biz_perf_02/ci_8f4e607_r1.json).
R1 is documentation closure awaiting owner diff review, not performance acceptance.

W00 verified merged PR #1, synchronized clean master at 3940d9b, PG17.6 physical
marker/system ID, matching Alembic head and false flags. Initial provisioning
found an incomplete older binary directory; no server or database was created
there. A complete existing binary installation initialized a fresh owned cluster.
No installer, business environment, old database or cloud endpoint was used.

W01 captured real SUCCESS/PUBLISHED 1/12-month roots and actual seven-table timed
plans. Twelve-month cross-table quality staged 1,566 singleton rows in 1,566 calls;
its 16.281 seconds includes 12.729 seconds of candidate upserts. The same run
retained two SQLSTATE 55P03 observations; overall success does not erase those
bounded observation failures. The two failed plan-capture attempts remain RED.

W02 implemented one candidate: same-transaction five-row quality batching before
the unchanged sector check. It is preserved in commits c0f0fca43f2fe4f66fa36c9e63dc465f36424b8b
and 6c4096e5de77368c67ff1c2cff7ddd3285a8e56e, without rewriting either commit.
The new batching test failed at `[1,1,1,1,1,1] != [5,1]` before the change;
afterward 10 focused new/original tests passed. This functional RED-to-GREEN proof
did not predict overall benefit. The retention failure below required withdrawal.
Current daily_quality.py is byte-equivalent in Git to baseline 3940d9b; there is
no retained business optimization and no financial/Raw/publishing/schema change.

Ten different real roots completed FIFO/dedup validation with all ten
SUCCESS/PUBLISHED in 398.76 seconds; original fault-matrix CI remains separate.
That local continuity receipt was produced before the candidate commit, carries
DIRTY source provenance, and is not exact-final-SHA performance acceptance.
The local resource preflight observed a memory/disk lower floor, not a refusal
or an exclusive/capability-qualified capacity reservation. Do not claim RAM was
exhausted: formal capacity remains deferred for lack of an allocated qualified
runner and representative million-row fixture, not because a small test passed.
The first comparison cohort was stopped because the old archive lacked Git while
the new runtime had Git. Only its verified controller was stopped; its active
root child finished naturally. The incomplete controller and all child receipts
remain separate. The corrected protocol uses two clean detached local Git clones
with LF line endings; no timing conclusion is drawn from the asymmetric cohort.

## Controlled Comparison And Withdrawal

The corrected cohort ran baseline 3940d9b905e5234368f8a7474ae2ce6de73b0cb3
against candidate 6c4096e5de77368c67ff1c2cff7ddd3285a8e56e. Both clean detached
Git clones had LF bytes and independently verified implementation identity.
All four optimization flags were false. Three AB/BA/AB pairs per window produced
18 zero-exit SUCCESS/PUBLISHED children and nine matching input snapshots,
complete financial table digests, identities, windows and publication counts.
Only root UUID/audit timestamps are normalized; NULL, serial IDs and other source
identity remain in the comparison. This is a four-security synthetic diagnostic,
not a representative universe or million-row test.

Times below are whole-root seconds; P95 is linear inclusive, with only three
samples per implementation/window. No statistical significance is claimed.

| Months | Old samples | New samples | Old/new median | Old/new P95 | Median improvement |
| --- | --- | --- | --- | --- | --- |
| 1 | 53.547, 63.094, 57.343 | 60.422, 59.750, 60.406 | 57.343 / 60.406 | 62.5189 / 60.4204 | -5.34% |
| 3 | 65.031, 66.906, 66.969 | 64.250, 59.437, 60.812 | 66.906 / 60.812 | 66.9627 / 63.9062 | +9.11% |
| 12 | 141.204, 128.640, 136.265 | 117.406, 126.421, 122.282 | 136.265 / 122.282 | 140.7101 / 126.0071 | +10.26% |

Quality-stage medians improved 42.34%, 45.92% and 42.17%; respectively two, three
and three pairs improved. Nevertheless the one-month whole-root median regression
of 5.34% exceeds the registered 5% ceiling. Overall retain_candidate=false.
The candidate was withdrawn, not retried with more rounds, filtered or admitted
by raising the ceiling. The controller was observed as nonzero by the PowerShell
wrapper (exit 1); this does not replace any of its 18 recorded child exit codes.

Evidence: [matrix](biz_perf_02/matrix.json), [raw index](biz_perf_02/raw_index.json),
[local test receipts](biz_perf_02/local_tests.json),
[original local log hashes](biz_perf_02/local_log_index.json). Lossless gzip observations
include all corrected samples, original failed diagnostics and asymmetric samples;
compressed/uncompressed hashes and original local log/XML hashes are recorded.
The original XML/logs remain in the ignored owned lab, without publishing paths,
SQL parameters or credentials. Timed plans are actual first lookup plans, not
publication replay. Successful driver SQL time and inclusive stage wall time are
reported separately; failed statement exclusive/server CPU time is unavailable,
not filled with zero. Inclusive overlapping stages must not be summed.

## Regression And Final CI

After withdrawal, 20 focused tests passed: six new explicitly pinned rejected-
candidate cases, two live restored-quality cases, nine observer/retention cases
and three original quality cases. The six cases record their rejected subject,
full candidate SHA and source hash; they do not re-route original tests or prove
current batching is active. Original safety assertions remain unchanged.
Earlier focused receipts include 10 and 17 passing cases. Ten real root receipts
remain separate from the current implementation's full fault matrix.

Unfiltered local Windows pytest failed collection with 10 errors because native
fcntl is unavailable. It is not a passing or skipped full suite. Ruff passed;
ordinary Linux CI on 8f4e6071b74ae90dd95eb56a71ade1ed3dcb1e6a subsequently passed.
R1 verifies that commit's actual receipts below, not the uncommitted R1 document
changes or a future commit. Engineering success does not close A05/A06 by itself.
No high-cost workflow dispatch, business cloud access, deployment, Worker or
Scheduler restart was performed.

## R1 Evidence Closure

Review baseline and origin/master both remain
8f4e6071b74ae90dd95eb56a71ade1ed3dcb1e6a. Entry worktree was clean; local/remote
branch inventory contains only master and its remote aliases. The app inventory
showed no other active Codex chat on this checkout; this is not a claim about
unobserved computers. PR #1 is merged at 3940d9b905e5234368f8a7474ae2ce6de73b0cb3,
which contains the governance commit. Both baseline and current daily_quality.py
have Git blob 2d07cd4bbc86c3b7035babcbca0c52c086195d7c. No business file changed in R1.

All runs below are ordinary push attempt 1 on that exact review SHA. The JSON
summary records every job ID/URL and each step number/name/conclusion from GitHub.

| Workflow and run | Successful jobs | Skipped jobs, not executed experiments |
| --- | --- | --- |
| [CI 41386309719](https://github.com/sssssssssh/ssh_stock/actions/runs/41386309719) | dependency-audit, lookup-diagnosis, test, workflow-contracts | authorize, ui-visual-acceptance, lookup-tail-attribution, capacity, publication-release-gate |
| [A4-1 41386309854](https://github.com/sssssssssh/ssh_stock/actions/runs/41386309854) | contracts | authorize, isolated-baseline |
| [A4-2 41386309794](https://github.com/sssssssssh/ssh_stock/actions/runs/41386309794) | contract-and-safety | authorize, laboratory, a42-acceptance-gate |
| [Publication V1.3 41386309722](https://github.com/sssssssssh/ssh_stock/actions/runs/41386309722) | contracts | authorize, candidate-performance |

All four workflows concluded success: 7 successful jobs and 12 skipped jobs in
19 checks. Skipped authorization/performance jobs are not passed experiments.
Existing lookup-diagnosis replays historical evidence; it is not new capacity
measurement. Existing synthetic smoke/capacity-named regression steps likewise
do not constitute the deferred BIZ-PERF-02 formal million-row matrix.

Main CI [test job 125087811786](https://github.com/sssssssssh/ssh_stock/actions/runs/41386309719/job/125087811786)
has success on each of the following actual steps:

| Step number | Actual step or command | Verified evidence |
| --- | --- | --- |
| 7 | V1.4 physically isolated and marked PG17 | disposable CI PG17, not business database |
| 12, 13, 14 | python -m alembic upgrade head; downgrade 0019_research_source_lineage; upgrade head | all success on CI fixture |
| 17 | Data publication and schedule compensation regressions | 45 cases, 0 failure/error/skip in targeted JUnit |
| 23 | Run python -m pytest -p scripts.a42331_pytest_safety --tb=no --show-capture=no -rN --cov=backend/app --cov-report=term-missing --cov-fail-under=70 --junitxml=.codex_tmp/m17_1_2-full.xml | 5297 passed, 0 failure/error/skip; 801 warnings; 2910.43s; coverage 89.99%, minimum 70% |
| 25, 26 | python -m alembic current; python -m alembic heads | both 0058_data_publication; receipt postgres_version_num=170011 |
| 27 | python -m ruff check backend tests migrations scripts | All checks passed |
| 29, 30 | docker compose config; docker compose build | both success |
| 31 | Data queue single/two Worker and atomic publication acceptance | synthetic 1/2 Workers complete 6/6 roots, atomic scenario 7; max_top_level_running=1 |
| 33 | docker run --rm --add-host backend:127.0.0.1 ssh-stock-frontend:local nginx -t | success |
| 35, 36, 37 | npm ci; npm run test:coverage; npm run build | 162 tests / 23 files passed; statement/line coverage 87.27% |
| 38 | M16.6 browser acceptance (isolated runner tooling) | success, distinct from skipped ui-visual-acceptance job |
| 41 | Runtime reliability desktop and narrow-screen synthetic acceptance | success |

Three existing downloaded artifacts were rehashed against freshly fetched GitHub
metadata, without downloading duplicates or modifying their contents:

| Artifact ID and name | SHA256 of downloaded ZIP |
| --- | --- |
| [13117382572](https://github.com/sssssssssh/ssh_stock/actions/runs/41386309719/artifacts/13117382572), a42331-safe-ci-8f4e6071b74ae90dd95eb56a71ade1ed3dcb1e6a-41386309719-1 | 13a757799ae38c66edcb3f98e9d75628bf2b38b0bd807da4829e170a6ad32c49 |
| [13117617185](https://github.com/sssssssssh/ssh_stock/actions/runs/41386309719/artifacts/13117617185), m17-1-2-suspend-evidence | 4e972dc9fecfa060d44339a128e8ef099db9608106ac1cf0facc861bca25c9b3 |
| [13117856303](https://github.com/sssssssssh/ssh_stock/actions/runs/41386309719/artifacts/13117856303), data-queue-container-acceptance | c344a5104a46dfdfac53cf474328020d79860a64c2607a9dfff77aa3b482e726 |

The two copies of m17_1_2-full.xml are identical, SHA256
1cf3d89ba657b33ba4688404876145e3ffb1069d5dcaf8956569d337be156401.
Parsed counts agree with failure.json and the log, not merely the workflow status.
The safe receipt has capacity_ready=false, performance_eligible=false and
production_read_authorized=false. No exported artifact grants production access.

### A05 And A06 Evidence Limits

The summary lists 69 exact sanitized testcase identifiers across quality,
continuity, publication, cancellation, performance-regression and cross-table
quality modules. These are a subset of the 5297, not extra tests. Parameterized
names are hashed by the existing sanitizer; hashes are not guessed fault labels.
No test was rerun, changed, skipped or redirected in R1.

For A05, the six new candidate-specific quality cases passed, but their fixture
loads 6c4096e, not current quality. The two test_live_* cases pass against current
quality: A-only visibility/IDs/first preimages and the sector-error valid prefix.
Current original publication tests also pass, including
test_real_quality_cannot_borrow_a_and_keeps_a_quality_published,
test_disconnect_mid_publication_rolls_back_a_and_holds_slot and
test_committed_publish_response_loss_never_rewrites_success; cancellation and
cross-table evidence cases are present in the same JUnit. However, the dedicated
repeat/malformed-threshold/mid-store quality scenarios are pinned candidate
proofs, not direct current-quality proofs. Keep A05 PARTIAL rather than claiming
that aggregate CI success supplies the entire task-specific safety proof.

For A06, the stored ten-root local receipt still has DIRTY source provenance.
The final-CI test_ten_different_real_roots_are_fifo_idempotent_and_published also
passed, and its source asserts ten distinct FIFO/deduplicated SUCCESS/PUBLISHED
roots. But the exported safe JUnit has zero property elements: it contains no
per-root UUID/source/generation receipt or same-identity fault-matrix mapping.
The existing separate fault tests and synthetic container scenarios pass; they
must not be combined with the DIRTY local receipt into a fabricated exact-final-
SHA ten-root/fault-matrix artifact. Keep A06 PARTIAL. Obtaining additional bounded
raw provenance would need a separately reviewed follow-up, not a rerun in R1.

The earlier commit comment called A05/A06 PASS_ENGINEERING. That was broader
than the task-specific evidence supports; this R1 document narrows the current
assessment to PARTIAL, preserving the original comment and raw records unchanged.

| Item | Before R1 | Final R1 assessment and remaining limit |
| --- | --- | --- |
| A01 | PASS | PASS: merged PR, master-only, synchronized review SHA |
| A02 | WITHDRAWN | WITHDRAWN: identical quality blob; candidate/RED-GREEN history retained |
| A03 | DATA_COMPLETE / RETENTION_FAILED | unchanged: 18 samples / 9 pairs, all 25 raw artifact hashes verified; no sample removed or rerun |
| A04 | PASS_SMALL_SCOPE | unchanged: recorded input/output/identity/publication predicates all match; four securities only |
| A05 | PARTIAL | PARTIAL: current and rejected-candidate subjects separated; dedicated current-quality failure-path evidence incomplete |
| A06 | PARTIAL | PARTIAL: native continuity testcase passed, but local ten-root provenance is DIRTY and final per-root/fault mapping is not exported |
| A07 | PENDING | PASS_ENGINEERING_FOR_8f4e6071: exact-SHA CI/JUnit/coverage/migration/frontend/Compose verified, not R1 diff or performance acceptance |
| A08 | PASS | PASS_LIMITED_SCOPE: PERFORMANCE_OPEN, formal million-row / >=30% acceptance not met |

R1 accessed Git/GitHub and existing synthetic evidence only; no business .env,
database connection, service start, pytest, Docker or matrix execution occurred.
This review changes only Markdown/JSON documentation. Its diff must be reviewed
by the owner before any commit; no push is authorized by this taskbook alone.

Formal W04 capacity remains NOT_RUN / RESOURCE_DEFERRED. There is no allocated
independent qualified runner and representative >1,000,000-row fixture. The
resource-floor observation is not capacity qualification. The >=30% formal
whole-root acceptance is not met. Ordinary engineering CI cannot close that gap.
Business withdrawal is complete; combined tooling rollback is documented in the
runbook. Stop here for review, without automatically trying another hotspot or
starting the next phase.
