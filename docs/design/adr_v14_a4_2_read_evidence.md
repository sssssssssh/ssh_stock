# ADR: A4-2 Read Evidence and SQL Experiments

Status: experiments in progress; no production candidate selected.
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

## SQL, Window and Resource Decision

Pending complete cursor measurements. No estimate-only winner. Final report must
answer all eight taskbook decision questions and preserve negative experiments.
Until those receipts exist the overall state is A4_2_NO_SAFE_WINNER,
READ_PERFORMANCE_PASS=NOT_CLAIMED; this is not authorization to change production.
