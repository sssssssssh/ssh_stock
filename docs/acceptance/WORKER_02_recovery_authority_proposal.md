# Independent recovery authority proposal — NOT_APPROVED / NOT_INSTALLED

This is a review proposal, not a signed approval, deployment or operator command.
The existing Python maintenance primitive is internal. No Web/CLI force, apply or
unlock route is added. The original v1 test authority interface is retained for
compatibility only; LocalTestAuthority is never a production identity provider.

## Required independent parties and facts

Two independent responsible people must approve an exact root UUID, worker
identity, execution-token fingerprint, candidate identity and evidence digest.
The fixed maintenance service needs a separate OS/service identity and narrowly
scoped DB credential, distinct from ordinary Workers and API. Installation,
credential provisioning, independent signer identity and its authenticated
approval/revocation store do not exist in this repository/environment. Until
approved and installed, RECOVERY_AUTHORITY_NOT_INSTALLED / EXECUTION_UNCONFIRMED.

The authority must independently enumerate every Worker host/container, including
legacy unlabelled instances. Capture host boot identity, container ID, image/content
identity, StartedAt/RestartCount/OOMKilled and old PID start identity; freeze claims
by a reviewed maintenance mechanism before collecting evidence. Absence of a process
with a reused PID or a disconnected SSH client is not an exit proof. Inventory
completeness must itself be established; unknown host = DENY.

For DB certainty, independently inventory all writer connections and transactions,
including legacy/unlabelled sessions, prepared transactions and commit receipts.
PID + backend_start + database/instance identity must match actual server facts;
application_name is a diagnostic label. It cannot authenticate an executor or
prove all hosts stopped. A missing current match, idle session, stale heartbeat,
empty pg_prepared_xacts or a current SELECT success alone is not commit certainty.
Network partition, lost COMMIT ACK or publish_started_at = DENY until reconciled.

## Approval protocol proposed for independent review

Approvals bind exact identity, source baseline, immutable proof digest, two signer
identities, approval ID, issue/expiry time (maximum five minutes), nonce and
revocation status. A fixed service must reject legacy approvals without these
fields, verify signatures/role separation against independently installed trust,
re-read revocation immediately before the guarded transaction, and consume the
approval in a separately audited durable authority store. Unknown consume ACK is
not retried as a fresh approval. This control-plane service/store is NOT implemented
or installed by this revision; optional time validation in the internal primitive
cannot replace it. It remains inappropriate to expose that primitive as a service.

The authority must keep claims frozen and all proved executors unable to restart
throughout DB CAS and commit. Process exit followed by automatic container restart
invalidates the proof. No trusted lifetime fence/platform = DENY. A new execution
token, different RUNNING child, active/pending publication, expired/revoked approval
or unknown transaction is refused, preserving original task/candidate/dirty facts.

Only a fresh trusted authority may call the existing normal ABORT/Dirty/CAS primitive.
Preserve the first error and candidate ledger; never delete Raw or rewrite public A.
After unknown recovery COMMIT ACK, use a new read-only transaction to inspect the
original approval audit and terminal facts. A matching recorded result is read back,
not a second write/claim. Different evidence/operator/identity is refused.

Rollback is application-code rollback only: do not erase committed audit, ABORTED
ledger or prior failure. No schema/control-store migration or business action is
authorized by this document. Independent reviewer/signatures/approval ID: absent.
