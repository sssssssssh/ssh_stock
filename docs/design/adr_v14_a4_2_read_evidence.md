# ADR: A4-2 Read Evidence and SQL Experiments

Status: A4_2_NO_SAFE_WINNER; no production candidate selected. Scale acceptance OPEN.
Baseline: f8df915. Production changes: NONE. A4-3/B/C: NOT AUTHORIZED.

## Safety Experiments

| Mechanism | Decision | Executable evidence and limitation |
| --- | --- | --- |
| E0 current SHA/whole-B/final SHA | SAFE_EQUIVALENT to existing E0 only | Reuse frozen guards without removal; cannot claim detection of unobserved ABA between checks |
| E1 root fingerprint memo | REJECTED | Real A UPDATE between commits accepted by memo; restore A before final SHA hides the intermediate read |
| E2 caller-generation B certificate | REJECTED | Direct SQL corrupts B without advancing caller generation; memo accepts, original E0 rejects |
| E3 transactional statement event counters | UNPROVEN, not eligible | Normal DML/ABA observed; privileged trigger bypass and rollback generation reuse remain explicit counterexamples |

Sources and real counterexamples: `scripts/ab_read_evidence_v14_a4_2.py` and
`tests/integration/test_ab_read_experiment_v14_a4_2.py`. Nine initial PG17 tests passed.
JUnit `.codex_tmp/a42-evidence-mechanisms.xml` records actual executions, not mocked guards.
The strengthened E2 probe binds root, execution token, lower/upper full natural
keys, version and config hash. These bindings prevent identity/range confusion,
but still do not detect a direct writer that leaves the caller's generation stale.
Even perfect interval partition coverage cannot repair that missing mutation signal.

E3 creates only fixture-local objects in `a42_lab` after verifying physical identity
and the UUID child DB. Statement triggers cover INSERT, UPDATE, DELETE and TRUNCATE,
including ON CONFLICT updates; rollback/savepoint semantics are transactional.
Counters are global and conservative: even out-of-read-set A writes cause abort,
so this is a stricter availability contract, NOT an unnoticed equivalent change.
Production would require trusted trigger ownership, revocation of disable/reset
privileges, defined maintenance/replication paths, hot-counter contention/WAL
measurement and separately approved migration/rollback. None is delivered here.
SAVEPOINT rollback can return a transactional counter to an older value while
the Python certificate survives. A later corrupt write can reuse the saved number
and incorrectly skip validation. The laboratory preserves this executable negative
case rather than claiming that transactional counters alone prove safety.

E3 trials retain the original final full-A verification in addition to event checks.
They cannot win by silently deleting T8. Installing triggers, initial full validation,
all new date fingerprints and full B revalidation after changed events must be reported.
No persistent certificate is shared with a future root or any historical result.

PostgreSQL [lock semantics](https://www.postgresql.org/docs/17/explicit-locking.html)
allow a transaction's own DML despite its SHARE lock, so a same-tx certificate also
needs mutation evidence; locking alone does not make local state immutable.
[Statement triggers](https://www.postgresql.org/docs/17/sql-createtrigger.html)
fire even for zero-row statements, so these counters deliberately accept false
invalidation, never silently treat such events as evidence of unchanged data.

## Decision Questions

1. **Cheaper equivalent evidence?** None proved. E0 preserves the current observed
   read-set contract, including direct A changes present at the next check. It is
   not an all-mutations audit. E1/E2 have executable counterexamples and E3 is
   UNPROVEN. A correct SQL variant retaining E0 does not cure E3 or strengthen E0.
2. **Preferred SQL and measured gain?** No selection before complete-scale results.
   S3/S3_INLINE isolate CTE materialization; S3_KEYS separates narrow masking keys
   from full native decoding; S4 compares typed anti-join; S5 removes only SQL
   ordering, retaining full-frame Python ordering. Q0 raw/service lack protection
   and are not eligible winners. Same-scope p50/p95 and raw plans belong in the
   [results report](../acceptance/v14_a4_2_experiment_results.md), not estimates.
   Current-code 100k S4 p50 is 6.4929/6.2960 seconds for fraction .1/1.0, against
   Q1 6.6329/6.4471: only 2.11%/2.34% faster, not the 30% target. Each includes T8.
3. **Stable at every scale?** Not established. Current-code 10k and 100k each have
   177 completed reads, 59 actual-plan groups and exact golden equality. Some
   alternatives regress at 10k; 100k gains are small. Million is still OPEN.
   Earlier exploratory receipts remain labelled with their different script body.
   All three alternating samples, regressions and failures remain visible.
4. **Schema/index/event costs?** S3-S5 use existing indexes and need no schema change
   in this laboratory. A production rewrite still requires separate approval.
   E3 would add triggers, counter DML, WAL, a hot row and an expanded maintenance
   contract. Installing triggers requires table locks; a transactionally reverted
   generation cannot safely be treated as a globally unique certificate. Legacy
   rows would need initial full validation. A rollback design cannot silently
   disable events while leaving trusted certificates alive. No production DDL,
   migration or cache has been delivered or authorized.
5. **Windows or one bounded SELECT?** Retain current behavior until measured.
   Windowing does not remove global T3/T4/T8 and can multiply DECLARE/FETCH and
   checkpoint cost. None/1/3/5/10/20 must include closed-day stored rows. A future
   view/index/sort audit may be proposed, but neither indexes nor the view are
   changed here; no independent small-window numerical engine is allowed.
   At 100k fraction .1, S3 single-query total median is 6.7518 seconds versus
   9.0441 for one-day windows, 6.9004 for five-day windows. This argues against
   adding finer windows blindly, not for changing production before million/RR2.
6. **Readers/writers/faults?** Existing Worker ownership, cancel, 57014, disconnect
   and unknown-commit slot rules are reused in real regression tests, not replaced.
   RR probes query public tables only. SHARE acquisition/hold and conflicting DML
   probes are recorded separately. Measured read-stage hold is a lower bound:
   actual factor computation/staging can keep the same transaction open longer.
   No claim about production writer latency or cloud lock budgets follows.
7. **No safe winner, next action?** Stop at A4-2. Keep the flag false and report
   READ_PERFORMANCE_PASS=NOT_CLAIMED. Do not relax timeout/identity/quality or hide
   slower trials. Only after review may a separate statistics/index audit or
   evidence/data-model discussion be scoped; there is no automatic A4-3 approval.
8. **Future stage B?** Historical reuse must independently prove Raw revision
   lineage, complete RPS cross-sections and trend checkpoints under the frozen
   version/config/source identity. A process-local SHA or E3 event counter is not
   a reusable historical artifact. No stage B/C implementation is included.

## Acceptance Boundary

Correctness tests proving a counterexample PASS when the unsafe shortcut is
detected. They do not make the shortcut SAFE_EQUIVALENT. In particular T15 is
UNPROVEN for unobserved ABA under the existing E0 contract, and E3 does not close
all bypass/rollback paths. All-I01-I10 production authorization is therefore not
claimed. This remains distinct from measured SQL equality under unchanged E0.

Exact-SHA CI, resource/scale coverage and any deferred matrix cells are reported
explicitly in the results report. A green diagnostic job is not production
performance acceptance. Next phase authorization requested: NO.
