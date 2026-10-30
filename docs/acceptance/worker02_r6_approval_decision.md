# R6 Independent Contract Decision

**DECISION_REQUIRED / CONTRACT_MIGRATION_BLOCKED / activation_allowed=false.**
This bounded decision page is not a signature, selector, recovery authority,
performance credential or permission to merge. No new contract is activated.

## Exact Review Input

Historical accepted source: `2779a2a7a7120c86f67b4991bce196c652b5ebb0`;
original guard baseline: `f00be6aa149d5fde145ae4137c01368a332b022f`.
R6 input: `fc8f4e4655aa780ae100dbb564164e6d1bf8d9a4`, tree
`68f1c0a3f7fcc35520059bc561fc99377b04ca42`. The existing exact 104-path review
inventory is `docs/acceptance/worker02_r5/source_inventory_PROPOSED.json`,
Git blob `30daf0bdffcbfe5aee3c78bd80d7e01abb3fb370`, Git-byte SHA256
`1bb0f667f32385efc70c91112b1d2cdcbcef2d9c22685a9bf325baac92a9c454`.
It is unsigned, not an allow-list. R6 delta: this file and
`docs/acceptance/worker02_r6_closeout.md`; their final blobs and containing commit/tree must be independently
recomputed from the final PR receipt, never accepted by trusting current HEAD.

## Why Rollback Is Not A Technical Fix

First divergence `c70c8ca7eff810fee4dccda16ab7ca54813a5567` adds seven paths
to the exact old 33-path set. All seven and the four old-authority append-only
diffs were reviewed, including the complete new tests:

| Added path | Classification / necessity |
| --- | --- |
| `backend/app/repositories/job_run.py` | Business + frozen-contract affected: CAS-owned JSONB merge preserves independent telemetry on freeze failure. |
| `backend/app/services/calculation_policy.py` | Business + frozen-contract affected: content identity, immutable old provenance, real drift/malformed identity refusal. |
| `backend/app/services/job_worker.py` | Business + frozen-contract affected: preserve safe policy-change reason and evidence. |
| `docs/acceptance/BIZ_POLICY_01_closeout.md` | Documentation; deleting it cannot restore the old business path set. |
| `docs/acceptance/BIZ_POLICY_01_runbook.md` | Documentation; not a runtime exception. |
| `tests/integration/test_business_policy_worker_pg17.py` | Regression: real Worker, concurrent metadata, old evidence, daily/catchup roots. |
| `tests/unit/test_business_policy_identity.py` | Regression: Git-only vs content/flag drift; malformed source and frozen identities. |

No demonstrated accidental, safely reversible change was found. Reverting
business safety or deleting its regressions merely to satisfy the old path
set is rejected. Four authority changes append descriptions, not strategy
weights, thresholds, S0-S6 definitions or published-result rewrites.

## Decision And Required Independent Actions

The repository owner must appoint a named independent maintainer. That
maintainer reviews every inventory row plus the exact R6 document delta,
recomputes path/blob/commit/tree identities, and either rejects migration or
authorizes a separately reviewed versioned selector implementation. Approval
must bind reviewer/organization, approval_id, UTC review/expiry, exact source
and tree, permitted invocation and verifiable detached signature. All are
currently **NOT PROVIDED**; the agent cannot supply them.

Old tasks/versions must keep their original immutable manifests, identities
and validators. New tasks may use a new version only after independent activation.
A new version may match only the independently signed exact
identity, never a directory glob, branch name, dynamic tree or default
fallback. Original financial/publication/owner/token and tamper negatives
remain unchanged. Required additional negatives: missing/expired/untrusted
signature, altered path/blob/tree/approval, wrong version, default drift and
historical-routing mismatch. Historical positives must remain reproducible.

After independent authorization, implement/review that selector in an
explicitly scoped task; authorization alone does not make existing CI green.
Then run the unchanged native preflights on the approved exact commit.
Inside the independently verified disposable PG17 runner (business dotenv
disabled), the post-approval commands include:

```bash
python -m pytest --cov=backend/app --cov-fail-under=70 --junitxml=.codex_tmp/r6-full.xml
python -m ruff check backend tests migrations scripts
```

Formal capacity still separately requires the original 1,443,097 rows x3,
resources and explicit execution authorization. Rollback revokes only the new
route and uses an independently reviewed immutable source/image; it never
rewrites Git history, terminal/audit/publication records or replays unknown ACK.

**No signer, no activation; no supported runner, no full acceptance.**
