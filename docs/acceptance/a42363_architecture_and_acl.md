# A42363 architecture and ACL

Separate installed hosts: registry / approval (A), consumer (B), pg_owner (O),
controller (C), supervisor (D), absence_auditor (E). No import opens a socket or DB.
ManagerFDs accepts only administrator-installed root/listener FDs. compose requires
the exact capabilities of its own domain; no network/CLI/env activation exists.

| Domain | Methods | Writer principal | Sources |
|---|---|---|---|
| registry | key-status/import/receipt | operator imports only KEY_STATUS | external Ed25519 record |
| approval | approval/import/revoke/receipt | operator imports APPROVAL/REVOCATION | two approvers, current epoch |
| B | consume/receipt/journal/resource-append/resource-scan/committed-receipt | supervisor consumes; C mutates resource ledger | transaction + fresh reader |
| O | create/receipt/run | installed read UIDs, method gate before lease | PG raw row + runtime inspector |
| C | create/destroy/reconcile/receipt | installed read UIDs | exact B ledger + raw identity |
| D | run/terminate/receipt | installed read UIDs | installed launcher + held cgroup FDs |
| E | journal/absent/receipt | installed read UIDs | readonly delegated store + independent journal |

METHODS is checked against the actual LocalService literal matrix. The old v1
deployment retains worker=supervisor UID compatibility. New v2 requires worker UID
different from all seven service UIDs; its root installation is NOT configured here.
Operators cannot read service data merely because import is allowed; readers cannot import.

DomainStore writes a fixed domain function, commits, and reads using a distinct actual
connection object before returning. 003 SQL derives the writer domain from session_user,
rejects cross-domain external imports, installs resource-transition and immutable-history
triggers, pins SECURITY DEFINER ownership/search_path and revokes PUBLIC. It is a review
bundle for an independently provisioned dedicated control plane, NOT a migration or
an assertion that real database privileges have been verified.

L0 DB drivers are DB_MODEL_ONLY. The six-process L1 receipt transport is real Unix
SCM_RIGHTS with immutable controlled records; it does not prove six independent UIDs,
PG durability, cgroup installation or complete real execution. Physical claims stay false.

Request data never provide executable/argv/env/SQL/DSN/path/PID. Scope binds token,
payload, full source/CI binding, fixture, nonce, image, namespace and epoch. Sensitive
credentials are FD-only and cannot be included in artifacts. Missing dependencies fail closed.
