# A42366 Concentrated Delivery

baseline_sha: f00be6aa149d5fde145ae4137c01368a332b022f
business_code_changed: NO
source_status: SOURCE_PARTIAL_ENGINEERING_BLOCKED
physical_status: NOT_RUN_NOT_AUTHORIZED
actual_g1_sql / podman / initdb / cgroup / mount: 0 / 0 / 0 / 0 / 0
policy/ADR/signatures: unchanged; no test signature is a live grant
BIZ-PERF-01: PERFORMANCE_OPEN

## Changes actually made

Publication now checks the original four identities and every ordered absence
observation, fresh B/C and root receipts, and a separate independent Reviewer
source. Self-review fails closed. Durable approval/intent/PUBLISHED precede
marker unlink; FINALIZED follows directory fsync. This fixes unsafe acceptance
and unlink-before-permanent-receipt, but does not supply the missing Reviewer.

The installed entry routes a new v5 FD-only package to the actual strict domain
receiver. B claim/budget has a concrete handler; O/C/D/E mutation receivers have
explicit missing-capability errors, not modeled success. Legacy v3 stays intact.
Peer identity precedes decoding; scope/source/install/namespace/budget and live
revocation are rechecked. Attempts/replies persist; unknown ACK cannot replay.

Recovery no longer cleans never-prepared or unknown-preparation resources. The
resource state machine records attempts before inspection and quarantines unknown
CREATE/START acknowledgements. Native reservation-only admission is now closed.
Owner audit exposes a persistent target registration adapter with strict original
PID/start/generation/role/db/namespace identity, without adding probe SQL.

The ten historical manifests and all original tests remain exact Git blobs.
Versioned whitelist pins individual paths/hashes; original negative readers,
full-tree FD checks, budgets, SQL, infrastructure and workflows are retained.

## P0 Remaining

| File / function | Exact missing implementation | Owner |
|---|---|---|
| a42366_reviewer.IndependentReviewSource | Independent Reviewer server, unforgeable credential/readback and separate store writer; constructor/revalidate intentionally refuse | G1 + independent security reviewer |
| a42366_installation.build_installed_domain | Actual O/C/D/E mutation/worker adapters remain CapabilityBlockedEndpoint, although receiver/FD entry and B handler are concrete | G1 implementation |
| a42365_writer_broker.verify_all_writers | No unbypassable host MAC/namespace/global writer provider; permanent DENY retained | G1 + platform security |
| a42365_budget.native_exec / PreEffectOperations | Native transitive census and real FS/bootstrap execution bridge not installed; no actual native command is admitted | G1 + kernel reviewer |
| AuditConnectionFactory.registered_session_source | Adapter exists, but real installed Worker -> Owner registration handshake is not assembled | G1 implementation |
| a42366_installation / original RootManager/provisioner | Root/Guardian/worker FD construction and cross-UID same-store RO namespace installation still missing | G1 + trusted root installer |

These are source gaps as well as platform dependencies, not merely pending
approval. This task does not qualify as SOURCE_READY_FOR_PLATFORM_REVIEW.
W00/W10 documentation work is implemented; W01/W02/W04/W05/W06/W07/W08 remain
PARTIAL, W03 EXTERNAL_BLOCKED plus missing kernel provider; W09 requires final CI.

## Validation and Review

Local targeted: 74 passed / one Linux-only node deselected before final evidence
registration. Full local pytest: ten platform collection errors; no business
dotenv or DB access. Ruff passed; final diff and exact manifest recorded in the
final delivery. See a42366_test_matrix.md and a42366_evidence.json for actual
nodes and raw record hashes. No physical or performance success is inferred.

Final exact SHA and four ordinary Actions run IDs are returned in the delivery
message and repository Actions checks; do not reuse the green baseline runs as
new-source evidence. No workflow_dispatch or high-cost experiment is triggered.

next_review_request: review the publication safety changes and versioned domain
contract, then independently design the all-writer/native-census/Reviewer/root
installation implementations. Do not start L2 or deployment from this handoff.

## Retained First Delivery Failure

45cbd6860a7c3812e0893d989545fb5d960a9490 was pushed before an independent
committed-object audit detected two Unicode manifest paths corrupted by Windows
GBK stdout decoding. A4-2 run 40617432307 failed its frozen-source step; it is
not a passing acceptance record. An actual RED encoding test was added, the
generator now emits escaped ASCII JSON before UTF-8 publication, and the manifest
is resealed. Historical manifests/source baselines are not rewritten. The final
SHA must obtain its own four ordinary runs; do not transfer the initial results.

618cacd5bac4875dd28a5a8c1075b8a558bbb56f passed A4-1/A4-2/Publication.
Main run 40617934049 completed full pytest with 5086 passed / 1 failed / 0 skipped,
coverage 89.37%. All 74 new Linux nodes passed. The one failure was original
test_a42351_AT19_committed_patch_hash_not_just_git_clean: the new independent
hash check refused correctly but used FROZEN_FILE_CHANGED before the expected
OVERLAY_BYTES_MISMATCH. Only the new guard's error taxonomy is corrected; the
original test, rejection and thresholds are unchanged. Core archive
12787191408 SHA256 99dcd701af665cf86cb530a1297bb637f31d9a173c15fe5bbf20592ca8b38d15
and A4-2 archive 12786545791 SHA256
13e5780fdaed7ddae5723ef58cccfd9b6b4c7eac2b90851f9837adcf04db9802 are retained.
