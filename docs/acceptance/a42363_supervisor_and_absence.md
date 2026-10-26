# Independent absence and supervision

E's independent UID alone is insufficient. DelegatedReadOnlyCollector pins held namespace
and runtime-store FDs plus root-installed visibility metadata; Podman info must identify
the delegated C store and rootless runtime. A different UID's empty default store fails.
Only fixed info/exists reads are available. Unknown code/output/permission is not absence.
E uses its own DomainStore, independently reads C's requested/reconciled receipts, requires
all four resource kinds, performs eight ordered observations (two full rounds), then
commits and independently reads its own audit. All physical delegation remains NOT_RUN.

CgroupScope requires the cgroup-v2 filesystem magic, root ownership and matching held
directory/kill/events/procs FDs. Ordinary L1 files cannot become kernel proof. It uses
pidfd TERM, cgroup.kill, populated=0 and owned-child reap; process-group emptiness alone
is never a termination certificate. InstalledWorkerLauncher requires an administrator
root manager, a distinct worker UID, installed hashed source FDs and a launch barrier
before attaching to a nondelegated cgroup. No request can name another PID or cgroup.

ArtifactPublisher creates .incomplete first and writes evidence then manifest in a
separate bounded child. Exclusive no-follow writes, fsync and a second supervised marker
removal prevent a blocked fsync from hiding incompleteness. Handler execution is also
supervised externally. These helpers signal only their own unreaped direct children,
never a request PID or a reaped/reused group. They do not claim descendant containment.

Unimplemented/unproven runtime binding remains a source/deployment blocker, not an L1
success. Worker JSON, C destroy JSON and B receipt cannot replace independent D/E facts.
The current method gate stops Drun before issuing a lease or starting any actual worker.

D uses RootManagerClient over a held kernel-root Unix peer channel; privileged launch,
credential FD transfer and cgroup operations stay in RootManager. WorkerProgram checks the
method gate before FD/credential/connection access, then sealed v2 lease, installed UID,
actual post-connect session evidence and the unchanged fixed16-query worker. Independent
target-session observation remains unapproved; the source does not invent that proof.

FDDeadlineGuardian is a separate process holding the exact kill FD. Its hard wall is
authorization1s plus SQL2s; handler blocking/death cannot suppress it. Proven termination
cancels and reaps it under a2s bound. Arming failure triggers exact-scope cleanup; unknown
termination quarantines the manager, never caches a success. Private ordinary-file L1
tests exercise firing/cancellation and never label those files as kernel cgroups.

E verifies the held namespace against the current kernel namespace and raw graphRoot
device/inode against its held store FD. Its command adapter permits only info/exists reads.
This is source validation; independent multi-UID filesystem delegation is NOT_PROVEN.
