# A42362 Architecture and Current Boundary

Status: PARTIAL_OFFLINE_TESTED; NOT CODE_READY. No physical G1.

## Actors and Source

A: ApprovalRegistryService imports only external Ed25519-attested canonical admin facts.
No signing/private-key generator exists. Peer ACL is checked before record/key access.
B: original ConsumerService plus resource append/scan use fixed SQL and independent fresh
reader connections. The verified complete grant payload is persisted in the consumption
transaction, so resource image/binding/limits cannot be borrowed from a caller dictionary.
C: Reconciler persists RESERVED and CREATE_ATTEMPTED before any driver mutation; it recovers
destroy-only from committed per-token facts. ExactSocketDirectory holds no-follow FDs.
E: AbsenceAuditor requires a distinct UID, a complete four-resource ledger and two rounds of
raw negative observations. C JSON is not an E fact. Its concrete audit storage wiring is missing.
D: Watchdog no longer returns early for a reaped leader. New outer helper can interrupt a
blocked handler/fsync fixture, but a process group does NOT prove no escaped descendant.

## Intended Sequence, Not an Executed Trace

```text
manager root readonly FDs -> actor-specific InstalledPolicy + installed listener
A external signed import -> immutable registry/approval -> B verify original grant
B lock approval/epoch -> consumption + full payload + audit -> COMMIT -> fresh reader
B per-resource RESERVED -> CREATE_ATTEMPTED -> C fixed mutation -> observed identity
D fixed worker [METHOD BLOCKED BEFORE CREDENTIAL/CONNECTION/PROBE]
failure -> C token-bound reconciliation -> per-resource remove/observe
C destruction record -> E independent raw observations -> own append-only store
independent readback -> non-qualifying review
```

Every service request uses closed Pydantic models. LocalReceiver now supports the seven
predeclared domains, not arbitrary domains, with actual SO_PEERCRED, fixed listener FD,
bounded canonical frames and absolute network deadline. Its handler is not itself a hard
deadline; service_main supplies a per-request fork/wait/kill boundary. Tests do not pretend
that seven objects running under one test UID demonstrate the seven installed actors.

## Not Yet Closed

service_host.service() composes A, B and a fail-closed Owner. C/E/D runtime backends are
explicitly unconfigured; their Python classes are not an installed closed chain.
ControlService sends reconcile after a lost create ACK, but no enabled C receiver/independent
B recovery receipt exists. E has no concrete durable store/namespace delegation composition.
The helper has no root-manager nondelegated cgroup, distinct worker UID or complete installed
worker/FD/artifact protocol. Do NOT relabel these source gaps as merely unrun physical tests.
These dependencies remain stopped after the W03 method decision, rather than activating an
unsafe partial pipeline. Installation review assets intentionally do not start it.
