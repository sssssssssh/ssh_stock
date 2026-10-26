# Complete-fix architecture, identities and actual contracts

The product remains 空间; no business API, computation, formula or user flow changes.
The implementation extends existing classes; no second business/runtime framework.

## Identity source

FixtureIdentity derives from the verified, committed Scope plus an installed
Installation. Every use verifies equality to a fresh derivation, including model_copy
mutations. Existing resource names remain compatible, but their meanings are explicit:

| Value | Derivation / independent constraint |
|---|---|
| token/payload/source/nonce/epoch | original immutable Scope and B full consumption |
| namespace/image/controller UID | Scope; original independent deployment verification still required |
| container | a42361- + fixture UUID without hyphens |
| volume / secret | container + -data / -owner-init |
| socket name | fixture UUID without hyphens, under installed /run/space-g1 |
| database | a42361_ + fixture UUID without hyphens |
| restricted role | a42363_probe_ + fixture UUID without hyphens |
| worker UID/shared GID | installed policy, distinct from C; physical mapping unverified |
| container PG UID/GID | 999:999, keep-id mapping requires independent host verification |
| system identifier / backend identity | raw PG only; never derived, filled or echoed from a request |

RawOwnerBackend with the actual OwnerRuntime obtains the dynamic plan BEFORE opening
a database connection. It refuses the9>8 budget. Its separate CREATE DATABASE phase
uses autocommit on postgres, then a distinct fixture connection; a durable attempt
precedes it. No retry/refund on uncertain create or commit. Old injected-row unit
fixtures still exercise their historical8-query model and remain DB_MODEL_ONLY.
They cannot enter the installed host's actual Owner create path.

ResourceDriver, PgFixtureRuntime, OwnerRuntime and WorkerProgram accept the same identity.
Scope mismatch fails before commands/credentials/connection. Probe credential target
has exact host/database/user fields; pre-connect lease has no backend_start. Worker
session checks the dynamic role, PID/start/generation and never trusts another session's
settings. The independent method gate precedes all credential/SQL operations.

## Dependency assembly and lifecycle

```text
external two-approver facts -> A registry/approval -> B consumption/full payload
                                      |             |
                                      v             v
                                  C ledger -> ResourceDriver -> PgFixtureRuntime
                                      |                 |          |
                                      |          prepare/start/readiness
                                      |                            v
                                      |                       Owner raw audit
                                      |                            |
                                      v                            v
                                stop/reconcile       D -> RootManager -> Worker
                                      |                    |           |
                                      v                 Guardian -> scope kill/reap
                           E delegated readonly view        |
                                      |               ArtifactPublisher
                                      v                    |
                                committed E            final D
                                      \                 /
                              six independent sources -> Reviewer (L1 only)
```

ControllerService with a real identity-bound driver requires the fixture dependency;
compose requires its explicit `fixture` capability. It calls prepare/start/readiness
rather than treating CREATED as ready. Creation budget/method preflight still stops
the first side effect. Recovery restores only committed original PG_PREPARED data;
START/STOP_ATTEMPTED with no acknowledgement stays UNKNOWN, not a second start/stop.
An initialization deadline cannot be reset by receiver restart. Stop failure does not
prevent attempts at safe reverse cleanup; the first stop failure remains sticky.

FixedCommandRunner now requires a real CgroupScope for every command, including short
commands formerly using the direct-child helper. The source path blocks a fork on a
gate, attaches it before exec, collects bounded output and requires whole-scope
termination, populated0 and reap before returning. No private file can instantiate a
kernel scope. Unavailable cgroup/UID/delegation is a block, not PGID success. This code
has NOT been exercised with kernel cgroups or Podman in this delivery.

Guardian handshakes ARMED before launch, then operates independently on the exact kill
FD. Python FD requires a raw digest as well as root ownership; worker source already
requires its pinned raw digest. Secrets use FDs, never argv/env. Publisher performs
filesystem work in bounded children. TERMINATION_PROVEN precedes publication; final
TERMINATED only follows acknowledged publication. Unavailable storage or unknown ACK
cannot provide the final D receipt even if marker restoration is itself unproven.

## Actual RPC/schema/ACL table

METHODS stays identical to the existing LocalService dictionary. New request_contract
is shared by DomainClient and ServiceHost. OS peer ACL executes before schema/backend
dispatch. The parameterized test `test_CF_AT09_AT10_every_method_has_peer_and_closed_body_contract`
generates a case for every26method×wrong-peer/invalid-body combination. This is rejection
coverage, not a claim of26positive physical operations. L1 exercises real A/B/C/D/E
receivers; O raw-row model is separate because actual O initialization is budget-blocked.

| Domain | Methods | Schema / allowed peers |
|---|---|---|
| registry | key-status/import/receipt | KeyLookup/ImportRequest/ExternalReceipt; read_uids / operator only import |
| approval | approval/receipt/import/revoke | ApprovalLookup/scope or ExternalReceipt/ImportRequest; revoke operator only |
| B | consume/receipt/journal/resource-append/resource-scan/committed-receipt | closed inherited models; consume D only, append C only, permitted independent readers |
| O | create/receipt/run | scope; control-isolation receipt has closed purpose/hash variant; create C only |
| C | create/destroy/receipt/reconcile | scope only; policy D read peer; no argv/path/DSN |
| E | journal/absent/receipt | scope only; independent configured readers |
| D | run/terminate/receipt | scope only; installed supervisor peer |
| root manager | run/terminate/receipt | exact installed Scope, root kernel peer and private channel |

The O run/session method remains approval-blocked, not a newly working target-session
observation API. Registry/key storage, dedicated domain DB writers, fresh receipt_reader,
append-only DDL003 and fixed search_path remain inherited. DomainStore additionally
calls the real Repository.verify_scope before O/C/D/E writes; legacy in-memory repository
fixtures do not establish persistence or cross-domain authority.

Error codes remain sanitized A42363_* values. Request schema -> RPC_BODY_SCHEMA;
identity -> FIXTURE_IDENTITY; budget -> INIT_BUDGET_INFEASIBLE; command without kernel
scope -> COMMAND_SCOPE_REQUIRED; volume deletion -> SAFE_DELETE_UNPROVEN; uncertain
commands/commit -> ACK_UNKNOWN/COMMIT_UNKNOWN_NO_RETRY; independent missing source ->
INDEPENDENT_SOURCE_UNAVAILABLE. Existing historical source-guard first-error codes remain.
