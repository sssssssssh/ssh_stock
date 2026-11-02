# R5 Source Contract Review

**CONTRACT_MIGRATION_BLOCKED; activation_allowed=false.** This package is not
approval, production recovery authority, a new selector or a release permit.

## Verified Divergence

The old guard baseline is `f00be6aa149d5fde145ae4137c01368a332b022f`.
`a42366_source_guard.verify()` requires the exact 33-path set and the recorded
Git bytes. The historical valid source is
`2779a2a7a7120c86f67b4991bce196c652b5ebb0`.
The first subsequent divergence is
`c70c8ca7eff810fee4dccda16ab7ca54813a5567`: 40 paths, seven additional paths,
none missing. It changes calculation identity/provenance in job_run,
calculation_policy and job_worker, appends four authorities and adds two
business-policy reports and two tests. These are not merely R4 documents.
Master `75076ea` still has 40 paths; R4 input `2bf219a` has 90.

Clean Linux original guard/negative tests plus the three native failing nodes:
historical **14 passed**; master **10 passed / 4 failed**; R4 input **10 passed /
4 failed**. Three native refusals are `A4235_FROZEN_FILE_CHANGED` at line 78;
the fourth is the old test-path immutability assertion. With the separately
marked PG17 environment, the original A4-2 `--contract-only` succeeds on
historical source and refuses master/input. No workload is measured.

All seven existing historical source-guard unit modules were also run whole
on clean 2779a2a: **73 passed / zero failures / zero skips**. The original
source, complete and review guard negatives remain unchanged; this does not
claim that all historical non-guard/full-suite tests were executed here.

The first replay accidentally used the VM host's old Git without `-C`
support, so requested historical/master checkouts stayed at input. Its logs
are retained as INVALID_HARNESS, not baseline evidence. Corrected runs use
Git 2.47.3 inside the test container and record checkout SHA and clean status.
An initial contract-only call lacked the mandatory physical test marker;
its refusal is likewise not relabelled a source-contract result.

## Exact Review Inventory

`source_inventory_PROPOSED.json` enumerates the complete changed path set
relative to the historical guard baseline, not a directory exemption. Each
row records historical, R4-input and proposed Git blob OIDs and SHA256,
old-stage membership, production-behavior scope, necessity, risk, associated
tests and an empty reviewer decision. Git-object bytes, not Windows CRLF
bytes, are authoritative. Existing R2/R4 proposal packages remain untouched.

The inventory itself cannot contain its own digest. Its row is explicitly
external-pinned: an independent reviewer must recompute it from the final
containing commit/tree and sign that identity. The staged-tree identifier is
only a reproducible review input, never a substitute final approval.
All old guards, dispatchers, workflows, tests and 11 manifests remain byte
identical to R4 input. R5 only adds diagnostics/tests/evidence and appends the
four authorities; no backend, default, Raw/publication SQL or schema changes.

## Proposed Activation Design (Not Implemented)

1. Independent repository maintainers select a new contract version, review
   every exact row against the containing commit and full tree, and supply
   reviewer identity, organization, UTC time, approval_id, expiry, permitted
   invocation and detached signature over that identity plus inventory hash.
2. A separately reviewed selector may route only that exact version and
   immutable approved source/tree to the new verification policy. Missing,
   expired, mismatched, self-issued or unverifiable approval must fail closed.
   No glob, branch-name trust, current-HEAD fallback or auto-regeneration.
3. Historical versions always route to their original manifests/validators
   and exact Git objects. New approval must not rewrite historical bytes or
   retroactively authorize old performance/parent/recovery identities.
4. Before activation, run original positives and all original tamper negatives
   plus missing-signature, altered-path/blob/tree/approval, expired authority,
   wrong version, default drift and historical-routing negatives. All current
   financial, publication, owner/token and unknown-ACK assertions must hold.
5. Rollback revokes the new selector route and uses the previous independently
   reviewed exact source/image, without resetting Git history or rewriting
   terminal/audit/publication records. Executor exit and transaction certainty
   require separate production authority, never an automatic replay.

| Required approval | Actual value |
| --- | --- |
| Independent reviewer / organization | NOT PROVIDED |
| Signed final commit and tree | NOT PROVIDED |
| approval_id / reviewed_at / expiry | NOT PROVIDED |
| Detached signature / trusted verifier | NOT PROVIDED |
| activation_allowed / dispatcher_implemented | false / false |
| Production recovery authority installed | false |

The repository owner must appoint an independent reviewer. The agent cannot
sign for that reviewer. Until the approved implementation and its negatives
are independently accepted, the native red gates remain correct refusals.
