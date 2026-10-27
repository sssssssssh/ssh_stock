# G1 PG17 Image Source (Not Built or Deployed)

No actual base/compiler/image digest or signing key is supplied in this repository.
Administrators must provide independently reviewed immutable OCI digests, a PG17 Debian
binary layout (/usr/lib/postgresql/17/bin), runtime999:999 and an offline compiler image.
The image recipe performs no download, package-manager/network operation or automatic
health loop. Native bootstrap explicitly initializes single-use PGDATA, writes SCRAM
HBA atomically, uses a secret pwfile FD, and execs Unix-only postgres. It never runs
the twelve Owner SQL statements or hides them as free initialization.

Static plan: python -m scripts.a42364_bootstrap_builder --plan <builder@digest> <pg17@digest>.
This returns exit2 and a proposed argv; it does NOT build an image or approve execution.
Actual build/create/start/initdb is NOT_AUTHORIZED in this task.

bootstrap.c checks container UID/GID999, no supplementary groups, directory ownership/
modes, single-use PGDATA and a0400 owner secret. It rejects partial initialization rather
than reinitializing. An outer installed Guardian must enforce the signed cold-start
deadline; this program's blocking initdb is not described as independently cancellable.
healthcheck.sh is a single budgeted pg_isready call, never a claim of Owner/SCRAM readiness.
Candidate driver disables automatic OCI health checks and uses the exact secret target
space-g1-owner. The legacy driver is NOT changed or enabled.

Supply-chain review bundle: manifest.json, manifest.sig (two external signature records),
image.oci, sbom.spdx.json and source.tar. The schema pins artifact digests and two base
image digests. verify_bundle checks checksums and installed independent signature roots;
the CLI only uses inherited root document FD3 and registry Unix FD6. It cannot generate
keys/signatures or authorize a live run. OCI/SBOM contents, transitive initdb exec census,
rootless UID maps and actual SCRAM must additionally pass future authorized L2 inspection.
An artifact checksum alone is NOT proof that its image contains the claimed binaries.

Source checks cover no network/privilege/secret-in-env, fixed entrypoint, explicit source,
HBA mutations and mapping/ownership mismatch. Native C syntax, sh syntax and controlled
unprivileged entry refusal are L1 only. Image build/physical assertions remain NOT_RUN.

Official semantics: [PG17 initdb](https://www.postgresql.org/docs/17/app-initdb.html),
[PG17 password authentication](https://www.postgresql.org/docs/17/auth-password.html).
