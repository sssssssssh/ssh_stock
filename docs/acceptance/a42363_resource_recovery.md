# Four-resource lifecycle and recovery

Resource names are derived only from fixed Scope fixture/token binding. Each mkdir,
volume, secret or container create needs a fresh B RESERVED then CREATE_ATTEMPTED ack.
OBSERVED_CREATED records the original identity hash. A lost commit/create response never
refunds a grant, reopens creation or scans a prefix. C has a real reconcile receiver.

| Failure point | Required action |
|---|---|
| reservation / attempted ACK unknown | stop; read exact B ledger; never create again |
| OS create succeeds, ID not persistently proven | ownership unknown; quarantine |
| OBSERVED_CREATED ACK lost | fresh ledger retains original identity |
| UNKNOWN / REMOVE_ATTEMPTED suffix | retain earlier OBSERVED_CREATED identity |
| same name/labels but different identity | quarantine, no removal |
| remove ACK lost | independent E negative observation before any completion |
| absent inspect / permission denied | unknown, never infer ABSENT |
| journal commit unknown | stop and independently read; never retry mutation blindly |

RecoveryEngine walks only this token's verified ordered B receipts in reverse four-resource
order. Unlike last-event-only recovery, it preserves the original identity across UNKNOWN.
Missing identity is conservative quarantine. It never enumerates unrelated resources.
Socket removal reuses the held parent FD/inode/marker/owner checks and never recurses.
Non-socket rm uses a proven immutable runtime ID; a volume without a proven removable ID
remains quarantined rather than falling back to a potentially recycled name.

Container templates fix digest, UID, no network, readonly root, dropped caps, no-new-privileges,
1CPU/512MiB/32PIDs, private PID/IPC and one bound volume. Secret creation uses an inherited
FD, never a password in argv/env. Epoch/namespace/owner/scope labels and creation metadata
must match. Runtime incompatibility is a blocked capability, not an automatic weaker mode.

DESTROY_REQUESTED/RECONCILED use independent durable domain receipts. Unknown C ack can
be recovered by a fresh receipt read. A reconciled incomplete token stays quarantined;
ordinary retry never silently creates another run or overwrites its first failure.
