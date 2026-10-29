# W01 Unsigned Contract Migration Proposal

Status: **CONTRACT_MIGRATION_BLOCKED**. This file grants no execution,
deployment, SQL optimization, performance or recovery authority.

## Historical Identity And Real Gap

- Historical valid source: `2779a2a7a7120c86f67b4991bce196c652b5ebb0`.
- Historical guard baseline: `f00be6aa149d5fde145ae4137c01368a332b022f`.
- PR input: `527f07593fc346f0448165e1f64dd6954eb798b4`.
- Master: `75076eac443d935d622bf59e12aad20ce5aba85e`.
- At input, guard expects exactly 33 stage paths; actual changed set is 78,
  with 45 additional paths and none missing. Four authority documents also
  contain later append-only sections. A directory-level exemption is unsafe.
- `source_inventory_PROPOSED.json` in this directory enumerates Git-blob
  hashes, exact changed paths, membership, control scope and reasons. It is
  supplementary review material, never a replacement historical manifest.
- The earlier R2 inventory remains byte-identical and unsigned. All 11
  historical manifests, dispatchers, guards, workflows and old tests stay
  unchanged by R4. No version selector is installed or activated.

The original clean Linux checkout passed 14 checks (11 source-guard and
negative tests plus the three native failing nodes). In the clean PR input
checkout, those three nodes fail at `a42366_source_guard.py:78`,
`A4235_FROZEN_FILE_CHANGED`. The A4-2 contract-only entry is replayed
separately; no experiment or formal capacity measurement is authorized.

## Independently Required Approval

| Field | Value |
| --- | --- |
| reviewer / independent organization | NOT PROVIDED |
| reviewed_at (UTC) | NOT PROVIDED |
| approval_id | NOT PROVIDED |
| exact approved final commit and tree | TO BE VERIFIED INDEPENDENTLY |
| detached signature / verification identity | NOT PROVIDED |
| activation_allowed | false |
| dispatcher_implemented | false |
| production recovery authority installed | false |

The reviewer must check the final immutable Git tree, source deltas, legacy
negative tests, financial parity, allowed invocation and expiry separately.
Documentation inventory is not a cryptographic signature. A later approval
must not modify or retroactively resign old manifests.

## Risk And Rollback

The R4 executable change is limited to matching recovery receipts and refusing
active children on duplicate recovery/read-only unknown-ACK reconciliation.
There is no schema, formula, A/B visibility, tombstone, configuration-default,
production SQL optimization or publication transaction change. A stricter
check may return UNCONFIRMED for inconsistent imported evidence; it must not
convert that condition to success or automatically retry an abort.

Keep the PR Draft and do not deploy. If a later authorized deployment needs
rollback, independently stop new claims, establish executor/commit certainty,
and redeploy the previously reviewed exact image. Never rewrite terminal
publication evidence, delete audit records or replay an unknown transaction.
Reverting source requires a new reviewed commit, not rewriting branch history.

## Reproducible Review

Use a disposable clean Linux checkout, not a running production worktree:

```bash
git fetch origin
git rev-parse HEAD origin/master
git merge-base origin/master HEAD
git diff --name-status 527f07593fc346f0448165e1f64dd6954eb798b4 HEAD
git diff f00be6aa149d5fde145ae4137c01368a332b022f HEAD --name-only
git diff 527f07593fc346f0448165e1f64dd6954eb798b4 HEAD -- .github migrations config infra scripts
python -m pytest tests/unit/test_a42366_source_guard.py
```

For every inventory row, recompute SHA-256 over `git show REV:PATH` bytes,
not an autocrlf working-tree file. Verify any new final-tree documentation
from Git directly; review-package files intentionally have no self-hash.
Failure of the old live guard on this branch is retained, not waived.
