# A42362 Installation Review, NOT An Installation Procedure

Status: PARTIAL_OFFLINE_TESTED / METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION.
No service/PG/Podman resource is installed or created by this source change.

| Actor | Illustrative UID | Socket | Database permissions |
|---|---:|---|---|
| A registry | 21001 | registry.sock | signed external registry imports, readonly facts |
| A approval | 21002 | approval.sock | signed external approvals/revocations; no B writes |
| B consumer | 21003 | consumer.sock | one-shot consumption and append-only resource events |
| Owner | 21004 | pg_owner.sock | dedicated synthetic initialization only, never business DB |
| C controller | 21005 | controller.sock | exact rootless resources; no control DB DML |
| E auditor | 21006 | absence_auditor.sock | independent readonly observations, own audit INSERT |
| D supervisor | 21007 | supervisor.sock | owned scope control; no owner credential |
| D worker | UNRESOLVED DISTINCT UID | private inherited FDs only | probe role only |

The old Deployment requires worker_uid==supervisor UID. This is NOT a sufficient
isolation guarantee for a supervisor holding privileged cgroup/credential FDs. Do not
pretend that a new class or different socket fixes this. A new reviewed manager/worker
identity protocol and actual namespace/cgroup checks are still required.

The sample policy is expired, contains no trust key/namespace/epoch and cannot activate
anything. Both units are disabled review templates, not a working bootstrap. The service
CLI exits2; service_main is an internal FD API only. Supplying a file/flag/token cannot
mint the InstalledPolicy seal. Future manager supplies readonly root-owned config FDs
and independently pinned digests; peer UIDs are checked with SO_PEERCRED before dispatch.

Do not install units, create roles, apply 001/002, restart services or run health/PG probes
as part of this task. Future real installation needs separate G1-I approval and G1-E is
another independent authorization. G2 remains total8; G3 remains unauthorized.

Stop design: manager refuses new calls; A appends revocations; consumed/unknown tokens
are never refunded; C reads only per-token committed resource ledger; unknown ownership
is quarantined. E unavailable or unknown absence never becomes cleanup success. No prune,
prefix enumeration/removal, arbitrary PID kill or blanket service restart is permitted.

Supply chain review must pin OS/systemd capability, OpenSSL3 binary+version, PG17 image
digest, rootless Podman binary/userns/secret metadata/cross-UID visibility, psycopg3.3.4,
libpq, private runtime env, worker package and cgroup descriptors. None is inferred from
this template. See method decisions and closeout for the precise remaining source gaps.
