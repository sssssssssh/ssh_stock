# A42362 Partial Closeout / Review Handoff

Baseline b32b9271596d92cfbec571fd3170aacbe17370cd, initially clean master and remote equal.
W00 commit freezes the exact48 path plan and three actual RED source regressions.
Status: PARTIAL_OFFLINE_TESTED / METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION. NOT CODE_READY.

## Implemented

- External-signature-only A import/read/revocation source and dedicated-control schema review.
- B immutable complete verified grant payload and per-resource append-only SQL adapter:
  exact ownership, transition constraints, no create replay, fresh committed reader.
- Loss of create ACK now issues a token-bound reconciliation request, never empty=absent.
- Compensation engine and real no-follow socket-directory cleanup, failure/timeout models.
- E rejects same UID, copied C JSON, missing resource set, permission unknown and recreation.
- Watchdog rejects a live visible group after leader exit. Bounded external helper tests
  support hard-stop of controlled blocking child IO and retain sticky first/cleanup errors.
- Probe/legacy create are method-blocked before credentials/connect/resource creation.

## Required Stop / Remaining Source Gaps

1. a42362_pg_owner_service.PgOwnerService owner_backend is still unconfigured: actual PG
   initialization/control-isolation response, leased credentials and raw role/session proof.
   Session GUC requires separate protocol decision; proposal is in method decisions.
2. a42362_service_host.service does not compose C/E/D runtime backends. Reconciler classes,
   E algorithm and Supervisor classes are not a complete deployed service just because named so.
3. a42362_reconcile.PodmanResourceDriver.create stops for secret/container; absent(non-socket)
   rejects. Precise namespace/epoch/secret-ID partial-create recovery still needs implementation.
4. AbsenceAuditor concrete append-only store/destruction lookup/independent namespace delegation
   and the independently readable recovery receipt are not wired.
5. SupervisorService actual fixed worker launcher/cgroup scope/terminate state/externally
   supervised final bundle publisher remain unimplemented; process groups cannot prove escape-free
   termination. Legacy Supervisor/Worker UID coupling must be redesigned, not ignored.
6. The systemd assets are disabled review templates. A trusted FD manager/ready/stop integration
   is not installed or complete. Platforms and all physical L2 tests are NOT_RUN.
7. ControlService reconciliation RPC has no enabled C receiver; failure stays quarantine.
   Full cross-domain raw receipt epoch/identity validation and offline Reviewer extension
   are not completed by this patch. Existing non-qualifying Reviewer behavior is unchanged.

These are source gaps, not only missing real-machine evidence. W00-W12 cannot all be PASS.
The dependency sequence stops at W03; later safety primitives are partial groundwork, not
an authorization to deploy. No budget or historical protocol is changed to manufacture ready.

## Actual Local Verification at Commit Preparation

- baseline portable prepared regression:59 passed,5.23s.
- baseline RED:3 failed,2.91s; same three source regressions after patch:3 passed.
- final portable new fault contracts:46 passed,2.52s; exit0, no skipped cases.
- first committed portable contracts plus exact-overlay tests:54 passed,17.49s.
- corrective inherited-check helper regressions:2 passed,1.70s (targeted selection).
- Linux-only fcntl/resource/SO_PEERCRED/process tests are NOT_RUN locally on Windows.
- Full pytest is delegated to the existing isolated Linux ordinary CI, not the business DB.
- Ruff/diff/current committed manifest checks must be recorded from actual final commands.

## Final SHA / CI Evidence Policy

Initial patch SHA 3b26edbfc6992a12a94b79f85dc3d50b3b8f53a7, ordinary CI run40267482237
attempt1:4311 passed,2 failed,674 warnings; zero skipped. The two inherited source checks
were not delegated by the new overlay: historical patch first-error classification and
the legacy targeted infra tree read. Both checks are restored IN ADDITION to the full
HEAD FD walk. Existing test assertions are unchanged; two new portable regression cases
cover the restored helper. This failed run is retained, not reclassified as PASS.
Final corrected SHA and complete CI result must be read independently below.
Its downloaded safe-CI ZIP matches API digest
21b7784bbd7f0e9618223dedd19283e6a310736ad82fa3aea421af5eb94b38e2;
all embedded JUnit file hashes match failure.json. All4251 baseline case identities
are retained, with62 new cases; all8 new controlled Linux L1 cases passed. This is
offline process/IPC evidence only, not physical PG/Podman/G1 approval or completeness.

This source document cannot contain its own Git SHA. The final delivery must report actual
40-character HEAD, origin/master, run/attempt/jobs and observed conclusions. Final Actions
raw JUnit/error/summary receipts already bind HEAD/run; ZIP API digest/download/content
checks must be reported separately. Do not reuse the taskbook's reported4251 baseline
as the new patch's result. Any old specialized workflow not triggered is NOT_TRIGGERED.
No manual dispatch or G1 physical run is permitted by this task. The final chat report
and same-SHA Actions artifacts supply actual post-push evidence, not a fabricated local JSON.

## Recovery / Next Review

Keep all real entries blocked. Reverting only this guard layer could break historical
pinning; rollback needs a separately reviewed exact overlay and must keep G1 closed.
Never reset consumed grants, erase audit facts, prune resources or kill arbitrary PIDs.
Next action is a protocol/identity/source review of the seven gaps above, not G1 execution.
See architecture, schema/budget, method decisions, capability matrix and AT traceability.
