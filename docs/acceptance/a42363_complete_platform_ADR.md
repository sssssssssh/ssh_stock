# ADR: immutable deletion, independent E and kernel boundaries

## Podman volume

Official [volume rm](https://docs.podman.io/en/latest/markdown/podman-volume-rm.1.html)
documents full/partial names as targets. Official
[volume inspect](https://docs.podman.io/en/latest/markdown/podman-volume-inspect.1.html)
lists StorageID, Mountpoint, LockNumber and creation metadata. An inspect StorageID
does not establish that rm accepts it as an immutable target. This is an inference
from those separate contracts; no supported-version runtime was executed here.

Selected safe behavior: **SAFE_DELETE_UNPROVEN / quarantined**. Even a JSON ID field
cannot authorize volume rm. Name-only fallback, partial matching, force, prune, prefix
scan, rm-all and recursive graphRoot deletion are forbidden. Old no-ID first error
REMOVE_ID_REQUIRED remains compatible; supplied-ID volume gets SAFE_DELETE_UNPROVEN.
Secret/container APIs have ID targets; retained original creation hash and raw ID,
not a same-name replacement, authorize removal. Unknown removal ACK only asks E;
it never repeats a remove while the old result remains unknown.

A possible future alternative is a one-fixture, exclusively owned runtime store with
nondelegated namespace, held store/lock FDs and no other writer across verify+remove.
It needs a reviewed runtime version/API, enforceable exclusion and replacement tests,
plus narrowly bounded destruction authority. A filesystem flock inside C alone does
not exclude Podman/another process and does not prove this mechanism. This alternative
is NOT_IMPLEMENTED/NOT_VERIFIED, not an excuse to send volume rm by name.

## Independent E visibility

E must share visibility of C's actual rootless store while keeping a distinct UID,
read-only delegation and independent journal writer. Collector checks actual UID,
root-owned collector FD/raw bytes, held namespace/store identities, rootless info
graphRoot and inode. No collector FD -> rejection before first info call. OS namespace
delegation/mount restrictions remain physical administrator requirements; source
checks and file models cannot certify them.

Two rounds inspect all4resources8times. Each round and the end re-read B ledger and
independent C destruction receipts. Rebuilt/replaced state, permission denied, non0/1
exit, wrong store or missing observations cannot become ABSENT. A full absence claim
still requires real multi-UID/namespace evidence, **PHYSICAL_VISIBILITY_NOT_VERIFIED**.

## D and command descendants

Root-owned cgroup-v2 FDs, namespace epoch, separate D/Worker UIDs, fixed root-owned Python
raw digest and worker digest, attach-before-exec, pidfd and populated0/reap are mandatory.
FDDeadlineGuardian acknowledges arm before launch. Handler death/EOF/deadline kills
the held scope; no caller PID/PGID is accepted. Every FixedCommandRunner invocation
requires a CgroupScope, including short commands. No configured scope means no spawn.
Kernel behavior, pidfd/cgroup permissions and real rootless subprocess lifetime remain
PLATFORM_NOT_VERIFIED/L2_NOT_RUN. A direct child exiting0 does not prove termination.

The private file FD guardian tests prove only independent process timing and IPC.
Ordinary files cannot pass cgroup fstatfs validation. Linux CI's setsid/pidfd scenario
retains exact owned-child cleanup and never fabricates a kernel certificate. MacOS
portable branches are reported separately, not counted as executed Linux cases.

No claim of a deployable pinned PG image/entrypoint, full OS installer, cross-UID store
delegation or physical resource cleanup is made. These gaps remain engineering/platform
blocks in the closeout. Source, approval, installation and physical proof are distinct.
