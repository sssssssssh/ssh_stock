# A42363 implementation and evidence handoff

Baseline5acc2e71c43cc77172e9caca103cc843c04d704d. Initial RED local commit900bc64,
10 failed,0 passed,exit1. First implementation contracts+process run:94 passed,12.78s.
After identity-preserving recovery was added, targeted contract run:94 passed,0.47s.
Final counts and exact-SHA ordinary CI must be read from actual subsequent commands;
these two runs have different case sets and must not be added together.

W00 freezes exact paths and four immutable older manifests. W01/W02 preserve old
signature/one-shot rules and add role-separated receipts plus reviewed SQL003.
W03 implements raw Owner collection and explicit session-method ADR. W04/W05 implement
four command templates, C composition, exact identity-preserving recovery and receipt
recovery. W06 adds delegated readonly E and its independent store. W07 adds cgroup FD,
installed worker and out-of-process artifact primitives. W08 adds strict v2 UID/RPC
composition and manager-FD validation. W09/W10 add six-source review and controlled
cross-process receipt transport. W11–W13 require final regression, scope audit and CI.

Source status remains PARTIAL_SOURCE_BLOCKED until end-to-end readiness is independently
shown. In particular: resource adapters may conservatively quarantine runtime volumes
without immutable removal IDs; real delegated store identity and approved target-session
evidence cannot be inferred from unit passes. WorkerProgram and RootManager now implement
the FD lease/launch/session gate, separate worker UID and out-of-process hard deadline;
administrator-installed bootstrap/capability wiring remains NOT_CONFIGURED.
These are not to be hidden behind the GUC decision or called merely missing deployment.
No actual G1 SQL, credential release, PG17/Podman, cgroup/systemd installation, cloud or
business operation has been performed. Old A42361/A42362 source gaps are not automatically
closed by adding similarly named classes. The final review must retain any remaining gaps.

CI identity policy: new final40-character HEAD=origin/master, run/attempt/jobs, JUnit
counts/coverage, actual downloaded artifact digests and internal SHA binding will be
reported from existing ordinary push workflows only. Historical40276286848 is not new
evidence. Never fabricate a future Run ID or dispatch G1 to make the handoff look complete.

Rollback requires a separately reviewed exact overlay; no consumed token refund, journal
rewrite, broad resource cleanup or historical protocol re-enable. Pending physical
L2 is NOT_RUN_NOT_AUTHORIZED; approval of option A is a distinct future decision.

## W00–W13 review state

| Work | Source and actual local evidence | Status / limitation |
|---|---|---|
| W00 | exact fifth overlay,10 initial failing inventory cases, historical manifests unchanged | L0 regression required on final clean HEAD |
| W01 | registry/approval import/revoke/receipt, operator-only direct-host negative, inherited Ed25519 | source + L0; real key custody NOT_CONFIGURED |
| W02 | reviewed SQL003, append-only role-derived records, new-connection receipts, unknown ACK quarantine | DB_MODEL_ONLY; actual PG privileges NOT_RUN |
| W03 | raw Owner/8 SQL audit, sealed FD lease/bootstrap, v2 pre/post-connect split, method ADR | METHOD_BLOCKED; not target-session verified |
| W04 | four fixed creation adapters, reservation/attempted-before-create | PARTIAL_SOURCE_BLOCKED: volume immutable removal contract unavailable |
| W05 | original identity retained across UNKNOWN, reverse recovery, no second create/remove after ACK uncertainty | L0 + real file-model L1; volume quarantines |
| W06 | distinct observer UID contract, held namespace/store, raw info/exists, independent journal/two rounds | source + L0/file L1; real delegated multi-UID visibility NOT_PROVEN |
| W07 | private root channel, exact cgroup FDs, pidfd, root launcher, durable run attempt, guardian/artifact deadlines | source + portable L1; kernel/credential deployment NOT_RUN |
| W08 | strict domain composition, manager FDs, peer/method ACL, externally supervised handlers | L0/L1; disabled review template only |
| W09 | concrete C/O/D/E algorithms through actual child processes, private files/Unix FDs, normal +12 fault types | DB_MODEL_ONLY/NONQUALIFYING; no G1 claim |
| W10 | six independently fetched source receipts, original approval/consumption/raw Owner and D/E chain validation | L0/L1 forged/rehashed source rejection |
| W11 | latest targeted149 passed4.33s; prior failure8 retained and fixed by canonical JSON records/framed streams | full final-HEAD regression still required |
| W12 | nine stage documents, exact AT01–AT88 obligations/test nodes, four append-only authorities | source acceptance matrix retains gaps, never88/88 physical PASS |
| W13 | one final push and same-SHA existing ordinary CI/artifact audit | actual identifiers only after push; no rerun/dispatch of expensive experiments |

Later targeted149 cases supersede146/139/108/94 runs; counts describe different suites,
not additive evidence. The8-failure intermediate run remains in local raw JUnit.
No production SQL/model/formula, workflow/dependency, old protocol/manifest or prior
one-time authorization was modified. Performance comparisons and603040-row capacity
are NOT_RUN in this source-only task, not inferred from offline latency.

Remaining decision/action owners:

1. Protocol reviewer: approve or reject the exact same-session option in session_method_ADR.
   No source switch, environment or CI can substitute for that decision.
2. Runtime/safety reviewer: select a provable immutable-volume removal/exclusion mechanism.
   Current name-only Podman interface cannot satisfy this contract; source quarantines
   before rm. This is an engineering/capability gap, not hidden as ordinary deployment.
3. Independent administrator after source review: install pinned bootstrap/capability FDs,
   authenticate the restricted probe role, dedicated control-plane DDL/roles and E's readonly
   multi-UID namespace/store delegation. All installation and physical verification NOT_RUN.
4. User after those gates: separately authorize isolated L2/G1. No token reset, retry for
   PASS, production SQL change or business database operation is included in this delivery.
