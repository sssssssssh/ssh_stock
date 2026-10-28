# BIZ-POLICY-01 Safe Field Revalidation

This is not an instruction to hot-pull into a running Worker. Do not change
business files under an executing process. The source fix does not authorize
cloud access, production deployment, task cancellation, retries or G1 execution.

## Diagnose before attributing the field failure

The 2025-02-01 through 2025-02-28 report failed during warmup approximately
2024-01-15 through 2024-01-31 after about 80 minutes. Neither screenshots nor
source inspection prove H1 (Git HEAD) or H2 (worktree) was the actual field cause.
H3 (business bytes) and H4 (flags/frozen identity) remain possible.

Only after the operator authorizes their own read-only business connection,
the operator can execute the following. This task does not execute it:

```sql
SELECT id, status, started_at, finished_at, error_message,
       job_metadata #> '{calculation_execution,source}' AS frozen_source,
       job_metadata #> '{calculation_execution,flags}' AS frozen_flags,
       job_metadata #> '{calculation_execution,source_diagnostics}' AS source_diagnostics,
       job_metadata #> '{policy_change}' AS policy_change,
       job_metadata #>> '{publication,state}' AS publication_state
FROM job_run
WHERE job_type = 'recalculate'
ORDER BY started_at DESC LIMIT 5;
```

Do not query credentials or export Raw rows. Missing historical diagnostics
mean UNKNOWN, not proof of Git drift. Failure codes remain
CALCULATION_POLICY_CHANGED with BUSINESS_SOURCE_CHANGED,
OPTIMIZATION_FLAGS_CHANGED, JOB_FROZEN_IDENTITY_MISMATCH or SOURCE_UNAVAILABLE.
The failure evidence contains only valid hashes, optional commit hashes and
CLEAN/DIRTY/UNAVAILABLE labels, never file contents/diffs or connection strings.

## Explicit operator gates

1. Read the old Job and publication ledger; confirm FAILED and ABORTED (or no
   candidate/NO_CHANGES where applicable). Preserve the old Job, candidates and logs.
2. Independently confirm no other RUNNING Writer, remote process or uncertain
   database operation owns the queue. Heartbeat loss is not proof of exit.
3. Safely stop or cooperatively cancel the old Worker and confirm execution exit.
   Do not force status changes, unlock an unknown writer or publish old candidates.
4. Deploy the reviewed exact commit and restart Worker only after that confirmation.
   No DDL, Raw refresh or optimization flag change is required by this fix.
5. Submit the same business date range with a NEW Job ID through the normal queue.
   FAILED jobs are not automatically retried or re-frozen to a new content identity.
6. Confirm the NEW Job SUCCESS and root PUBLISHED plus normal quality/Golden.
   Until then use BUSINESS_POLICY_SOURCE_FIXED_PENDING_REAL_JOB only after source
   and isolated PG17 acceptance, never BUSINESS_POLICY_CONFIRMED.

Rollback means safely stopping the new Worker, reverting application release and
restarting under a coherent source tree; do not downgrade schema, clear data,
rewrite failed evidence or reuse a partial candidate. Old code retains the Git
false-positive risk. This fix provides no permission for G1/L2 experiments.
