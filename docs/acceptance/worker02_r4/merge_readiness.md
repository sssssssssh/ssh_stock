# W06 Merge Readiness

**MERGE_RECOMMENDATION: NO**

This is a scoped source repair and review handoff, not release approval. Keep
PR #1 Draft, master and both remote branches intact. Do not deploy.

## Acceptance Checklist

| ID | Evidence / required disposition |
| --- | --- |
| AT01 | Baseline SHAs, PR checkout/tree, four PR runs, push run and master controls in baseline.md / baseline_evidence.json |
| AT02 | Exact native nodes, logs/XML/artifact digests and replay traces in failure_matrix.csv / evidence_index.json |
| AT03 | Clean historical Linux 14 passed; original negative cases and all old manifests/tests/guards/workflows unchanged; unsigned migration BLOCKED |
| AT04 | Receipt false successes reproduced RED in unit and real PG17, strict matching implemented, GREEN/new regression coverage recorded |
| AT05 | Run unchanged PG17 timeout/lock/disconnect/ACK/CAS/terminal modules; report XML literally, not native CI preflight as full pytest |
| AT06 | Three unchanged real queued OFF/ON lifecycles; exact financial hashes and diagnostic phase evidence in JUnit properties |
| AT07 | No installed authority, no replay of unknown COMMIT, new read-only confirmation refuses inconsistent evidence |
| AT08 | Normal branch push only; final four PR Actions plus push CI receipts are posted to PR #1, source HEAD and merge checkout distinguished |
| AT09 | Unfiltered Linux pytest on the final commit; original failing and passing nodes retained; post-commit receipt, never skipped-node green |
| AT10 | RESOURCE_DEFERRED at original 1443097 x 3; no smaller capacity substitute |
| AT11 | FIELD_NOT_RETESTED; no production/onsite authority or access this round |
| AT12 | Existing work branch only, Draft PR, no merge/delete/deploy |

## Post-Commit Receipt

Tests and CI must run against the delivered commit, not a documentation
follow-up SHA. Consequently final SHA/run IDs, full-suite result and raw
evidence digests are published in the immutable closeout comment on
[PR #1](https://github.com/sssssssssh/ssh_stock/pull/1), after this commit is
created and tested. Do not treat this table as a prediction that pending
executions pass. Baseline failures and all new failures remain blocking.

Required receipt fields: LATEST_SHA, BASE_SHA, CHANGED_FILES,
REPRODUCED_FAILURES, FIXED_REGRESSIONS, OPEN_BLOCKERS, CI_RUNS,
FULL_TEST_RESULT, PERFORMANCE_STATUS, FIELD_STATUS, MERGE_RECOMMENDATION.
Raw large logs/XML remain ignored, indexed by name, source identity and
SHA-256; native artifacts are independently recoverable from GitHub APIs.

## Open Blockers / Next Independent Inputs

1. CONTRACT_MIGRATION_BLOCKED: independent reviewer/signature/approval and
   exact final-tree acceptance are absent. No old contract relaxation.
2. Final ordinary CI and Linux full-suite failures must be reported as-is.
   A synthetic merge being conflict-free is not a release gate.
3. RESOURCE_DEFERRED: sufficient isolated resources and a separately reviewed
   full-scale measurement schedule are needed for the unchanged matrix.
4. FIELD_NOT_RETESTED: production read-only review and physical authority
   require separate authorization. No local synthetic evidence proves them.

No automatic next phase is authorized. Review this patch and evidence first.
