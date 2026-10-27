# D2: SAFE_VOLUME_DISPOSAL

NOT_APPROVED. **Approve / Reject / Need changes** unselected.
Current engineering result: ENGINEERING_BLOCKED_BY_RUNTIME_CAPABILITY.
Recommendation: Need changes; global exclusion is not implemented.

## Concrete Alternatives and Version

A: EXCLUSIVE_STORE, podman-5.6.2-name-lookup, one fixture/store plus kernel-enforced
all-writer broker. KernelStoreCapability verifies held graphRoot/runRoot identity,
runtime UID/GID0700, namespace and epoch. ExclusiveStoreManager checks original
creation facts twice and mount count0, persists attempt before exact-name removal.
Operation is ONLY volume rm <exact-fixture-name>; StorageID, --force, --all and
prune cannot substitute. An application flock or census cannot exclude hostile
same-UID writer/API/helper processes or prevent an ABA race.

B: OWNER_DIRECTORY_V4 changes the four-resource/mount/evidence contract and is
explicitly rejected by the v3 candidate router. It requires a new separately
reviewed protocol and implementation; this change does not silently select it.
No resource-count/budget/legacy SQL limits change under A.

## Complete Protocol and Permission Contract

Use CandidateDecision/SignedDecision schema from a42364_protocol_decision.py:
kind SAFE_VOLUME_DISPOSAL, choice EXCLUSIVE_STORE, version
a42364.external-decision.v3, full Scope, proposal/installation/image hashes,
issued/expires(max300s), unique decision_nonce and disposition. Independent OWNER
and SAFETY_PLATFORM Ed25519 signatures cover canonical payload. No signatures or
real digests exist. Source bytes and all interfaces are pinned in the eighth
manifest; StoreIdentity must derive from actual held FDs, never copy a model hash.
Global writer policy is a mandatory installed kernel capability, NOT an approval
boolean. Root owns broker; runtime holds private store; C uses fixed manager
methods; E has separate UID and kernel-read-only visibility. See architecture.

The broker's required API is verify_all_writers(scope, identity) and
exclusive(scope, identity), with surviving scope/epoch binding and audited
recovery. Its implementation, root provisioner and deployment policy are missing.
This is a SOURCE gap, not just an unsigned decision or missing L2 run.

## Failure, Recovery and Rollback

CREATE/START/STOP/REMOVE use unique attempted facts. An ACK loss is quarantined,
not retried after receiver restart. Original identity cannot be replaced by a new
inspection having the same labels. Secret/Container deletion uses original
immutable identity; Volume's API is name-only, hence needs stronger exclusion.
Any unknown writer/mount/permission/replacement or failed ledger read => no rm.
first_error survives; cleanup_codes append separately; no refund/recreate/prune.
Rollback closes new manager routing and preserves legacy SAFE_DELETE_UNPROVEN;
never delete unrelated stores or switch to B implicitly.

HIGH risk until the actual broker, namespace lifetime/restart policy and exclusive
transaction are independently implemented/reviewed. Required L2: cross-process
external CLI/API writers, ABA, running mount, daemon restart, ACK loss, same-name
replacement and independent E two rounds. None was run.

| Independent reviewer | Disposition | kid / external record | Signature / time |
|---|---|---|---|
| Project OWNER | Unselected | NOT_PROVIDED | NOT_SIGNED |
| SAFETY_PLATFORM | Unselected | NOT_PROVIDED | NOT_SIGNED |

Both signatures still do not authorize installation or a real G1/L2 run.
