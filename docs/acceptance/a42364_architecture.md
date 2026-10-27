# A42364 Architecture and Permission Boundaries

Status: PARTIAL_ENGINEERING_BLOCKED. Source/static/offline work only.
Baseline: 60eeb0f123d61c082a6bb9bab53cd0f45b45202f.
No real G1, database, Podman, cgroup, cloud, image build or installation was run.

## Authority Flow

```text
External OWNER + independent SAFETY_PLATFORM
    -> root-pinned installation FD + A registry revocation channel
    -> three versioned decisions (NOT execution authority)
    -> separate G1_L2_EXECUTION one-shot grant
A approval -> B consume/append-only budget -> O Owner -> C resources
    -> root manager -> Guardian ARMED -> D worker
    -> C destroy/reconcile -> E two independent rounds -> Reviewer
```

Root manager UID0 owns trusted code, installation and sealed capabilities.
A registry, approval, B consumer, O pg_owner, C controller, D supervisor, E
absence_auditor, worker and runtime are nine distinct nonroot principals.
C and E must not inherit runtime write credentials. Worker receives only probe
credentials; O's secret is not an RPC/body/argv/environment field.
Scope binds full source/HEAD/run/attempt/nonce/fixture/image/namespace/epoch identity.

## Source Entry Points

- Image: fixed POSIX wrapper -> native bootstrap -> initdb -> Unix-only postgres.
- BootstrapBuilder: deterministic source archive, bounded static image checks and
  checksum plus independently installed signature verification. It never builds.
- InstallationPackage.stage: exact six files under held root parent, O_EXCL,
  no-follow, fsync, .incomplete; no enable/start, UID allocation or recursive cleanup.
- entry.py: validates inherited root FD and source archive before application imports.
- InstalledServiceHost: kernel peer UID before decoding closed RPC; status-only when
  no constructed runtime backend exists. No client-provided PID/argv/class/path.
- CandidateRootManager: separate authority, held kernel cgroup and installed launcher;
  store capability checked before claim/spawn; Guardian armed before child release.
- PersistentBootstrapBudget: B journal named attempts, unique append/fresh read;
  restart does not reset counters or accept a duplicate unknown ACK.
- OperationJournal: original identity/epoch + attempted/done/failure receipts.
- FixedReadOnlyCollector: actual RO-mount flags, namespace and store inode checks,
  pinned collector hash; permission errors remain ABSENCE_UNKNOWN.
- CandidateSessionExecutor: exact 16 slots; same backend identity before/after;
  actual wire parameter OIDs, output OIDs and fixed GUC projection.
- EvidenceGate: six independent reader callbacks, cross-digests and two four-resource
  rounds. Model receipts always nonqualifying, even if self-consistent.

Nine a42363 modules append explicit candidate adapter factories. They do not change
legacy entrypoints, frozen SQL, limits, historical grants or production modules.

## Remaining Source Responsibilities

| Location | Missing capability | Responsible party |
|---|---|---|
| KernelStoreCapability.writer_broker | Kernel-enforced exclusion of ALL CLI/API/helper writers, including hostile runtime UID and restart | Platform/security implement and review policy |
| serve_installed / InstalledServiceHost | Default factory only serves status; full A/B/O/C/D/E capability construction and lifecycle wiring absent | G1 engineering |
| FixtureSocketDirectory / managed_driver | Dedicated runtime UID vs legacy C-owned socket requires a reviewed provisioner/UID-map adapter | G1 engineering + platform |
| ReadOnlyDelegation | Provision independent E UID visibility in the SAME store under RO kernel mounts/idmaps | Platform + G1 engineering |
| PersistentBootstrapBudget / native initdb | Whole-chain command reservation wiring and measured transitive helper census absent | G1 engineering |
| PinnedSessionSource.connections | Separately budgeted Owner audit connection factory, not reusing bootstrap's one-shot fixture-connect slot | G1 engineering |
| Single-use prebuilt | Planner only; provisioning, attestation and one-time physical consumption not implemented | G1 engineering |

These are not all external approval gaps and must not be described as "only deploy
and test". No placeholder writer broker, flock, JSON approval or tests-as-authority
can close them. Systemd units are packaging inputs, not proof of a running service.
