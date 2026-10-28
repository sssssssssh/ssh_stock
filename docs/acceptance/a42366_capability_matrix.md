# A42366 Capability Matrix

Overall: SOURCE_PARTIAL_ENGINEERING_BLOCKED. Physical: NOT_RUN_NOT_AUTHORIZED.
Unit/fault-model PASS and an actual Unix/SQLite L1 node are separate evidence.
Neither is a kernel, installation, PG17/SCRAM or performance qualification.

| Work | Production entry and actual adapter | Receipt / recovery | Status and remaining boundary |
|---|---|---|---|
| W00 | a42366_baseline.md; a42366_publication tests against baseline methods | seven behavioral RED failures; exact source overlay | IMPLEMENTED; original manifests/tests retained |
| W01 | a42365_supervisor.StagedPublisher.finalize -> a42366_publication.finalize | fresh B/C/originals, ordered 4x2; AUDIT_VERIFIED/PUBLISH_INTENT/PUBLISHED before unlink, FINALIZED after fsync | PARTIAL: safety defects fixed; IndependentReviewSource intentionally refuses, no independent Reviewer service |
| W02 | a42364_manager.serve_installed -> serve_installed_domain -> build_installed_domain -> RuntimeDomainServer | actual strict Unix receiver, peer before decode; durable RPC ATTEMPTED/COMMITTED, no replay | PARTIAL: B claim/budget handler concrete; O/C/D/E installed mutation handlers remain explicit CapabilityBlockedEndpoint |
| W03 | InstalledWriterBroker.verify_all_writers / exclusive / dispatch | old unconditional kernel-capability refusal unchanged | EXTERNAL_BLOCKED plus SOURCE_MISSING kernel provider; all fourteen command routes denied |
| W04 | ConsumerEndpoint.budget -> reserve_request -> BudgetService; RemoteBudget | shared SQLite atomic reserves, old fork/concurrency regressions retained | PARTIAL: native_exec now refuses reservation-only admission; no real native census/FS execution bridge |
| W05 | AuditConnectionFactory.registered_session_source -> PinnedSessionSource -> RegisteredSessionSource | immutable TARGET_SESSION_REGISTERED, original PID/start/generation/role/db/namespace | PARTIAL: real audit adapter helper wired; worker/Owner installation handshake still not assembled |
| W06 | RuntimeCoordinator.reconcile_scope; ControllerEndpoint -> ResourceLifecycle | cleanup only after committed prep; CREATE/START unknown remain quarantined; first error preserved | PARTIAL: production lifecycle fixes concrete, but C live Broker adapter cannot be installed without W03 |
| W07 | AbsenceEndpoint -> independently supplied observer; finalize -> IndependentReviewSource | two fresh B/C rounds, original digests, monotonic timestamps, failure not ABSENT | PARTIAL: same-store RO namespace launcher and independent Reviewer server/custody missing |
| W08 | InstalledSupervisor -> exact CandidateRootManager; v5 FD factory | object-shaped fake launcher denied before journal/effects | PARTIAL: real cgroup/Guardian/worker FD installation factory missing; root v5 entry refuses |
| W09 | exact a42366 source guard, current ordinary CI | ten historical manifests immutable; old injection readers and full-tree FD guard preserved | PARTIAL until exact-SHA CI reviewed; local Windows full collection blocked |
| W10 | a42366_platform_handoff.md | unselected ADRs, unsigned authorizations retained | IMPLEMENTED handoff; approvals and physical validation NOT_RUN |

V5 is a new source/installation contract, not an upgrade of an old signature.
Legacy v3 document validation, principals and old probe bytes are retained.
Companion FD6 is pinned by the v5 document; detached decisions on FD9 bind the
outer installation digest, avoiding a cyclic document/signature hash. Root-only
documents cannot be used as an E domain or as Reviewer credentials.
