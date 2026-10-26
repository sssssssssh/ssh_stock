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
without immutable removal IDs; real delegated store identity and complete supervisor/
worker credential-session/bootstrap integration cannot be inferred from unit passes.
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
