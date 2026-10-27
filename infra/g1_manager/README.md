# G1 Trusted FD Package Source

The package has nine distinct nonroot principals: A registry, A approval, B consumer,
O owner, C controller, D supervisor, E auditor, worker and runtime; manager is root0.
An administrator provisions names/UIDs, approved interpreter/dependency closure,
private sockets/namespaces and nondelegated cgroup v2. This task installs nothing.

InstallationPackage.stage accepts only a fixed root-owned parent FD for /opt/space-g1,
and six exact files (three units, source.zip, entry.py, installation.json). O_EXCL,
no-follow, write/fsync and an incomplete marker prevent silent partial overwrites.
No service enable/start, UID creation, recursive rollback, Docker/Podman or SQL is run.
Source archive generation is deterministic and does not fetch dependencies.

FD3: root0400 read-only document for a service, or root-sealed single-worker capsule.
FD5: administrator-supplied Unix listening socket; peer UID precedes dispatch.
Worker independently hashes the root-owned source archive before importing its code;
credentials are root-sealed and bound to worker PID, fixture, epoch and expiry.
Owner RPC accepts only the installed worker UID and exact scope/backend identity.
Kernel cgroup/kill/events/procs capabilities use existing CgroupScope/Guardian/Launcher;
ordinary files/process groups cannot replace them. No argv/env/request PID capability.

The executable entrypoint can serve installation status. Its default factory does not
construct an all-writer kernel broker or fully provisioned C/O/E runtime. Units without
trusted FD handoff exit78, not a fictitious READY. This is a remaining SOURCE/ENGINEERING
gap, not just a request for deployment approval. KernelStoreCapability cannot be created
from a flock or approved=true flag; SAFE_DELETE_UNPROVEN remains. Read-only E mounts must
be both visible to its independent UID and kernel-read-only, not just O_RDONLY directory
descriptors. Wrong store, inaccessible files or Podman permission failure mean UNKNOWN.

Reviewer outcomes are OFFLINE_CROSS_DOMAIN_VERIFIED / qualifies=false only. Stop new
consumption first; independently terminate held scope, reconcile exact original resources
and request E. A lost ACK is never a permission to recreate/delete/prune or refund tokens.
No service installation/run commands are authorized here. See a42364_runbook.md and ADRs.
