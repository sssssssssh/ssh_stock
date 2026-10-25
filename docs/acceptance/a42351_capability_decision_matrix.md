# A42351 — feasibility and budget decisions (offline only)

| Area | Modeled | Requires physical evidence | Current availability / protocol decision |
|---|---|---|---|
| Fixture / role | identity and overprivilege negatives | trusted harness, owner, effective role and view visibility | NOT_PROVEN; no privilege escalation |
| Prepared identity | bytes/OID/key/session assertions in old mocks | real driver SQL bytes, parameter OID, driver cache key, same PID/backend_start and pool checkout generation | C0/C1 NOT_PROVEN |
| Prepared counters | custom/generic/from_sql modeled | same-session pg_prepared_statements projections under least role | sixth driver prepare != stable server plan |
| Cached plan | fail-closed NOT_VERIFIED | trustworthy read of actual cached structure without execution/disturbance | CACHED_PLAN_STRUCTURE_NOT_VERIFIED |
| Backend CPU | identity/interval arithmetic only | reciprocal container/PID/backend_start/process start ticks/namespace/clockticks mapping and permission visibility | METRIC_UNAVAILABLE, never zero fill |
| Worker / RSS / GC | frozen scope contracts | whole joined worker CPU, process elapsed, lifetime RSS high-water and natural GC | no GC changes, subtraction or wall-time substitution |
| Long window | offline 250ms geometry | real 2–8 complete ticks, before/during/after lookup, bounded SQL/tick/stop | short lookup BRACKET_UNCOVERED, not performance proof |
| Grant / cleanup | schema rejection only | independent signature, persistent consumption, owned destruction audit | NOT_IMPLEMENTED / NOT_PROVEN |

## Prepared is not cached-plan stability

The psycopg SQL bytes/parameter-OID key and prepare_threshold must be observed on the
same real session and pool generation. Driver execution count, server from_sql,
custom_plans and generic_plans have distinct meanings. Passing a threshold or observing
the sixth prepare does not prove a stable cached plan or sufficient steady-state warmup.
Synthetic constant SQL and C0/C1 lookup are different experimental targets: synthetic
results cannot prove C0/C1 correctness, latency, plan choice or readiness.

Fresh planning output and prepared counters cannot establish cached-plan structure.
No EXPLAIN EXECUTE, forced prepare, planner setting, resetting statistics or hidden SQL
is permitted as a purported zero-disturbance workaround. If no credible method exists,
retain CACHED_PLAN_STRUCTURE_NOT_VERIFIED and stop that claim.

## CPU and long-window evidence

Future backend CPU must be a cumulative **user + system** delta over the same backend
lifecycle, with independently verified bidirectional namespace/PID/start/clockticks
mapping. SQL wall and total process CPU are not replacements. Unknown remains None;
clock or identity ambiguity rejects. Whole-worker thread CPU is only known after join;
its ratio continues to use process elapsed, not a shorter lookup duration. RSS remains
process lifetime high-water, not a per-query allocation delta. Natural GC stays enabled.

Proposed long-window model: ticks exactly 250ms apart, 2–8 total; SQL ≤100ms,
tick ≤25ms, stop/join ≤2000ms. Full completed ticks before, inside and after lookup
are required (a geometry with only two ticks cannot cover all three). Short lookup is
BRACKET_UNCOVERED; no slowing business SQL, padding ticks, adding samples or silent
resampling. Model validation is not observation or authorization.

## Independent protocol decisions still pending

- Effective protocol: total **8** warmups, unchanged.
- A: choose a **fixed 16 or fixed 32**, not both or adaptive escalation; before approval
  specify sufficiency, stopping rules, total cost, session/target identity and source.
  Neither is approved; 16 is a necessary lower bound, not steady-state proof.
- B: cold→prepared research needs a new target, estimand and acceptance contract;
  it cannot reuse steady-state thresholds or serve as a passing calibration.
- C: remain BLOCKED (current default).

G1 is only a proposed synthetic capability probe and is NOT_RUN_NOT_AUTHORIZED.
G2 remains PENDING; G3 remains NOT_AUTHORIZED (128 real points NOT_RUN).
C1 causality/P95, L2/capacity and production remain INSUFFICIENT_EVIDENCE.
No repair candidate is selected. This task ends at code contracts and reviewable design.
