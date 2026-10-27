# D1: BOOTSTRAP_AND_BUDGET

Decision status: NOT_APPROVED. Disposition: **Approve / Reject / Need changes**
(unselected). Both independent signatures and installation remain absent.
Recommendation: Need changes until the cost census and trusted wiring are complete.

## Concrete Alternatives

A: FRESH_DYNAMIC, a42364.bootstrap-candidate.v3, candidate 12 SQL / 32 commands /
30s, replacing ONLY a separately signed bootstrap protocol. Legacy 8/12/2s remains.
B: SINGLE_USE_PREBUILT, same aggregate accounting, no free builder SQL/exec; requires
a separate single-use attestation/consumption implementation that does not yet exist.
No alternative authorizes performance measurements, G2 or G3.

Complete raw SQL, 44-operation ledger, template hashes and model plan hashes:
[a42364_cost_ledger.md](a42364_cost_ledger.md).
Image source: Containerfile, bootstrap.c/.sh, HBA, healthcheck and supply verifier
under infra/g1_pg17_image. Full source hashes are pinned in the eighth manifest.
No real immutable base image/compiler/OCI/SBOM digest is provided or invented.
Administrator must supply actual reviewed digests and offline artifacts.

## Signed Protocol

CandidateDecision/SignedDecision in a42364_protocol_decision.py are the complete
strict schema (extra fields forbidden). Canonical integer-only JSON payload:
version, kind=BOOTSTRAP_AND_BUDGET, choice, disposition, complete Scope,
proposal_sha256, installation_sha256, image_manifest_sha256, issued_at, expires_at
(max TTL300s), decision_nonce. Envelope has exactly two signatures:
OWNER/kid/signature_b64 and SAFETY_PLATFORM/kid/signature_b64.
Both Ed25519 signatures cover the identical canonical payload, using independent
root-installed keys. A fresh peer-pinned registry channel verifies kid/hash,
installation/epoch, revocation and <=1s observation. No test vector, environment
boolean, CLI key, missing registry or expired installation is formal authority.
All exact source-file hashes are in a42364_overlay_manifest.json; the model
hash is not a real approval digest.

## Permissions, Failure and Rollback

Root installs code/keys/FDs; B owns named budget attempts; O alone holds Owner
credentials and autocommit CREATE DATABASE. Worker only receives probe credentials
in a root-sealed short lease. Permission diagram: architecture document.
Attempt commits precede effects. Unknown ACK keeps consumed/quarantined state;
no repeated CREATE, new nonce workaround, token refund or in-place reinstall.
Rollback means close candidate routing and retain legacy DENY, not downgrade or
erase append-only records. No live installation/cleanup is authorized here.

## Risks and Required Acceptance

HIGH: unmeasured initdb descendant/internal SQL census; global budget bridge missing;
real UID/secret/socket mapping and complete installer factory missing; prebuilt
alternative remains a planner. Declared allocation29s is not measured P95.
Before any future L2, prove all named costs, SCRAM/HBA/privileges, host maps, pinned
supply-chain and root Guardian deadline; never enlarge existing limits silently.
Primary references: [PG17 initdb](https://www.postgresql.org/docs/17/app-initdb.html),
[PG17 SCRAM](https://www.postgresql.org/docs/17/auth-password.html).

| Independent reviewer | Disposition | kid / external record | Signature / time |
|---|---|---|---|
| Project OWNER | Unselected | NOT_PROVIDED | NOT_SIGNED |
| SAFETY_PLATFORM | Unselected | NOT_PROVIDED | NOT_SIGNED |

Any unselected/expired/rejected/changed record means DENY. Even both approvals do
not replace the separate G1_L2_EXECUTION grant and installed physical validation.
