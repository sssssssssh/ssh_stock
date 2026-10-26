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
