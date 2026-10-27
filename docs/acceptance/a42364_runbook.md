# A42364 Run, Stop and Recovery

This is a SOURCE-stage runbook, not authorization to deploy.
Real build/install/PG/Podman/cgroup/cloud/business DB access is forbidden now.
No .env or DSN is needed for this work. Do not start any application service.

## Allowed Verification

Use an isolated dependency environment. Portable unit files under test_a42364_*
cover schemas, exact templates, journals and negative paths. Linux L1 files are
test_a42364_process.py and test_a42364_chain.py: native compilation/refusal,
shellcheck/sh -n, private child fault injection and Unix FD/persistent SQLite
MODEL_ONLY chain. None may run initdb, Podman or create a real cgroup.
Existing ordinary push CI supplies its own synthetic PG17 business regression
instance; that is not G1 and must never point at a user's database.

Run repository Ruff and git diff --check. After commit, exact overlay tests
require a clean worktree and canonical Git blobs. Windows CRLF/Linux resource/
fcntl/peercred differences mean Linux-only full regression belongs on existing
ordinary CI; no skip/xfail or new/manual high-cost workflow is allowed.

## Administrator Preparation for a FUTURE Authorized Phase

1. Review all three ADRs and unresolved SOURCE gaps in architecture/capability
   matrix. Do not sign an incomplete runtime as safe.
2. Provide actual offline compiler and PG17 digests, OCI/SBOM/source bundle,
   two independent external signature roots, revocation registry and custody review.
3. Implement/review kernel writer broker and default manager capability factory,
   dedicated runtime UID/socket mapping and same-store read-only E provisioner.
4. Verify all binary hashes, dependency closure, source ZIP, root0400 installation,
   root-sealed leases and FD handoff. Stage writer never starts services.
5. Review separate exact-scope G1_L2_EXECUTION permission and L2 plan. No run command
   is supplied as a shortcut around missing source/authorization.

## Stop and Recovery Contract

Stop accepting new consumption first. Only the installed root manager may
terminate its OWN held cgroup using kill/events/procs FD and exact pidfd; parent
exit/process-group emptiness is not a terminated certificate. Guardian must be
ARMED before child release. A cancellation/ACK loss does not refund a token.
C reloads original committed attempts/identities, never recreates or removes a
replacement. If any deletion result is unknown, ask independent E; do not resend.
Volume stays SAFE_DELETE_UNPROVEN without the all-writer broker.
E rechecks B/C receipts and same-store delegation before/during/after two rounds.
Permission/namespace/epoch/recreation/reader failure means INCOMPLETE_QUARANTINED.
Keep .incomplete and first_error; append cleanup_codes. Do not prune, enumerate a
prefix, recursively delete a store or replace failed evidence with an empty list.

## Publication and Rollback

Only existing supervised publication ordering can remove .incomplete after data
and manifest fsync, held-scope cleanup and committed TERMINATED. A JSON response
is not that receipt. New installation defaults are status-only and do not yet
wire that complete lifecycle. Rollback retains all append-only history and closes
the candidate route; it is NOT a migration downgrade, live cleanup or grant reset.
