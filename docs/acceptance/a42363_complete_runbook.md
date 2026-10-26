# Review-only installation, stop and recovery handoff

This is a review checklist, not permission or a runnable deployment instruction.
Current status ENGINEERING_BLOCKED. Do not run G1, PG17, Podman, DDL003, systemd,
manual workflows or business DB commands from this delivery.

1. Reviewer checks exact source SHA, six-layer fingerprints, unchanged five manifests,
   original grant history, local RED/GREEN evidence and final same-SHA ordinary CI.
2. Protocol owner resolves the exact GUC proposal and the separate infeasible fresh
   initialization/authentication contract. No configuration boolean changes a gate.
3. Runtime owner supplies a pinned image with a complete reviewed bootstrap entrypoint,
   fixed socket mount, data mount, private network/PID/IPC, UID/GID mapping and bounded
   initialization plan. The current candidate entrypoint is not installed or proven.
4. Safety owner resolves volume immutable removal or exclusive-store destruction proof.
   Until then quarantine is mandatory, including on otherwise successful cleanup.
5. Independent administrator reviews dedicated control DB DDL001/002/003 and role
   grants. The business DB is outside scope. New domain writers have separate users;
   receipt_reader uses a fresh connection; no PUBLIC write/function grant or inherited
   writer membership. DDL is not automatically applied and was not physically tested.
6. Administrator provisions root-owned listener/source/binary/credential/namespace/
   store/cgroup FDs, separate7domain UIDs and Worker UID, root manager channel, E
   readonly collector and independent audit store. Install scripts into the isolated
   Python runtime from the exact reviewed source; do not resolve imports from a writable
   checkout. Kernel cgroup and mount delegation must be tested under separate authority.
7. Only after all source/protocol/platform evidence can a distinct G1 pre-review be
   requested. Current answer is **NO**. G2 total8 remains pending; G3 unauthorized.

Stop/recovery sequence: stop admission before new consumption/create/run; preserve
CONSUMED/RUN_ATTEMPTED and original ledger identities; terminate via root manager and
guardian, separately prove scope populated0/reap; publish bounded artifacts before D
TERMINATED; request C stop and reverse reconcile; E independently audits4resources in
two rounds against unchanged B/C receipts. Keep first_error and cleanup_codes separate.
Do not auto-reissue unknown create/start/stop/remove, refund a token or overwrite history.

Source restart behavior: C restores PG_PREPARED original ID/config only. Lost start/stop
ACK stays UNKNOWN. Missing creation identity, replaced objects, foreign socket entries,
volume identity uncertainty and unavailable independent audit require quarantine/manual
review. Never recover by inspecting a similar name or deleting a directory recursively.
When artifact filesystem recovery fails, preserve the original error and marker-restore
cleanup code; no final D receipt is issued. A leftover JSON manifest is not success.

Rollback is a new reviewed exact overlay. No history rewriting, broad cleanup, token
reset, silent old protocol fallback or automatic expensive CI experiment is authorized.
