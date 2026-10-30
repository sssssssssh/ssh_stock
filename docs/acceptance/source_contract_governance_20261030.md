# Source Contract Governance: Owner-Authorized Version Separation

## Authorization And Baseline

On 2026-10-30 the project owner explicitly authorized governance changes on
`codex/biz-worker-02`: separate daily development checks from historical A4/G1
source contracts, preserve original manifests/tests/records, retain business
safety, and submit for renewed review. This supersedes the earlier request to
defer governance adaptation. It is not a detached cryptographic signature or
a G1, recovery, capacity, production database, deployment or merge grant.

Input commit: `010dc6bfaeaaacdceafa48d7dcd5f56a10d180f7`, tree
`19cccc4d962631d255ae54d3df44c3e58596622a`. PR #1 remains Draft.
The [R6 exact-SHA receipt](https://github.com/sssssssssh/ssh_stock/pull/1#issuecomment-6519484189)
records the original RED and all remaining unrelated platform/field/capacity gaps.

## Causal Change

The ordinary business verifier selected old exact-set validators merely
because their historical manifest files existed. Legal current changes then
failed `a42366_source_guard.py:78` with `A4235_FROZEN_FILE_CHANGED`. This was
a governance/version mismatch, not evidence of a financial calculation bug.
The new explicit default is `development.source.v1`. It validates current
committed bytes, independent readers and the existing complete no-follow tree
check. It does not require an old stage path set and cannot issue execution
authority. Current static definition hashes bind current committed blobs;
old frozen hashes still independently verify their original Git objects.

The historical route is `a42366.source.v1`, pinned to commit
`2779a2a7a7120c86f67b4991bce196c652b5ebb0`, tree
`27d9e7a9b384c063f0e7b4e5364d35b1761e6121`. Both must match before use.
There is no unknown-version fallback or implicit history-to-current upgrade.
All eleven historical manifest files remain byte-identical to their old Git
objects. No original tests or workflow files are edited by this change.

## Original Tests, Not Waived Assertions

Only the following node describes a particular historical stage's complete
test-file set rather than current business behavior:

`tests/unit/test_a42366_source_guard.py::test_AT_W09_historical_manifests_and_all_original_tests_keep_their_blobs`

Its original function and assertions execute in a fresh pinned historical
checkout through an explicit pytest route. It is not deleted, deselected,
skipped, rewritten or converted to xfail. Child failure, missing XML, incorrect
counts or any skip fail the parent. JUnit identifies the historical SHA and
contract version; a terminal summary discloses the route. Other safety tests
continue against current code. The registry is a single exact node, not a glob.
Before delegation, the original test files' current committed and physical
bytes must still equal the historical originals: routing cannot hide edits to
an old test. Raw JUnit retains version properties; the existing CI redactor
may omit properties, so the terminal version summary and final receipt remain
explicit. The redaction policy is not weakened.

A separate new offline regression executes all seven original historical
source-contract modules: 73 original positive and negative cases. Its child
count is reported separately from the parent test count and is not backend
coverage or a current performance credential. The child uses historical
PYTHONPATH/config, strips database connection environment and never copies
`.env`; it does not obtain a business connection or fetch missing history.

## CI Before And After

| Layer | Before | After implementation |
| --- | --- | --- |
| CI archive/lookup static checks | 142/1 and 106/1, blocked on old source set | Current static contract; final exact-SHA result in PR receipt |
| A4-1 contracts | 48/1, old source set refusal | Current static tests; original real measurement source refusal unchanged |
| A4-2 contract-only | Old exact-source delegation refused before safety tests | Current static version plus immutable historical facts; real laboratory entry unchanged |
| Publication contracts | 85 passed; no performance run | No source/workflow change; actual new result required |
| Historical source tests | Old stage assertion wrongly applied to latest tree | Original assertion executed on its exact historical tree; all 73 old positives/negatives also run |
| Formal release/recovery/capacity | Separate explicit gates, missing authority/evidence refuses | Unchanged; daily/static success supplies no grant |

No workflow YAML, trigger, job condition, experiment scale, one-shot policy,
Release Gate, financial formula, production SQL, migration, strategy or default
performance switch changes. Existing contract-only CI callers use the new
static route; real experiment entry points retain their old strict guards.
No costly experiment, production access, field recovery or deployment is
authorized or performed. Normal CI evidence must not be labeled performance
acceptance. Platform and unrelated failures remain failures, not waived tests.

## Validation And Rollback

Run focused new routing/history tests, original source safety regressions,
then normal pytest/ruff on an appropriate Linux runner. Full-suite coverage
must retain its original 70% threshold. Exact final commit, real counts,
failures/skips and native CI URLs are recorded in the PR receipt after push;
do not create another documentation commit relabeling the tested identity.
No unexecuted or earlier-SHA result is a current PASS.

Rollback uses a new `git revert` commit for this governance change after
review, never a history reset or edits to historical manifests. Restoring the
old default will restore its known current-source refusals; this is not a
reason to weaken old assertions. No business data, Job state, authority,
published generation, cache or database schema needs modification. Stop for
review after delivery; do not merge, delete the branch or start a new phase.
