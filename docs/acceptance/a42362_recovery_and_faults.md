# A42362 Recovery and Fault Boundaries

## Per-Resource State

NONE -> RESERVED -> CREATE_ATTEMPTED -> OBSERVED_CREATED -> REMOVE_ATTEMPTED -> OBSERVED_ABSENT.
UNKNOWN can only enter remove/isolated reconciliation, never create again.
Unique transition constraints mean repeated removal needs an exact new review of UNKNOWN
states; the current same-event uniqueness may require manual quarantine, not an unsafe retry.
No successful cleanup can erase the original error.

Each creation stage has an offline crash/ACK-loss model test. Reservations are committed
and independently read before driver mutation. Lost commit/ACK never causes consumption or
create retry/refund. Recovery scans only exact token/payload/binding rows; no name enumeration.
A missing ledger means MANUAL_QUARANTINE_NO_LEDGER, NOT proof that nothing exists.

Container identity requires exact name/labels/image/isolation/mount/resource settings.
Volume/secret ownership is checked before deletion; missing raw identity remains quarantine.
Actual namespace/creation-time proof and partial secret-ID recovery are not fully implemented.
Socket removal uses a held parent FD, no-follow leaf/marker, UID/GID/device/inode and exact
directory entries. Unknown files are not deleted. Atime advancement is not treated as tamper.

The C driver currently stops before real secret/container creation because the Owner method
is blocked. Its non-socket absence method explicitly requires independent E; there is no
complete physical destroy path. The pure compensation algorithm is NOT equivalent to that path.

## Failure Responsibility

| Failure | Code / state | Responsibility / minimum evidence |
|---|---|---|
| Consumption commit/ACK unknown | COMMIT_UNKNOWN_NO_RETRY | B operator; original token/transaction/reader facts, no refund |
| Create ACK lost | CREATE_ACK_UNKNOWN, quarantine | C + B; four resource entries, actual expected IDs/labels |
| Ledger absent/identity drift | MANUAL_QUARANTINE / OWNERSHIP_UNKNOWN | independent administrator, no automatic delete |
| Cleanup budget exceeded | CLEANUP_TIMEOUT_QUARANTINE | C; original error and last committed removal prefix |
| E unavailable/permission/race | ABSENCE_UNKNOWN | E; no absent certificate |
| Child group remains | TERMINATION_NOT_PROVEN | D; group/start/PID facts and root-manager scope review |
| fsync/IPC helper blocks | OUTER_IO_DEADLINE + cleanup_codes | D; stable .incomplete, no complete manifest |
| OOM/power loss/daemon loss | INCOMPLETE_QUARANTINED | independently recover B ledger; unknown is not absent |

Only controlled local processes/Unix fixtures are exercised in L1. No real OOM, Podman
restart, namespace migration, power loss or live storage crash is represented as tested.
The old ControlService now requests token-bound reconcile on create ACK loss and keeps
first_error sticky. Since the actual C/E/D composition is missing, W07 is still PARTIAL.
